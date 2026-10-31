from datetime import date

from sqlalchemy import func, select

from database import SessionLocal
from models import AcademicYear, Class, School


GRADES = range(1, 12)

PARALLELS = {
    "a": "А",
    "b": "Б",
    "v": "В",
    "g": "Г",
}

SCHOOL_SHORT_NAME = "Школа № 1"
ACADEMIC_YEAR_NAME = "2026–2027"


def seed_database():
    with SessionLocal() as session:
        # Находим школу или создаём её.
        school = session.scalar(
            select(School).where(
                School.short_name == SCHOOL_SHORT_NAME
            )
        )

        if school is None:
            school = School(
                region="Тестовый регион",
                city="Тестовый город",
                address="Тестовый адрес",
                short_name=SCHOOL_SHORT_NAME,
                full_name="Средняя общеобразовательная школа № 1",
                timezone="Asia/Yekaterinburg",
            )
            session.add(school)
            session.flush()

        # Находим нужный учебный год.
        academic_year = session.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.name == ACADEMIC_YEAR_NAME,
            )
        )

        if academic_year is None:
            # Проверяем, есть ли у школы другой активный год.
            active_year = session.scalar(
                select(AcademicYear.id).where(
                    AcademicYear.school_id == school.id,
                    AcademicYear.is_active.is_(True),
                )
            )

            academic_year = AcademicYear(
                school_id=school.id,
                name=ACADEMIC_YEAR_NAME,
                start_date=date(2026, 9, 1),
                end_date=date(2027, 5, 31),
                is_active=active_year is None,
            )
            session.add(academic_year)
            session.flush()

        created_count = 0

        # Создаём классы, если их ещё нет.
        for grade in GRADES:
            for parallel_code, parallel_name in PARALLELS.items():
                class_code = f"{grade}{parallel_code}"
                class_name = f"{grade}{parallel_name}"

                existing_class = session.scalar(
                    select(Class).where(
                        Class.school_id == school.id,
                        Class.academic_year_id == academic_year.id,
                        Class.code == class_code,
                    )
                )

                if existing_class is None:
                    session.add(
                        Class(
                            school_id=school.id,
                            academic_year_id=academic_year.id,
                            code=class_code,
                            name=class_name,
                        )
                    )
                    created_count += 1

        session.flush()

        # Считаем классы именно этой школы и этого учебного года.
        total_classes = session.scalar(
            select(func.count(Class.id)).where(
                Class.school_id == school.id,
                Class.academic_year_id == academic_year.id,
            )
        )

        session.commit()

        print("Демонстрационные данные подготовлены.")
        print(f"Школа: {school.short_name} (ID: {school.id})")
        print(
            f"Учебный год: {academic_year.name} "
            f"(ID: {academic_year.id})"
        )
        print(
            "Статус учебного года: "
            f"{'активный' if academic_year.is_active else 'неактивный'}"
        )
        print(f"Новых классов добавлено: {created_count}")
        print(f"Всего классов в учебном году: {total_classes}")
        print("Ожидаемое количество классов: 44")


if __name__ == "__main__":
    seed_database()
