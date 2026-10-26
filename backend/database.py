import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Загружаем настройки из backend/.env независимо от текущей папки терминала.
ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_FILE)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        f"Переменная DATABASE_URL не найдена. Проверь файл: {ENV_FILE}"
    )

# Подключение к PostgreSQL.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Фабрика сессий для выполнения запросов к БД.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# Общий базовый класс будущих моделей таблиц.
class Base(DeclarativeBase):
    pass
