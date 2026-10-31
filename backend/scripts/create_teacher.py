from sqlalchemy import select
from sqlalchemy.orm import Session

from database import engine
from models import User, Teacher, School


def main():
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

            user = db.scalar(
                select(User).where(User.sferum_id == sferum_id)
            )

            if user is None:
                user = User(
                    sferum_id=sferum_id,
                    full_name=full_name,
                )
                db.add(user)
                db.flush()

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
