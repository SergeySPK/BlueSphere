from datetime import date

from sqlalchemy import select

from database import SessionLocal
from models import AcademicYear, Class, School


GRADES = range(1, 12)
PARALLELS = {
    "a": "А",
    "b": "Б",
    "v": "В",
    "g": "Г",
}


def seed_database():
    with SessionLocal() as session:
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

        created_count = 0

        for grade in GRADES:
            for parallel_id, parallel_name in PARALLELS.items():
                class_id = f"{grade}{parallel_id}"
                class_name = f"{grade}{parallel_name}"

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
                    created_count += 1

        session.commit()

        total_classes = session.scalar(
            select(Class.id).where(Class.school_id == school.id)
        )

        print("Демонстрационные данные подготовлены.")
        print(f"Новых классов добавлено: {created_count}")
        print("Ожидаемое количество классов: 44")
        print("Параллели: А, Б, В, Г.")
        print("Учебный год: 2026–2027.")


if __name__ == "__main__":
    seed_database()
