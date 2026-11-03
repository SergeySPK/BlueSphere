import asyncio
import logging
import os
from datetime import datetime, time as datetime_time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Date, Time, and_, case, cast, func, or_, select, update

from database import SessionLocal
from max_sender import create_max_bot, send_notification
from models import (
    School,
    Class,
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


def is_notification_time_allowed(
    now_utc: datetime,
    survey_date,
    timezone_name: str,
) -> bool:
    """
    Проверяет, разрешена ли отправка уведомления
    в местном времени школы.

    В день опроса: 18:00–22:00.
    На следующий день: 08:00–18:00.
    После этого отправка прекращается.
    """

    if not timezone_name:
        return False

    try:
        school_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.error(
            "Некорректный часовой пояс школы: %s",
            timezone_name,
        )
        return False

    local_now = now_utc.astimezone(school_timezone)
    local_time = local_now.time().replace(tzinfo=None)

    if local_now.date() == survey_date:
        return (
            datetime_time(18, 0)
            <= local_time
            < datetime_time(22, 0)
        )

    if local_now.date() == survey_date + timedelta(days=1):
        return (
            datetime_time(8, 0)
            <= local_time
            < datetime_time(18, 0)
        )

    return False


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
    1. Закрывает просроченные опросы.
    2. Определяет местные даты школ.
    3. Создаёт экземпляры опросов.
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
    Атомарно забирает одно доступное для отправки уведомление.

    Учитывает:
    - временное окно школы;
    - статус опроса;
    - срок закрытия опроса;
    - задержку между попытками;
    - ограничение числа попыток.

    SKIP LOCKED защищает от одновременного захвата
    одного уведомления несколькими процессами.
    """

    # Получаем только школы с корректными часовыми поясами.
    timezone_names = session.scalars(
        select(School.timezone)
        .where(School.timezone.is_not(None))
        .distinct()
    ).all()

    valid_timezones = []

    for timezone_name in timezone_names:
        try:
            ZoneInfo(timezone_name)
            valid_timezones.append(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            logger.error(
                "Пропускаем школу с некорректным часовым поясом: %s",
                timezone_name,
            )

    if not valid_timezones:
        return None

    local_now = case(
        (
            School.timezone.in_(valid_timezones),
            func.timezone(School.timezone, now_utc),
        ),
        else_=None,
    )

    local_date = cast(local_now, Date)
    local_time = cast(local_now, Time)

    send_window = or_(
        and_(
            local_date == SurveyInstance.survey_date,
            local_time >= datetime_time(18, 0),
            local_time < datetime_time(22, 0),
        ),
        and_(
            local_date == SurveyInstance.survey_date + timedelta(days=1),
            local_time >= datetime_time(8, 0),
            local_time < datetime_time(18, 0),
        ),
    )

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
            Class,
            Class.id == SurveyInstance.class_id,
        )
        .join(
            School,
            School.id == Class.school_id,
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
            School.timezone.in_(valid_timezones),
            send_window,
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


def reset_exhausted_notifications(
    session,
    now_utc: datetime,
) -> int:
    """
    Возвращает в очередь уведомления, исчерпавшие три попытки
    в день проведения опроса.

    Повторная отправка разрешается только на следующий день
    с 08:00 до 18:00 по местному времени школы.
    Закрытые опросы не затрагиваются.
    """

    rows = session.execute(
        select(
            SurveyNotification,
            SurveyInstance.survey_date,
            School.timezone,
        )
        .join(
            SurveyInstance,
            SurveyInstance.id == SurveyNotification.instance_id,
        )
        .join(
            Class,
            Class.id == SurveyInstance.class_id,
        )
        .join(
            School,
            School.id == Class.school_id,
        )
        .where(
            SurveyNotification.status == "failed",
            SurveyNotification.attempt_count >= MAX_NOTIFICATION_ATTEMPTS,
            or_(
                SurveyNotification.error.is_(None),
                SurveyNotification.error != "Некорректный MAX user_id.",
            ),
            SurveyInstance.status == "open",
            SurveyInstance.closes_at > now_utc,
        )
    ).all()

    reset_count = 0

    for notification, survey_date, timezone_name in rows:
        if not timezone_name:
            continue

        try:
            school_timezone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            continue

        local_now = now_utc.astimezone(school_timezone)

        local_time = local_now.time().replace(tzinfo=None)

        # Сбрасываем попытки только на следующий день после опроса.
        if local_now.date() != survey_date + timedelta(days=1):
            continue

        # Разрешённый интервал: с 08:00 до 17:59.
        if not (
            datetime_time(8, 0)
            <= local_time
            < datetime_time(18, 0)
        ):
            continue

        last_attempt_at = notification.last_attempt_at

        if last_attempt_at is not None:
            last_attempt_date = last_attempt_at.astimezone(
                school_timezone
            ).date()

            if local_now.date() <= last_attempt_date:
                continue

        notification.status = "pending"
        notification.attempt_count = 0
        notification.error = None
        reset_count += 1

    if reset_count:
        session.commit()

        logger.info(
            "Возвращено в очередь уведомлений после исчерпания попыток: %s",
            reset_count,
        )

    return reset_count


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
        reset_exhausted_notifications(session, now_utc)

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
