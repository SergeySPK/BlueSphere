from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    Class,
    School,
    Schedule,
    TeachingAssignment,
    Subject,
    SurveyQuestion,
    SurveyQuestionOption,
    SurveyInstance,
    SurveyInstanceQuestion,
    SurveyInstanceOption,
    Student,
    StudentEnrollment,
    User,
    SurveyNotification,
)

NO_SUBJECT_OPTION = "Никакой"


def get_classes_with_schedule(session: Session, survey_date: date):
    """Возвращает классы, у которых есть расписание на указанную дату."""

    stmt = (
        select(Class.id, Class.code, Class.name, School.timezone)
        .join(School, School.id == Class.school_id)
        .join(TeachingAssignment, TeachingAssignment.class_id == Class.id)
        .join(Schedule, Schedule.assignment_id == TeachingAssignment.id)
        .where(Schedule.date == survey_date)
        .distinct()
        .order_by(Class.code, Class.id)
    )

    return session.execute(stmt).all()


def get_subject_names(
    session: Session,
    class_id: int,
    survey_date: date,
) -> list[str]:
    """Получает предметы из расписания конкретного класса на указанную дату."""

    stmt = (
        select(Subject.name)
        .join(TeachingAssignment, TeachingAssignment.subject_id == Subject.id)
        .join(Schedule, Schedule.assignment_id == TeachingAssignment.id)
        .where(
            TeachingAssignment.class_id == class_id,
            Schedule.date == survey_date,
        )
        .distinct()
        .order_by(Subject.name)
    )

    return list(session.scalars(stmt).all())


def prepare_question_options(
    session: Session,
    question: SurveyQuestion,
    class_id: int,
    survey_date: date,
):
    """Подготавливает варианты ответа для будущего экземпляра вопроса."""

    if question.options_source == "static":
        options = session.scalars(
            select(SurveyQuestionOption)
            .where(SurveyQuestionOption.question_id == question.id)
            .order_by(
                SurveyQuestionOption.sort_order,
                SurveyQuestionOption.id,
            )
        ).all()

        if not options:
            raise ValueError(
                f"У статического вопроса №{question.sort_order} "
                f"«{question.title}» нет вариантов ответа."
            )

        prepared = [
            {
                "source_option_id": option.id,
                "title": option.title,
                "sort_order": option.sort_order,
                "is_exclusive": option.is_exclusive,
            }
            for option in options
        ]

    elif question.options_source == "subjects":
        subject_names = get_subject_names(
            session,
            class_id,
            survey_date,
        )

        if not subject_names:
            raise ValueError(
                f"Для класса ID {class_id} на {survey_date} "
                "не найдены предметы в расписании."
            )

        if NO_SUBJECT_OPTION in subject_names:
            raise ValueError(
                f"В расписании класса ID {class_id} уже есть предмет "
                f"с зарезервированным названием «{NO_SUBJECT_OPTION}»."
            )

        prepared = [
            {
                "source_option_id": None,
                "title": name,
                "sort_order": index,
                "is_exclusive": False,
            }
            for index, name in enumerate(subject_names, start=1)
        ]

        prepared.append(
            {
                "source_option_id": None,
                "title": NO_SUBJECT_OPTION,
                "sort_order": len(prepared) + 1,
                "is_exclusive": True,
            }
        )

    else:
        raise ValueError(
            f"У вопроса №{question.sort_order} неизвестный источник вариантов: "
            f"{question.options_source!r}."
        )

    if question.min_answer < 1 or question.max_answer < question.min_answer:
        raise ValueError(
            f"Некорректные ограничения ответов у вопроса №{question.sort_order}."
        )

    if question.answer_type == "single":
        if question.min_answer != 1 or question.max_answer != 1:
            raise ValueError(
                f"Для одиночного выбора у вопроса №{question.sort_order} "
                "должны быть min_answer=max_answer=1."
            )

    elif question.answer_type != "multiple":
        raise ValueError(
            f"Неизвестный тип ответа у вопроса №{question.sort_order}: "
            f"{question.answer_type!r}."
        )

    if question.max_answer > len(prepared):
        raise ValueError(
            f"У вопроса №{question.sort_order} max_answer={question.max_answer}, "
            f"но доступно только {len(prepared)} вариантов."
        )

    if sum(1 for option in prepared if option["is_exclusive"]) > 1:
        raise ValueError(
            f"У вопроса №{question.sort_order} "
            "больше одного исключительного варианта."
        )

    return prepared


def _create_instance(
    session: Session,
    class_id: int,
    survey_date: date,
    opens_at: datetime,
    closes_at: datetime,
    questions: list,
) -> int:
    """Создаёт экземпляр опроса и копирует в него вопросы и варианты."""

    instance = SurveyInstance(
        class_id=class_id,
        survey_date=survey_date,
        opens_at=opens_at,
        closes_at=closes_at,
        status="open",
    )

    session.add(instance)
    session.flush()

    for question, options in questions:
        instance_question = SurveyInstanceQuestion(
            instance_id=instance.id,
            source_question_id=question.id,
            title=question.title,
            bot_text=question.bot_text,
            answer_type=question.answer_type,
            min_answer=question.min_answer,
            max_answer=question.max_answer,
            sort_order=question.sort_order,
        )

        session.add(instance_question)
        session.flush()

        for option in options:
            session.add(
                SurveyInstanceOption(
                    instance_question_id=instance_question.id,
                    source_option_id=option["source_option_id"],
                    title=option["title"],
                    sort_order=option["sort_order"],
                    is_exclusive=option["is_exclusive"],
                )
            )

    return instance.id


def create_survey_instances_for_date(
    session: Session,
    survey_date: date,
    now: datetime | None = None,
    enforce_time_window: bool = True,
) -> dict:
    """
    Создаёт экземпляры опросов для всех классов с расписанием на дату.

    Каждый класс обрабатывается в отдельной транзакции.
    Уже существующие экземпляры не создаются повторно.

    Для автоматического планировщика:
    - учитывается локальное время каждой школы;
    - опрос создаётся не раньше 18:00;
    - просроченные опросы не создаются.
    """

    if now is None:
        now = datetime.now(ZoneInfo("UTC"))

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Время now должно содержать часовой пояс.")

    classes = get_classes_with_schedule(session, survey_date)

    result = {
        "created": [],
        "skipped": [],
        "errors": [],
    }

    if not classes:
        return result

    questions = session.scalars(
        select(SurveyQuestion)
        .where(SurveyQuestion.is_active.is_(True))
        .order_by(SurveyQuestion.sort_order, SurveyQuestion.id)
    ).all()

    if not questions:
        result["errors"].append("В базе нет активных шаблонов вопросов.")
        return result

    for class_id, class_code, class_name, timezone_name in classes:
        try:
            if not timezone_name:
                raise ValueError("У школы не задан часовой пояс.")

            try:
                school_timezone = ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(
                    f"Неизвестный часовой пояс: {timezone_name!r}."
                ) from exc

            opens_at = datetime.combine(
                survey_date,
                time(18, 0),
                tzinfo=school_timezone,
            )

            closes_at = datetime.combine(
                survey_date + timedelta(days=1),
                time(18, 0),
                tzinfo=school_timezone,
            )

            if enforce_time_window:
                now_local = now.astimezone(school_timezone)

                if now_local < opens_at:
                    result["skipped"].append(
                        {
                            "class_id": class_id,
                            "class_code": class_code,
                            "reason": "Время открытия ещё не наступило.",
                        }
                    )
                    continue

                if now_local >= closes_at:
                    result["skipped"].append(
                        {
                            "class_id": class_id,
                            "class_code": class_code,
                            "reason": "Срок проведения опроса уже истёк.",
                        }
                    )
                    continue

            existing_id = session.scalar(
                select(SurveyInstance.id).where(
                    SurveyInstance.class_id == class_id,
                    SurveyInstance.survey_date == survey_date,
                )
            )

            if existing_id is not None:
                result["skipped"].append(
                    {
                        "class_id": class_id,
                        "class_code": class_code,
                        "reason": f"Экземпляр уже существует (ID {existing_id}).",
                    }
                )
                continue

            prepared_questions = []

            for question in questions:
                options = prepare_question_options(
                    session,
                    question,
                    class_id,
                    survey_date,
                )
                prepared_questions.append((question, options))

            # SAVEPOINT позволяет откатить только создание одного класса.
            with session.begin_nested():
                instance_id = _create_instance(
                    session=session,
                    class_id=class_id,
                    survey_date=survey_date,
                    opens_at=opens_at,
                    closes_at=closes_at,
                    questions=prepared_questions,
                )

                session.flush()

            session.commit()

            result["created"].append(
                {
                    "class_id": class_id,
                    "class_code": class_code,
                    "class_name": class_name,
                    "instance_id": instance_id,
                }
            )

        except IntegrityError:
            session.rollback()

            # Возможен конфликт, если другой процесс одновременно
            # создал экземпляр того же класса и даты.
            existing_id = session.scalar(
                select(SurveyInstance.id).where(
                    SurveyInstance.class_id == class_id,
                    SurveyInstance.survey_date == survey_date,
                )
            )

            if existing_id is not None:
                result["skipped"].append(
                    {
                        "class_id": class_id,
                        "class_code": class_code,
                        "reason": (
                            "Экземпляр был создан параллельным процессом "
                            f"(ID {existing_id})."
                        ),
                    }
                )
            else:
                result["errors"].append(
                    {
                        "class_id": class_id,
                        "class_code": class_code,
                        "error": "Ошибка ограничения целостности базы данных.",
                    }
                )

        except Exception as exc:
            session.rollback()

            result["errors"].append(
                {
                    "class_id": class_id,
                    "class_code": class_code,
                    "error": str(exc),
                }
            )

    return result


def create_survey_notifications(
    session: Session,
    instance: SurveyInstance,
) -> dict[str, int]:
    """
    Создаёт уведомления для учеников, зачисленных в класс
    на дату проведения опроса.

    Ученик включается в рассылку только при наличии ровно
    одной активной записи StudentEnrollment на дату опроса.

    Student.class_id для определения получателей не используется.
    """

    # Сначала находим учеников, у которых есть зачисление
    # именно в класс текущего опроса на нужную дату.
    target_student_ids = (
        select(StudentEnrollment.student_id)
        .where(
            StudentEnrollment.class_id == instance.class_id,
            StudentEnrollment.start_date <= instance.survey_date,
            (
                StudentEnrollment.end_date.is_(None)
                | (StudentEnrollment.end_date >= instance.survey_date)
            ),
        )
        .distinct()
    )

    # Для каждого такого ученика проверяем все его активные
    # зачисления, включая записи в других классах.
    enrollment_rows = session.execute(
        select(
            StudentEnrollment.student_id,
            func.count(StudentEnrollment.id).label("enrollment_count"),
            func.min(StudentEnrollment.class_id).label("enrolled_class_id"),
        )
        .where(
            StudentEnrollment.student_id.in_(target_student_ids),
            StudentEnrollment.start_date <= instance.survey_date,
            (
                StudentEnrollment.end_date.is_(None)
                | (StudentEnrollment.end_date >= instance.survey_date)
            ),
        )
        .group_by(StudentEnrollment.student_id)
    ).all()

    created = 0
    skipped = 0

    for row in enrollment_rows:
        if row.enrollment_count != 1 or row.enrolled_class_id != instance.class_id:
            skipped += 1
            continue

        student_id = row.student_id

        student_data = session.execute(
            select(Student.id, User.sferum_id)
            .join(User, User.id == Student.user_id)
            .where(
                Student.id == student_id,
                User.is_demo.is_(False),
            )
        ).first()

        if student_data is None:
            skipped += 1
            continue

        sferum_id = student_data.sferum_id

        if not sferum_id or not sferum_id.isdigit():
            skipped += 1
            continue

        if int(sferum_id) <= 0:
            skipped += 1
            continue

        notification = SurveyNotification(
            instance_id=instance.id,
            student_id=student_id,
            status="pending",
            attempt_count=0,
        )

        try:
            with session.begin_nested():
                session.add(notification)
                session.flush()

            created += 1
        except IntegrityError:
            skipped += 1

    return {
        "created": created,
        "skipped": skipped,
    }


def close_expired_survey_instances(
    session: Session,
    now: datetime | None = None,
) -> int:
    """
    Закрывает открытые экземпляры опросов, срок которых истёк.

    Используется UTC, чтобы корректно сравнивать даты школ
    с разными часовыми поясами.

    Возвращает количество закрытых экземпляров.
    """

    if now is None:
        now = datetime.now(ZoneInfo("UTC"))

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Время now должно содержать часовой пояс.")

    now_utc = now.astimezone(ZoneInfo("UTC"))

    result = session.execute(
        update(SurveyInstance)
        .where(
            SurveyInstance.status == "open",
            SurveyInstance.closes_at <= now_utc,
        )
        .values(status="closed")
    )

    closed_count = result.rowcount or 0
    session.commit()

    return closed_count
