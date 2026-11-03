"""Создание экземпляров опроса на указанную дату.

По умолчанию работает в режиме предварительного просмотра.
Для записи в БД необходимо явно указать --create.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from sqlalchemy.orm import Session

# Позволяет запускать файл из backend/scripts.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from user_mode import validate_database_mode
from database import engine, SessionLocal
from models import SurveyQuestion, SurveyInstance
from survey_instance_service import (
    create_survey_instances_for_date,
    get_classes_with_schedule,
    prepare_question_options,
)

NO_SUBJECT_OPTION = "Никакой"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Предварительный просмотр или создание экземпляров опроса."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Дата опроса в формате ГГГГ-ММ-ДД, например 2026-10-30.",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Записать экземпляры опроса в базу. Без этого флага только предпросмотр.",
    )
    return parser.parse_args()


def main() -> int:
    validate_database_mode(engine)
    args = parse_args()

    try:
        survey_date = date.fromisoformat(args.date)
    except ValueError:
        print("Ошибка: дата должна быть в формате ГГГГ-ММ-ДД.")
        return 1

    session: Session = SessionLocal()

    try:
        classes = get_classes_with_schedule(session, survey_date)
        if not classes:
            print(f"На {survey_date} не найдено ни одного класса с расписанием.")
            return 0

        questions = session.scalars(
            select(SurveyQuestion)
            .where(SurveyQuestion.is_active.is_(True))
            .order_by(SurveyQuestion.sort_order, SurveyQuestion.id)
        ).all()

        if not questions:
            raise ValueError("В базе нет активных шаблонов вопросов.")

        # Сначала проверяем все данные и часовые пояса. До окончания проверки
        # никаких записей в БД не производится.
        prepared_classes = []
        for class_id, class_code, class_name, timezone_name in classes:
            if not timezone_name:
                raise ValueError(
                    f"У школы класса {class_code} (ID {class_id}) не задан часовой пояс."
                )

            try:
                school_timezone = ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError as exc:
                raise ValueError(
                    f"Неизвестный часовой пояс {timezone_name!r} "
                    f"у класса {class_code} (ID {class_id})."
                ) from exc

            opens_at = datetime.combine(
                survey_date, time(18, 0), tzinfo=school_timezone
            )
            closes_at = datetime.combine(
                survey_date + timedelta(days=1),
                time(17, 59),
                tzinfo=school_timezone,
            )

            existing = session.scalar(
                select(SurveyInstance.id).where(
                    SurveyInstance.class_id == class_id,
                    SurveyInstance.survey_date == survey_date,
                )
            )

            prepared_questions = []
            for question in questions:
                options = prepare_question_options(
                    session, question, class_id, survey_date
                )
                prepared_questions.append((question, options))

            prepared_classes.append(
                {
                    "id": class_id,
                    "code": class_code,
                    "name": class_name,
                    "timezone": timezone_name,
                    "opens_at": opens_at,
                    "closes_at": closes_at,
                    "existing_id": existing,
                    "questions": prepared_questions,
                }
            )

        print(f"Дата опроса: {survey_date}")
        print(f"Активных шаблонов: {len(questions)}")
        print(f"Классов с расписанием: {len(prepared_classes)}")
        print()

        to_create = []
        for item in prepared_classes:
            print(
                f"Класс {item['code']} — {item['name']} "
                f"(ID {item['id']}, часовой пояс {item['timezone']})"
            )
            print(f"  Открытие: {item['opens_at'].isoformat()}")
            print(f"  Закрытие: {item['closes_at'].isoformat()}")

            if item["existing_id"] is not None:
                print(
                    f"  ПРОПУСК: экземпляр уже существует "
                    f"(ID {item['existing_id']})."
                )
                print()
                continue

            for question, options in item["questions"]:
                print(
                    f"  Вопрос {question.sort_order}: {question.title} "
                    f"[{question.answer_type}, вариантов: {len(options)}]"
                )
                for option in options:
                    suffix = " (исключительный)" if option["is_exclusive"] else ""
                    print(f"    - {option['title']}{suffix}")

            to_create.append(item)
            print()

        if not args.create:
            print("РЕЖИМ ПРЕДПРОСМОТРА: база данных не изменялась.")
            print("Для создания запусти эту же команду с флагом --create.")
            return 0

        if not to_create:
            print("Новых экземпляров для создания нет.")
            return 0

        result = create_survey_instances_for_date(
            session=session,
            survey_date=survey_date,
            enforce_time_window=False,
        )

        created_count = len(result["created"])

        for item in result["created"]:
            print(
                f"СОЗДАНО: класс {item['class_code']} — "
                f"{item['class_name']} "
                f"(экземпляр ID {item['instance_id']})."
            )

        for item in result["skipped"]:
            print(
                f"ПРОПУСК: класс {item['class_code']} "
                f"(ID {item['class_id']}): {item['reason']}"
            )

        for item in result["errors"]:
            if isinstance(item, dict):
                print(
                    f"ОШИБКА: класс {item['class_code']} "
                    f"(ID {item['class_id']}): {item['error']}",
                    file=sys.stderr,
                )
            else:
                print(f"ОШИБКА: {item}", file=sys.stderr)

        print()
        print(f"Создано экземпляров: {created_count}")

        if result["errors"]:
            return 1

    except Exception as exc:
        session.rollback()
        print(f"Ошибка: {exc}", file=sys.stderr)
        print("Изменения этого запуска не сохранены.", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
