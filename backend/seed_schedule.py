
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


def seed_schedule():
    with SessionLocal() as session:
        # Используем существующую демонстрационную школу.
        school = session.scalar(
            select(School).where(School.short_name == "Школа № 1")
        )
        if school is None:
            raise RuntimeError("Не найдена школа «Школа № 1». Сначала запусти seed.py.")

        academic_year = session.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.name == "2026–2027",
            )
        )
        if academic_year is None:
            raise RuntimeError("Не найден учебный год 2026–2027.")

        classes = {
            class_id: session.get(Class, class_id)
            for class_id in ("5a", "5b", "5v")
        }
        if any(school_class is None for school_class in classes.values()):
            raise RuntimeError("Не найдены все три класса: 5a, 5b, 5v.")

        # Демонстрационные учителя.
        teachers_data = [
            ("demo-teacher-1", "Сидоров Сергей Сергеевич"),
            ("demo-teacher-2", "Петров Павел Петрович"),
            ("demo-teacher-3", "Кузнецова Ольга Константиновна"),
            ("demo-teacher-4", "Иванов Иван Иванович"),
            ("demo-teacher-5", "Смирнова Анна Андреевна"),
        ]

        teachers = {}
        for sferum_id, full_name in teachers_data:
            user = session.scalar(
                select(User).where(User.sferum_id == sferum_id)
            )
            if user is None:
                user = User(sferum_id=sferum_id, full_name=full_name)
                session.add(user)
                session.flush()

            teacher = session.scalar(
                select(Teacher).where(
                    Teacher.user_id == user.id,
                    Teacher.school_id == school.id,
                )
            )
            if teacher is None:
                teacher = Teacher(user_id=user.id, school_id=school.id)
                session.add(teacher)
                session.flush()

            teachers[sferum_id] = teacher

        # Демонстрационные предметы.
        subject_names = [
            "Физкультура",
            "История",
            "Русский язык",
            "Математика",
            "Английский язык",
        ]

        subjects = {}
        for name in subject_names:
            subject = session.scalar(
                select(Subject).where(
                    Subject.school_id == school.id,
                    Subject.name == name,
                )
            )
            if subject is None:
                subject = Subject(school_id=school.id, name=name)
                session.add(subject)
                session.flush()
            subjects[name] = subject

        # Пять уроков для каждого из трёх классов.
        lesson_templates = [
            (1, "Физкультура", "demo-teacher-1", "Спортзал", "Сдача нормативов"),
            (2, "История", "demo-teacher-2", "204", "ВКР"),
            (3, "Русский язык", "demo-teacher-3", "301", "Входная контрольная работа"),
            (4, "Математика", "demo-teacher-4", "302", "Проверочная работа"),
            (5, "Английский язык", "demo-teacher-5", "108", "Обычный урок"),
        ]

        # Дата совпадает с примером в исходном API: 9 сентября 2026 года.
        lesson_date = date(2026, 9, 9)
        created_count = 0

        for class_id, school_class in classes.items():
            for number, subject_name, teacher_key, room, lesson_type in lesson_templates:
                teacher = teachers[teacher_key]
                subject = subjects[subject_name]

                assignment = session.scalar(
                    select(TeachingAssignment).where(
                        TeachingAssignment.teacher_id == teacher.id,
                        TeachingAssignment.class_id == class_id,
                        TeachingAssignment.subject_id == subject.id,
                        TeachingAssignment.academic_year_id == academic_year.id,
                        TeachingAssignment.subgroup == 0,
                    )
                )
                if assignment is None:
                    assignment = TeachingAssignment(
                        teacher_id=teacher.id,
                        class_id=class_id,
                        subject_id=subject.id,
                        academic_year_id=academic_year.id,
                        subgroup=0,
                    )
                    session.add(assignment)
                    session.flush()

                lesson = session.scalar(
                    select(Schedule).where(
                        Schedule.assignment_id == assignment.id,
                        Schedule.date == lesson_date,
                        Schedule.lesson_number == number,
                    )
                )
                if lesson is None:
                    session.add(
                        Schedule(
                            assignment_id=assignment.id,
                            date=lesson_date,
                            lesson_number=number,
                            room=room,
                            lesson_type=lesson_type,
                        )
                    )
                    created_count += 1

        session.commit()
        print("Демонстрационные данные расписания подготовлены.")
        print(f"Дата уроков: {lesson_date}")
        print(f"Новых записей расписания: {created_count}")
        print("Классы: 5А, 5Б, 5В.")


if __name__ == "__main__":
    seed_schedule()
