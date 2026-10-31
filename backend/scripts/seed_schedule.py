from datetime import date, timedelta
from calendar import monthrange

from sqlalchemy import select

from database import SessionLocal
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
ACADEMIC_YEAR_NAME = "2026–2027"

today = date.today()
first_day = today.replace(day=1)
last_day = today.replace(day=monthrange(today.year, today.month)[1])

LESSON_DATES = [
    first_day + timedelta(days=offset)
    for offset in range((last_day - first_day).days + 1)
    if (first_day + timedelta(days=offset)).weekday() < 5
]


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

    return [
        (subject, number)
        for number, subject in enumerate(subjects, 1)
    ]


def get_or_create_teacher(session, school, sferum_id, full_name):
    user = session.scalar(
        select(User).where(User.sferum_id == sferum_id)
    )

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


def seed_schedule():
    with SessionLocal() as session:
        school = session.scalar(
            select(School).where(
                School.short_name == SCHOOL_SHORT_NAME
            )
        )

        if school is None:
            raise RuntimeError(
                "Сначала запусти seed.py: школа не найдена."
            )

        academic_year = session.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.name == ACADEMIC_YEAR_NAME,
            )
        )

        if academic_year is None:
            raise RuntimeError(
                "Сначала запусти seed.py: учебный год не найден."
            )

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
            raise RuntimeError(
                "Классы не найдены. Сначала запусти seed.py."
            )

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
            name: get_or_create_subject(session, school, name)
            for name in SUBJECT_NAMES
        }

        created_count = 0
        existing_count = 0

        for lesson_date in LESSON_DATES:
            for school_class in classes:
                plan = make_lesson_plan(
                    school_class.code,
                    lesson_date,
                )

                for subject_name, lesson_number in plan:
                    subject = subjects[subject_name]

                    if subject_name == "Английский язык":
                        subgroups = (1, 2)
                    else:
                        subgroups = (0,)

                    for subgroup in subgroups:
                        if subject_name == "Английский язык":
                            teacher_key = (
                                "demo-teacher-5"
                                if subgroup == 1
                                else "demo-teacher-6"
                            )
                            room = ENGLISH_ROOMS[subgroup]
                            lesson_type = "Обычный урок"
                        else:
                            teacher_key, room, lesson_type = (
                                LESSON_DETAILS[subject_name]
                            )

                        assignment = get_or_create_assignment(
                            session,
                            teachers[teacher_key],
                            school_class,
                            subject,
                            academic_year,
                            subgroup,
                        )

                        created = get_or_create_lesson(
                            session,
                            assignment,
                            lesson_date,
                            lesson_number,
                            room,
                            lesson_type,
                        )

                        if created:
                            created_count += 1
                        else:
                            existing_count += 1

        session.commit()

        print("Демонстрационное расписание подготовлено.")
        print(f"Школа: {school.short_name}")
        print(f"Учебный год: {academic_year.name}")
        print(f"Период: {LESSON_DATES[0]} — {LESSON_DATES[-1]}")
        print(f"Классов обработано: {len(classes)}")
        print(f"Новых записей расписания: {created_count}")
        print(f"Уже существующих записей пропущено: {existing_count}")


if __name__ == "__main__":
    seed_schedule()
