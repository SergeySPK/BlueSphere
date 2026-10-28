
from pathlib import Path
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl

from sqlalchemy import select

from database import SessionLocal
from models import User, Teacher, Student, Administrator

import asyncio
import logging
import os

import httpx
from dotenv import load_dotenv
from maxapi import Bot, Dispatcher
from maxapi.types import CommandStart, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types.attachments.buttons import LinkButton

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

token = os.getenv("BOT_TOKEN")
if not token:
    raise RuntimeError("В backend/.env не найден BOT_TOKEN")

API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip()
BOT_INTERNAL_SECRET = os.getenv("BOT_INTERNAL_SECRET", "")
FRONTEND_ENABLED = os.getenv("FRONTEND_ENABLED", "false").strip().lower() == "true"

bot = Bot(token=token)
dp = Dispatcher()


def get_user_profile(max_user_id: int):
    """Находит пользователя MAX в БД и определяет его роли."""
    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(User.sferum_id == str(max_user_id))
        )

        if user is None:
            return None

        roles = []

        teacher = db.scalar(
            select(Teacher).where(Teacher.user_id == user.id)
        )
        if teacher is not None:
            roles.append("teacher")

        student = db.scalar(
            select(Student).where(Student.user_id == user.id)
        )
        if student is not None:
            roles.append("student")

        administrator = db.scalar(
            select(Administrator).where(
                Administrator.user_id == user.id
            )
        )
        if administrator is not None:
            roles.append("admin")

        return {
            "user_id": user.id,
            "sferum_id": user.sferum_id,
            "full_name": user.full_name,
            "roles": roles,
            "class_id": student.class_id if student is not None else None,
        }

    finally:
        db.close()


def build_frontend_ticket_url(frontend_url: str, ticket: str) -> str | None:
    """Добавляет билет к адресу приложения, если URL выглядит настроенным."""
    parsed = urlparse(frontend_url)

    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.hostname in {"example.com", "localhost"}
    ):
        return None

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["ticket"] = ticket

    return urlunparse(parsed._replace(query=urlencode(query)))


async def create_auth_ticket(max_user_id: int) -> str | None:
    """Запрашивает у backend одноразовый билет авторизации."""
    if not API_BASE_URL or not BOT_INTERNAL_SECRET:
        logger.error("Не настроены API_BASE_URL или BOT_INTERNAL_SECRET")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/auth/ticket",
                headers={"X-Bot-Secret": BOT_INTERNAL_SECRET},
                json={"max_user_id": str(max_user_id)},
            )

        if response.status_code != 200:
            logger.error(
                "Backend не выдал билет авторизации: HTTP %s",
                response.status_code,
            )
            return None

        data = response.json()
        ticket = data.get("ticket")

        if not isinstance(ticket, str) or not ticket:
            logger.error("Backend вернул некорректный билет авторизации")
            return None

        return ticket

    except (httpx.HTTPError, ValueError):
        logger.exception("Ошибка при запросе билета авторизации")
        return None


async def send_app_button(event: MessageCreated, max_user_id: int):
    """Выдаёт билет и отправляет кнопку перехода в приложение."""
    if not FRONTEND_ENABLED:
        await event.message.answer(
            "Ваш аккаунт подтверждён, но сайт Blue Sphere "
            "ещё не опубликовано. Попробуйте позже."
        )
        return
    frontend_url = build_frontend_ticket_url(FRONTEND_URL, "placeholder")

    if frontend_url is None:
        await event.message.answer(
            "Ваш аккаунт подтверждён, но сайт Blue Sphere ещё не настроен. "
            "Попробуйте позже."
        )
        return

    ticket = await create_auth_ticket(max_user_id)

    if ticket is None:
        await event.message.answer(
            "Не удалось подготовить вход в Blue Sphere. "
            "Попробуйте позже."
        )
        return

    app_url = build_frontend_ticket_url(FRONTEND_URL, ticket)
    if app_url is None:
        await event.message.answer(
            "Ссылка на приложение настроена некорректно. "
            "Обратитесь к администратору."
        )
        return

    keyboard = InlineKeyboardBuilder().add(
        LinkButton(text="Открыть Blue Sphere", url=app_url)
    ).as_markup()

    await event.message.answer(
        "Ваш аккаунт подтверждён. Нажмите кнопку, чтобы открыть Blue Sphere.",
        attachments=[keyboard],
    )


@dp.message_created(CommandStart())
async def start_handler(event: MessageCreated):
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

    if not roles:
        await event.message.answer(
            "Ваш аккаунт найден, но для него не назначена роль. "
            "Обратитесь к администратору."
        )
        return

    await send_app_button(event, sender.user_id)


async def main():
    logger.info("Запускаем тестового бота Blue Sphere")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
