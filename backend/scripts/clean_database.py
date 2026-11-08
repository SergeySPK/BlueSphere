import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

import models  # noqa: F401
from database import Base, engine
from user_mode import is_demo_mode


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Полная очистка данных приложения "
            "с сохранением схемы и миграций."
        )
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Разрешить интерактивное подтверждение очистки.",
    )
    return parser.parse_args()


def clean_database():
    if is_demo_mode():
        raise RuntimeError(
            "Очистка разрешена только при DEMO_MODE=false."
        )

    database_name = engine.url.database
    if not database_name:
        raise RuntimeError(
            "Не удалось определить имя подключённой базы данных."
        )

    print("ВНИМАНИЕ: будут удалены все данные приложения.")
    print(f"Подключённая база: {database_name}")
    print("Схема таблиц и alembic_version сохранятся.")

    confirmation = input(
        f"Для продолжения введи точное имя базы "
        f"{database_name}: "
    ).strip()

    if confirmation != database_name:
        print("Подтверждение не совпало. Очистка отменена.")
        return 1

    preparer = engine.dialect.identifier_preparer

    # Base.metadata содержит таблицы приложения.
    # alembic_version в Base.metadata не входит.
    table_names = [
        preparer.quote(table.name)
        for table in Base.metadata.sorted_tables
    ]

    if not table_names:
        print("В metadata нет таблиц для очистки.")
        return 0

    statement = (
        "TRUNCATE TABLE "
        + ", ".join(table_names)
        + " RESTART IDENTITY CASCADE"
    )

    with engine.begin() as connection:
        connection.execute(text(statement))

    print(f"Очищено таблиц: {len(table_names)}")
    print("Версия Alembic и схема БД сохранены.")
    return 0


if __name__ == "__main__":
    args = parse_args()

    if not args.confirm:
        print("Для запуска укажи флаг --confirm.")
        raise SystemExit(2)

    raise SystemExit(clean_database())
