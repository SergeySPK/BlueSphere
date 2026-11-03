import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

# Добавляем папку backend в пути поиска модулей Python.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from user_mode import get_or_create_user, validate_database_mode
from database import engine
from models import Administrator, School


def main():
    validate_database_mode(engine)
    print("=== Добавление администратора BlueSphere ===")

    sferum_id = input("MAX user_id администратора: ").strip()
    full_name = input("ФИО администатора: ").strip()
    school_id_input = input("ID школы (например, 1): ").strip()

    if not sferum_id or not full_name or not school_id_input:
        print("Ошибка: все поля обязательны.")
        return

    try:
        school_id = int(school_id_input)
    except ValueError:
        print("Ошибка: ID школы должен быть целым числом.")
        return
    with Session(engine) as db:
        try:
            school = db.get(School, school_id)

            if school is None:
                print(f"Ошибка: школа с ID {school_id} не найдена.")
                return

            user, created = get_or_create_user(
                db,
                sferum_id,
                full_name,
            )

            if created:
                print(f"Создан пользователь: {full_name}")
            else:
                print(
                    f"Пользователь уже существует: " f"{user.full_name} (ID={user.id})"
                )

            administrator = db.scalar(
                select(Administrator).where(
                    Administrator.user_id == user.id,
                    Administrator.school_id == school_id,
                )
            )

            if administrator is not None:
                print("Этот пользователь уже администратор выбранной школы.")
                db.rollback()
                return

            administrator = Administrator(
                user_id=user.id,
                school_id=school_id,
                position="Фронтенд-разработчик",
            )

            db.add(administrator)
            db.commit()

            print("\nАдминистратор успешно добавлен.")
            print(f"Внутренний ID пользователя: {user.id}")
            print(f"MAX user_id: {user.sferum_id}")
            print(f"Школа: {school_id}")
            print("Роль: admin")

        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
