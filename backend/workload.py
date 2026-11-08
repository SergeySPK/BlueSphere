from datetime import date
from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Schedule, TeachingAssignment


def get_daily_lesson_counts(
    db: Session,
    class_id: int,
    start_date: date,
    end_date: date,
) -> Dict[date, int]:
    """Считает уроки по дням, не удваивая уроки разных подгрупп."""

    rows = db.execute(
        select(
            Schedule.date,
            func.count(func.distinct(Schedule.lesson_number)),
        )
        .join(
            TeachingAssignment,
            Schedule.assignment_id == TeachingAssignment.id,
        )
        .where(
            TeachingAssignment.class_id == class_id,
            Schedule.date >= start_date,
            Schedule.date <= end_date,
        )
        .group_by(Schedule.date)
    ).all()

    return {
        day: count
        for day, count in rows
    }


def get_load_level(lesson_count: int) -> int | None:
    """
    Переводит количество уроков в уровень нагрузки.

    0 — перегрузка.
    4 — очень лёгкий день.
    None — уроков нет.
    """

    if lesson_count < 0:
        raise ValueError("Количество уроков не может быть отрицательным.")

    if lesson_count == 0:
        return None

    if lesson_count >= 7:
        return 0

    if lesson_count == 6:
        return 1

    if lesson_count == 5:
        return 2

    if lesson_count == 4:
        return 3

    return 4
