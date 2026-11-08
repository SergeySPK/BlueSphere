import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from database import SessionLocal, engine
from models import (
    AcademicYear,
    Administrator,
    Class,
    School,
    Student,
    StudentEnrollment,
    Subject,
    Teacher,
    TeacherClassAccess,
)
from user_mode import (
    get_or_create_user,
    is_demo_mode,
    validate_database_mode,
)


SCHOOL_SHORT_NAME = "Школа № 1"
ACADEMIC_YEAR_NAME = "2026-2027"

GRADES = range(1, 12)
PARALLELS = {
    "a": "А",
    "b": "Б",
    "v": "В",
    "g": "Г",
}

TEACHERS = [
    ("teacher-1", "Иванов Иван Иванович"),
    ("teacher-2", "Петров Пётр Петрович"),
    ("teacher-3", "Сидоров Сергей Сергеевич"),
    ("teacher-4", "Смирнова Анна Андреевна"),
    ("teacher-5", "Кузнецова Ольга Константиновна"),
    ("teacher-6", "Попов Алексей Александрович"),
    ("teacher-7", "Васильева Мария Сергеевна"),
    ("teacher-8", "Морозов Дмитрий Викторович"),
    ("teacher-9", "Новикова Елена Павловна"),
    ("teacher-10", "Фёдоров Михаил Андреевич"),
    ("teacher-11", "Волкова Наталья Игоревна"),
    ("teacher-12", "Алексеев Андрей Олегович"),
]

ADMINISTRATORS = [
    ("admin-1", "Орлова Татьяна Николаевна", "Директор"),
    ("admin-2", "Захаров Владимир Петрович", "Заместитель директора"),
    ("admin-3", "Романова Ирина Александровна", "Администратор"),
]

SUBJECTS = [
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


def get_or_create_school(session):
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

    return school


def get_or_create_academic_year(session, school):
    academic_year = session.scalar(
        select(AcademicYear).where(
            AcademicYear.school_id == school.id,
            AcademicYear.name == ACADEMIC_YEAR_NAME,
        )
    )

    if academic_year is None:
        active_year = session.scalar(
            select(AcademicYear.id).where(
                AcademicYear.school_id == school.id,
                AcademicYear.is_active.is_(True),
            )
        )

        if active_year is not None:
            raise RuntimeError(
                "У школы уже есть другой активный учебный год. "
                "Автоматически переключать его небезопасно."
            )

        academic_year = AcademicYear(
            school_id=school.id,
            name=ACADEMIC_YEAR_NAME,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            is_active=True,
        )
        session.add(academic_year)
        session.flush()

    return academic_year


def get_or_create_class(
    session,
    school,
    academic_year,
    grade,
    parallel_code,
    parallel_name,
):
    code = f"{grade}{parallel_code}"
    name = f"{grade}{parallel_name}"

    school_class = session.scalar(
        select(Class).where(
            Class.school_id == school.id,
            Class.academic_year_id == academic_year.id,
            Class.code == code,
        )
    )

    if school_class is None:
        school_class = Class(
            school_id=school.id,
            academic_year_id=academic_year.id,
            code=code,
            name=name,
        )
        session.add(school_class)
        session.flush()

    return school_class


def get_or_create_teacher(session, school, sferum_id, full_name):
    user, _ = get_or_create_user(
        session,
        sferum_id=sferum_id,
        full_name=full_name,
    )

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


def get_or_create_student(session, school_class, index):
    sferum_id = f"student-{index}"
    full_name = f"Ученик {index:02d}"

    user, _ = get_or_create_user(
        session,
        sferum_id=sferum_id,
        full_name=full_name,
    )

    student = session.scalar(
        select(Student).where(Student.user_id == user.id)
    )

    if student is None:
        student = Student(
            user_id=user.id,
            class_id=school_class.id,
        )
        session.add(student)
        session.flush()
    elif student.class_id != school_class.id:
        raise RuntimeError(
            f"{sferum_id} уже закреплён за другим классом."
        )

    enrollment = session.scalar(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.class_id == school_class.id,
            StudentEnrollment.start_date == date(2026, 9, 1),
            StudentEnrollment.end_date.is_(None),
        )
    )

    if enrollment is None:
        active_enrollment = session.scalar(
            select(StudentEnrollment.id).where(
                StudentEnrollment.student_id == student.id,
                StudentEnrollment.end_date.is_(None),
            )
        )
        if active_enrollment is not None:
            raise RuntimeError(
                f"У {sferum_id} уже есть другое активное зачисление."
            )

        session.add(
            StudentEnrollment(
                student_id=student.id,
                class_id=school_class.id,
                start_date=date(2026, 9, 1),
                end_date=None,
            )
        )

    return student


def get_or_create_administrator(
    session,
    school,
    sferum_id,
    full_name,
    position,
):
    user, _ = get_or_create_user(
        session,
        sferum_id=sferum_id,
        full_name=full_name,
    )

    administrator = session.scalar(
        select(Administrator).where(
            Administrator.user_id == user.id,
            Administrator.school_id == school.id,
        )
    )

    if administrator is None:
        administrator = Administrator(
            user_id=user.id,
            school_id=school.id,
            position=position,
        )
        session.add(administrator)

    return administrator


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


def seed_database():
    validate_database_mode(engine)

    if is_demo_mode():
        raise RuntimeError(
            "Для этого набора данных требуется DEMO_MODE=false."
        )

    with SessionLocal() as session:
        try:
            school = get_or_create_school(session)
            academic_year = get_or_create_academic_year(
                session,
                school,
            )

            classes = []
            for grade in GRADES:
                for parallel_code, parallel_name in PARALLELS.items():
                    classes.append(
                        get_or_create_class(
                            session,
                            school,
                            academic_year,
                            grade,
                            parallel_code,
                            parallel_name,
                        )
                    )

            teachers = [
                get_or_create_teacher(
                    session,
                    school,
                    sferum_id,
                    full_name,
                )
                for sferum_id, full_name in TEACHERS
            ]

            for index, school_class in enumerate(classes, start=1):
                get_or_create_student(
                    session,
                    school_class,
                    index,
                )

            for sferum_id, full_name, position in ADMINISTRATORS:
                get_or_create_administrator(
                    session,
                    school,
                    sferum_id,
                    full_name,
                    position,
                )

            subjects = [
                get_or_create_subject(session, school, name)
                for name in SUBJECTS
            ]

            # Каждый учитель получает доступ к нескольким классам.
            # Назначения по предметам будут созданы seed_schedule.py.
            for class_index, school_class in enumerate(classes):
                teacher = teachers[class_index % len(teachers)]

                existing_access = session.scalar(
                    select(TeacherClassAccess.id).where(
                        TeacherClassAccess.teacher_id == teacher.id,
                        TeacherClassAccess.class_id == school_class.id,
                    )
                )

                if existing_access is None:
                    session.add(
                        TeacherClassAccess(
                            teacher_id=teacher.id,
                            class_id=school_class.id,
                            school_id=school.id,
                            academic_year_id=academic_year.id,
                        )
                    )

            session.flush()

            counts = {
                "classes": session.scalar(
                    select(func.count(Class.id)).where(
                        Class.school_id == school.id,
                        Class.academic_year_id == academic_year.id,
                    )
                ),
                "teachers": session.scalar(
                    select(func.count(Teacher.id)).where(
                        Teacher.school_id == school.id,
                    )
                ),
                "students": session.scalar(
                    select(func.count(Student.id))
                    .join(
                        StudentEnrollment,
                        StudentEnrollment.student_id == Student.id,
                    )
                    .join(Class, Class.id == StudentEnrollment.class_id)
                    .where(
                        Class.school_id == school.id,
                        Class.academic_year_id == academic_year.id,
                    )
                ),
                "administrators": session.scalar(
                    select(func.count(Administrator.id)).where(
                        Administrator.school_id == school.id,
                    )
                ),
                "subjects": session.scalar(
                    select(func.count(Subject.id)).where(
                        Subject.school_id == school.id,
                    )
                ),
            }

            if counts != {
                "classes": 44,
                "teachers": 12,
                "students": 44,
                "administrators": 3,
                "subjects": 12,
            }:
                raise RuntimeError(
                    f"Контрольные количества не совпали: {counts}"
                )

            session.commit()

            print("Базовые данные подготовлены.")
            print(f"Школа: {school.short_name} (ID {school.id})")
            print(f"Учебный год: {academic_year.name}")
            for key, value in counts.items():
                print(f"{key}: {value}")

        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    seed_database()
