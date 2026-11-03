import os
from pathlib import Path

from dotenv import load_dotenv
from maxapi import Bot


def create_max_bot() -> Bot:
    """Создаёт отдельный экземпляр MAX Bot для отправки уведомлений."""

    env_file = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_file)

    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана.")

    return Bot(token=token)


async def send_notification(
    bot: Bot,
    user_id: int,
    text: str,
) -> None:
    """Отправляет личное уведомление пользователю MAX."""

    if user_id <= 0:
        raise ValueError("Некорректный MAX user_id.")

    if not text.strip():
        raise ValueError("Текст уведомления не может быть пустым.")

    result = await bot.send_message(
        user_id=user_id,
        text=text,
    )

    if result is None:
        raise RuntimeError("MAX SDK не вернул объект отправленного сообщения.")
