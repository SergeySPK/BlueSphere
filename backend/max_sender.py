import os
from pathlib import Path

from dotenv import load_dotenv
from maxapi import Bot
from maxapi.types.attachments.attachment import ButtonsPayload
from maxapi.types.attachments.buttons import CallbackButton
from sqlalchemy import select

from database import SessionLocal
from models import (
    Student,
    SurveyInstanceOption,
    SurveyNotification,
    SurveyResponse,
    SurveyResponseOption,
    User,
)
from survey_service import (
    complete_survey_progress,
    get_next_question,
    save_survey_question_message_id,
    start_survey_progress,
)


INVITATION_TEXT = (
    "Для вас подготовлен новый опрос, пожалуйста, "
    "пройдите его, ответив на несколько вопросов"
)


def create_max_bot() -> Bot:
    """Создаёт отдельный экземпляр MAX Bot для отправки сообщений."""

    env_file = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_file)

    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана.")

    return Bot(token=token)


def _get_student_delivery_state(max_user_id: int, instance_id: int):
    """Получает состояние прохождения и ID последнего сообщения ученика."""

    db = SessionLocal()

    try:
        result = db.execute(
            select(
                User.full_name,
                Student.id.label("student_id"),
                SurveyNotification.progress_status,
                SurveyNotification.max_message_id,
            )
            .join(Student, Student.user_id == User.id)
            .join(
                SurveyNotification,
                SurveyNotification.student_id == Student.id,
            )
            .where(
                User.sferum_id == str(max_user_id),
                SurveyNotification.instance_id == instance_id,
            )
        ).first()

        if result is None:
            return None

        return {
            "full_name": result.full_name,
            "student_id": result.student_id,
            "progress_status": result.progress_status,
            "max_message_id": result.max_message_id,
        }

    finally:
        db.close()


def _get_question_options(question_id: int) -> list[dict]:
    """Получает варианты ответа на вопрос."""

    db = SessionLocal()

    try:
        options = db.execute(
            select(
                SurveyInstanceOption.id,
                SurveyInstanceOption.title,
            )
            .where(
                SurveyInstanceOption.instance_question_id == question_id
            )
            .order_by(SurveyInstanceOption.sort_order)
        ).all()

        return [
            {
                "id": option.id,
                "title": option.title,
            }
            for option in options
        ]

    finally:
        db.close()


def _get_selected_options(
    student_id: int,
    question_id: int,
) -> list[int]:
    """Получает выбранные учеником варианты чернового ответа."""

    db = SessionLocal()

    try:
        response = db.scalar(
            select(SurveyResponse).where(
                SurveyResponse.instance_question_id == question_id,
                SurveyResponse.student_id == student_id,
                SurveyResponse.status == "draft",
            )
        )

        if response is None:
            return []

        return db.scalars(
            select(SurveyResponseOption.option_id).where(
                SurveyResponseOption.response_id == response.id
            )
        ).all()

    finally:
        db.close()


def _build_multiple_keyboard(
    question_id: int,
    options: list[dict],
    selected_ids: list[int],
):
    """Создаёт клавиатуру для вопроса с несколькими вариантами."""

    buttons = []

    for option in options:
        mark = "☑" if option["id"] in selected_ids else "☐"

        buttons.append(
            [
                CallbackButton(
                    text=f"{mark} {option['title']}",
                    payload=(
                        f"survey_toggle:{question_id}:{option['id']}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            CallbackButton(
                text="Готово",
                payload=f"survey_done:{question_id}",
            )
        ]
    )

    return ButtonsPayload(buttons=buttons).pack()


def _build_question_keyboard(
    question: dict,
    student_id: int,
):
    """Создаёт клавиатуру в зависимости от типа вопроса."""

    question_id = question["question_id"]
    options = _get_question_options(question_id)

    if question["answer_type"] == "multiple":
        selected_ids = _get_selected_options(
            student_id,
            question_id,
        )

        return _build_multiple_keyboard(
            question_id,
            options,
            selected_ids,
        )

    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text=option["title"],
                    payload=(
                        f"survey:{question_id}:{option['id']}"
                    ),
                )
            ]
            for option in options
        ]
    ).pack()


async def send_survey_invitation_and_question(
    bot: Bot,
    max_user_id: int,
    instance_id: int,
) -> None:
    """Отправляет приглашение и первый вопрос конкретного опроса."""

    state = _get_student_delivery_state(
        max_user_id,
        instance_id,
    )

    if state is None:
        raise RuntimeError(
            "Не найдена запись уведомления ученика. "
            f"MAX user_id={max_user_id}, instance_id={instance_id}"
        )

    progress = state["progress_status"]

    # Завершённый или закрытый опрос повторно не отправляем.
    if progress in ("completed", "closed"):
        return

    # Вопрос уже был отправлен — не создаём дубликат.
    if state["max_message_id"]:
        return

    # При первом запуске сначала отправляем приглашение.
    if progress == "not_started":
        await bot.send_message(
            user_id=max_user_id,
            text=INVITATION_TEXT,
        )

        progress = start_survey_progress(
            max_user_id,
            instance_id,
        )

        if progress is None:
            raise RuntimeError(
                "Не удалось начать прохождение опроса."
            )

        if progress in ("completed", "closed"):
            return

    elif progress != "in_progress":
        raise RuntimeError(
            f"Неизвестное состояние прохождения: {progress!r}"
        )

    # Повторно читаем состояние после начала прохождения.
    state = _get_student_delivery_state(
        max_user_id,
        instance_id,
    )

    if state is None:
        raise RuntimeError(
            "Не удалось повторно получить состояние прохождения."
        )

    if state["progress_status"] != "in_progress":
        return

    if state["max_message_id"]:
        return

    question = get_next_question(
        max_user_id,
        instance_id,
    )

    if question is None:
        complete_survey_progress(
            max_user_id,
            instance_id,
        )
        return

    keyboard = _build_question_keyboard(
        question,
        state["student_id"],
    )

    name = state["full_name"] or "ученик"

    sent_message = await bot.send_message(
        user_id=max_user_id,
        text=f"Привет, {name}!\n\n{question['bot_text']}",
        attachments=[keyboard],
    )

    message = getattr(sent_message, "message", None)
    body = getattr(message, "body", None)
    message_id = getattr(body, "mid", None)

    if not message_id:
        raise RuntimeError(
            "MAX SDK не вернул ID сообщения с первым вопросом."
        )

    saved = save_survey_question_message_id(
        max_user_id,
        instance_id,
        str(message_id),
    )

    if not saved:
        raise RuntimeError(
            "Не удалось сохранить ID сообщения с первым вопросом."
        )


async def send_notification(
    bot: Bot,
    user_id: int,
    instance_id: int,
) -> None:
    """Отправляет приглашение и первый вопрос конкретного опроса."""

    if user_id <= 0:
        raise ValueError("Некорректный MAX user_id.")

    if instance_id <= 0:
        raise ValueError("Некорректный ID экземпляра опроса.")

    await send_survey_invitation_and_question(
        bot=bot,
        max_user_id=user_id,
        instance_id=instance_id,
    )
