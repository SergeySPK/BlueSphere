from datetime import date

from sqlalchemy import select

from database import SessionLocal
from models import (
    AcademicYear,
    Class,
    School,
    Student,
    StudentEnrollment,
    User,
)


SCHOOL_SHORT_NAME = "Школа № 1"
ACADEMIC_YEAR_NAME = "2026–2027"

MAX_USER_ID = "109083347"
TEST_NAME = "Шаманиди Сергей"
TEST_CLASS_CODE = "9b"

ENROLLMENT_START_DATE = date(2026, 9, 1)


def main():
    with SessionLocal() as db:
        try:
            # Находим школу.
            school = db.scalar(
                select(School).where(
                    School.short_name == SCHOOL_SHORT_NAME
                )
            )

            if school is None:
                raise RuntimeError(
                    f"Школа «{SCHOOL_SHORT_NAME}» не найдена."
                )

            # Находим учебный год.
            academic_year = db.scalar(
                select(AcademicYear).where(
                    AcademicYear.school_id == school.id,
                    AcademicYear.name == ACADEMIC_YEAR_NAME,
                )
            )

            if academic_year is None:
                raise RuntimeError(
                    f"Учебный год «{ACADEMIC_YEAR_NAME}» не найден."
                )

            # Находим класс по публичному коду, а не по первичному ключу.
            school_class = db.scalar(
                select(Class).where(
                    Class.school_id == school.id,
                    Class.academic_year_id == academic_year.id,
                    Class.code == TEST_CLASS_CODE,
                )
            )

            if school_class is None:
                raise RuntimeError(
                    f"Класс {TEST_CLASS_CODE} "
                    f"не найден в учебном году {ACADEMIC_YEAR_NAME}."
                )

            # Находим пользователя MAX или создаём его.
            user = db.scalar(
                select(User).where(
                    User.sferum_id == MAX_USER_ID
                )
            )

            if user is None:
                user = User(
                    sferum_id=MAX_USER_ID,
                    full_name=TEST_NAME,
                )
                db.add(user)
                db.flush()
                print("Создан тестовый пользователь.")
            else:
                print(
                    f"Пользователь уже существует: "
                    f"{user.full_name} (ID={user.id})."
                )

            # Находим роль ученика.
            student = db.scalar(
                select(Student).where(
                    Student.user_id == user.id
                )
            )

            if student is None:
                student = Student(
                    user_id=user.id,
                    class_id=school_class.id,
                )
                db.add(student)
                db.flush()

                print(
                    f"Добавлена роль ученика, "
                    f"класс {school_class.code}."
                )
            elif student.class_id != school_class.id:
                raise RuntimeError(
                    "У пользователя уже есть роль ученика "
                    f"в другом классе (ID={student.class_id}). "
                    "Автоматический перевод не выполняется."
                )
            else:
                print(
                    f"Роль ученика уже существует, "
                    f"класс: {school_class.code}."
                )

            # Проверяем текущую запись об обучении.
            active_enrollment = db.scalar(
                select(StudentEnrollment).where(
                    StudentEnrollment.student_id == student.id,
                    StudentEnrollment.end_date.is_(None),
                )
            )

            if active_enrollment is None:
                enrollment = StudentEnrollment(
                    student_id=student.id,
                    class_id=school_class.id,
                    start_date=ENROLLMENT_START_DATE,
                )
                db.add(enrollment)
                print(
                    "Создана запись об обучении "
                    f"с {ENROLLMENT_START_DATE}."
                )

            elif active_enrollment.class_id != school_class.id:
                raise RuntimeError(
                    "Активная запись StudentEnrollment "
                    "указывает на другой класс. "
                    "Автоматическое изменение истории запрещено."
                )
            else:
                print(
                    "Активная запись об обучении уже существует."
                )

            db.commit()

            print("\nТестовый ученик подготовлен.")
            print(f"Школа: {school.short_name}")
            print(f"Учебный год: {academic_year.name}")
            print(f"Класс: {school_class.code}")
            print(f"MAX user_id: {user.sferum_id}")
            print("Можно проверять /start в MAX.")

        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
