from pathlib import Path
import asyncio
import logging
import os
from dotenv import load_dotenv
from maxapi import Bot, Dispatcher
from maxapi.types import CommandStart, MessageCreated, MessageCallback
from maxapi.types.attachments.attachment import ButtonsPayload
from maxapi.types.attachments.buttons import CallbackButton

from sqlalchemy import select, text

from database import SessionLocal, engine
from models import (
    User,
    Teacher,
    Student,
    Administrator,
    SurveyInstanceOption,
    SurveyResponse,
    SurveyResponseOption,
)
from survey_service import (
    get_available_survey,
    get_next_question,
    get_survey_progress,
    start_survey_progress,
    save_survey_question_message_id,
    complete_survey_progress,
    process_survey_callback,
)

# Загрузка переменных окружения из backend/.env
load_dotenv(Path(__file__).resolve().parent / ".env")


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Проверка наличия токена
token = os.getenv("BOT_TOKEN")

if not token:
    raise RuntimeError("В backend/.env не найден BOT_TOKEN")


# Создание бота и диспетчера
bot = Bot(token=token)
dp = Dispatcher()


def get_user_profile(max_user_id: int):
    """Находит пользователя MAX и определяет его роли одним запросом."""

    db = SessionLocal()

    try:
        result = db.execute(
            select(
                User,
                Teacher.id.label("teacher_id"),
                Student.id.label("student_id"),
                Student.class_id.label("class_id"),
                Administrator.id.label("admin_id"),
            )
            .outerjoin(Teacher, Teacher.user_id == User.id)
            .outerjoin(Student, Student.user_id == User.id)
            .outerjoin(Administrator, Administrator.user_id == User.id)
            .where(User.sferum_id == str(max_user_id))
        ).first()

        if result is None:
            return None

        user = result[0]
        teacher_id = result.teacher_id
        student_id = result.student_id
        class_id = result.class_id
        admin_id = result.admin_id

        roles = []

        if teacher_id is not None:
            roles.append("teacher")

        if student_id is not None:
            roles.append("student")

        if admin_id is not None:
            roles.append("admin")

        return {
            "user_id": user.id,
            "sferum_id": user.sferum_id,
            "full_name": user.full_name,
            "roles": roles,
            "class_id": class_id,
        }

    finally:
        db.close()


def get_question_options(question_id: int):
    """Получает варианты ответа для вопроса опроса."""

    db = SessionLocal()

    try:
        options = db.scalars(
            select(SurveyInstanceOption)
            .where(SurveyInstanceOption.instance_question_id == question_id)
            .order_by(SurveyInstanceOption.sort_order)
        ).all()

        return [
            {
                "id": option.id,
                "title": option.title,
                "is_exclusive": option.is_exclusive,
            }
            for option in options
        ]

    finally:
        db.close()


def get_selected_options(max_user_id: int, question_id: int):
    """Возвращает ID вариантов, выбранных учеником в черновике."""

    db = SessionLocal()

    try:
        user = db.scalar(select(User).where(User.sferum_id == str(max_user_id)))

        if user is None:
            return []

        student = db.scalar(select(Student).where(Student.user_id == user.id))

        if student is None:
            return []

        response = db.scalar(
            select(SurveyResponse).where(
                SurveyResponse.instance_question_id == question_id,
                SurveyResponse.student_id == student.id,
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


def build_multiple_keyboard(question_id: int, options: list, selected_ids: list):
    """Создаёт клавиатуру для вопроса с несколькими вариантами."""

    buttons = []

    for option in options:
        is_selected = option["id"] in selected_ids
        mark = "☑" if is_selected else "☐"

        buttons.append(
            [
                CallbackButton(
                    text=f"{mark} {option['title']}",
                    payload=f"survey_toggle:{question_id}:{option['id']}",
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


async def send_callback_message(event, text: str):
    """Подтверждает callback и отправляет отдельное сообщение."""
    await event.ack()
    await event.bot.send_message(
        user_id=event.callback.user.user_id,
        text=text,
    )


async def edit_callback_message(event, text: str, keyboard=None):
    """Подтверждает нажатие и редактирует исходное сообщение."""

    if event.message is None or event.message.body is None:
        await event.ack()
        await event.bot.send_message(
            user_id=event.callback.user.user_id,
            text=text,
            attachments=[keyboard] if keyboard is not None else None,
        )
        return

    await event.edit(
        text=text,
        attachments=[keyboard] if keyboard is not None else [],
    )


@dp.message_created(CommandStart())
async def start_handler(event: MessageCreated):
    """Обрабатывает команду /start."""

    sender = event.message.sender

    if sender is None:
        await event.message.answer(
            "Не удалось определить пользователя. Попробуйте ещё раз."
        )
        return

    profile = get_user_profile(sender.user_id)

    if profile is None:
        await event.message.answer(
            "Вы ещё не зарегистрированы в Blue Sphere. "
            "Обратитесь к администратору школы."
        )
        return

    roles = profile["roles"]

    # Учитель
    if "teacher" in roles:
        await event.message.answer(
            "Здравствуйте! Вы учитель.\n"
            "Управление нагрузкой доступно в приложении Blue Sphere."
        )
        return

    # Ученик
    if "student" in roles:
        name = profile["full_name"] or sender.first_name

        survey = get_available_survey(sender.user_id)

        if survey is None:
            await event.message.answer(
                f"Привет, {name}!\n"
                "Сейчас для тебя нет доступных опросов."
            )
            return

        instance_id = survey["instance_id"]

        # Проверяем, не проходил ли ученик этот опрос ранее.
        progress = get_survey_progress(
            sender.user_id,
            instance_id,
        )

        if progress == "completed":
            # Не отправляем повторное сообщение:
            # сообщение об успешном завершении должно остаться неизменным.
            return

        if progress == "closed":
            await event.message.answer(
                "Время прохождения этого опроса завершилось."
            )
            return

        if progress == "in_progress":
            # Ученик уже начал опрос.
            # Повторный /start не должен создавать дубликат вопроса.
            return

        # Начинаем прохождение только при первом запуске.
        progress = start_survey_progress(
            sender.user_id,
            instance_id,
        )

        if progress is None:
            logger.error(
                "Не удалось начать опрос: отсутствует запись уведомления. "
                "MAX user_id: %s, instance_id: %s",
                sender.user_id,
                instance_id,
            )

            await event.message.answer(
                "Не удалось начать опрос. Попробуйте позже."
            )
            return

        if progress == "completed":
            return

        if progress == "closed":
            await event.message.answer(
                "Время прохождения этого опроса завершилось."
            )
            return

        question = get_next_question(
            sender.user_id,
            instance_id,
        )

        if question is None:
            complete_survey_progress(
                sender.user_id,
                instance_id,
            )
            await event.message.answer(
                f"Привет, {name}!\n"
                "Ты уже ответил на все вопросы этого опроса. Спасибо!"
            )
            return

        options = get_question_options(question["question_id"])

        if question["answer_type"] == "multiple":
            selected_ids = get_selected_options(
                sender.user_id,
                question["question_id"],
            )

            keyboard = build_multiple_keyboard(
                question["question_id"],
                options,
                selected_ids,
            )

        else:
            keyboard = ButtonsPayload(
                buttons=[
                    [
                        CallbackButton(
                            text=option["title"],
                            payload=(
                                f"survey:{question['question_id']}:"
                                f"{option['id']}"
                            ),
                        )
                    ]
                    for option in options
                ]
            ).pack()

        # Отправляем первый вопрос.
        sent_message = await event.message.answer(
            f"Привет, {name}!\n\n{question['bot_text']}",
            attachments=[keyboard],
        )

        # Сохраняем ID сообщения, чтобы впоследствии
        # планировщик мог отредактировать его при закрытии опроса.
        try:
            message_id = sent_message.message.body.mid

            saved = save_survey_question_message_id(
                sender.user_id,
                instance_id,
                str(message_id),
            )

            if not saved:
                logger.error(
                    "Не удалось сохранить ID сообщения с вопросом. "
                    "MAX user_id: %s, instance_id: %s",
                    sender.user_id,
                    instance_id,
                )

        except (AttributeError, TypeError):
            logger.exception(
                "Не удалось получить ID отправленного сообщения MAX. "
                "MAX user_id: %s, instance_id: %s",
                sender.user_id,
                instance_id,
            )

        return

    # Администратор
    if "admin" in roles:
        await event.message.answer(
            "Здравствуйте! Вы администратор Blue Sphere.\n"
            "Управление нагрузкой и классами доступно в приложении Blue Sphere."
        )
        return

    # Пользователь без назначенной роли
    await event.message.answer(
        "Ваш аккаунт найден, но для него не назначена роль. "
        "Обратитесь к администратору."
    )


@dp.message_callback()
async def callback_handler(event: MessageCallback):
    """Обрабатывает ответы ученика на вопросы опроса."""

    payload = event.callback.payload
    max_user_id = event.callback.user.user_id

    # Разбираем callback.
    try:
        parts = payload.split(":")
        action = parts[0]
        question_id = int(parts[1])

        if action in ("survey", "survey_toggle"):
            option_id = int(parts[2])
        else:
            option_id = None

    except (AttributeError, IndexError, ValueError):
        await send_callback_message(
            event,
            "Не удалось обработать ответ. Попробуй ещё раз.",
        )
        return

    if action not in ("survey", "survey_toggle", "survey_done"):
        await send_callback_message(
            event,
            "Неизвестное действие.",
        )
        return

    # Обрабатываем callback в одной сессии и одной транзакции БД.
    result = process_survey_callback(
        max_user_id,
        action,
        question_id,
        option_id,
    )

    status = result["status"]

    # Опрос уже закрыт или недоступен.
    if status == "closed":
        await send_callback_message(
            event,
            "Время прохождения этого опроса завершилось.",
        )
        return

    # Ученик уже отправил ответ на этот вопрос.
    if status == "already_submitted":
        await send_callback_message(
            event,
            "Ты уже ответил на этот вопрос.",
        )
        return

    # Достигнут лимит вариантов.
    if status == "limit_reached":
        await event.ack(
            notification="Можно выбрать не более двух вариантов."
        )
        return

    # Ученик ещё не выбрал необходимое количество вариантов.
    if status == "incomplete":
        await send_callback_message(
            event,
            "Сначала выбери хотя бы один вариант.",
        )
        return

    # Вопрос больше не является текущим.
    if status == "question_unavailable":
        await send_callback_message(
            event,
            "Этот вопрос уже недоступен.",
        )
        return

    # Ошибка сохранения ответа или некорректный callback.
    if status == "invalid":
        if action == "survey_toggle":
            error_message = (
                "Не удалось сохранить выбор. "
                "Возможно, опрос уже закрыт."
            )
        elif action == "survey_done":
            error_message = (
                "Не удалось отправить ответ. "
                "Возможно, опрос уже закрыт."
            )
        else:
            error_message = (
                "Не удалось сохранить ответ. "
                "Возможно, опрос уже закрыт."
            )

        await send_callback_message(event, error_message)
        return

    # Обновляем клавиатуру при выборе нескольких вариантов.
    if status == "saved":
        question = result["question"]

        keyboard = build_multiple_keyboard(
            question_id,
            result["options"],
            result["selected_ids"],
        )

        await edit_callback_message(
            event,
            question["bot_text"],
            keyboard,
        )
        return

    # После успешного сохранения одиночного или множественного ответа
    # получаем данные следующего вопроса из результата обработки.
    if status != "submitted":
        await send_callback_message(
            event,
            "Не удалось обработать ответ. Попробуй ещё раз.",
        )
        return

    message = result["message"]
    question = result["question"]

    # Если вопросов больше нет — завершаем прохождение.
    if question is None:
        if not result["completed"]:
            logger.error(
                "Не удалось зафиксировать завершение опроса. "
                "MAX user_id: %s, instance_id: %s",
                max_user_id,
                result.get("instance_id"),
            )

        await edit_callback_message(
            event,
            f"{message}\nТы ответил на все вопросы. Спасибо!",
        )
        return

    options = result["options"]

    # Формируем клавиатуру для следующего вопроса.
    if question["answer_type"] == "multiple":
        keyboard = build_multiple_keyboard(
            question["question_id"],
            options,
            result["selected_ids"],
        )

    else:
        keyboard = ButtonsPayload(
            buttons=[
                [
                    CallbackButton(
                        text=option["title"],
                        payload=(
                            f"survey:{question['question_id']}:"
                            f"{option['id']}"
                        ),
                    )
                ]
                for option in options
            ]
        ).pack()

    # Переходим к следующему вопросу, редактируя то же сообщение.
    await edit_callback_message(
        event,
        f"{message}\n\n{question['bot_text']}",
        keyboard,
    )


async def main():
    logger.info("Запускаем тестового бота Blue Sphere")

    # Прогреваем подключение к PostgreSQL перед запуском бота.
    logger.info("Проверяем подключение к PostgreSQL...")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    logger.info("Подключение к PostgreSQL успешно установлено.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
