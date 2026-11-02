import pytest
import max_bot
from sqlalchemy.orm import Session

from models import SurveyResponse, SurveyResponseOption


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
    import asyncio
    from types import SimpleNamespace

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
    import asyncio
    from types import SimpleNamespace

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
    import asyncio
    from types import SimpleNamespace

    messages = []

    async def fake_send_callback_message(event, text):
        messages.append(text)

    monkeypatch.setattr(
        max_bot_module,
        "send_callback_message",
        fake_send_callback_message,
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: None,
    )

    event = SimpleNamespace(
        callback=SimpleNamespace(
            payload="survey:25:10",
            user=SimpleNamespace(user_id=12345),
        )
    )

    asyncio.run(max_bot_module.callback_handler(event))

    assert messages == ["Сейчас опрос недоступен или его время уже закончилось."]


def test_callback_handler_completes_single_answer(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

    edited_messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "save_single_answer",
        lambda **kwargs: "submitted",
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_next_question",
        lambda user_id, instance_id: None,
    )

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
    import asyncio
    from types import SimpleNamespace

    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "save_single_answer",
        lambda **kwargs: "already_submitted",
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

    assert messages == ["Ты уже ответил на этот вопрос."]


def test_callback_handler_acknowledges_selection_limit(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

    notifications = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "toggle_multiple_answer",
        lambda **kwargs: "limit_reached",
    )

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
    import asyncio
    from types import SimpleNamespace

    edited_messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "toggle_multiple_answer",
        lambda **kwargs: "saved",
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_next_question",
        lambda user_id, instance_id: {
            "question_id": 25,
            "answer_type": "multiple",
            "bot_text": "Выбери предметы:",
        },
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_question_options",
        lambda question_id: [
            {"id": 10, "title": "Математика", "is_exclusive": False},
        ],
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_selected_options",
        lambda user_id, question_id: [10],
    )
    monkeypatch.setattr(
        max_bot_module,
        "build_multiple_keyboard",
        lambda question_id, options, selected_ids: "test_keyboard",
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

    assert edited_messages == [("Выбери предметы:", "test_keyboard")]


def test_callback_handler_rejects_incomplete_multiple_answer(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "submit_multiple_answer",
        lambda **kwargs: "incomplete",
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
    import asyncio
    from types import SimpleNamespace

    edited_messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "submit_multiple_answer",
        lambda **kwargs: "submitted",
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_next_question",
        lambda user_id, instance_id: {
            "question_id": 26,
            "answer_type": "single",
            "bot_text": "Оцени своё состояние:",
        },
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_question_options",
        lambda question_id: [
            {"id": 20, "title": "Хорошо", "is_exclusive": False},
            {"id": 21, "title": "Отлично", "is_exclusive": False},
        ],
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
    assert edited_messages[0][0] == ("Ответ отправлен!\n\nОцени своё состояние:")
    assert edited_messages[0][1] is not None


def test_callback_handler_finishes_after_last_multiple_answer(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

    edited_messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "submit_multiple_answer",
        lambda **kwargs: "submitted",
    )
    monkeypatch.setattr(
        max_bot_module,
        "get_next_question",
        lambda user_id, instance_id: None,
    )

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
    import asyncio
    from types import SimpleNamespace

    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "save_single_answer",
        lambda **kwargs: "invalid",
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

    assert messages == ["Не удалось сохранить ответ. Возможно, опрос уже закрыт."]


def test_callback_handler_rejects_already_submitted_multiple_answer(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
        lambda user_id: {"instance_id": 100},
    )
    monkeypatch.setattr(
        max_bot_module,
        "submit_multiple_answer",
        lambda **kwargs: "already_submitted",
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
    import asyncio
    from types import SimpleNamespace

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
        "Вы ещё не зарегистрированы в Blue Sphere. "
        "Обратитесь к администратору школы."
    ]


def test_start_handler_shows_teacher_greeting(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: {
            "full_name": "Тестовый учитель",
            "roles": ["teacher"],
        },
    )

    async def fake_answer(text, **kwargs):
        messages.append(text)

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=12345,
                first_name="Учитель",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert messages == [
        "Здравствуйте! Вы учитель.\n"
        "Управление нагрузкой доступно в приложении Blue Sphere."
    ]


def test_start_handler_shows_admin_greeting(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: {
            "full_name": "Тестовый администратор",
            "roles": ["admin"],
        },
    )

    async def fake_answer(text, **kwargs):
        messages.append(text)

    event = SimpleNamespace(
        message=SimpleNamespace(
            sender=SimpleNamespace(
                user_id=12345,
                first_name="Администратор",
            ),
            answer=fake_answer,
        )
    )

    asyncio.run(max_bot_module.start_handler(event))

    assert messages == ["Здравствуйте! Вы администратор Blue Sphere."]


def test_start_handler_handles_user_without_role(
    monkeypatch,
    max_bot_module,
):
    import asyncio
    from types import SimpleNamespace

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
    import asyncio
    from types import SimpleNamespace

    messages = []

    monkeypatch.setattr(
        max_bot_module,
        "get_user_profile",
        lambda user_id: {
            "full_name": "Тестовый ученик",
            "roles": ["student"],
        },
    )

    monkeypatch.setattr(
        max_bot_module,
        "get_available_survey",
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
        "Привет, Тестовый ученик!\n" "Сейчас для тебя нет доступных опросов."
    ]
