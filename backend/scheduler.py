import asyncio
import logging
import os
from datetime import datetime, time as datetime_time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Date, Time, and_, case, cast, delete, func, or_, select, update

from database import SessionLocal
from max_sender import create_max_bot, send_notification
from ai_queue import enqueue_ai_job
from ai_config import get_ai_config_if_configured
from models import (
    AcademicYear,
    School,
    Class,
    Student,
    SurveyInstance,
    SurveyNotification,
    SurveyInstanceQuestion,
    SurveyResponse,
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
NOTIFICATION_HEARTBEAT_SECONDS = 60
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


def enqueue_daily_ai_jobs(
    session,
    now_utc: datetime,
) -> int:
    """
    Ставит ежедневные AI-задачи для школ, у которых
    наступило 22:00 по локальному времени.

    Одна задача на школу и локальную дату.
    Повторные вызовы защищены dedupe_key.
    """

    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc должен содержать часовой пояс.")

    if get_ai_config_if_configured() is None:
        logger.info(
            "AI-провайдер не настроен. "
            "Постановка ежедневных AI-задач отключена."
        )
        return 0

    schools = session.scalars(
        select(School).order_by(School.id)
    ).all()

    enqueued_count = 0

    for school in schools:
        if not school.timezone:
            logger.error(
                "У школы %s не задан часовой пояс. "
                "AI-анализ пропущен.",
                school.id,
            )
            continue

        try:
            school_timezone = ZoneInfo(school.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            logger.error(
                "Некорректный часовой пояс школы %s: %s. "
                "AI-анализ пропущен.",
                school.id,
                school.timezone,
            )
            continue

        local_now = now_utc.astimezone(school_timezone)

        # Планировщик вызывается каждую минуту.
        # Окно в одну минуту обеспечивает однократную постановку
        # при штатном цикле, а dedupe_key защищает от дублей.
        if local_now.hour != 22 or local_now.minute != 0:
            continue

        analysis_date = local_now.date()

        academic_year = session.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.is_active.is_(True),
            )
        )

        if academic_year is None:
            logger.warning(
                "Для школы %s не найден активный учебный год. "
                "AI-анализ пропущен.",
                school.id,
            )
            continue

        # Пока период ограничен оставшейся частью учебного года.
        # Worker самостоятельно выберет из него будущие даты
        # расписания, на которые есть уроки.
        period_start = analysis_date + timedelta(days=1)
        period_end = min(
            analysis_date + timedelta(days=14),
            academic_year.end_date,
        )

        if period_start > period_end:
            logger.info(
                "Для школы %s нет будущих дат в учебном году.",
                school.id,
            )
            continue

        dedupe_key = (
            f"daily-school-{school.id}-{analysis_date.isoformat()}"
        )

        try:
            enqueue_ai_job(
                session,
                school_id=school.id,
                academic_year_id=academic_year.id,
                class_id=None,
                scope="school",
                analysis_date=analysis_date,
                period_start=period_start,
                period_end=period_end,
                dedupe_key=dedupe_key,
                trigger="daily",
            )

            enqueued_count += 1

        except ValueError:
            # Если такой ключ уже использован с другим payload,
            # это не штатный дубль, а конфликт данных.
            logger.exception(
                "Конфликт постановки AI-задачи для школы %s "
                "за дату %s.",
                school.id,
                analysis_date,
            )

    if enqueued_count:
        session.commit()

        logger.info(
            "В очередь AI поставлено задач: %s.",
            enqueued_count,
        )

    return enqueued_count


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
        enqueue_daily_ai_jobs(
            session=session,
            now_utc=now_utc,
        )
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


def delete_expired_draft_responses(
    session,
    now_utc: datetime,
) -> int:
    """
    Удаляет черновые ответы для опросов, срок которых истёк.

    Связанные варианты ответов удаляются автоматически
    через ON DELETE CASCADE.

    Отправленные ответы не затрагиваются.
    """

    expired_instance_ids = select(SurveyInstance.id).where(
        SurveyInstance.closes_at <= now_utc,
    )

    expired_question_ids = select(
        SurveyInstanceQuestion.id
    ).where(
        SurveyInstanceQuestion.instance_id.in_(
            expired_instance_ids
        )
    )

    draft_response_ids = select(
        SurveyResponse.id
    ).where(
        SurveyResponse.status == "draft",
        SurveyResponse.instance_question_id.in_(
            expired_question_ids
        ),
    )

    result = session.execute(
        delete(SurveyResponse).where(
            SurveyResponse.id.in_(draft_response_ids)
        )
    )

    deleted_count = result.rowcount or 0

    session.commit()

    return deleted_count


def mark_survey_notification_closed(
    notification_id: int,
    now_utc: datetime,
) -> None:
    """Фиксирует закрытие прохождения опроса конкретным учеником."""

    session = SessionLocal()

    try:
        notification = session.get(
            SurveyNotification,
            notification_id,
        )

        if notification is None:
            return

        # Не изменяем успешно завершённые прохождения.
        if notification.progress_status == "completed":
            return

        if notification.progress_status in (
            "not_started",
            "in_progress",
        ):
            notification.progress_status = "closed"
            notification.closed_at = now_utc

            session.commit()

    except Exception:
        session.rollback()
        logger.exception(
            "Не удалось закрыть прохождение уведомления %s",
            notification_id,
        )
        raise

    finally:
        session.close()


async def close_expired_student_surveys(
    bot,
    now_utc: datetime,
) -> int:
    """
    Закрывает просроченные прохождения.

    Сначала закрывает прохождения в БД и удаляет черновики.
    Затем, если MAX Bot доступен, редактирует сообщения.

    Если редактирование не удалось, max_message_id сохраняется,
    чтобы повторить операцию в следующем цикле планировщика.
    """

    session = SessionLocal()

    try:
        deleted_count = delete_expired_draft_responses(
            session,
            now_utc,
        )

        if deleted_count:
            logger.info(
                "Удалено черновых ответов просроченных опросов: %s",
                deleted_count,
            )

        rows = session.execute(
            select(
                SurveyNotification.id,
                SurveyNotification.progress_status,
                SurveyNotification.max_message_id,
            )
            .join(
                SurveyInstance,
                SurveyInstance.id == SurveyNotification.instance_id,
            )
            .where(
                SurveyInstance.closes_at <= now_utc,
                or_(
                    SurveyNotification.progress_status.in_(
                        ["not_started", "in_progress"]
                    ),
                    and_(
                        SurveyNotification.progress_status == "closed",
                        SurveyNotification.max_message_id.is_not(None),
                    ),
                ),
            )
            .order_by(SurveyNotification.id)
        ).all()

        notifications = [
            {
                "id": row.id,
                "progress_status": row.progress_status,
                "max_message_id": row.max_message_id,
            }
            for row in rows
        ]

        # Закрываем все незавершённые прохождения в БД,
        # независимо от доступности MAX API.
        notification_ids = [
            item["id"]
            for item in notifications
            if item["progress_status"] in ("not_started", "in_progress")
        ]

        closed_count = 0

        if notification_ids:
            result = session.execute(
                update(SurveyNotification)
                .where(
                    SurveyNotification.id.in_(notification_ids),
                    SurveyNotification.progress_status.in_(
                        ["not_started", "in_progress"]
                    ),
                )
                .values(
                    progress_status="closed",
                    closed_at=now_utc,
                )
            )

            closed_count = result.rowcount or 0
            session.commit()

    except Exception:
        session.rollback()
        logger.exception(
            "Ошибка закрытия просроченных прохождений"
        )
        raise

    finally:
        session.close()

    if closed_count:
        logger.info(
            "Закрыто просроченных прохождений: %s",
            closed_count,
        )

    # В безопасном режиме на этом заканчиваем.
    # Сообщения MAX останутся в очереди на редактирование.
    if bot is None:
        return closed_count

    edited_count = 0

    for notification in notifications:
        notification_id = notification["id"]
        progress_status = notification["progress_status"]
        message_id = notification["max_message_id"]

        # Редактируем только сообщения незавершённых прохождений.
        # Также повторно обрабатываем ранее закрытые прохождения,
        # у которых ещё сохранился max_message_id.
        if progress_status not in ("in_progress", "closed"):
            continue

        if not message_id:
            continue

        try:
            await bot.edit_message(
                message_id=str(message_id),
                text="Опрос окончен, спасибо за ответы",
                attachments=[],
            )

        except Exception:
            logger.exception(
                "Не удалось закрыть сообщение MAX. "
                "Notification ID: %s, message ID: %s. "
                "Редактирование будет повторено.",
                notification_id,
                message_id,
            )
            continue

        # Удаляем ID только после успешного редактирования.
        # Проверка message_id защищает от очистки нового сообщения,
        # если оно было сохранено параллельно.
        cleanup_session = SessionLocal()

        try:
            cleanup_session.execute(
                update(SurveyNotification)
                .where(
                    SurveyNotification.id == notification_id,
                    SurveyNotification.progress_status == "closed",
                    SurveyNotification.max_message_id == message_id,
                )
                .values(max_message_id=None)
            )

            cleanup_session.commit()
            edited_count += 1

        except Exception:
            cleanup_session.rollback()
            logger.exception(
                "Не удалось очистить ID закрытого сообщения. "
                "Notification ID: %s",
                notification_id,
            )

        finally:
            cleanup_session.close()

    if edited_count:
        logger.info(
            "Успешно отредактировано сообщений MAX: %s",
            edited_count,
        )

    return closed_count


def recover_stale_notifications(session, now_utc: datetime) -> int:
    """
    Возвращает зависшие уведомления со статусом sending в очередь.
    Если попытки закончились, переводит их в failed.
    Закрытые и завершённые опросы не затрагиваются.
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
            SurveyNotification.progress_status.in_(
                ["not_started", "in_progress"]
            ),
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
            SurveyNotification.progress_status.in_(
                ["not_started", "in_progress"]
            ),
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
            SurveyNotification.progress_status.in_(["not_started", "in_progress"]),
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
    instance_id = notification.instance_id
    attempt_number = notification.attempt_count

    session.commit()

    return (
        notification_id,
        max_user_id,
        instance_id,
        attempt_number,
    )


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
            SurveyNotification.progress_status.in_(["not_started", "in_progress"]),
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
    attempt_number: int,
    success: bool,
    error: str | None = None,
) -> bool:
    """Сохраняет результат только актуальной попытки отправки."""

    session = SessionLocal()

    try:
        values = {}

        if success:
            values.update(
                status="sent",
                sent_at=datetime.now(timezone.utc),
                error=None,
            )
        else:
            values.update(
                status=(
                    "failed"
                    if attempt_number >= MAX_NOTIFICATION_ATTEMPTS
                    else "pending"
                ),
                error=(error or "Неизвестная ошибка")[:2000],
            )

        result = session.execute(
            update(SurveyNotification)
            .where(
                SurveyNotification.id == notification_id,
                SurveyNotification.status == "sending",
                SurveyNotification.attempt_count == attempt_number,
            )
            .values(**values)
        )

        updated = result.rowcount == 1
        session.commit()

        if not updated:
            logger.warning(
                "Результат устаревшей попытки отправки проигнорирован: "
                "notification_id=%s, attempt=%s",
                notification_id,
                attempt_number,
            )

        return updated

    except Exception:
        session.rollback()
        logger.exception(
            "Не удалось сохранить результат уведомления %s",
            notification_id,
        )
        raise

    finally:
        session.close()


def refresh_notification_lease(
    notification_id: int,
    attempt_number: int,
) -> bool:
    """
    Продлевает lease только для актуальной попытки отправки.
    """
    session = SessionLocal()

    try:
        result = session.execute(
            update(SurveyNotification)
            .where(
                SurveyNotification.id == notification_id,
                SurveyNotification.status == "sending",
                SurveyNotification.attempt_count == attempt_number,
            )
            .values(
                last_attempt_at=datetime.now(timezone.utc),
            )
        )

        refreshed = result.rowcount == 1
        session.commit()

        return refreshed

    except Exception:
        session.rollback()
        logger.exception(
            "Ошибка обновления lease уведомления %s, попытка %s",
            notification_id,
            attempt_number,
        )
        raise

    finally:
        session.close()


async def maintain_notification_lease(
    notification_id: int,
    attempt_number: int,
) -> None:
    """
    Периодически продлевает lease активной попытки отправки.
    Завершается, если попытка больше не владеет уведомлением.
    """
    while True:
        await asyncio.sleep(NOTIFICATION_HEARTBEAT_SECONDS)

        try:
            refreshed = await asyncio.to_thread(
                refresh_notification_lease,
                notification_id,
                attempt_number,
            )
        except Exception:
            # Временная ошибка БД не должна останавливать heartbeat.
            continue

        if not refreshed:
            logger.warning(
                "Lease уведомления потерян: notification_id=%s, "
                "attempt=%s",
                notification_id,
                attempt_number,
            )
            return


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

        # Удаляем черновики и закрываем прохождения,
        # для которых не требуется обращение к MAX API.
        await close_expired_student_surveys(
            bot=None,
            now_utc=now_utc,
        )

        if not SEND_NOTIFICATIONS:
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
                        "Пропускаем школу с некорректным "
                        "часовым поясом: %s",
                        timezone_name,
                    )

            pending_count = 0

            if valid_timezones:
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
                        local_date
                        == SurveyInstance.survey_date + timedelta(days=1),
                        local_time >= datetime_time(8, 0),
                        local_time < datetime_time(18, 0),
                    ),
                )

                pending_count = session.scalar(
                    select(func.count(SurveyNotification.id))
                    .select_from(SurveyNotification)
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
                        SurveyNotification.status == "pending",
                        SurveyNotification.progress_status.in_(
                            ["not_started", "in_progress"]
                        ),
                        SurveyNotification.attempt_count
                        < MAX_NOTIFICATION_ATTEMPTS,
                        or_(
                            SurveyNotification.last_attempt_at.is_(None),
                            SurveyNotification.last_attempt_at
                            <= now_utc
                            - timedelta(minutes=RETRY_DELAY_MINUTES),
                        ),
                        SurveyInstance.status == "open",
                        SurveyInstance.closes_at > now_utc,
                        School.timezone.in_(valid_timezones),
                        send_window,
                    )
                ) or 0

            logger.debug(
                "Безопасный режим: уведомлений, доступных для попытки "
                "отправки сейчас, — %s. Сообщения в MAX не отправляются.",
                pending_count,
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
        bot = create_max_bot()

        # Закрываем просроченные сообщения MAX
        # и удаляем клавиатуры активных вопросов.
        await close_expired_student_surveys(
            bot=bot,
            now_utc=datetime.now(timezone.utc),
        )

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

            notification_id, max_user_id, instance_id, attempt_number = claimed

            heartbeat_task = asyncio.create_task(
                maintain_notification_lease(
                    notification_id=notification_id,
                    attempt_number=attempt_number,
                )
            )

            try:
                await send_notification(
                    bot=bot,
                    user_id=max_user_id,
                    instance_id=instance_id,
                )

                update_notification_result(
                    notification_id=notification_id,
                    attempt_number=attempt_number,
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
                        attempt_number=attempt_number,
                        success=False,
                        error=str(error),
                    )
                except Exception:
                    logger.exception(
                        "Не удалось обновить статус уведомления %s",
                        notification_id,
                    )

            finally:
                heartbeat_task.cancel()

                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

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
