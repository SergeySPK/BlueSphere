import asyncio
import pytest
from types import SimpleNamespace
import max_bot
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import SurveyNotification, SurveyResponse, SurveyResponseOption

@pytest.fixture
def max_bot_module(db_session, monkeypatch):
    """Подключает MAX-бот к общей тестовой транзакции."""

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        max_bot,
        "SessionLocal",
        test_session_factory,
    )

    return max_bot


def mock_process_survey_callback(monkeypatch, result):
    """Подменяет единую обработку callback для тестов."""

    monkeypatch.setattr(
        max_bot,
        "process_survey_callback",
        lambda max_user_id, action, question_id, option_id=None: result,
    )


def test_get_question_options_returns_sorted_options(
    survey_test_data,
    max_bot_module,
):
    data = survey_test_data
    question = data["questions"][0]

    result = max_bot_module.get_question_options(question.id)

    expected = [
        {
            "id": option.id,
            "title": option.title,
            "is_exclusive": option.is_exclusive,
        }
        for option in data["options"][0]
    ]

    assert result == expected


def test_get_selected_options_returns_draft_selections(
    survey_test_data,
    db_session,
    max_bot_module,
):
    data = survey_test_data
    question = data["questions"][1]
    selected_options = data["options"][1][:2]

    # Создаём черновик ответа ученика.
    draft = SurveyResponse(
        instance_question_id=question.id,
        student_id=data["student"].id,
        status="draft",
    )
    db_session.add(draft)
    db_session.flush()

    # Сохраняем два выбранных варианта.
    for option in selected_options:
        db_session.add(
            SurveyResponseOption(
                response_id=draft.id,
                option_id=option.id,
                instance_question_id=question.id,
            )
        )

    db_session.flush()

    result = max_bot_module.get_selected_options(
        data["max_user_id"],
        question.id,
    )

    assert set(result) == {option.id for option in selected_options}


def test_build_multiple_keyboard_marks_selected_options(
    monkeypatch,
    max_bot_module,
):
    # Подменяем классы MAX SDK простыми объектами,
    # чтобы проверить содержимое клавиатуры без обращения к MAX.

    class FakeCallbackButton:
        def __init__(self, text, payload):
            self.text = text
            self.payload = payload

    class FakeButtonsPayload:
        def __init__(self, buttons):
            self.buttons = buttons

        def pack(self):
            return self

    monkeypatch.setattr(
        max_bot_module,
        "CallbackButton",
        FakeCallbackButton,
    )
    monkeypatch.setattr(
        max_bot_module,
        "ButtonsPayload",
        FakeButtonsPayload,
    )

    options = [
        {"id": 10, "title": "Математика", "is_exclusive": False},
        {"id": 11, "title": "История", "is_exclusive": False},
        {"id": 12, "title": "Никакой", "is_exclusive": True},
    ]

    keyboard = max_bot_module.build_multiple_keyboard(
        question_id=25,
        options=options,
        selected_ids=[11],
    )

    assert len(keyboard.buttons) == 4

    assert keyboard.buttons[0][0].text == "☐ Математика"
    assert keyboard.buttons[0][0].payload == "survey_toggle:25:10"

    assert keyboard.buttons[1][0].text == "☑ История"
    assert keyboard.buttons[1][0].payload == "survey_toggle:25:11"

    assert keyboard.buttons[2][0].text == "☐ Никакой"
    assert keyboard.buttons[2][0].payload == "survey_toggle:25:12"

    assert keyboard.buttons[3][0].text == "Готово"
    assert keyboard.buttons[3][0].payload == "survey_done:25"


def test_callback_handler_rejects_malformed_payload(
    monkeypatch,
    max_bot_module,
):
    messages = []

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="incorrect_payload",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Не удалось обработать ответ. Попробуй ещё раз."]


def test_callback_handler_rejects_unknown_action(
    monkeypatch,
    max_bot_module,
):
    messages = []

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="unknown:25",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Неизвестное действие."]


def test_callback_handler_rejects_unavailable_survey(
    monkeypatch,
    max_bot_module,
):
    messages = []

    mock_process_survey_callback(monkeypatch, {"status": "closed"})

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey:25:10",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Время прохождения этого опроса завершилось."]


def test_callback_handler_completes_single_answer(
    monkeypatch,
    max_bot_module,
):
    edited_messages = []

    mock_process_survey_callback(monkeypatch, {"status": "submitted", "message": "Ответ сохранён!", "question": None, "completed": True, "instance_id": 100})

    async def fake_edit_callback_message(event, text, keyboard=None):
        edited_messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "edit_callback_message",
        fake_edit_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey:25:10",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert edited_messages == ["Ответ сохранён!\nТы ответил на все вопросы. Спасибо!"]


def test_callback_handler_rejects_already_submitted_single_answer(
    monkeypatch,
    max_bot_module,
):
    messages = []

    mock_process_survey_callback(monkeypatch, {"status": "already_submitted"})

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey:25:10",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Ты уже ответил на этот вопрос."]


def test_callback_handler_acknowledges_selection_limit(
    monkeypatch,
    max_bot_module,
):
    notifications = []

    mock_process_survey_callback(monkeypatch, {"status": "limit_reached"})

    async def fake_ack(notification=None):
        notifications.append(notification)

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey_toggle:25:12",
            user=SimpleNamespace(user_id=12345),
        ),
        ack=fake_ack,
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert notifications == ["Можно выбрать не более двух вариантов."]


def test_callback_handler_updates_multiple_choice_keyboard(
    monkeypatch,
    max_bot_module,
):
    edited_messages = []

    mock_process_survey_callback(
        monkeypatch,
        {
            "status": "saved",
            "instance_id": 100,
            "question": {
                "question_id": 25,
                "answer_type": "multiple",
                "bot_text": "Выбери предметы:",
            },
            "options": [
                {
                    "id": 10,
                    "title": "Математика",
                    "is_exclusive": False,
                },
            ],
            "selected_ids": [10],
            "completed": False,
        },
    )

    async def fake_edit_callback_message(event, text, keyboard=None):
        edited_messages.append((text, keyboard))

    monkeypatch.setattr(
        max_bot_module,
        "edit_callback_message",
        fake_edit_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey_toggle:25:10",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert edited_messages[0][0] == "Выбери предметы:"
    assert edited_messages[0][1] is not None


def test_callback_handler_rejects_incomplete_multiple_answer(
    monkeypatch,
    max_bot_module,
):
    messages = []

    mock_process_survey_callback(monkeypatch, {"status": "incomplete"})

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey_done:25",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Сначала выбери хотя бы один вариант."]


def test_callback_handler_completes_multiple_answer_and_advances(
    monkeypatch,
    max_bot_module,
):
    edited_messages = []

    mock_process_survey_callback(
        monkeypatch,
        {
            "status": "submitted",
            "instance_id": 100,
            "message": "Ответ отправлен!",
            "question": {
                "question_id": 26,
                "answer_type": "single",
                "bot_text": "Оцени своё состояние:",
            },
            "options": [
                {
                    "id": 20,
                    "title": "Хорошо",
                    "is_exclusive": False,
                },
                {
                    "id": 21,
                    "title": "Отлично",
                    "is_exclusive": False,
                },
            ],
            "selected_ids": [],
            "completed": False,
        },
    )

    async def fake_edit_callback_message(event, text, keyboard=None):
        edited_messages.append((text, keyboard))

    monkeypatch.setattr(
        max_bot_module,
        "edit_callback_message",
        fake_edit_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey_done:25",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert len(edited_messages) == 1
    assert edited_messages[0][0] == "Ответ отправлен!\n\nОцени своё состояние:"
    assert edited_messages[0][1] is not None


def test_callback_handler_finishes_after_last_multiple_answer(
    monkeypatch,
    max_bot_module,
):
    edited_messages = []

    mock_process_survey_callback(monkeypatch, {"status": "submitted", "message": "Ответ отправлен!", "question": None, "completed": True, "instance_id": 100})

    async def fake_edit_callback_message(event, text, keyboard=None):
        edited_messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "edit_callback_message",
        fake_edit_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey_done:25",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert edited_messages == ["Ответ отправлен!\nТы ответил на все вопросы. Спасибо!"]


def test_callback_handler_handles_failed_single_answer(
    monkeypatch,
    max_bot_module,
):
    messages = []

    mock_process_survey_callback(monkeypatch, {"status": "invalid"})

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey:25:10",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Не удалось сохранить ответ. Возможно, опрос уже закрыт."]


def test_callback_handler_rejects_already_submitted_multiple_answer(
    monkeypatch,
    max_bot_module,
):
    messages = []

    mock_process_survey_callback(monkeypatch, {"status": "already_submitted"})

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey_done:25",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Ты уже ответил на этот вопрос."]


def test_start_handler_rejects_unregistered_user(
    monkeypatch,
    max_bot_module,
):
    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: None,
    )

    async def fake_answer(text, **kwargs):
        messages.append(text)

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=12345,
                first_name="Сергей",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert messages == [
        "Вы ещё не зарегистрированы в Планировщике учебной нагрузки. "
        "Обратитесь к администратору школы."
    ]


def test_start_handler_shows_teacher_greeting(
    monkeypatch,
    max_bot_module,
):
    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: {
            "full_name": "Иванов Иван Иванович",
            "roles": ["teacher"],
        },
    )

    async def fake_answer(text, **kwargs):
        messages.append({
            "text": text,
            "format": kwargs.get("format"),
        })

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=12345,
                first_name="Иван",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert len(messages) == 1
    assert "Здравствуйте, Иван Иванович!" in messages[0]["text"]
    assert "Планировщик учебной нагрузки" in messages[0]["text"]
    assert "Получать рекомендации" in messages[0]["text"]
    assert messages[0]["format"] == "markdown"


def test_start_handler_shows_admin_greeting(
    monkeypatch,
    max_bot_module,
):
    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: {
            "full_name": "Петров Пётр Петрович",
            "roles": ["admin"],
        },
    )

    async def fake_answer(text, **kwargs):
        messages.append({
            "text": text,
            "format": kwargs.get("format"),
        })

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=12345,
                first_name="Пётр",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert len(messages) == 1
    assert "Здравствуйте, Пётр Петрович!" in messages[0]["text"]
    assert "управления учебной нагрузкой" in messages[0]["text"]
    assert "всем классам Вашей школы" in messages[0]["text"]
    assert messages[0]["format"] == "markdown"


def test_start_handler_handles_user_without_role(
    monkeypatch,
    max_bot_module,
):
    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: {
            "full_name": "Пользователь",
            "roles": [],
        },
    )

    async def fake_answer(text, **kwargs):
        messages.append(text)

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=12345,
                first_name="Пользователь",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert messages == [
        "Ваш аккаунт найден, но для него не назначена роль. "
        "Обратитесь к администратору."
    ]


def test_start_handler_shows_student_without_available_survey(
    monkeypatch,
    max_bot_module,
):
    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: {
            "full_name": "Иванов Иван Иванович",
            "roles": ["student"],
        },
    )

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: None,
    )

    async def fake_answer(text, **kwargs):
        messages.append({
            "text": text,
            "format": kwargs.get("format"),
        })

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=12345,
                first_name="Иван",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert len(messages) == 1
    assert "Привет, Иван!" in messages[0]["text"]
    assert "Планировщик учебной нагрузки" in messages[0]["text"]
    assert "Опрос анонимный" in messages[0]["text"]
    assert messages[0]["format"] == "markdown"


@pytest.mark.parametrize(
    ("full_name", "fallback_name", "expected"),
    [
        (
            "Иванов Иван Иванович",
            "MAX",
            ("Иван", "Иванович"),
        ),
        (
            "Иванов Иван",
            "MAX",
            ("Иван", None),
        ),
        (
            "Иванов",
            "MAX",
            ("MAX", None),
        ),
        (
            None,
            "MAX",
            ("MAX", None),
        ),
        (
            None,
            None,
            ("друг", None),
        ),
    ],
)
def test_get_greeting_name(
    max_bot_module,
    full_name,
    fallback_name,
    expected,
):
    assert max_bot_module.get_greeting_name(
        full_name,
        fallback_name,
    ) == expected


def test_start_handler_restores_question_on_repeated_start(
    db_session,
    survey_test_data,
    survey_service_session,
    max_bot_module,
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

    class FakeCallbackButton:
        def __init__(self, text, payload):
            self.text = text
            self.payload = payload

    class FakeButtonsPayload:
        def __init__(self, buttons):
            self.buttons = buttons

        def pack(self):
            return self

    monkeypatch.setattr(
        max_bot_module,
        "CallbackButton",
        FakeCallbackButton,
    )
    monkeypatch.setattr(
        max_bot_module,
        "ButtonsPayload",
        FakeButtonsPayload,
    )

    sent_messages = []
    message_counter = 0

    async def fake_answer(text, **kwargs):
        nonlocal message_counter
        message_counter += 1

        sent_messages.append({
            "text": text,
            "attachments": kwargs.get("attachments"),
            "format": kwargs.get("format"),
        })

        return SimpleNamespace(
            message=SimpleNamespace(
                body=SimpleNamespace(
                    mid=f"test-max-message-{message_counter}",
                ),
            )
        )

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=data["max_user_id"],
                first_name="Иван",
            ),
            answer=fake_answer,
        )
    )

    # Первый /start.
    asyncio.run(max_bot_module.start_handler(event))

    db_session.refresh(notification)

    assert notification.progress_status == "in_progress"
    assert notification.started_at is not None
    assert notification.max_message_id == "test-max-message-2"

    assert len(sent_messages) == 2

    # Первое сообщение — приветствие.
    assert "Планировщик учебной нагрузки" in sent_messages[0]["text"]
    assert sent_messages[0]["format"] == "markdown"
    assert sent_messages[0]["attachments"] is None

    # Второе сообщение — первый вопрос.
    assert sent_messages[1]["text"] == "Общая оценка состояния"
    assert sent_messages[1]["attachments"]

    # Повторный /start.
    asyncio.run(max_bot_module.start_handler(event))

    db_session.refresh(notification)

    # Снова приветствие и актуальный незавершённый вопрос.
    assert len(sent_messages) == 4

    assert "Планировщик учебной нагрузки" in sent_messages[2]["text"]
    assert sent_messages[3]["text"] == "Общая оценка состояния"
    assert sent_messages[3]["attachments"]

    # Прогресс не сброшен, ID сообщения обновлён.
    assert notification.progress_status == "in_progress"
    assert notification.max_message_id == "test-max-message-4"


def test_start_handler_restores_multiple_answer_draft(
    db_session,
    survey_test_data,
    survey_service_session,
    max_bot_module,
    monkeypatch,
):
    data = survey_test_data

    notification = SurveyNotification(
        instance_id=data["instance"].id,
        student_id=data["student"].id,
        status="sent",
        progress_status="in_progress",
    )
    db_session.add(notification)

    first_question = data["questions"][0]

    first_response = SurveyResponse(
        instance_question_id=first_question.id,
        student_id=data["student"].id,
        status="submitted",
    )

    db_session.add(first_response)

    question = data["questions"][1]
    selected_options = data["options"][1][:2]

    draft = SurveyResponse(
        instance_question_id=question.id,
        student_id=data["student"].id,
        status="draft",
    )
    db_session.add(draft)
    db_session.flush()

    for option in selected_options:
        db_session.add(
            SurveyResponseOption(
                response_id=draft.id,
                option_id=option.id,
                instance_question_id=question.id,
            )
        )

    db_session.commit()

    class FakeCallbackButton:
        def __init__(self, text, payload):
            self.text = text
            self.payload = payload

    class FakeButtonsPayload:
        def __init__(self, buttons):
            self.buttons = buttons

        def pack(self):
            return self

    monkeypatch.setattr(
        max_bot_module,
        "CallbackButton",
        FakeCallbackButton,
    )
    monkeypatch.setattr(
        max_bot_module,
        "ButtonsPayload",
        FakeButtonsPayload,
    )

    sent_messages = []

    async def fake_answer(text, **kwargs):
        sent_messages.append({
            "text": text,
            "attachments": kwargs.get("attachments"),
        })

        return SimpleNamespace(
            message=SimpleNamespace(
                body=SimpleNamespace(mid="draft-test-message"),
            )
        )

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=data["max_user_id"],
                first_name="Иван",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert len(sent_messages) == 2

    # Бот восстановил именно второй вопрос.
    assert sent_messages[1]["text"] == question.bot_text

    keyboard = sent_messages[1]["attachments"][0]

    # Два сохранённых варианта снова отмечены.
    assert keyboard.buttons[0][0].text.startswith("☑")
    assert keyboard.buttons[1][0].text.startswith("☑")

    # Остальные варианты не должны быть отмечены.
    assert keyboard.buttons[2][0].text.startswith("☐")

    # Payload кнопок должен соответствовать исходным вариантам.
    assert keyboard.buttons[0][0].payload == (
        f"survey_toggle:{question.id}:{data['options'][1][0].id}"
    )
    assert keyboard.buttons[1][0].payload == (
        f"survey_toggle:{question.id}:{data['options'][1][1].id}"
    )

    # Кнопка подтверждения должна относиться к этому вопросу.
    assert keyboard.buttons[-1][0].payload == f"survey_done:{question.id}"

    # Кнопка подтверждения тоже присутствует.
    assert keyboard.buttons[-1][0].text == "Готово"

    db_session.refresh(notification)

    assert notification.progress_status == "in_progress"
    assert notification.max_message_id == "draft-test-message"


def test_start_handler_opens_next_unanswered_question(
    db_session,
    survey_test_data,
    survey_service_session,
    max_bot_module,
    monkeypatch,
):
    from datetime import datetime, timezone

    data = survey_test_data

    notification = SurveyNotification(
        instance_id=data["instance"].id,
        student_id=data["student"].id,
        status="sent",
        progress_status="in_progress",
    )
    db_session.add(notification)

    first_question = data["questions"][0]

    submitted_response = SurveyResponse(
        instance_question_id=first_question.id,
        student_id=data["student"].id,
        status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(submitted_response)
    db_session.commit()

    class FakeCallbackButton:
        def __init__(self, text, payload):
            self.text = text
            self.payload = payload

    class FakeButtonsPayload:
        def __init__(self, buttons):
            self.buttons = buttons

        def pack(self):
            return self

    monkeypatch.setattr(
        max_bot_module,
        "CallbackButton",
        FakeCallbackButton,
    )
    monkeypatch.setattr(
        max_bot_module,
        "ButtonsPayload",
        FakeButtonsPayload,
    )

    sent_messages = []

    async def fake_answer(text, **kwargs):
        sent_messages.append({
            "text": text,
            "attachments": kwargs.get("attachments"),
        })

        return SimpleNamespace(
            message=SimpleNamespace(
                body=SimpleNamespace(mid="next-question-message"),
            )
        )

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=data["max_user_id"],
                first_name="Иван",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert len(sent_messages) == 2
    assert sent_messages[1]["text"] == data["questions"][1].bot_text
    assert sent_messages[1]["attachments"]


def test_callback_handler_completes_full_survey(
    db_session,
    survey_test_data,
    survey_service_session,
    max_bot_module,
    monkeypatch,
):
    data = survey_test_data
    user_id = data["max_user_id"]
    instance_id = data["instance"].id

    notification = SurveyNotification(
        instance_id=instance_id,
        student_id=data["student"].id,
        status="sent",
        progress_status="in_progress",
        max_message_id="test-question-message",
    )
    db_session.add(notification)
    db_session.commit()

    class FakeCallbackButton:
        def __init__(self, text, payload):
            self.text = text
            self.payload = payload

    class FakeButtonsPayload:
        def __init__(self, buttons):
            self.buttons = buttons

        def pack(self):
            return self

    monkeypatch.setattr(
        max_bot_module,
        "CallbackButton",
        FakeCallbackButton,
    )
    monkeypatch.setattr(
        max_bot_module,
        "ButtonsPayload",
        FakeButtonsPayload,
    )

    edited_messages = []

    def make_event(payload):
        async def fake_edit(**kwargs):
            edited_messages.append(kwargs)

        return SimpleNamespace(
            callback=SimpleNamespace(
                payload=payload,
                user=SimpleNamespace(user_id=user_id),
            ),
            message=SimpleNamespace(
                body=SimpleNamespace(mid="test-question-message"),
            ),
            edit=fake_edit,
        )

    # Вопрос 1: одиночный ответ.
    first_question = data["questions"][0]
    first_option = data["options"][0][0]

    asyncio.run(
        max_bot_module.callback_handler(
            make_event(
                f"survey:{first_question.id}:{first_option.id}"
            )
        )
    )

    first_response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == first_question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )

    assert first_response is not None
    assert first_response.status == "submitted"

    # Вопрос 2: множественный выбор.
    second_question = data["questions"][1]
    second_option = data["options"][1][0]

    asyncio.run(
        max_bot_module.callback_handler(
            make_event(
                f"survey_toggle:{second_question.id}:{second_option.id}"
            )
        )
    )

    second_response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == second_question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )

    assert second_response is not None
    assert second_response.status == "draft"

    asyncio.run(
        max_bot_module.callback_handler(
            make_event(f"survey_done:{second_question.id}")
        )
    )

    db_session.refresh(second_response)

    assert second_response.status == "submitted"

    # Вопрос 3: множественный выбор.
    third_question = data["questions"][2]
    third_option = data["options"][2][0]

    asyncio.run(
        max_bot_module.callback_handler(
            make_event(
                f"survey_toggle:{third_question.id}:{third_option.id}"
            )
        )
    )

    third_response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == third_question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )

    assert third_response is not None
    assert third_response.status == "draft"

    asyncio.run(
        max_bot_module.callback_handler(
            make_event(f"survey_done:{third_question.id}")
        )
    )

    db_session.refresh(third_response)
    db_session.refresh(notification)

    assert third_response.status == "submitted"
    assert notification.progress_status == "completed"
    assert notification.completed_at is not None

    # Все три ответа должны сохраниться.
    responses = db_session.scalars(
        select(SurveyResponse).where(
            SurveyResponse.student_id == data["student"].id,
        )
    ).all()

    assert len(responses) == 3
    assert all(response.status == "submitted" for response in responses)

    # После завершения повторное нажатие не должно менять ответы.
    messages = []

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    asyncio.run(
        max_bot_module.callback_handler(
            make_event(f"survey_done:{third_question.id}")
        )
    )

    assert messages == [
        "Время прохождения этого опроса завершилось."
    ]

    # Повторный /start после завершения сообщает, что ученик уже ответил на все вопросы.
    start_messages = []

    async def fake_start_answer(text, **kwargs):
        start_messages.append(text)

    start_event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=user_id,
                first_name="Ученик",
            ),
            answer=fake_start_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(start_event))

    assert len(start_messages) == 2

    assert "Привет" in start_messages[0]
    assert "Планировщик учебной нагрузки" in start_messages[0]

    assert (
        start_messages[1]
        == "Ты уже ответил на все вопросы этого опроса. Спасибо! 💙"
    )

    db_session.refresh(notification)

    assert notification.progress_status == "completed"


@pytest.mark.parametrize(
    "progress_status",
    ["completed", "closed", "not_started"],
)
def test_callback_handler_rejects_inactive_survey_progress(
    progress_status,
    monkeypatch,
    max_bot_module,
):
    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_survey_progress",
        lambda user_id, instance_id: progress_status,
    )

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey:25:10",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == [
        "Время прохождения этого опроса завершилось."
    ]
