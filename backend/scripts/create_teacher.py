import sys
from pathlib import Path

# Добавляем папку backend в пути поиска модулей Python.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.orm import Session

from user_mode import get_or_create_user, validate_database_mode
from database import engine
from models import Teacher, School


def main():
    validate_database_mode(engine)
    print("=== Добавление учителя BlueSphere ===")

    sferum_id = input("MAX user_id учителя: ").strip()
    full_name = input("ФИО учителя: ").strip()
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
                print(f"Пользователь уже существует: {user.full_name} (ID={user.id})")

            teacher = db.scalar(
                select(Teacher).where(
                    Teacher.user_id == user.id,
                    Teacher.school_id == school_id,
                )
            )

            if teacher is not None:
                print(
                    f"Пользователь {user.full_name} "
                    f"уже является учителем школы {school_id}."
                )
                db.rollback()
                return

            teacher = Teacher(
                user_id=user.id,
                school_id=school_id,
            )

            db.add(teacher)
            db.commit()

            print("\nУчитель успешно добавлен.")
            print(f"ФИО: {user.full_name}")
            print(f"ID пользователя в БД: {user.id}")
            print(f"ID учителя: {teacher.id}")
            print(f"Школа: {school.short_name or school.full_name}")

        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
