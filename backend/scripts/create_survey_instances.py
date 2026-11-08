"""Создание экземпляров опроса на указанную дату.

Вопросы и варианты берутся исключительно из активных шаблонов,
а экземпляры создаются штатным survey_instance_service.

Без --create выполняется только предварительный просмотр.
--seed-responses создаёт обобщённые ответы учеников по фактической
структуре экземпляров и закрывает исторические опросы.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal, engine
from models import (
    StudentEnrollment,
    SurveyInstance,
    SurveyInstanceOption,
    SurveyInstanceQuestion,
    SurveyResponse,
    SurveyResponseOption,
)
from survey_instance_service import (
    create_survey_instances_for_date,
    get_classes_with_schedule,
)
from user_mode import validate_database_mode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Создание экземпляров опроса на указанную дату."
    )
    parser.add_argument(
        "--date",
        required=True,
        type=date.fromisoformat,
        help="Дата опроса в формате YYYY-MM-DD.",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Создать экземпляры. Без флага выполняется предпросмотр.",
    )
    parser.add_argument(
        "--seed-responses",
        action="store_true",
        help=(
            "Создать ответы учеников и закрыть опросы. "
            "Используется для подготовки исторических данных."
        ),
    )

    args = parser.parse_args()

    if args.seed_responses and not args.create:
        parser.error("--seed-responses требует указать --create.")

    return args


def get_enrolled_student_ids(
    session: Session,
    class_id: int,
    survey_date: date,
) -> list[int]:
    """Ученики с единственным действующим зачислением в этот класс на дату."""

    active_enrollments = (
        select(
            StudentEnrollment.student_id,
            func.count(StudentEnrollment.id).label("enrollment_count"),
            func.min(StudentEnrollment.class_id).label("enrolled_class_id"),
        )
        .where(
            StudentEnrollment.start_date <= survey_date,
            (
                StudentEnrollment.end_date.is_(None)
                | (StudentEnrollment.end_date >= survey_date)
            ),
        )
        .group_by(StudentEnrollment.student_id)
        .subquery()
    )

    rows = session.execute(
        select(active_enrollments.c.student_id).where(
            active_enrollments.c.enrollment_count == 1,
            active_enrollments.c.enrolled_class_id == class_id,
        )
    )

    return sorted(row.student_id for row in rows)


def make_answer_options(
    instance_question: SurveyInstanceQuestion,
    options: list[SurveyInstanceOption],
    student_id: int,
    survey_date: date,
) -> list[SurveyInstanceOption]:
    """Выбирает допустимые варианты, не предполагая содержание вопроса."""

    if instance_question.answer_type not in {"single", "multiple"}:
        raise ValueError(
            f"Вопрос ID {instance_question.id} имеет неподдерживаемый "
            f"тип ответа {instance_question.answer_type!r}."
        )

    if not options:
        raise ValueError(
            f"У вопроса экземпляра ID {instance_question.id} нет вариантов."
        )

    min_answer = instance_question.min_answer
    max_answer = instance_question.max_answer

    if min_answer < 1 or max_answer < min_answer:
        raise ValueError(
            f"У вопроса экземпляра ID {instance_question.id} "
            "некорректные ограничения min_answer/max_answer."
        )

    if instance_question.answer_type == "single":
        if min_answer != 1 or max_answer != 1:
            raise ValueError(
                f"У одиночного вопроса ID {instance_question.id} "
                "ограничения должны быть равны 1."
            )
        max_answer = 1

    if max_answer > len(options):
        raise ValueError(
            f"У вопроса экземпляра ID {instance_question.id} "
            f"max_answer={max_answer}, но вариантов только {len(options)}."
        )

    exclusive = [option for option in options if option.is_exclusive]
    regular = [option for option in options if not option.is_exclusive]

    if len(exclusive) > 1:
        raise ValueError(
            f"У вопроса экземпляра ID {instance_question.id} "
            "обнаружено несколько исключительных вариантов."
        )

    if len(regular) < min_answer:
        if min_answer == 1 and exclusive:
            return [exclusive[0]]

        raise ValueError(
            f"У вопроса экземпляра ID {instance_question.id} "
            "недостаточно обычных вариантов для min_answer."
        )

    seed_text = (
        f"{survey_date.isoformat()}:{student_id}:{instance_question.id}"
    )
    seed = int.from_bytes(
        hashlib.sha256(seed_text.encode("utf-8")).digest()[:8],
        byteorder="big",
    )
    rng = random.Random(seed)

    # Исключительный вариант может быть выбран только отдельно.
    if exclusive and min_answer == 1 and rng.random() < 0.15:
        return [exclusive[0]]

    count = rng.randint(min_answer, min(max_answer, len(regular)))

    if count < min_answer:
        if min_answer == 1 and exclusive:
            return [exclusive[0]]
        raise ValueError(
            f"Для вопроса экземпляра ID {instance_question.id} "
            "невозможно сформировать допустимый ответ."
        )

    return rng.sample(regular, count)


def seed_instance_responses(
    session: Session,
    instance: SurveyInstance,
) -> tuple[int, int]:
    """Создаёт ответы по всем вопросам экземпляра для учеников класса."""

    students = get_enrolled_student_ids(
        session,
        class_id=instance.class_id,
        survey_date=instance.survey_date,
    )

    questions = session.scalars(
        select(SurveyInstanceQuestion)
        .where(SurveyInstanceQuestion.instance_id == instance.id)
        .order_by(
            SurveyInstanceQuestion.sort_order,
            SurveyInstanceQuestion.id,
        )
    ).all()

    if not questions:
        raise ValueError(
            f"У экземпляра опроса ID {instance.id} нет вопросов."
        )

    created_count = 0
    existing_count = 0
    submitted_at = datetime.now(timezone.utc)

    for question in questions:
        options = session.scalars(
            select(SurveyInstanceOption)
            .where(
                SurveyInstanceOption.instance_question_id == question.id
            )
            .order_by(
                SurveyInstanceOption.sort_order,
                SurveyInstanceOption.id,
            )
        ).all()

        for student_id in students:
            existing = session.scalar(
                select(SurveyResponse.id).where(
                    SurveyResponse.instance_question_id == question.id,
                    SurveyResponse.student_id == student_id,
                )
            )

            if existing is not None:
                existing_count += 1
                continue

            selected_options = make_answer_options(
                instance_question=question,
                options=options,
                student_id=student_id,
                survey_date=instance.survey_date,
            )

            response = SurveyResponse(
                instance_question_id=question.id,
                student_id=student_id,
                status="submitted",
                submitted_at=submitted_at,
            )
            session.add(response)
            session.flush()

            for option in selected_options:
                session.add(
                    SurveyResponseOption(
                        response_id=response.id,
                        option_id=option.id,
                        instance_question_id=question.id,
                    )
                )

            created_count += 1

    return created_count, existing_count


def main() -> int:
    args = parse_args()
    validate_database_mode(engine)

    session: Session = SessionLocal()

    try:
        classes = get_classes_with_schedule(session, args.date)

        if not classes:
            print(f"На {args.date} нет классов с расписанием.")
            return 0

        existing_count = session.scalar(
            select(func.count(SurveyInstance.id)).where(
                SurveyInstance.survey_date == args.date
            )
        ) or 0

        print(f"Дата опроса: {args.date}")
        print(f"Классов с расписанием: {len(classes)}")
        print(f"Уже существующих экземпляров на эту дату: {existing_count}")

        if not args.create:
            print("Предпросмотр завершён. База данных не изменялась.")
            print("Для создания добавь флаг --create.")
            return 0

        result = create_survey_instances_for_date(
            session=session,
            survey_date=args.date,
            enforce_time_window=False,
        )

        print(f"\nСоздано экземпляров: {len(result['created'])}")

        for item in result["created"]:
            print(
                f"  Создано: {item['class_code']} — {item['class_name']} "
                f"(ID экземпляра: {item['instance_id']})"
            )

        for item in result["skipped"]:
            print(
                f"  Пропуск: {item['class_code']} — {item['reason']}"
            )

        for item in result["errors"]:
            if isinstance(item, dict):
                print(
                    f"  Ошибка класса {item.get('class_code')}: "
                    f"{item.get('error')}",
                    file=sys.stderr,
                )
            else:
                print(f"  Ошибка: {item}", file=sys.stderr)

        if args.seed_responses:
            instances = session.scalars(
                select(SurveyInstance).where(
                    SurveyInstance.survey_date == args.date
                )
            ).all()

            total_created = 0
            total_existing = 0

            for instance in instances:
                created, existing = seed_instance_responses(
                    session,
                    instance,
                )
                total_created += created
                total_existing += existing

                # Исторические экземпляры закрыты и не должны попадать
                # в текущий поток прохождения опросов.
                instance.status = "closed"

            session.commit()

            print("\nИсторические ответы подготовлены.")
            print(f"Новых ответов: {total_created}")
            print(f"Уже существующих ответов: {total_existing}")
            print(f"Закрыто экземпляров: {len(instances)}")
            print("Уведомления MAX не создавались.")

        if result["errors"]:
            return 1

        return 0

    except Exception as exc:
        session.rollback()
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
