import sys
from pathlib import Path

# Добавляем папку backend в пути поиска модулей Python.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import argparse
from datetime import date, timedelta

from sqlalchemy import select

from database import SessionLocal, engine
from scripts.user_mode import validate_database_mode
from models import (
    AcademicYear,
    Class,
    Schedule,
    School,
    Subject,
    Teacher,
    TeachingAssignment,
    User,
)

SCHOOL_SHORT_NAME = "Школа № 1"
ACADEMIC_YEAR_NAME = "2026-2027"

TEACHERS_DATA = [
    ("demo-teacher-1", "Сидоров Сергей Сергеевич"),
    ("demo-teacher-2", "Петров Павел Петрович"),
    ("demo-teacher-3", "Кузнецова Ольга Константиновна"),
    ("demo-teacher-4", "Иванов Иван Иванович"),
    ("demo-teacher-5", "Смирнова Анна Андреевна"),
    ("demo-teacher-6", "Батонова Ирина Александровна"),
]

SUBJECT_NAMES = [
    "Физкультура",
    "История",
    "Русский язык",
    "Математика",
    "Английский язык",
]

LESSON_DETAILS = {
    "Физкультура": ("demo-teacher-1", "Спортзал", "Сдача нормативов"),
    "История": ("demo-teacher-2", "204", "Обычный урок"),
    "Русский язык": (
        "demo-teacher-3",
        "301",
        "Входная контрольная работа",
    ),
    "Математика": ("demo-teacher-4", "302", "Проверочная работа"),
}

ENGLISH_ROOMS = {1: "108", 2: "109"}

BASE_SUBJECTS = [
    "Русский язык",
    "Математика",
    "История",
    "Английский язык",
    "Физкультура",
]

# Сохраняем последовательность уроков за 9 сентября.
EXISTING_PLANS = {
    "5a": [
        ("Физкультура", 1),
        ("История", 2),
        ("Русский язык", 3),
        ("Математика", 4),
        ("Английский язык", 5),
    ],
    "5b": [
        ("История", 1),
        ("Русский язык", 2),
        ("Математика", 3),
        ("Английский язык", 4),
        ("Физкультура", 5),
    ],
    "5v": [
        ("Русский язык", 1),
        ("Математика", 2),
        ("Английский язык", 3),
        ("Физкультура", 4),
        ("История", 5),
    ],
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Заполнение расписания за указанный период."
    )

    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        required=True,
        help="Начальная дата в формате YYYY-MM-DD",
    )

    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        required=True,
        help="Конечная дата в формате YYYY-MM-DD",
    )

    args = parser.parse_args()

    if args.start_date > args.end_date:
        parser.error("--start-date не может быть позже --end-date")

    return args


def get_lesson_dates(start_date, end_date):
    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
        if (start_date + timedelta(days=offset)).weekday() < 5
    ]


def make_lesson_plan(class_code, lesson_date):
    if lesson_date == date(2026, 9, 9) and class_code in EXISTING_PLANS:
        return EXISTING_PLANS[class_code]

    grade = int("".join(char for char in class_code if char.isdigit()))
    parallel = class_code[-1]

    parallel_index = {
        "a": 0,
        "b": 1,
        "v": 2,
        "g": 3,
    }.get(parallel, 0)

    # Меняем порядок предметов между классами и датами.
    shift = (grade + parallel_index + lesson_date.day) % len(BASE_SUBJECTS)
    subjects = BASE_SUBJECTS[shift:] + BASE_SUBJECTS[:shift]

    return [(subject, number) for number, subject in enumerate(subjects, 1)]


def get_or_create_teacher(session, school, sferum_id, full_name):
    user = session.scalar(select(User).where(User.sferum_id == sferum_id))

    if user is None:
        user = User(
            sferum_id=sferum_id,
            full_name=full_name,
        )
        session.add(user)
        session.flush()

    teacher = session.scalar(
        select(Teacher).where(
            Teacher.user_id == user.id,
            Teacher.school_id == school.id,
        )
    )

    if teacher is None:
        teacher = Teacher(
            user_id=user.id,
            school_id=school.id,
        )
        session.add(teacher)
        session.flush()

    return teacher


def get_or_create_subject(session, school, name):
    subject = session.scalar(
        select(Subject).where(
            Subject.school_id == school.id,
            Subject.name == name,
        )
    )

    if subject is None:
        subject = Subject(
            school_id=school.id,
            name=name,
        )
        session.add(subject)
        session.flush()

    return subject


def get_or_create_assignment(
    session,
    teacher,
    school_class,
    subject,
    academic_year,
    subgroup,
):
    assignment = session.scalar(
        select(TeachingAssignment).where(
            TeachingAssignment.school_id == school_class.school_id,
            TeachingAssignment.teacher_id == teacher.id,
            TeachingAssignment.class_id == school_class.id,
            TeachingAssignment.subject_id == subject.id,
            TeachingAssignment.academic_year_id == academic_year.id,
            TeachingAssignment.subgroup == subgroup,
        )
    )

    if assignment is None:
        assignment = TeachingAssignment(
            school_id=school_class.school_id,
            teacher_id=teacher.id,
            class_id=school_class.id,
            subject_id=subject.id,
            academic_year_id=academic_year.id,
            subgroup=subgroup,
        )
        session.add(assignment)
        session.flush()

    return assignment


def get_or_create_lesson(
    session,
    assignment,
    lesson_date,
    lesson_number,
    room,
    lesson_type,
):
    lesson = session.scalar(
        select(Schedule).where(
            Schedule.assignment_id == assignment.id,
            Schedule.date == lesson_date,
            Schedule.lesson_number == lesson_number,
        )
    )

    if lesson is None:
        lesson = Schedule(
            assignment_id=assignment.id,
            date=lesson_date,
            lesson_number=lesson_number,
            room=room,
            lesson_type=lesson_type,
        )
        session.add(lesson)
        session.flush()
        return True

    # Существующую запись не перезаписываем.
    return False


def seed_schedule(start_date, end_date):
    validate_database_mode(engine)

    lesson_dates = get_lesson_dates(start_date, end_date)

    if not lesson_dates:
        raise ValueError("В указанном диапазоне нет будних дней.")

    with SessionLocal() as session:
        school = session.scalar(
            select(School).where(School.short_name == SCHOOL_SHORT_NAME)
        )

        if school is None:
            raise RuntimeError("Сначала запусти seed.py: школа не найдена.")

        academic_year = session.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.name == ACADEMIC_YEAR_NAME,
            )
        )

        if academic_year is None:
            raise RuntimeError("Сначала запусти seed.py: учебный год не найден.")

        if not academic_year.is_active:
            raise RuntimeError(
                f"Учебный год {academic_year.name} не является активным."
            )

        classes = session.scalars(
            select(Class)
            .where(
                Class.school_id == school.id,
                Class.academic_year_id == academic_year.id,
            )
            .order_by(Class.code)
        ).all()

        if not classes:
            raise RuntimeError("Классы не найдены. Сначала запусти seed.py.")

        # Создаём или получаем преподавателей и предметы.
        teachers = {
            sferum_id: get_or_create_teacher(
                session,
                school,
                sferum_id,
                full_name,
            )
            for sferum_id, full_name in TEACHERS_DATA
        }

        subjects = {
            name: get_or_create_subject(session, school, name) for name in SUBJECT_NAMES
        }

        # Создаём назначения заранее: по одному на класс,
        # предмет и подгруппу, а не для каждого отдельного урока.
        assignments = {}

        for school_class in classes:
            for subject_name in BASE_SUBJECTS:
                subject = subjects[subject_name]

                subgroups = (1, 2) if subject_name == "Английский язык" else (0,)

                for subgroup in subgroups:
                    if subject_name == "Английский язык":
                        teacher_key = (
                            "demo-teacher-5" if subgroup == 1 else "demo-teacher-6"
                        )
                    else:
                        teacher_key = LESSON_DETAILS[subject_name][0]

                    assignment = get_or_create_assignment(
                        session,
                        teachers[teacher_key],
                        school_class,
                        subject,
                        academic_year,
                        subgroup,
                    )

                    assignments[(school_class.id, subject_name, subgroup)] = assignment

        # Загружаем существующие уроки одним запросом.
        assignment_ids = [assignment.id for assignment in assignments.values()]

        existing_lessons = session.scalars(
            select(Schedule).where(
                Schedule.assignment_id.in_(assignment_ids),
                Schedule.date >= start_date,
                Schedule.date <= end_date,
            )
        ).all()

        existing_keys = {
            (
                lesson.assignment_id,
                lesson.date,
                lesson.lesson_number,
            )
            for lesson in existing_lessons
        }

        # Формируем новые уроки в памяти.
        new_lessons = []
        existing_count = 0

        for lesson_date in lesson_dates:
            for school_class in classes:
                plan = make_lesson_plan(
                    school_class.code,
                    lesson_date,
                )

                for subject_name, lesson_number in plan:
                    subgroups = (1, 2) if subject_name == "Английский язык" else (0,)

                    for subgroup in subgroups:
                        assignment = assignments[
                            (school_class.id, subject_name, subgroup)
                        ]

                        key = (
                            assignment.id,
                            lesson_date,
                            lesson_number,
                        )

                        if key in existing_keys:
                            existing_count += 1
                            continue

                        if subject_name == "Английский язык":
                            room = ENGLISH_ROOMS[subgroup]
                            lesson_type = "Обычный урок"
                        else:
                            _, room, lesson_type = LESSON_DETAILS[subject_name]

                        new_lessons.append(
                            Schedule(
                                assignment_id=assignment.id,
                                date=lesson_date,
                                lesson_number=lesson_number,
                                room=room,
                                lesson_type=lesson_type,
                            )
                        )

                        existing_keys.add(key)

        # Сохраняем все новые уроки одним пакетом.
        session.add_all(new_lessons)
        session.commit()

        print("Демонстрационное расписание подготовлено.")
        print(f"Школа: {school.short_name}")
        print(f"Учебный год: {academic_year.name}")
        print(f"Запрошенный период: {start_date} — {end_date}")
        print(f"Будних дней: {len(lesson_dates)}")
        print(f"Классов обработано: {len(classes)}")
        print(f"Новых записей расписания: {len(new_lessons)}")
        print(f"Уже существующих записей пропущено: {existing_count}")


if __name__ == "__main__":
    args = parse_args()
    seed_schedule(args.start_date, args.end_date)
