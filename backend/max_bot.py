from pathlib import Path
from sqlalchemy import select

from database import SessionLocal
from models import User, Teacher, Student, Administrator

import asyncio
import logging
import os

from dotenv import load_dotenv
from maxapi import Bot, Dispatcher
from maxapi.types import CommandStart, MessageCreated

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

token = os.getenv("BOT_TOKEN")
if not token:
    raise RuntimeError("В backend/.env не найден BOT_TOKEN")

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

    if "teacher" in roles:
        await event.message.answer(
            "Здравствуйте! Вы учитель.\n"
            "Управление нагрузкой доступно в приложении Blue Sphere."
        )
        return

    if "student" in roles:
        name = profile["full_name"] or sender.first_name
        await event.message.answer(
            f"Привет, {name}!\n"
            "Здесь ты сможешь проходить опросы о школьной нагрузке."
        )
        return

    if "admin" in roles:
        await event.message.answer(
            "Здравствуйте! Вы администратор Blue Sphere."
        )
        return

    await event.message.answer(
        "Ваш аккаунт найден, но для него не назначена роль. "
        "Обратитесь к администратору."
    )


async def main():
    logger.info("Запускаем тестового бота Blue Sphere")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
