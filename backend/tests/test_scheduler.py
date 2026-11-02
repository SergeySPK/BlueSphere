from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import scheduler
from models import SurveyNotification


def create_notification(db_session, survey_test_data, **kwargs):
    """Создаёт уведомление для тестового ученика."""

    notification = SurveyNotification(
        instance_id=survey_test_data["instance"].id,
        student_id=survey_test_data["student"].id,
        status=kwargs.get("status", "pending"),
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
    now = datetime.now(timezone.utc)

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
    now = datetime.now(timezone.utc)

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
        from sqlalchemy.orm import Session

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
        success=True,
    )

    db_session.refresh(notification)

    assert notification.status == "sent"
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
        from sqlalchemy.orm import Session

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
        success=False,
        error="Временная ошибка MAX API",
    )

    db_session.refresh(notification)

    assert notification.status == "pending"
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
        from sqlalchemy.orm import Session

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
        success=False,
        error="MAX API недоступен",
    )

    db_session.refresh(notification)

    assert notification.status == "failed"
    assert notification.error == "MAX API недоступен"


import asyncio


def test_process_notification_queue_safe_mode(
    db_session,
    monkeypatch,
):
    from sqlalchemy.orm import Session

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


def test_process_notification_queue_respects_batch_limit(
    db_session,
    monkeypatch,
):
    from sqlalchemy.orm import Session

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

        return notification_id, 999999999

    def fake_create_max_bot():
        return fake_bot

    async def fake_send_notification(bot, user_id, text):
        assert bot is fake_bot
        assert user_id == 999999999
        assert text.strip()
        sent_notifications.append(user_id)

    def fake_update_notification_result(
        notification_id,
        success,
        error=None,
    ):
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
