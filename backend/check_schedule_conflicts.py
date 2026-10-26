
from sqlalchemy import select

from database import SessionLocal
from models import (
    Class,
    Schedule,
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
                Class.name,
                Subject.name,
                Teacher.id,
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
            .order_by(Schedule.date, Schedule.lesson_number)
        ).all()

        lessons = []

        for schedule, assignment, class_name, subject_name, teacher_id, teacher_name in rows:
            lessons.append({
                "id": schedule.id,
                "date": schedule.date,
                "number": schedule.lesson_number,
                "class_name": class_name,
                "class_id": assignment.class_id,
                "subgroup": assignment.subgroup,
                "subject": subject_name,
                "teacher_id": teacher_id,
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

                # Один учитель не может вести два урока одновременно.
                if first["teacher_id"] == second["teacher_id"]:
                    conflicts.append(
                        (
                            "УЧИТЕЛЬ",
                            first,
                            second,
                            f'{first["teacher_name"]} назначен на два урока',
                        )
                    )

                # Один кабинет не может использоваться дважды одновременно.
                if (
                    first["room"]
                    and second["room"]
                    and first["room"].strip().casefold()
                    == second["room"].strip().casefold()
                ):
                    conflicts.append(
                        (
                            "КАБИНЕТ",
                            first,
                            second,
                            f'Кабинет {first["room"]} занят дважды',
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
                                    f'{first["class_name"]}: пересекаются '
                                    f'подгруппы {first_group} и {second_group}'
                                ),
                            )
                        )

        if not conflicts:
            print("Конфликтов не найдено.")
            return

        print(f"Найдено конфликтов: {len(conflicts)}\n")

        for conflict_type, first, second, description in conflicts:
            print(f"[{conflict_type}] {description}")
            print(
                f'  Урок ID {first["id"]}: '
                f'{first["date"]}, урок №{first["number"]}, '
                f'{first["class_name"]}, {first["subject"]}, '
                f'{first["teacher_name"]}, кабинет {first["room"]}, '
                f'подгруппа {first["subgroup"]}'
            )
            print(
                f'  Урок ID {second["id"]}: '
                f'{second["date"]}, урок №{second["number"]}, '
                f'{second["class_name"]}, {second["subject"]}, '
                f'{second["teacher_name"]}, кабинет {second["room"]}, '
                f'подгруппа {second["subgroup"]}'
            )
            print()


if __name__ == "__main__":
    check_schedule_conflicts()
