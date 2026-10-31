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


def check_schedule_conflicts():
    with SessionLocal() as session:
        rows = session.execute(
            select(
                Schedule,
                TeachingAssignment,
                Class.id,
                Class.code,
                Class.name,
                School.id,
                School.short_name,
                AcademicYear.name,
                Subject.name,
                Teacher.user_id,
                User.id,
                User.full_name,
            )
            .join(
                TeachingAssignment,
                Schedule.assignment_id == TeachingAssignment.id,
            )
            .join(
                Class,
                TeachingAssignment.class_id == Class.id,
            )
            .join(
                School,
                TeachingAssignment.school_id == School.id,
            )
            .join(
                AcademicYear,
                TeachingAssignment.academic_year_id == AcademicYear.id,
            )
            .join(
                Subject,
                TeachingAssignment.subject_id == Subject.id,
            )
            .join(
                Teacher,
                TeachingAssignment.teacher_id == Teacher.id,
            )
            .join(
                User,
                Teacher.user_id == User.id,
            )
            .order_by(
                Schedule.date,
                Schedule.lesson_number,
                School.id,
                Class.id,
            )
        ).all()

        lessons = []

        for row in rows:
            (
                schedule,
                assignment,
                class_id,
                class_code,
                class_name,
                school_id,
                school_name,
                academic_year_name,
                subject_name,
                teacher_user_id,
                user_id,
                teacher_name,
            ) = row

            lessons.append({
                "id": schedule.id,
                "date": schedule.date,
                "number": schedule.lesson_number,
                "school_id": school_id,
                "school_name": school_name,
                "academic_year": academic_year_name,
                "class_id": class_id,
                "class_code": class_code,
                "class_name": class_name,
                "subgroup": assignment.subgroup,
                "subject": subject_name,
                "teacher_user_id": user_id,
                "teacher_name": teacher_name,
                "room": schedule.room,
            })

        conflicts = []

        for i, first in enumerate(lessons):
            for second in lessons[i + 1:]:

                # Сравниваем только уроки в одно время.
                if (
                    first["date"] != second["date"]
                    or first["number"] != second["number"]
                ):
                    continue

                # Один пользователь не может вести два урока одновременно,
                # даже если он зарегистрирован учителем в разных школах.
                if (
                    first["teacher_user_id"]
                    == second["teacher_user_id"]
                ):
                    conflicts.append(
                        (
                            "УЧИТЕЛЬ",
                            first,
                            second,
                            f'{first["teacher_name"]} назначен на два урока',
                        )
                    )

                # Один кабинет нельзя использовать одновременно
                # в пределах одной школы.
                if (
                    first["school_id"] == second["school_id"]
                    and first["room"]
                    and second["room"]
                    and first["room"].strip().casefold()
                    == second["room"].strip().casefold()
                ):
                    conflicts.append(
                        (
                            "КАБИНЕТ",
                            first,
                            second,
                            (
                                f'{first["school_name"]}: '
                                f'кабинет {first["room"]} занят дважды'
                            ),
                        )
                    )

                # Проверяем пересечение занятий внутри одного класса.
                if first["class_id"] == second["class_id"]:
                    first_group = first["subgroup"]
                    second_group = second["subgroup"]

                    # 0 означает весь класс, поэтому пересекается
                    # с любой другой подгруппой.
                    groups_overlap = (
                        first_group == 0
                        or second_group == 0
                        or first_group == second_group
                    )

                    if groups_overlap:
                        conflicts.append(
                            (
                                "КЛАСС",
                                first,
                                second,
                                (
                                    f'{first["class_name"]} '
                                    f'({first["class_code"]}): '
                                    f'пересекаются подгруппы '
                                    f'{first_group} и {second_group}'
                                ),
                            )
                        )

        if not conflicts:
            print("Конфликтов не найдено.")
            return

        print(f"Найдено конфликтов: {len(conflicts)}\n")

        for conflict_type, first, second, description in conflicts:
            print(f"[{conflict_type}] {description}")

            for lesson in (first, second):
                print(
                    f'  Урок ID {lesson["id"]}: '
                    f'{lesson["date"]}, урок №{lesson["number"]}'
                )
                print(
                    f'    Школа: {lesson["school_name"]}'
                )
                print(
                    f'    Учебный год: {lesson["academic_year"]}'
                )
                print(
                    f'    Класс: {lesson["class_name"]} '
                    f'({lesson["class_code"]})'
                )
                print(
                    f'    Предмет: {lesson["subject"]}'
                )
                print(
                    f'    Учитель: {lesson["teacher_name"]}'
                )
                print(
                    f'    Кабинет: {lesson["room"]}'
                )
                print(
                    f'    Подгруппа: {lesson["subgroup"]}'
                )

            print()


if __name__ == "__main__":
    check_schedule_conflicts()
