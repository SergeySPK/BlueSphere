from datetime import date

from sqlalchemy import select

from database import SessionLocal
from models import AcademicYear, Class, School


def seed_database():
    with SessionLocal() as session:
        # Если школа уже существует, повторно данные не добавляем.
        school = session.scalar(
            select(School).where(School.short_name == "Школа № 1")
        )

        if school is None:
            school = School(
                region="Тестовый регион",
                city="Тестовый город",
                address="Тестовый адрес",
                short_name="Школа № 1",
                full_name="Средняя общеобразовательная школа № 1",
            )
            session.add(school)
            session.flush()

        # Проверяем, есть ли учебный год у этой школы.
        academic_year = session.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.name == "2026–2027",
            )
        )

        if academic_year is None:
            academic_year = AcademicYear(
                school_id=school.id,
                name="2026–2027",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 5, 31),
            )
            session.add(academic_year)
            session.flush()

        # Добавляем демонстрационные классы, если их ещё нет.
        demo_classes = [
            ("5a", "5А"),
            ("5b", "5Б"),
            ("5v", "5В"),
        ]

        for class_id, class_name in demo_classes:
            existing_class = session.get(Class, class_id)

            if existing_class is None:
                session.add(
                    Class(
                        id=class_id,
                        school_id=school.id,
                        academic_year_id=academic_year.id,
                        name=class_name,
                    )
                )

        session.commit()

        print("Демонстрационные данные добавлены.")
        print("Классы: 5А, 5Б, 5В.")


if __name__ == "__main__":
    seed_database()
