import asyncio
from datetime import datetime, timedelta, timezone, time, date
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

import scheduler
from models import (
    User,
    Teacher,
    Subject,
    TeachingAssignment,
    Schedule,
    SurveyQuestion,
    SurveyQuestionOption,
    SurveyInstance,
    SurveyNotification,
    SurveyResponse,
    SurveyResponseOption,
)

def create_notification(db_session, survey_test_data, **kwargs):
    """Создаёт уведомление для тестового ученика."""

    notification = SurveyNotification(
        instance_id=survey_test_data["instance"].id,
        student_id=survey_test_data["student"].id,
        status=kwargs.get("status", "pending"),
        progress_status=kwargs.get("progress_status", "not_started"),
        attempt_count=kwargs.get("attempt_count", 0),
        last_attempt_at=kwargs.get("last_attempt_at"),
        error=kwargs.get("error"),
    )

    db_session.add(notification)
    db_session.flush()

    return notification


def test_get_pending_notification_claims_notification(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    # 19:00 по времени школы Asia/Yekaterinburg.
    now = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        14, 0,
        tzinfo=timezone.utc,
    )

    notification = create_notification(
        db_session,
        survey_test_data,
    )

    result = scheduler.get_pending_notification(
        db_session,
        now,
    )

    assert result == (
        notification.id,
        survey_test_data["max_user_id"],
        survey_test_data["instance"].id,
        notification.attempt_count,
    )

    db_session.refresh(notification)

    assert notification.status == "sending"
    assert notification.attempt_count == 1
    assert notification.last_attempt_at == now
    assert notification.error is None


def test_get_pending_notification_respects_retry_delay(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    # 19:00 по времени школы Asia/Yekaterinburg.
    now = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        14, 0,
        tzinfo=timezone.utc,
    )

    notification = create_notification(
        db_session,
        survey_test_data,
        attempt_count=1,
        last_attempt_at=now - timedelta(minutes=1),
    )

    result = scheduler.get_pending_notification(
        db_session,
        now,
    )

    assert result is None

    result = scheduler.get_pending_notification(
        db_session,
        now + timedelta(minutes=5),
    )

    assert result == (
        notification.id,
        survey_test_data["max_user_id"],
        survey_test_data["instance"].id,
        notification.attempt_count,
    )

    db_session.refresh(notification)

    assert notification.status == "sending"
    assert notification.attempt_count == 2


def test_get_pending_notification_ignores_closed_survey(
    db_session,
    survey_test_data,
):
    now = datetime.now(timezone.utc)

    survey_test_data["instance"].status = "closed"
    db_session.flush()

    notification = create_notification(
        db_session,
        survey_test_data,
    )

    result = scheduler.get_pending_notification(
        db_session,
        now,
    )

    assert result is None

    db_session.refresh(notification)
    assert notification.status == "pending"


def test_recover_stale_notifications_returns_notification_to_pending(
    db_session,
    survey_test_data,
):
    now = datetime.now(timezone.utc)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        attempt_count=1,
        last_attempt_at=now - timedelta(minutes=15),
    )

    result = scheduler.recover_stale_notifications(
        db_session,
        now,
    )

    assert result == 1

    db_session.refresh(notification)

    assert notification.status == "pending"
    assert notification.error is not None


def test_recover_stale_notifications_marks_exhausted_notification_failed(
    db_session,
    survey_test_data,
):
    now = datetime.now(timezone.utc)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=now - timedelta(minutes=15),
    )

    result = scheduler.recover_stale_notifications(
        db_session,
        now,
    )

    assert result == 1

    db_session.refresh(notification)

    assert notification.status == "failed"
    assert notification.error is not None


def test_update_notification_result_marks_notification_as_sent(
    db_session,
    survey_test_data,
    monkeypatch,
):
    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        attempt_count=1,
    )

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    scheduler.update_notification_result(
        notification_id=notification.id,
        attempt_number=notification.attempt_count,
        success=True,
    )

    db_session.refresh(notification)

    assert notification.status == "sent"
    assert notification.attempt_count == 1
    assert notification.sent_at is not None
    assert notification.error is None


def test_update_notification_result_returns_notification_to_pending(
    db_session,
    survey_test_data,
    monkeypatch,
):
    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        attempt_count=1,
    )

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    scheduler.update_notification_result(
        notification_id=notification.id,
        attempt_number=notification.attempt_count,
        success=False,
        error="Временная ошибка MAX API",
    )

    db_session.refresh(notification)

    assert notification.status == "pending"
    assert notification.attempt_count == 1
    assert notification.error == "Временная ошибка MAX API"


def test_update_notification_result_marks_exhausted_notification_as_failed(
    db_session,
    survey_test_data,
    monkeypatch,
):
    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
    )

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    scheduler.update_notification_result(
        notification_id=notification.id,
        attempt_number=notification.attempt_count,
        success=False,
        error="MAX API недоступен",
    )

    db_session.refresh(notification)

    assert notification.status == "failed"
    assert notification.attempt_count == 3
    assert notification.error == "MAX API недоступен"


def test_process_notification_queue_safe_mode(
    db_session,
    monkeypatch,
):
    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )
    monkeypatch.setattr(scheduler, "SEND_NOTIFICATIONS", False)

    def forbidden_bot_creation():
        raise AssertionError("MAX Bot не должен создаваться.")

    async def forbidden_sending(*args, **kwargs):
        raise AssertionError("Отправка сообщений запрещена.")

    monkeypatch.setattr(
        scheduler,
        "create_max_bot",
        forbidden_bot_creation,
    )
    monkeypatch.setattr(
        scheduler,
        "send_notification",
        forbidden_sending,
    )

    asyncio.run(scheduler.process_notification_queue())


def test_update_notification_result_ignores_stale_attempt(
    db_session,
    survey_test_data,
    monkeypatch,
):
    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        attempt_count=2,
    )

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    result = scheduler.update_notification_result(
        notification_id=notification.id,
        attempt_number=1,
        success=True,
    )

    db_session.refresh(notification)

    assert result is False
    assert notification.status == "sending"
    assert notification.attempt_count == 2
    assert notification.sent_at is None


def test_process_notification_queue_respects_batch_limit(
    db_session,
    monkeypatch,
):
    class FakeBot:
        def __init__(self):
            self.closed = False

        async def close_session(self):
            self.closed = True

    fake_bot = FakeBot()
    sent_notifications = []
    claimed_notifications = []

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    def fake_get_pending_notification(session, now_utc):
        notification_id = len(claimed_notifications) + 1

        if notification_id > scheduler.NOTIFICATION_BATCH_SIZE:
            return None

        claimed_notifications.append(notification_id)

        return notification_id, 999999999, 1, 1

    def fake_create_max_bot():
        return fake_bot

    async def fake_send_notification(bot, user_id, instance_id):
        assert bot is fake_bot
        assert user_id == 999999999
        assert instance_id > 0
        sent_notifications.append(user_id)

    def fake_update_notification_result(
        notification_id,
        attempt_number,
        success,
        error=None,
    ):
        assert attempt_number == 1
        assert success is True
        assert error is None

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )
    monkeypatch.setattr(scheduler, "SEND_NOTIFICATIONS", True)
    monkeypatch.setattr(
        scheduler,
        "get_pending_notification",
        fake_get_pending_notification,
    )
    monkeypatch.setattr(
        scheduler,
        "create_max_bot",
        fake_create_max_bot,
    )
    monkeypatch.setattr(
        scheduler,
        "send_notification",
        fake_send_notification,
    )
    monkeypatch.setattr(
        scheduler,
        "update_notification_result",
        fake_update_notification_result,
    )

    asyncio.run(scheduler.process_notification_queue())

    assert len(claimed_notifications) == scheduler.NOTIFICATION_BATCH_SIZE
    assert len(sent_notifications) == scheduler.NOTIFICATION_BATCH_SIZE
    assert fake_bot.closed is True


def test_notification_time_allowed_at_18_00():
    now = datetime(
        2026, 11, 2, 13, 0,
        tzinfo=timezone.utc,
    )

    assert scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )


def test_notification_time_not_allowed_before_18_00():
    now = datetime(
        2026, 11, 2, 12, 59,
        tzinfo=timezone.utc,
    )

    assert not scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )


def test_notification_time_not_allowed_at_22_00():
    now = datetime(
        2026, 11, 2, 17, 0,
        tzinfo=timezone.utc,
    )

    assert not scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )


def test_notification_time_allowed_next_day_at_08_00():
    now = datetime(
        2026, 11, 3, 3, 0,
        tzinfo=timezone.utc,
    )

    assert scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )


def test_notification_time_not_allowed_next_day_before_08_00():
    now = datetime(
        2026, 11, 2, 22, 59,
        tzinfo=timezone.utc,
    )

    assert not scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )


def test_notification_time_allowed_next_day_at_17_59():
    now = datetime(
        2026, 11, 3, 12, 59,
        tzinfo=timezone.utc,
    )

    assert scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )


def test_notification_time_not_allowed_next_day_at_18_00():
    now = datetime(
        2026, 11, 3, 13, 0,
        tzinfo=timezone.utc,
    )

    assert not scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )


def test_notification_time_uses_school_timezone():
    # 13:00 UTC = 18:00 в Екатеринбурге.
    now = datetime(
        2026, 11, 2, 13, 0,
        tzinfo=timezone.utc,
    )

    assert scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Asia/Yekaterinburg",
    )

    # В Берлине в это время 14:00 — отправка запрещена.
    assert not scheduler.is_notification_time_allowed(
        now,
        date(2026, 11, 2),
        "Europe/Berlin",
    )


def test_reset_exhausted_notifications_after_08_00(
    db_session,
    survey_test_data,
):
    now = datetime(
        2026, 11, 2, 23, 0,
        tzinfo=timezone.utc,
    )

    notification = create_notification(
        db_session,
        survey_test_data,
        status="failed",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=datetime(
            2026, 11, 2, 10, 0,
            tzinfo=timezone.utc,
        ),
    )

    # В тестовой школе Asia/Yekaterinburg это 04:00 3 ноября,
    # поэтому сбрасывать попытки ещё рано.
    result = scheduler.reset_exhausted_notifications(
        db_session,
        now,
    )

    assert result == 0

    db_session.refresh(notification)
    assert notification.status == "failed"


def test_reset_exhausted_notifications_at_08_00(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    now = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        3, 0,
        tzinfo=timezone.utc,
    )

    survey_test_data["instance"].survey_date -= timedelta(days=1)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="failed",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=datetime(
            survey_date.year,
            survey_date.month,
            survey_date.day,
            tzinfo=timezone.utc,
        ) - timedelta(days=1),
    )

    # В тестовой школе это 08:00.
    result = scheduler.reset_exhausted_notifications(
        db_session,
        now,
    )

    assert result == 1

    db_session.refresh(notification)

    assert notification.status == "pending"
    assert notification.attempt_count == 0
    assert notification.error is None


def test_get_pending_notification_allows_old_survey_at_17_59(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    # 17:59 следующего дня по времени Екатеринбурга.
    now = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        12, 59,
        tzinfo=timezone.utc,
    ) + timedelta(days=1)

    notification = create_notification(
        db_session,
        survey_test_data,
    )

    result = scheduler.get_pending_notification(
        db_session,
        now,
    )

    assert result == (
        notification.id,
        survey_test_data["max_user_id"],
        survey_test_data["instance"].id,
        1,
    )


def test_get_pending_notification_rejects_old_survey_at_18_00(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    # 18:00 следующего дня по времени Екатеринбурга.
    now = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        13, 0,
        tzinfo=timezone.utc,
    ) + timedelta(days=1)

    notification = create_notification(
        db_session,
        survey_test_data,
    )

    result = scheduler.get_pending_notification(
        db_session,
        now,
    )

    assert result is None

    db_session.refresh(notification)

    assert notification.status == "pending"
    assert notification.attempt_count == 0


def test_reset_exhausted_notifications_at_17_59(
    db_session,
    survey_test_data,
):
    """В 17:59 следующего дня исчерпанные попытки сбрасываются."""
    survey_date = survey_test_data["instance"].survey_date
    next_survey_date = survey_date + timedelta(days=1)
    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    now = datetime(
        next_survey_date.year,
        next_survey_date.month,
        next_survey_date.day,
        17,
        59,
        tzinfo=school_timezone,
    ).astimezone(timezone.utc)

    last_attempt_at = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        20,
        0,
        tzinfo=school_timezone,
    ).astimezone(timezone.utc)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="failed",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=last_attempt_at,
    )

    result = scheduler.reset_exhausted_notifications(
        db_session,
        now,
    )

    assert result == 1

    db_session.refresh(notification)

    assert notification.status == "pending"
    assert notification.attempt_count == 0
    assert notification.error is None


def test_reset_exhausted_notifications_not_allowed_at_18_00(
    db_session,
    survey_test_data,
):
    """В 18:00 следующего дня попытки уже не сбрасываются."""
    survey_date = survey_test_data["instance"].survey_date
    next_survey_date = survey_date + timedelta(days=1)
    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    now = datetime(
        next_survey_date.year,
        next_survey_date.month,
        next_survey_date.day,
        18,
        0,
        tzinfo=school_timezone,
    ).astimezone(timezone.utc)

    last_attempt_at = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        20,
        0,
        tzinfo=school_timezone,
    ).astimezone(timezone.utc)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="failed",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=last_attempt_at,
    )

    result = scheduler.reset_exhausted_notifications(
        db_session,
        now,
    )

    assert result == 0

    db_session.refresh(notification)

    assert notification.status == "failed"
    assert notification.attempt_count == scheduler.MAX_NOTIFICATION_ATTEMPTS


def test_notification_queue_switches_to_new_survey_at_18_00(
    db_session,
    survey_test_data,
):
    """В 18:00 старый опрос закрывается, очередь выбирает новый."""
    data = survey_test_data
    old_instance = data["instance"]
    survey_date = old_instance.survey_date

    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    new_survey_date = survey_date + timedelta(days=1)
    next_new_survey_date = new_survey_date + timedelta(days=1)

    transition_time = datetime(
        new_survey_date.year,
        new_survey_date.month,
        new_survey_date.day,
        18,
        0,
        tzinfo=school_timezone,
    ).astimezone(timezone.utc)

    # Старый опрос должен закончиться ровно в 18:00.
    old_instance.closes_at = transition_time

    old_notification = create_notification(
        db_session,
        data,
    )

    # Создаём новый опрос для того же класса.
    new_instance = SurveyInstance(
        class_id=data["class"].id,
        survey_date=new_survey_date,
        opens_at=transition_time,
        closes_at=datetime(
            next_new_survey_date.year,
            next_new_survey_date.month,
            next_new_survey_date.day,
            18,
            0,
            tzinfo=school_timezone,
        ).astimezone(timezone.utc),
        status="open",
    )

    db_session.add(new_instance)
    db_session.flush()

    new_notification = SurveyNotification(
        instance_id=new_instance.id,
        student_id=data["student"].id,
        status="pending",
        attempt_count=0,
    )

    db_session.add(new_notification)
    db_session.flush()

    # Сначала закрываем старый опрос.
    closed_count = scheduler.close_expired_survey_instances(
        db_session,
        now=transition_time,
    )

    assert closed_count >= 1

    db_session.refresh(old_instance)
    assert old_instance.status == "closed"

    # Теперь проверяем выбор уведомления из очереди.
    result = scheduler.get_pending_notification(
        db_session,
        transition_time,
    )

    assert result == (
        new_notification.id,
        data["max_user_id"],
        new_instance.id,
        1,
    )

    db_session.refresh(old_notification)
    db_session.refresh(new_notification)

    # Старое уведомление не должно отправляться.
    assert old_notification.status == "pending"

    # Новое уведомление должно быть захвачено очередью.
    assert new_notification.status == "sending"
    assert new_notification.attempt_count == 1


def test_run_scheduler_once_creates_survey_and_notifications(
    db_session,
    survey_test_data,
    monkeypatch,
):
    """
    Проверяет полный цикл планировщика:
    - закрытие предыдущего опроса;
    - создание нового опроса;
    - создание уведомления;
    - отсутствие повторных записей при повторном запуске.
    """

    school = survey_test_data["school"]
    academic_year = survey_test_data["academic_year"]
    class_obj = survey_test_data["class"]
    old_instance = survey_test_data["instance"]
    student = survey_test_data["student"]

    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    # Новый опрос должен открыться завтра ровно в 18:00.
    target_date = old_instance.survey_date + timedelta(days=1)

    local_now = datetime.combine(
        target_date,
        time(18, 0),
        tzinfo=school_timezone,
    )

    now_utc = local_now.astimezone(timezone.utc)

    # Старый опрос должен закрыться в момент запуска планировщика.
    old_instance.closes_at = local_now

    # Для старого опроса уже существует уведомление.
    old_notification = create_notification(
        db_session,
        survey_test_data,
    )

    # Создаём учителя и необходимые для расписания записи.
    teacher_user = User(
        sferum_id="888888888",
        full_name="Тестовый учитель",
        is_demo=False,
    )
    db_session.add(teacher_user)
    db_session.flush()

    teacher = Teacher(
        user_id=teacher_user.id,
        school_id=school.id,
    )
    db_session.add(teacher)

    subject = Subject(
        school_id=school.id,
        name="Тестовый предмет",
    )
    db_session.add(subject)
    db_session.flush()

    assignment = TeachingAssignment(
        school_id=school.id,
        teacher_id=teacher.id,
        class_id=class_obj.id,
        subject_id=subject.id,
        academic_year_id=academic_year.id,
        subgroup=0,
    )
    db_session.add(assignment)
    db_session.flush()

    schedule = Schedule(
        assignment_id=assignment.id,
        date=target_date,
        lesson_number=1,
        room="101",
        lesson_type="Урок",
    )
    db_session.add(schedule)

    # Создаём активный шаблон вопроса и вариант ответа.
    question = SurveyQuestion(
        title="Тестовый вопрос",
        bot_text="Как прошёл учебный день?",
        answer_type="single",
        options_source="static",
        min_answer=1,
        max_answer=1,
        sort_order=0,
        is_active=True,
    )
    db_session.add(question)
    db_session.flush()

    option = SurveyQuestionOption(
        question_id=question.id,
        title="Хорошо",
        sort_order=0,
        is_exclusive=False,
    )
    db_session.add(option)
    db_session.flush()

    # Фиксируем время внутри планировщика.
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now_utc

    monkeypatch.setattr(scheduler, "datetime", FrozenDateTime)

    # Планировщик должен использовать ту же тестовую транзакцию.
    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    # Первый запуск планировщика.
    scheduler.run_scheduler_once()

    db_session.expire_all()

    # Проверяем закрытие старого опроса.
    db_session.refresh(old_instance)

    assert old_instance.status == "closed"

    # Проверяем создание нового опроса.
    new_instance = db_session.scalar(
        select(SurveyInstance).where(
            SurveyInstance.class_id == class_obj.id,
            SurveyInstance.survey_date == target_date,
        )
    )

    assert new_instance is not None
    assert new_instance.status == "open"
    assert new_instance.opens_at == local_now

    expected_closes_at = datetime.combine(
        target_date + timedelta(days=1),
        time(18, 0),
        tzinfo=school_timezone,
    )

    assert new_instance.closes_at == expected_closes_at

    # Проверяем, что уведомление создано для нового опроса.
    new_notifications = db_session.scalars(
        select(SurveyNotification).where(
            SurveyNotification.instance_id == new_instance.id,
            SurveyNotification.student_id == student.id,
        )
    ).all()

    assert len(new_notifications) == 1
    assert new_notifications[0].status == "pending"
    assert new_notifications[0].attempt_count == 0

    # У старого опроса не должно появиться новых уведомлений.
    old_notifications = db_session.scalars(
        select(SurveyNotification).where(
            SurveyNotification.instance_id == old_instance.id,
        )
    ).all()

    assert len(old_notifications) == 1
    assert old_notifications[0].id == old_notification.id
    assert old_notifications[0].status == "pending"

    # Повторный запуск не должен создавать дубликаты.
    scheduler.run_scheduler_once()

    db_session.expire_all()

    all_new_notifications = db_session.scalars(
        select(SurveyNotification).where(
            SurveyNotification.instance_id == new_instance.id,
            SurveyNotification.student_id == student.id,
        )
    ).all()

    assert len(all_new_notifications) == 1

    all_new_instances = db_session.scalars(
        select(SurveyInstance).where(
            SurveyInstance.class_id == class_obj.id,
            SurveyInstance.survey_date == target_date,
        )
    ).all()

    assert len(all_new_instances) == 1


def test_close_expired_student_surveys_deletes_only_drafts(
    db_session,
    survey_test_data,
    monkeypatch,
):
    """Черновики удаляются, отправленные ответы сохраняются."""

    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].closes_at = now - timedelta(seconds=1)

    notification = create_notification(
        db_session,
        data,
    )
    notification.progress_status = "in_progress"
    notification.max_message_id = "test-message-1"
    db_session.flush()

    draft_question = data["questions"][0]
    submitted_question = data["questions"][1]

    draft_response = SurveyResponse(
        instance_question_id=draft_question.id,
        student_id=data["student"].id,
        status="draft",
    )

    submitted_response = SurveyResponse(
        instance_question_id=submitted_question.id,
        student_id=data["student"].id,
        status="submitted",
        submitted_at=now - timedelta(minutes=5),
    )

    db_session.add_all([
        draft_response,
        submitted_response,
    ])
    db_session.flush()

    draft_option = data["options"][0][0]
    submitted_option = data["options"][1][0]

    db_session.add_all([
        SurveyResponseOption(
            response_id=draft_response.id,
            option_id=draft_option.id,
            instance_question_id=draft_question.id,
        ),
        SurveyResponseOption(
            response_id=submitted_response.id,
            option_id=submitted_option.id,
            instance_question_id=submitted_question.id,
        ),
    ])
    db_session.flush()

    draft_response_id = draft_response.id
    submitted_response_id = submitted_response.id
    notification_id = notification.id

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    class FakeBot:
        def __init__(self):
            self.edited_messages = []

        async def edit_message(self, **kwargs):
            self.edited_messages.append(kwargs)

    bot = FakeBot()

    result = asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=bot,
            now_utc=now,
        )
    )

    assert result == 1

    db_session.expire_all()

    assert db_session.get(
        SurveyResponse,
        draft_response_id,
    ) is None

    assert db_session.get(
        SurveyResponse,
        submitted_response_id,
    ) is not None

    draft_option_rows = db_session.scalars(
        select(SurveyResponseOption).where(
            SurveyResponseOption.response_id == draft_response_id,
        )
    ).all()
    assert draft_option_rows == []

    submitted_option_rows = db_session.scalars(
        select(SurveyResponseOption).where(
            SurveyResponseOption.response_id == submitted_response_id,
        )
    ).all()
    assert len(submitted_option_rows) == 1

    refreshed_notification = db_session.get(
        SurveyNotification,
        notification_id,
    )
    assert refreshed_notification.progress_status == "closed"

    assert len(bot.edited_messages) == 1
    assert bot.edited_messages[0]["message_id"] == "test-message-1"
    assert bot.edited_messages[0]["text"] == "Опрос окончен, спасибо за ответы"
    assert bot.edited_messages[0]["attachments"] == []


def test_close_expired_student_surveys_retries_after_max_error(
    db_session,
    survey_test_data,
    monkeypatch,
):
    """При ошибке MAX API опрос закрывается в БД, а редактирование повторяется позже."""

    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].closes_at = now - timedelta(seconds=1)

    notification = create_notification(
        db_session,
        data,
    )
    notification.progress_status = "in_progress"
    notification.max_message_id = "test-message-2"

    db_session.flush()

    notification_id = notification.id

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    class BrokenBot:
        async def edit_message(self, **kwargs):
            raise RuntimeError("MAX API временно недоступен")

    # Первый вызов: MAX API недоступен, но запись в БД закрывается.
    result = asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=BrokenBot(),
            now_utc=now,
        )
    )

    assert result == 1

    db_session.expire_all()

    refreshed_notification = db_session.get(
        SurveyNotification,
        notification_id,
    )

    assert refreshed_notification.progress_status == "closed"
    assert refreshed_notification.closed_at is not None
    assert refreshed_notification.max_message_id == "test-message-2"

    # Второй вызов: MAX API снова доступен, сообщение успешно редактируется.
    class WorkingBot:
        def __init__(self):
            self.edited = False

        async def edit_message(self, **kwargs):
            self.edited = True

            assert kwargs["message_id"] == "test-message-2"
            assert kwargs["text"] == "Опрос окончен, спасибо за ответы"
            assert kwargs["attachments"] == []

    bot = WorkingBot()

    result = asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=bot,
            now_utc=now + timedelta(minutes=1),
        )
    )

    # Запись уже была закрыта при первом вызове.
    assert result == 0
    assert bot.edited is True

    db_session.expire_all()

    refreshed_notification = db_session.get(
        SurveyNotification,
        notification_id,
    )

    assert refreshed_notification.progress_status == "closed"
    assert refreshed_notification.closed_at is not None
    assert refreshed_notification.max_message_id is None


def test_close_expired_student_surveys_safe_mode(
    db_session,
    survey_test_data,
    monkeypatch,
):
    """Без MAX Bot активное сообщение не закрывается преждевременно."""

    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].closes_at = now - timedelta(seconds=1)

    notification = create_notification(
        db_session,
        data,
    )
    notification.progress_status = "in_progress"
    notification.max_message_id = "test-message-3"

    db_session.flush()

    notification_id = notification.id

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    result = asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=None,
            now_utc=now,
        )
    )

    assert result == 1

    db_session.expire_all()

    refreshed_notification = db_session.get(
        SurveyNotification,
        notification_id,
    )

    assert refreshed_notification.progress_status == "closed"
    assert refreshed_notification.closed_at is not None
    assert refreshed_notification.max_message_id == "test-message-3"


def test_close_expired_student_surveys_does_not_close_before_deadline(
    db_session,
    monkeypatch,
    survey_test_data,
):
    data = survey_test_data
    instance = data["instance"]

    notification = SurveyNotification(
        instance_id=instance.id,
        student_id=data["student"].id,
        status="sent",
        progress_status="in_progress",
        max_message_id=12345,
    )
    db_session.add(notification)
    db_session.commit()

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="rollback_only",
        )

    monkeypatch.setattr(scheduler, "SessionLocal", test_session_factory)

    now = instance.closes_at - timedelta(seconds=1)

    asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=None,
            now_utc=now,
        )
    )

    db_session.refresh(notification)

    assert notification.progress_status == "in_progress"


def test_close_expired_student_surveys_closes_at_exact_deadline(
    db_session,
    monkeypatch,
    survey_test_data,
):
    data = survey_test_data
    instance = data["instance"]

    notification = SurveyNotification(
        instance_id=instance.id,
        student_id=data["student"].id,
        status="sent",
        progress_status="not_started",
    )
    db_session.add(notification)
    db_session.commit()

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="rollback_only",
        )

    monkeypatch.setattr(scheduler, "SessionLocal", test_session_factory)

    asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=None,
            now_utc=instance.closes_at,
        )
    )

    db_session.refresh(notification)

    assert notification.progress_status == "closed"


def test_close_expired_student_surveys_preserves_completed_notification(
    db_session,
    monkeypatch,
    survey_test_data,
):
    data = survey_test_data
    instance = data["instance"]

    notification = SurveyNotification(
        instance_id=instance.id,
        student_id=data["student"].id,
        status="sent",
        progress_status="completed",
    )
    db_session.add(notification)
    db_session.commit()

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="rollback_only",
        )

    monkeypatch.setattr(scheduler, "SessionLocal", test_session_factory)

    asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=None,
            now_utc=instance.closes_at + timedelta(seconds=1),
        )
    )

    db_session.refresh(notification)

    assert notification.progress_status == "completed"


def test_close_expired_student_surveys_closes_not_started_notification(
    db_session,
    monkeypatch,
    survey_test_data,
):
    data = survey_test_data
    instance = data["instance"]

    notification = SurveyNotification(
        instance_id=instance.id,
        student_id=data["student"].id,
        status="pending",
        progress_status="not_started",
    )
    db_session.add(notification)
    db_session.commit()

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="rollback_only",
        )

    monkeypatch.setattr(scheduler, "SessionLocal", test_session_factory)

    asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=None,
            now_utc=instance.closes_at + timedelta(seconds=1),
        )
    )

    db_session.refresh(notification)

    assert notification.progress_status == "closed"


def test_safe_mode_deletes_expired_draft_responses(
    db_session,
    monkeypatch,
    survey_test_data,
):
    data = survey_test_data
    instance = data["instance"]
    question = data["questions"][0]
    option = data["options"][0][0]

    notification = SurveyNotification(
        instance_id=instance.id,
        student_id=data["student"].id,
        status="sent",
        progress_status="in_progress",
        max_message_id=12345,
    )

    draft_response = SurveyResponse(
        instance_question_id=question.id,
        student_id=data["student"].id,
        status="draft",
    )

    db_session.add_all([notification, draft_response])
    db_session.flush()

    draft_option = SurveyResponseOption(
        response_id=draft_response.id,
        option_id=option.id,
        instance_question_id=question.id,
    )
    db_session.add(draft_option)
    db_session.commit()

    draft_response_id = draft_response.id

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="rollback_only",
        )

    monkeypatch.setattr(scheduler, "SessionLocal", test_session_factory)

    asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=None,
            now_utc=instance.closes_at,
        )
    )

    db_session.expire_all()

    remaining_response = db_session.get(
        SurveyResponse,
        draft_response_id,
    )

    remaining_options = db_session.scalars(
        select(SurveyResponseOption).where(
            SurveyResponseOption.response_id == draft_response_id,
        )
    ).all()

    db_session.refresh(notification)

    assert remaining_response is None
    assert remaining_options == []
    assert notification.progress_status == "closed"
    assert notification.max_message_id == "12345"


def test_close_expired_student_surveys_retries_after_safe_mode(
    db_session,
    survey_test_data,
    monkeypatch,
):
    """После безопасного закрытия сообщение редактируется при следующем запуске."""

    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].closes_at = now - timedelta(seconds=1)

    notification = create_notification(
        db_session,
        data,
    )
    notification.progress_status = "in_progress"
    notification.max_message_id = "test-message-safe-retry"
    db_session.flush()

    notification_id = notification.id

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    # Первый запуск — безопасный режим.
    result = asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=None,
            now_utc=now,
        )
    )

    assert result == 1

    db_session.expire_all()
    notification = db_session.get(
        SurveyNotification,
        notification_id,
    )

    assert notification.progress_status == "closed"
    assert notification.max_message_id == "test-message-safe-retry"

    # Второй запуск — MAX Bot доступен.
    class FakeBot:
        def __init__(self):
            self.edited_messages = []

        async def edit_message(self, **kwargs):
            self.edited_messages.append(kwargs)

    bot = FakeBot()

    result = asyncio.run(
        scheduler.close_expired_student_surveys(
            bot=bot,
            now_utc=now + timedelta(minutes=1),
        )
    )

    assert result == 0
    assert len(bot.edited_messages) == 1

    assert bot.edited_messages[0]["message_id"] == (
        "test-message-safe-retry"
    )
    assert bot.edited_messages[0]["text"] == (
        "Опрос окончен, спасибо за ответы"
    )
    assert bot.edited_messages[0]["attachments"] == []

    db_session.expire_all()
    notification = db_session.get(
        SurveyNotification,
        notification_id,
    )

    assert notification.progress_status == "closed"
    assert notification.max_message_id is None


def test_recover_stale_notifications_ignores_completed(
    db_session,
    survey_test_data,
):
    now = datetime.now(timezone.utc)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        progress_status="completed",
        attempt_count=1,
        last_attempt_at=now - timedelta(minutes=15),
    )

    result = scheduler.recover_stale_notifications(
        db_session,
        now,
    )

    assert result == 0

    db_session.refresh(notification)

    assert notification.status == "sending"
    assert notification.progress_status == "completed"
    assert notification.attempt_count == 1


def test_recover_stale_notifications_ignores_closed(
    db_session,
    survey_test_data,
):
    now = datetime.now(timezone.utc)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        progress_status="closed",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=now - timedelta(minutes=15),
    )

    result = scheduler.recover_stale_notifications(
        db_session,
        now,
    )

    assert result == 0

    db_session.refresh(notification)

    assert notification.status == "sending"
    assert notification.progress_status == "closed"
    assert notification.attempt_count == scheduler.MAX_NOTIFICATION_ATTEMPTS


def test_reset_exhausted_notifications_ignores_completed(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    now = datetime.combine(
        survey_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=3)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="failed",
        progress_status="completed",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=now - timedelta(hours=1),
    )

    result = scheduler.reset_exhausted_notifications(
        db_session,
        now,
    )

    assert result == 0

    db_session.refresh(notification)

    assert notification.status == "failed"
    assert notification.progress_status == "completed"
    assert notification.attempt_count == scheduler.MAX_NOTIFICATION_ATTEMPTS


def test_reset_exhausted_notifications_ignores_closed(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    now = datetime.combine(
        survey_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=3)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="failed",
        progress_status="closed",
        attempt_count=scheduler.MAX_NOTIFICATION_ATTEMPTS,
        last_attempt_at=now - timedelta(hours=1),
    )

    result = scheduler.reset_exhausted_notifications(
        db_session,
        now,
    )

    assert result == 0

    db_session.refresh(notification)

    assert notification.status == "failed"
    assert notification.progress_status == "closed"
    assert notification.attempt_count == scheduler.MAX_NOTIFICATION_ATTEMPTS


def test_get_pending_notification_ignores_completed(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    now = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        14,
        0,
        tzinfo=timezone.utc,
    )

    notification = create_notification(
        db_session,
        survey_test_data,
        status="pending",
        progress_status="completed",
    )

    result = scheduler.get_pending_notification(
        db_session,
        now,
    )

    assert result is None

    db_session.refresh(notification)

    assert notification.status == "pending"
    assert notification.progress_status == "completed"
    assert notification.attempt_count == 0


def test_get_pending_notification_ignores_closed(
    db_session,
    survey_test_data,
):
    survey_date = survey_test_data["instance"].survey_date

    now = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        14,
        0,
        tzinfo=timezone.utc,
    )

    notification = create_notification(
        db_session,
        survey_test_data,
        status="pending",
        progress_status="closed",
    )

    result = scheduler.get_pending_notification(
        db_session,
        now,
    )

    assert result is None

    db_session.refresh(notification)

    assert notification.status == "pending"
    assert notification.progress_status == "closed"
    assert notification.attempt_count == 0


def test_refresh_notification_lease_only_updates_current_attempt(
    db_session,
    survey_test_data,
    monkeypatch,
):
    old_timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)

    notification = create_notification(
        db_session,
        survey_test_data,
        status="sending",
        attempt_count=2,
        last_attempt_at=old_timestamp,
    )

    db_session.commit()

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        test_session_factory,
    )

    # Актуальная попытка должна продлить lease.
    assert scheduler.refresh_notification_lease(
        notification.id,
        2,
    ) is True

    db_session.refresh(notification)

    assert notification.last_attempt_at > old_timestamp

    refreshed_timestamp = notification.last_attempt_at

    # Устаревшая попытка не должна менять timestamp.
    assert scheduler.refresh_notification_lease(
        notification.id,
        1,
    ) is False

    db_session.refresh(notification)

    assert notification.last_attempt_at == refreshed_timestamp


def test_maintain_notification_lease_stops_when_attempt_is_stale(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        scheduler,
        "NOTIFICATION_HEARTBEAT_SECONDS",
        0,
    )

    def fake_refresh(notification_id, attempt_number):
        calls.append((notification_id, attempt_number))
        return False

    monkeypatch.setattr(
        scheduler,
        "refresh_notification_lease",
        fake_refresh,
    )

    asyncio.run(
        scheduler.maintain_notification_lease(
            notification_id=123,
            attempt_number=2,
        )
    )

    assert calls == [(123, 2)]
