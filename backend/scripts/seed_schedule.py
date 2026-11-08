import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from database import SessionLocal, engine
from models import (
    AcademicYear,
    AIDailyForecast,
    Class,
    Schedule,
    School,
    Subject,
    Teacher,
    TeacherClassAccess,
    TeachingAssignment,
)
from user_mode import validate_database_mode


SCHOOL_SHORT_NAME = "Школа № 1"
ACADEMIC_YEAR_NAME = "2026-2027"

DEFAULT_START_DATE = date(2026, 11, 1)
DEFAULT_END_DATE = date(2026, 12, 31)

SUBJECT_NAMES = [
    "Русский язык",
    "Литература",
    "Математика",
    "Алгебра",
    "Геометрия",
    "История",
    "Обществознание",
    "Английский язык",
    "Биология",
    "География",
    "Физика",
    "Химия",
]

LESSON_TYPES = [
    "Обычный урок",
    "Практическая работа",
    "Самостоятельная работа",
    "Проверочная работа",
    "Контрольная работа",
    "Лабораторная работа",
    "Подготовка к контрольной работе",
]

ROOMS = [
    "101", "102", "103", "104",
    "201", "202", "203", "204",
    "301", "302", "303", "304",
]


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Некорректная дата: {value!r}. "
            "Используй формат YYYY-MM-DD."
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Создание тестового расписания и Python-прогнозов "
            "за указанный период."
        )
    )

    parser.add_argument(
        "--start-date",
        type=parse_iso_date,
        default=DEFAULT_START_DATE,
        metavar="YYYY-MM-DD",
        help=(
            "Начало периода генерации расписания. "
            "По умолчанию: 2026-11-01."
        ),
    )

    parser.add_argument(
        "--end-date",
        type=parse_iso_date,
        default=DEFAULT_END_DATE,
        metavar="YYYY-MM-DD",
        help=(
            "Конец периода генерации расписания. "
            "По умолчанию: 2026-12-31."
        ),
    )

    args = parser.parse_args()

    if args.start_date > args.end_date:
        parser.error(
            "--start-date не может быть позже --end-date."
        )

    return args


def lesson_dates(start_date, end_date):
    current = start_date
    result = []

    while current <= end_date:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)

    return result


def parse_class_code(code):
    grade_text = "".join(char for char in code if char.isdigit())
    parallel = code[-1].lower()

    parallel_index = {
        "a": 0,
        "b": 1,
        "v": 2,
        "g": 3,
    }

    if not grade_text or parallel not in parallel_index:
        raise ValueError(f"Неизвестный код класса: {code}")

    return int(grade_text), parallel_index[parallel]


def make_plan(school_class, lesson_date):
    grade, parallel_index = parse_class_code(school_class.code)

    # От 3 до 7 уроков в зависимости от класса и даты.
    lesson_count = 3 + (
        grade * 3 + parallel_index * 2 + lesson_date.day
    ) % 5

    shift = (
        grade + parallel_index + lesson_date.timetuple().tm_yday
    ) % len(SUBJECT_NAMES)

    rotated = SUBJECT_NAMES[shift:] + SUBJECT_NAMES[:shift]

    plan = []
    for lesson_number in range(1, lesson_count + 1):
        subject_index = (lesson_number - 1) % len(rotated)
        subject_name = rotated[subject_index]

        type_index = (
            grade * 7
            + parallel_index * 3
            + lesson_date.day
            + lesson_number
        ) % len(LESSON_TYPES)

        lesson_type = LESSON_TYPES[type_index]

        # У части классов контрольные и проверочные распределены
        # по разным дням, чтобы получить неодинаковые профили нагрузки.
        if (
            lesson_number in {2, 3}
            and (grade + parallel_index + lesson_date.day) % 7 == 0
        ):
            lesson_type = "Контрольная работа"

        plan.append((subject_name, lesson_number, lesson_type))

    return plan


def get_or_create_assignment(
    session,
    school_class,
    academic_year,
    subject,
    teacher,
):
    assignment = session.scalar(
        select(TeachingAssignment).where(
            TeachingAssignment.teacher_id == teacher.id,
            TeachingAssignment.class_id == school_class.id,
            TeachingAssignment.subject_id == subject.id,
            TeachingAssignment.academic_year_id == academic_year.id,
            TeachingAssignment.subgroup == 0,
        )
    )

    if assignment is None:
        assignment = TeachingAssignment(
            school_id=school_class.school_id,
            teacher_id=teacher.id,
            class_id=school_class.id,
            subject_id=subject.id,
            academic_year_id=academic_year.id,
            subgroup=0,
        )
        session.add(assignment)
        session.flush()

    access = session.scalar(
        select(TeacherClassAccess.id).where(
            TeacherClassAccess.teacher_id == teacher.id,
            TeacherClassAccess.class_id == school_class.id,
        )
    )

    if access is None:
        session.add(
            TeacherClassAccess(
                teacher_id=teacher.id,
                class_id=school_class.id,
                school_id=school_class.school_id,
                academic_year_id=academic_year.id,
            )
        )

    return assignment


def seed_schedule(start_date, end_date):
    validate_database_mode(engine)

    dates = lesson_dates(start_date, end_date)
    if not dates:
        raise ValueError("В указанном диапазоне нет будних дней.")

    with SessionLocal() as session:
        try:
            school = session.scalar(
                select(School).where(
                    School.short_name == SCHOOL_SHORT_NAME
                )
            )
            if school is None:
                raise RuntimeError("Сначала запусти scripts/seed.py.")

            academic_year = session.scalar(
                select(AcademicYear).where(
                    AcademicYear.school_id == school.id,
                    AcademicYear.name == ACADEMIC_YEAR_NAME,
                )
            )
            if academic_year is None or not academic_year.is_active:
                raise RuntimeError(
                    "Не найден активный учебный год 2026-2027."
                )

            classes = session.scalars(
                select(Class)
                .where(
                    Class.school_id == school.id,
                    Class.academic_year_id == academic_year.id,
                )
                .order_by(Class.code)
            ).all()

            teachers = session.scalars(
                select(Teacher)
                .where(Teacher.school_id == school.id)
                .order_by(Teacher.id)
            ).all()

            subjects = session.scalars(
                select(Subject)
                .where(Subject.school_id == school.id)
            ).all()

            if len(classes) != 44:
                raise RuntimeError(
                    f"Ожидалось 44 класса, найдено {len(classes)}."
                )
            if len(teachers) != 12:
                raise RuntimeError(
                    f"Ожидалось 12 учителей, найдено {len(teachers)}."
                )

            subjects_by_name = {item.name: item for item in subjects}
            missing_subjects = set(SUBJECT_NAMES) - set(subjects_by_name)
            if missing_subjects:
                raise RuntimeError(
                    f"Не найдены предметы: {sorted(missing_subjects)}"
                )

            assignments = {}
            for school_class in classes:
                for subject_index, subject_name in enumerate(SUBJECT_NAMES):
                    teacher = teachers[subject_index]
                    subject = subjects_by_name[subject_name]

                    assignments[(school_class.id, subject_name)] = (
                        get_or_create_assignment(
                            session,
                            school_class,
                            academic_year,
                            subject,
                            teacher,
                        )
                    )

            assignment_ids = [
                assignment.id
                for assignment in assignments.values()
            ]

            existing_lessons = session.scalars(
                select(Schedule).where(
                    Schedule.assignment_id.in_(assignment_ids),
                    Schedule.date >= start_date,
                    Schedule.date <= end_date,
                )
            ).all()

            existing_keys = {
                (
                    item.assignment_id,
                    item.date,
                    item.lesson_number,
                )
                for item in existing_lessons
            }

            new_lessons = []
            lesson_dates_by_class = {}

            for lesson_date in dates:
                for class_index, school_class in enumerate(classes):
                    plan = make_plan(school_class, lesson_date)
                    lesson_dates_by_class.setdefault(
                        school_class.id,
                        set(),
                    ).add(lesson_date)

                    for subject_name, lesson_number, lesson_type in plan:
                        assignment = assignments[
                            (school_class.id, subject_name)
                        ]

                        key = (
                            assignment.id,
                            lesson_date,
                            lesson_number,
                        )
                        if key in existing_keys:
                            continue

                        room_index = (
                            class_index + lesson_number
                        ) % len(ROOMS)

                        new_lessons.append(
                            Schedule(
                                assignment_id=assignment.id,
                                date=lesson_date,
                                lesson_number=lesson_number,
                                room=ROOMS[room_index],
                                lesson_type=lesson_type,
                            )
                        )
                        existing_keys.add(key)

            session.add_all(new_lessons)
            session.flush()

            # Заполняем только будущие даты. Сегодня и прошедшие даты
            # не меняем. День без уроков не получает прогноз.
            today = date.today()
            forecast_created = 0
            forecast_existing = 0

            for school_class in classes:
                grade, parallel_index = parse_class_code(
                    school_class.code
                )

                scheduled_dates = lesson_dates_by_class.get(
                    school_class.id,
                    set(),
                )

                for target_date in sorted(scheduled_dates):
                    if target_date <= today:
                        continue

                    existing_forecast = session.scalar(
                        select(AIDailyForecast).where(
                            AIDailyForecast.class_id == school_class.id,
                            AIDailyForecast.date == target_date,
                        )
                    )

                    if existing_forecast is not None:
                        forecast_existing += 1
                        continue

                    # Детерминированно распределяем значения 0–4.
                    # Значение 0 означает перегрузку, 4 — лёгкий день.
                    level = (
                        grade
                        + parallel_index * 2
                        + target_date.day
                        + target_date.month
                    ) % 5

                    session.add(
                        AIDailyForecast(
                            class_id=school_class.id,
                            date=target_date,
                            level=level,
                            source="python",
                            analysis_run_id=None,
                        )
                    )
                    forecast_created += 1

            session.commit()

            print("Расписание подготовлено.")
            print(f"Период: {start_date} — {end_date}")
            print(f"Классов: {len(classes)}")
            print(f"Учителей: {len(teachers)}")
            print(f"Предметов: {len(subjects_by_name)}")
            print(f"Будних дней: {len(dates)}")
            print(f"Новых уроков: {len(new_lessons)}")
            print(f"Новых Python-прогнозов: {forecast_created}")
            print(f"Существующих прогнозов пропущено: {forecast_existing}")

        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    args = parse_args()
    seed_schedule(args.start_date, args.end_date)
