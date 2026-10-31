from datetime import date

from sqlalchemy import select

from database import SessionLocal
from models import (
    AcademicYear,
    Class,
    Schedule,
    School,
    Subject,
    TeachingAssignment,
)


SCHOOL_SHORT_NAME = "Школа № 1"
ACADEMIC_YEAR_NAME = "2026–2027"

# Номер урока для каждого предмета в каждом классе.
# Английский язык у обеих подгрупп проходит в одно время.
LESSON_NUMBERS = {
    "5a": {
        "Физкультура": 1,
        "История": 2,
        "Русский язык": 3,
        "Математика": 4,
        "Английский язык": 5,
    },
    "5b": {
        "История": 1,
        "Русский язык": 2,
        "Математика": 3,
        "Английский язык": 4,
        "Физкультура": 5,
    },
    "5v": {
        "Русский язык": 1,
        "Математика": 2,
        "Английский язык": 3,
        "Физкультура": 4,
        "История": 5,
    },
}

ROOMS = {
    "Физкультура": "Спортзал",
    "История": "204",
    "Русский язык": "301",
    "Математика": "302",
    "Английский язык": {
        1: "108",
        2: "109",
    },
}

SCHEDULE_DATE = date(2026, 9, 9)


def main():
    with SessionLocal() as db:
        school = db.scalar(
            select(School).where(
                School.short_name == SCHOOL_SHORT_NAME
            )
        )

        if school is None:
            raise RuntimeError(
                f"Школа «{SCHOOL_SHORT_NAME}» не найдена."
            )

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

        rows = db.execute(
            select(
                Schedule,
                TeachingAssignment,
                Subject,
                Class,
            )
            .join(
                TeachingAssignment,
                Schedule.assignment_id == TeachingAssignment.id,
            )
            .join(
                Subject,
                TeachingAssignment.subject_id == Subject.id,
            )
            .join(
                Class,
                TeachingAssignment.class_id == Class.id,
            )
            .where(
                Schedule.date == SCHEDULE_DATE,
                TeachingAssignment.school_id == school.id,
                TeachingAssignment.academic_year_id == academic_year.id,
                Class.school_id == school.id,
                Class.academic_year_id == academic_year.id,
                Class.code.in_(LESSON_NUMBERS.keys()),
            )
        ).all()

        if not rows:
            print(
                f"На дату {SCHEDULE_DATE} для школы "
                f"«{SCHOOL_SHORT_NAME}» расписание не найдено. "
                "Сначала проверь seed_schedule.py."
            )
            return

        # Сначала проверяем все записи, ничего не изменяя.
        updates = []

        for lesson, assignment, subject, school_class in rows:
            class_code = school_class.code
            subject_name = subject.name

            if class_code not in LESSON_NUMBERS:
                raise ValueError(
                    f"Неизвестный код класса: {class_code}"
                )

            if subject_name not in LESSON_NUMBERS[class_code]:
                raise ValueError(
                    f"Для класса {class_code} не настроен "
                    f"предмет «{subject_name}»."
                )

            if subject_name == "Английский язык":
                if assignment.subgroup not in ROOMS[subject_name]:
                    raise ValueError(
                        f"Неизвестная подгруппа английского языка: "
                        f"{assignment.subgroup}"
                    )

                room = ROOMS[subject_name][assignment.subgroup]
            else:
                room = ROOMS[subject_name]

            lesson_number = LESSON_NUMBERS[class_code][subject_name]

            updates.append(
                (lesson, lesson_number, room)
            )

        # Проверяем, что изменение номеров не нарушит уникальность
        # (assignment_id, date, lesson_number).
        target_numbers = set()

        for lesson, lesson_number, room in updates:
            key = (lesson.assignment_id, lesson_number)

            if key in target_numbers:
                raise ValueError(
                    "Обнаружены две записи с одинаковым "
                    f"номером урока для одного назначения: {key}"
                )

            target_numbers.add(key)

        updated_count = 0

        for lesson, lesson_number, room in updates:
            lesson.lesson_number = lesson_number
            lesson.room = room
            updated_count += 1

        db.commit()

        print("Расписание успешно обновлено.")
        print(f"Школа: {school.short_name}")
        print(f"Учебный год: {academic_year.name}")
        print(f"Дата: {SCHEDULE_DATE}")
        print(f"Обновлено записей: {updated_count}")
        print("ID существующих записей сохранены.")


if __name__ == "__main__":
    main()
