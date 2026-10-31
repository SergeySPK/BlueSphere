from sqlalchemy import select
from sqlalchemy.orm import Session

from database import engine
from models import User, Administrator, School


def main():
    print("=== Добавление администратора BlueSphere ===")

    sferum_id = input("MAX user_id разработчика: ").strip()
    full_name = input("Имя разработчика: ").strip()
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
                print(f"Создан пользователь: {full_name}")
            else:
                print(
                    f"Пользователь уже существует: "
                    f"{user.full_name} (ID={user.id})"
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
