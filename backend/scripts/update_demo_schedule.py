from datetime import date

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

LESSON_DATE = date(2026, 9, 9)
LESSON_NUMBER = 5


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


def get_or_create_lesson(session, assignment, room, lesson_type):
    lesson = session.scalar(
        select(Schedule).where(
            Schedule.assignment_id == assignment.id,
            Schedule.date == LESSON_DATE,
            Schedule.lesson_number == LESSON_NUMBER,
        )
    )

    if lesson is None:
        lesson = Schedule(
            assignment_id=assignment.id,
            date=LESSON_DATE,
            lesson_number=LESSON_NUMBER,
            room=room,
            lesson_type=lesson_type,
        )
        session.add(lesson)
        session.flush()
    else:
        lesson.room = room
        lesson.lesson_type = lesson_type

    return lesson


def update_demo_schedule():
    with SessionLocal() as session:
        school = session.scalar(
            select(School).where(
                School.short_name == SCHOOL_SHORT_NAME
            )
        )

        if school is None:
            raise RuntimeError(
                f"Не найдена школа «{SCHOOL_SHORT_NAME}». "
                "Сначала запусти seed.py."
            )

        academic_year = session.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.name == ACADEMIC_YEAR_NAME,
            )
        )

        if academic_year is None:
            raise RuntimeError(
                f"Не найден учебный год {ACADEMIC_YEAR_NAME}."
            )

        subject = session.scalar(
            select(Subject).where(
                Subject.school_id == school.id,
                Subject.name == "Английский язык",
            )
        )

        if subject is None:
            raise RuntimeError(
                "Не найден предмет «Английский язык»."
            )

        classes = session.scalars(
            select(Class).where(
                Class.school_id == school.id,
                Class.academic_year_id == academic_year.id,
                Class.code.in_(("5a", "5b", "5v")),
            )
        ).all()

        classes_by_code = {
            school_class.code: school_class
            for school_class in classes
        }

        missing_classes = {
            "5a", "5b", "5v"
        } - classes_by_code.keys()

        if missing_classes:
            raise RuntimeError(
                "Не найдены классы: "
                + ", ".join(sorted(missing_classes))
            )

        # Первый преподаватель — Смирнова Анна Андреевна.
        first_teacher_user = session.scalar(
            select(User).where(
                User.sferum_id == "demo-teacher-5"
            )
        )

        if first_teacher_user is None:
            raise RuntimeError(
                "Не найдена Смирнова А.А. "
                "Проверь данные, созданные seed_schedule.py."
            )

        first_teacher = session.scalar(
            select(Teacher).where(
                Teacher.user_id == first_teacher_user.id,
                Teacher.school_id == school.id,
            )
        )

        if first_teacher is None:
            raise RuntimeError(
                "Не найден профиль учителя Смирновой А.А."
            )

        second_teacher = get_or_create_teacher(
            session,
            school,
            "demo-teacher-6",
            "Батонова Ирина Александровна",
        )

        for class_code in ("5a", "5b", "5v"):
            school_class = classes_by_code[class_code]

            # Ищем назначение первой подгруппы.
            first_assignment = session.scalar(
                select(TeachingAssignment).where(
                    TeachingAssignment.school_id == school.id,
                    TeachingAssignment.teacher_id == first_teacher.id,
                    TeachingAssignment.class_id == school_class.id,
                    TeachingAssignment.subject_id == subject.id,
                    TeachingAssignment.academic_year_id == academic_year.id,
                    TeachingAssignment.subgroup == 1,
                )
            )

            if first_assignment is None:
                # Если его нет, проверяем старое назначение subgroup=0.
                first_assignment = session.scalar(
                    select(TeachingAssignment).where(
                        TeachingAssignment.school_id == school.id,
                        TeachingAssignment.teacher_id == first_teacher.id,
                        TeachingAssignment.class_id == school_class.id,
                        TeachingAssignment.subject_id == subject.id,
                        TeachingAssignment.academic_year_id == academic_year.id,
                        TeachingAssignment.subgroup == 0,
                    )
                )

                if first_assignment is not None:
                    first_assignment.subgroup = 1
                    session.flush()
                else:
                    first_assignment = get_or_create_assignment(
                        session,
                        first_teacher,
                        school_class,
                        subject,
                        academic_year,
                        subgroup=1,
                    )

            get_or_create_lesson(
                session,
                first_assignment,
                room="108",
                lesson_type="Обычный урок",
            )

            # Создаём или находим назначение второй подгруппы.
            second_assignment = get_or_create_assignment(
                session,
                second_teacher,
                school_class,
                subject,
                academic_year,
                subgroup=2,
            )

            get_or_create_lesson(
                session,
                second_assignment,
                room="109",
                lesson_type="Обычный урок",
            )

        session.commit()

        print("Демонстрационное расписание обновлено.")
        print(f"Школа: {school.short_name}")
        print(f"Учебный год: {academic_year.name}")
        print(f"Дата: {LESSON_DATE}")
        print(f"Номер урока: {LESSON_NUMBER}")
        print("Английский язык: кабинеты 108 и 109.")
        print("Подгруппа 1: Смирнова А.А.")
        print("Подгруппа 2: Батонова И.А.")
        print("Классы: 5А, 5Б, 5В.")


if __name__ == "__main__":
    update_demo_schedule()
