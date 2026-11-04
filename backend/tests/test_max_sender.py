import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

import max_sender
from models import SurveyNotification


@pytest.fixture
def max_sender_module(db_session, monkeypatch):
    """Направляет MAX sender в тестовую транзакцию."""

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        max_sender,
        "SessionLocal",
        test_session_factory,
    )

    return max_sender


def test_send_survey_invitation_and_question_is_idempotent(
    db_session,
    survey_test_data,
    survey_service_session,
    max_sender_module,
    monkeypatch,
):
    data = survey_test_data

    notification = SurveyNotification(
        instance_id=data["instance"].id,
        student_id=data["student"].id,
        status="pending",
        progress_status="not_started",
    )
    db_session.add(notification)
    db_session.commit()

    # В этом тесте проверяем отправку сообщений,
    # поэтому клавиатуру заменяем простым объектом.
    monkeypatch.setattr(
        max_sender_module,
        "_build_question_keyboard",
        lambda question, student_id: "test-keyboard",
    )

    class FakeBot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

            if kwargs["text"] == max_sender_module.INVITATION_TEXT:
                return None

            return SimpleNamespace(
                message=SimpleNamespace(
                    body=SimpleNamespace(mid="sender-test-message-1"),
                )
            )

    bot = FakeBot()

    # Первая отправка.
    asyncio.run(
        max_sender_module.send_survey_invitation_and_question(
            bot=bot,
            max_user_id=data["max_user_id"],
            instance_id=data["instance"].id,
        )
    )

    db_session.refresh(notification)

    assert notification.progress_status == "in_progress"
    assert notification.started_at is not None
    assert notification.max_message_id == "sender-test-message-1"

    assert len(bot.messages) == 2

    assert bot.messages[0]["text"] == (
        "Для вас подготовлен новый опрос, пожалуйста, "
        "пройдите его, ответив на несколько вопросов"
    )

    assert bot.messages[1]["text"] == (
        "Привет, Тестовый ученик!\n\n"
        "Общая оценка состояния"
    )

    assert bot.messages[1]["attachments"] == ["test-keyboard"]

    # Повторный вызов не должен отправлять приглашение
    # и первый вопрос второй раз.
    asyncio.run(
        max_sender_module.send_survey_invitation_and_question(
            bot=bot,
            max_user_id=data["max_user_id"],
            instance_id=data["instance"].id,
        )
    )

    assert len(bot.messages) == 2

    db_session.refresh(notification)

    assert notification.progress_status == "in_progress"
    assert notification.max_message_id == "sender-test-message-1"
