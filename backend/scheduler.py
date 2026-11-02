import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select, update

from database import SessionLocal
from max_sender import create_max_bot, send_notification
from models import (
    School,
    Student,
    SurveyInstance,
    SurveyNotification,
    User,
)
from survey_instance_service import (
    close_expired_survey_instances,
    create_survey_instances_for_date,
    create_survey_notifications,
)

# Интервал между проверками планировщика.
CHECK_INTERVAL_SECONDS = 60
MAX_NOTIFICATION_ATTEMPTS = 3
SENDING_TIMEOUT_MINUTES = 10
NOTIFICATION_BATCH_SIZE = 20
RETRY_DELAY_MINUTES = 5

# Реальная отправка отключена по умолчанию.
SEND_NOTIFICATIONS = os.getenv("SEND_NOTIFICATIONS", "false").lower() == "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)


def get_school_local_dates(session, now_utc: datetime) -> set:
    """
    Возвращает набор местных дат для всех корректно настроенных школ.

    Для каждой школы дата вычисляется в её собственном часовом поясе.
    """

    timezones = session.scalars(select(School.timezone).distinct()).all()

    local_dates = set()

    for timezone_name in timezones:
        if not timezone_name:
            logger.error(
                "У школы не задан часовой пояс. " "Создание опросов для неё невозможно."
            )
            continue

        try:
            school_timezone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            logger.error(
                "Некорректный часовой пояс школы: %s",
                timezone_name,
            )
            continue

        local_date = now_utc.astimezone(school_timezone).date()
        local_dates.add(local_date)

    return local_dates


def run_scheduler_once() -> None:
    """
    Выполняет один цикл планировщика:
    1. Определяет местные даты школ.
    2. Создаёт экземпляры опросов.
    3. Закрывает просроченные опросы.
    4. Добавляет уведомления в очередь.
    """

    now_utc = datetime.now(timezone.utc)

    session = SessionLocal()

    try:
        # Закрываем просроченные опросы независимо от настроек школ.
        closed_count = close_expired_survey_instances(
            session=session,
            now=now_utc,
        )

        if closed_count:
            logger.info(
                "Закрыто просроченных опросов: %s",
                closed_count,
            )

        local_dates = get_school_local_dates(session, now_utc)

        if not local_dates:
            logger.warning(
                "Не удалось определить местные даты школ. "
                "Создание новых опросов пропущено."
            )
            return

        # Создаём экземпляры опросов для каждой местной даты.
        for survey_date in sorted(local_dates):
            result = create_survey_instances_for_date(
                session=session,
                survey_date=survey_date,
                now=now_utc,
                enforce_time_window=True,
            )

            logger.info(
                "Дата %s: создано опросов — %s, " "пропущено — %s, ошибок — %s",
                survey_date,
                len(result["created"]),
                len(result["skipped"]),
                len(result["errors"]),
            )

            for error in result["errors"]:
                logger.error(
                    "Ошибка создания опроса: %s",
                    error,
                )

        # Повторно проверяем открытые экземпляры.
        # Это позволяет восстановить очередь уведомлений,
        # если предыдущий запуск завершился после создания опроса,
        # но до формирования уведомлений.
        instance_dates = local_dates | {
            survey_date - timedelta(days=1) for survey_date in local_dates
        }

        instances = session.scalars(
            select(SurveyInstance).where(
                SurveyInstance.status == "open",
                SurveyInstance.survey_date.in_(instance_dates),
            )
        ).all()

        for instance in instances:
            try:
                result = create_survey_notifications(
                    session=session,
                    instance=instance,
                )

                session.commit()

                if result["created"]:
                    logger.info(
                        "Опрос %s: добавлено уведомлений — %s",
                        instance.id,
                        result["created"],
                    )

            except Exception:
                session.rollback()

                logger.exception(
                    "Ошибка формирования уведомлений " "для опроса %s",
                    instance.id,
                )

    except Exception:
        session.rollback()
        logger.exception("Ошибка выполнения цикла планировщика")

    finally:
        session.close()


def recover_stale_notifications(session, now_utc: datetime) -> int:
    """
    Возвращает зависшие уведомления со статусом sending в очередь.
    Если попытки закончились, переводит их в failed.
    """

    stale_before = now_utc - timedelta(minutes=SENDING_TIMEOUT_MINUTES)

    stale_condition = or_(
        SurveyNotification.last_attempt_at.is_(None),
        SurveyNotification.last_attempt_at < stale_before,
    )

    # Попытки закончились — окончательно помечаем как failed.
    failed_result = session.execute(
        update(SurveyNotification)
        .where(
            SurveyNotification.status == "sending",
            SurveyNotification.attempt_count >= MAX_NOTIFICATION_ATTEMPTS,
            stale_condition,
        )
        .values(
            status="failed",
            error="Истекло время ожидания отправки.",
        )
    )

    # Попытки ещё остались — возвращаем уведомления в очередь.
    pending_result = session.execute(
        update(SurveyNotification)
        .where(
            SurveyNotification.status == "sending",
            SurveyNotification.attempt_count < MAX_NOTIFICATION_ATTEMPTS,
            stale_condition,
        )
        .values(
            status="pending",
            error="Предыдущая попытка отправки зависла.",
        )
    )

    session.commit()

    recovered = pending_result.rowcount or 0
    failed = failed_result.rowcount or 0

    if recovered or failed:
        logger.warning(
            "Восстановление очереди: возвращено в pending — %s, "
            "переведено в failed — %s",
            recovered,
            failed,
        )

    return recovered + failed


def get_pending_notification(session, now_utc: datetime):
    """
    Атомарно забирает одно уведомление из очереди.

    SKIP LOCKED позволяет нескольким процессам работать
    с очередью без одновременного захвата одной записи.
    """

    result = session.execute(
        select(
            SurveyNotification,
            User.sferum_id,
        )
        .join(
            SurveyInstance,
            SurveyInstance.id == SurveyNotification.instance_id,
        )
        .join(
            Student,
            Student.id == SurveyNotification.student_id,
        )
        .join(
            User,
            User.id == Student.user_id,
        )
        .where(
            SurveyNotification.status == "pending",
            SurveyNotification.attempt_count < MAX_NOTIFICATION_ATTEMPTS,
            or_(
                SurveyNotification.last_attempt_at.is_(None),
                SurveyNotification.last_attempt_at
                <= now_utc - timedelta(minutes=RETRY_DELAY_MINUTES),
            ),
            SurveyInstance.status == "open",
            SurveyInstance.closes_at > now_utc,
        )
        .order_by(
            SurveyNotification.created_at,
            SurveyNotification.id,
        )
        .limit(1)
        .with_for_update(
            skip_locked=True,
            of=SurveyNotification,
        )
    ).first()

    if result is None:
        return None

    notification, sferum_id = result

    try:
        max_user_id = int(sferum_id)
    except (TypeError, ValueError):
        notification.status = "failed"
        notification.error = "Некорректный MAX user_id."
        session.commit()
        return None

    if max_user_id <= 0:
        notification.status = "failed"
        notification.error = "Некорректный MAX user_id."
        session.commit()
        return None

    notification.status = "sending"
    notification.attempt_count += 1
    notification.last_attempt_at = now_utc
    notification.error = None

    notification_id = notification.id

    session.commit()

    return notification_id, max_user_id


def update_notification_result(
    notification_id: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Сохраняет результат попытки отправки."""

    session = SessionLocal()

    try:
        notification = session.get(
            SurveyNotification,
            notification_id,
        )

        if notification is None:
            logger.error(
                "Уведомление %s не найдено после отправки.",
                notification_id,
            )
            return

        if success:
            notification.status = "sent"
            notification.sent_at = datetime.now(timezone.utc)
            notification.error = None
        else:
            if notification.attempt_count >= MAX_NOTIFICATION_ATTEMPTS:
                notification.status = "failed"
            else:
                notification.status = "pending"

            notification.error = (error or "Неизвестная ошибка")[:2000]

        session.commit()

    except Exception:
        session.rollback()
        logger.exception(
            "Не удалось сохранить результат уведомления %s",
            notification_id,
        )
        raise

    finally:
        session.close()


async def process_notification_queue() -> None:
    """
    Обрабатывает пакет уведомлений.

    При SEND_NOTIFICATIONS=false работает в безопасном режиме:
    показывает количество ожидающих уведомлений,
    не отправляя сообщения в MAX.
    """

    now_utc = datetime.now(timezone.utc)
    session = SessionLocal()

    try:
        recover_stale_notifications(session, now_utc)

        if not SEND_NOTIFICATIONS:
            pending_count = session.scalar(
                select(func.count())
                .select_from(SurveyNotification)
                .join(
                    SurveyInstance,
                    SurveyInstance.id == SurveyNotification.instance_id,
                )
                .where(
                    SurveyNotification.status == "pending",
                    SurveyNotification.attempt_count < MAX_NOTIFICATION_ATTEMPTS,
                    SurveyInstance.status == "open",
                    SurveyInstance.closes_at > now_utc,
                )
            )

            logger.info(
                "Безопасный режим: ожидают отправки уведомлений — %s. "
                "Сообщения в MAX не отправляются.",
                pending_count or 0,
            )
            return

    except Exception:
        session.rollback()
        logger.exception("Ошибка подготовки очереди уведомлений")
        return

    finally:
        session.close()

    bot = None
    sent_count = 0
    failed_count = 0

    try:
        for _ in range(NOTIFICATION_BATCH_SIZE):
            session = SessionLocal()

            try:
                claimed = get_pending_notification(
                    session,
                    datetime.now(timezone.utc),
                )
            except Exception:
                session.rollback()
                logger.exception("Ошибка получения уведомления из очереди")
                break
            finally:
                session.close()

            if claimed is None:
                break

            notification_id, max_user_id = claimed

            try:
                if bot is None:
                    bot = create_max_bot()

                await send_notification(
                    bot=bot,
                    user_id=max_user_id,
                    text=(
                        "Опрос для вашего класса уже доступен. "
                        "Откройте бота Blue Sphere и нажмите /start, "
                        "чтобы пройти опрос."
                    ),
                )

                update_notification_result(
                    notification_id=notification_id,
                    success=True,
                )

                sent_count += 1

                logger.info(
                    "Уведомление %s успешно отправлено.",
                    notification_id,
                )

            except Exception as error:
                failed_count += 1

                logger.exception(
                    "Ошибка отправки уведомления %s",
                    notification_id,
                )

                try:
                    update_notification_result(
                        notification_id=notification_id,
                        success=False,
                        error=str(error),
                    )
                except Exception:
                    logger.exception(
                        "Не удалось обновить статус уведомления %s",
                        notification_id,
                    )

    finally:
        if bot is not None:
            try:
                await bot.close_session()
            except Exception:
                logger.exception("Ошибка закрытия сессии MAX Bot")

    if sent_count or failed_count:
        logger.info(
            "Обработка пакета завершена: успешно — %s, ошибок — %s.",
            sent_count,
            failed_count,
        )


async def main() -> None:
    logger.info("Планировщик Blue Sphere запущен.")

    try:
        while True:
            run_scheduler_once()
            await process_notification_queue()
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        logger.info("Планировщик остановлен.")
        raise

    except KeyboardInterrupt:
        logger.info("Планировщик остановлен пользователем.")


if __name__ == "__main__":
    asyncio.run(main())
