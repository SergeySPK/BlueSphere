import sys
from pathlib import Path
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

# Добавляем папку backend в пути поиска модулей Python.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from user_mode import get_or_create_user, validate_database_mode
from database import engine
from models import (
    AcademicYear,
    Class,
    School,
    Student,
    StudentEnrollment,
)


def main():
    validate_database_mode(engine)
    print("=== Добавление ученика BlueSphere ===")

    # 1. Запрашиваем данные у пользователя
    sferum_id = input("MAX user_id ученика: ").strip()
    full_name = input("ФИО ученика: ").strip()
    school_id_input = input("ID школы (например, 1): ").strip()
    year_name = (
        input("Учебный год (например, 2026-2027): ")
        .strip()
        .replace("–", "-")
        .replace("—", "-")
    )
    class_code = input("Код класса (например, 9b): ").strip()

    # Запрос даты зачисления (если оставить пустым, ставим 1 сентября 2026)
    date_input = input("Дата зачисления (ГГГГ-ММ-ДД, Enter для 2026-09-01): ").strip()

    if not all([sferum_id, full_name, school_id_input, year_name, class_code]):
        print("Ошибка: все основные поля (кроме даты) обязательны.")
        return

    try:
        school_id = int(school_id_input)
    except ValueError:
        print("Ошибка: ID школы должен быть целым числом.")
        return

    try:
        enrollment_start_date = (
            date.fromisoformat(date_input) if date_input else date(2026, 9, 1)
        )
    except ValueError:
        print("Ошибка: неверный формат даты. Используйте ГГГГ-ММ-ДД.")
        return

    # 2. Работа с базой данных (аналогично add_admin.py)
    with Session(engine) as db:
        try:
            # Проверяем школу
            school = db.get(School, school_id)
            if school is None:
                print(f"Ошибка: школа с ID {school_id} не найдена.")
                return

            # Проверяем учебный год
            academic_year = db.scalar(
                select(AcademicYear).where(
                    AcademicYear.school_id == school.id,
                    AcademicYear.name == year_name,
                )
            )
            if academic_year is None:
                print(f"Ошибка: учебный год «{year_name}» не найден.")
                return

            # Проверяем класс
            school_class = db.scalar(
                select(Class).where(
                    Class.school_id == school.id,
                    Class.academic_year_id == academic_year.id,
                    Class.code == class_code,
                )
            )
            if school_class is None:
                print(f"Ошибка: класс {class_code} не найден в году {year_name}.")
                return

            # Находим или создаем пользователя
            user, created = get_or_create_user(
                db,
                sferum_id,
                full_name,
            )

            if created:
                print(f"Создан пользователь: {full_name}")
            else:
                print(f"Пользователь уже существует: {user.full_name} (ID={user.id})")

            # Находим или создаем роль ученика
            student = db.scalar(select(Student).where(Student.user_id == user.id))

            if student is None:
                student = Student(user_id=user.id, class_id=school_class.id)
                db.add(student)
                db.flush()
                print(f"Добавлена роль ученика, класс {school_class.code}.")
            elif student.class_id != school_class.id:
                print(
                    f"ОШИБКА: Пользователь уже ученик другого класса (ID={student.class_id})."
                )
                db.rollback()
                return
            else:
                print(f"Роль ученика уже существует, класс: {school_class.code}.")

            # Проверяем запись об обучении (StudentEnrollment)
            active_enrollment = db.scalar(
                select(StudentEnrollment).where(
                    StudentEnrollment.student_id == student.id,
                    StudentEnrollment.start_date <= enrollment_start_date,
                    (
                        StudentEnrollment.end_date.is_(None)
                        | (StudentEnrollment.end_date >= enrollment_start_date)
                    ),
                )
            )

            if active_enrollment is None:
                enrollment = StudentEnrollment(
                    student_id=student.id,
                    class_id=school_class.id,
                    start_date=enrollment_start_date,
                )
                db.add(enrollment)
                print(f"Создана запись об обучении с {enrollment_start_date}.")
            elif active_enrollment.class_id != school_class.id:
                print("ОШИБКА: Активная запись об обучении указывает на другой класс.")
                db.rollback()
                return
            else:
                print("Активная запись об обучении уже существует.")

            db.commit()

            print("\nУченик успешно добавлен/обновлен.")
            print(f"MAX user_id: {user.sferum_id}")
            print(f"Школа: {school.short_name}")
            print(f"Учебный год: {academic_year.name}")
            print(f"Класс: {school_class.code}")
            print("Роль: student")

        except Exception as e:
            db.rollback()
            print(f"\nПроизошла ошибка при работе с БД: {e}")


if __name__ == "__main__":
    main()
