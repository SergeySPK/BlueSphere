from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging
from contextlib import nullcontext

from sqlalchemy import and_, func, select, delete

from database import SessionLocal
from models import (
    User,
    Student,
    StudentEnrollment,
    Class,
    School,
    SurveyInstance,
    SurveyInstanceQuestion,
    SurveyInstanceOption,
    SurveyResponse,
    SurveyResponseOption,
    SurveyNotification,
)

logger = logging.getLogger(__name__)


def _is_survey_open(instance, school_timezone: str, now=None) -> bool:
    """
    Проверяет, находится ли опрос в допустимом временном интервале.

    Все даты должны содержать информацию о часовом поясе.
    Отсутствующий или некорректный часовой пояс означает отказ в доступе.
    """

    if not school_timezone:
        return False

    try:
        ZoneInfo(school_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return False

    opens_at = instance.opens_at
    closes_at = instance.closes_at

    if opens_at is None or closes_at is None:
        return False

    # Не пытаемся угадывать часовой пояс для некорректных дат.
    if opens_at.tzinfo is None or opens_at.utcoffset() is None:
        return False

    if closes_at.tzinfo is None or closes_at.utcoffset() is None:
        return False

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        return False

    now_utc = now.astimezone(timezone.utc)
    opens_at_utc = opens_at.astimezone(timezone.utc)
    closes_at_utc = closes_at.astimezone(timezone.utc)

    return opens_at_utc <= now_utc < closes_at_utc


def get_effective_survey_status(instance, school_timezone: str, now=None) -> str:
    """
    Возвращает актуальный статус опроса для API.

    Не изменяет статус в базе данных.
    Просроченные открытые опросы возвращает как закрытые.
    """
    if instance.status != "open":
        return instance.status

    if not school_timezone:
        return "closed"

    try:
        ZoneInfo(school_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return "closed"

    opens_at = instance.opens_at
    closes_at = instance.closes_at

    if opens_at is None or closes_at is None:
        return "closed"

    if (
        opens_at.tzinfo is None
        or opens_at.utcoffset() is None
        or closes_at.tzinfo is None
        or closes_at.utcoffset() is None
    ):
        return "closed"

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        return "closed"

    now_utc = now.astimezone(timezone.utc)
    closes_at_utc = closes_at.astimezone(timezone.utc)

    if now_utc >= closes_at_utc:
        return "closed"

    return "open"


def get_available_survey(max_user_id: int, *, db=None):
    """
    Находит доступный опрос для ученика MAX.

    Проверяет:
    - наличие пользователя и роли ученика;
    - ровно одно подходящее зачисление на дату опроса;
    - статус и временные границы опроса;
    - корректность часового пояса школы;
    - наличие вопросов в экземпляре.

    Возвращает словарь с данными опроса или None.
    """

    owns_session = db is None

    if owns_session:
        db = SessionLocal()

    try:
        # 1. Получаем открытые опросы и количество
        # подходящих зачислений для найденного ученика.
        question_count = (
            select(func.count(SurveyInstanceQuestion.id))
            .where(
                SurveyInstanceQuestion.instance_id == SurveyInstance.id
            )
            .scalar_subquery()
        )

        instances = db.execute(
            select(
                Student.id.label("student_id"),
                SurveyInstance,
                School.timezone,
                func.count(StudentEnrollment.id).label("enrollment_count"),
                question_count.label("questions_count"),
            )
            .select_from(User)
            .join(
                Student,
                Student.user_id == User.id,
            )
            .join(
                SurveyInstance,
                SurveyInstance.status == "open",
            )
            .join(
                Class,
                Class.id == SurveyInstance.class_id,
            )
            .join(
                School,
                School.id == Class.school_id,
            )
            .outerjoin(
                StudentEnrollment,
                and_(
                    StudentEnrollment.student_id == Student.id,
                    StudentEnrollment.class_id == SurveyInstance.class_id,
                    StudentEnrollment.start_date <= SurveyInstance.survey_date,
                    (
                        StudentEnrollment.end_date.is_(None)
                        | (
                            StudentEnrollment.end_date
                            >= SurveyInstance.survey_date
                        )
                    ),
                ),
            )
            .where(
                User.sferum_id == str(max_user_id),
            )
            .group_by(
                SurveyInstance.id,
                School.timezone,
                Student.id,
            )
            .order_by(SurveyInstance.survey_date)
        ).all()

        available_instances = []

        # 3. Проверяем каждый экземпляр без дополнительных SQL-запросов.
        for student_id_value, instance, school_timezone, enrollment_count, questions_count in instances:

            # Доступ разрешён только при ровно одном зачислении.
            if enrollment_count != 1:
                continue

            # Не используем часовой пояс сервера как запасной вариант.
            if not _is_survey_open(instance, school_timezone):
                continue

            available_instances.append(
                {
                    "instance": instance,
                    "timezone": ZoneInfo(school_timezone),
                    "opens_at": instance.opens_at,
                    "closes_at": instance.closes_at,
                    "questions_count": questions_count,
                    "student_id": student_id_value,
                }
            )

        if not available_instances:
            return None

        # 4. Возвращаем первый доступный экземпляр,
        # у которого есть вопросы.
        for item in available_instances:
            instance = item["instance"]
            questions_count = item["questions_count"]

            if questions_count == 0:
                continue

            return {
                "instance_id": instance.id,
                "class_id": instance.class_id,
                "survey_date": instance.survey_date,
                "opens_at": item["opens_at"],
                "closes_at": item["closes_at"],
                "questions_count": questions_count,
                "student_id": item["student_id"],
            }

        return None

    finally:
        if owns_session:
            db.close()


def get_next_question(max_user_id: int, instance_id: int, *, db=None):
    """
    Возвращает первый вопрос, на который ученик ещё не ответил.

    Если все вопросы отправлены, возвращает None.
    Функция только читает БД.
    """

    owns_session = db is None

    if owns_session:
        db = SessionLocal()

    try:
        # Подзапрос: считаем количество подходящих зачислений
        # ученика в класс на дату конкретного опроса.
        enrollment_count = (
            select(func.count(StudentEnrollment.id))
            .where(
                StudentEnrollment.student_id == Student.id,
                StudentEnrollment.class_id == SurveyInstance.class_id,
                StudentEnrollment.start_date <= SurveyInstance.survey_date,
                (
                    StudentEnrollment.end_date.is_(None)
                    | (StudentEnrollment.end_date >= SurveyInstance.survey_date)
                ),
            )
            .correlate(Student, SurveyInstance)
            .scalar_subquery()
        )

        # Одним запросом находим первый незавершённый вопрос.
        result = db.execute(
            select(
                Student.id.label("student_id"),
                SurveyInstance.id.label("instance_id"),
                SurveyInstance.opens_at,
                SurveyInstance.closes_at,
                School.timezone.label("school_timezone"),
                SurveyInstanceQuestion.id.label("question_id"),
                SurveyInstanceQuestion.title,
                SurveyInstanceQuestion.bot_text,
                SurveyInstanceQuestion.answer_type,
                SurveyInstanceQuestion.min_answer,
                SurveyInstanceQuestion.max_answer,
            )
            .select_from(User)
            .join(Student, Student.user_id == User.id)
            .join(
                SurveyInstance,
                SurveyInstance.id == instance_id,
            )
            .join(Class, Class.id == SurveyInstance.class_id)
            .join(School, School.id == Class.school_id)
            .join(
                SurveyInstanceQuestion,
                SurveyInstanceQuestion.instance_id == SurveyInstance.id,
            )
            .outerjoin(
                SurveyResponse,
                and_(
                    SurveyResponse.instance_question_id == SurveyInstanceQuestion.id,
                    SurveyResponse.student_id == Student.id,
                ),
            )
            .where(
                User.sferum_id == str(max_user_id),
                SurveyInstance.status == "open",
                enrollment_count == 1,
                (SurveyResponse.id.is_(None) | (SurveyResponse.status == "draft")),
            )
            .order_by(SurveyInstanceQuestion.sort_order)
            .limit(1)
        ).first()

        if result is None:
            return None

        if not _is_survey_open(result, result.school_timezone):
            return None

        return {
            "student_id": result.student_id,
            "instance_id": result.instance_id,
            "question_id": result.question_id,
            "title": result.title,
            "bot_text": result.bot_text,
            "answer_type": result.answer_type,
            "min_answer": result.min_answer,
            "max_answer": result.max_answer,
        }

    finally:
        if owns_session:
            db.close()


def get_next_question_payload(
    student_id: int,
    instance_id: int,
    *,
    db,
):
    """
    Одним запросом получает первый незавершённый вопрос,
    его варианты и выбранные учеником варианты черновика.
    """

    # Проверяем, что ученик был зачислен в класс на дату опроса.
    enrollment_count = (
        select(func.count(StudentEnrollment.id))
        .where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.class_id == SurveyInstance.class_id,
            StudentEnrollment.start_date <= SurveyInstance.survey_date,
            (
                StudentEnrollment.end_date.is_(None)
                | (StudentEnrollment.end_date >= SurveyInstance.survey_date)
            ),
        )
        .correlate(SurveyInstance)
        .scalar_subquery()
    )

    # Находим ID первого незавершённого вопроса.
    first_question_id = (
        select(SurveyInstanceQuestion.id)
        .select_from(SurveyInstance)
        .join(
            SurveyInstanceQuestion,
            SurveyInstanceQuestion.instance_id == SurveyInstance.id,
        )
        .outerjoin(
            SurveyResponse,
            and_(
                SurveyResponse.instance_question_id == SurveyInstanceQuestion.id,
                SurveyResponse.student_id == student_id,
            ),
        )
        .where(
            SurveyInstance.id == instance_id,
            SurveyInstance.status == "open",
            enrollment_count == 1,
            (
                SurveyResponse.id.is_(None)
                | (SurveyResponse.status == "draft")
            ),
        )
        .order_by(SurveyInstanceQuestion.sort_order)
        .limit(1)
        .scalar_subquery()
    )

    # Проверяем, выбран ли конкретный вариант в черновике.
    is_selected = (
        select(SurveyResponseOption.id)
        .where(
            SurveyResponseOption.response_id == SurveyResponse.id,
            SurveyResponseOption.option_id == SurveyInstanceOption.id,
            SurveyResponseOption.instance_question_id
            == SurveyInstanceQuestion.id,
        )
        .exists()
    )

    rows = db.execute(
        select(
            SurveyInstance.opens_at,
            SurveyInstance.closes_at,
            School.timezone.label("school_timezone"),
            SurveyInstanceQuestion.id.label("question_id"),
            SurveyInstanceQuestion.title,
            SurveyInstanceQuestion.bot_text,
            SurveyInstanceQuestion.answer_type,
            SurveyInstanceQuestion.min_answer,
            SurveyInstanceQuestion.max_answer,
            SurveyInstanceOption.id.label("option_id"),
            SurveyInstanceOption.title.label("option_title"),
            SurveyInstanceOption.is_exclusive,
            is_selected.label("is_selected"),
        )
        .select_from(SurveyInstanceQuestion)
        .join(
            SurveyInstance,
            SurveyInstance.id == SurveyInstanceQuestion.instance_id,
        )
        .join(Class, Class.id == SurveyInstance.class_id)
        .join(School, School.id == Class.school_id)
        .outerjoin(
            SurveyResponse,
            and_(
                SurveyResponse.instance_question_id == SurveyInstanceQuestion.id,
                SurveyResponse.student_id == student_id,
                SurveyResponse.status == "draft",
            ),
        )
        .outerjoin(
            SurveyInstanceOption,
            SurveyInstanceOption.instance_question_id
            == SurveyInstanceQuestion.id,
        )
        .where(SurveyInstanceQuestion.id == first_question_id)
        .order_by(SurveyInstanceOption.sort_order)
    ).all()

    if not rows:
        return None

    first_row = rows[0]

    if not _is_survey_open(first_row, first_row.school_timezone):
        return None

    options = []
    selected_ids = []

    for row in rows:
        if row.option_id is None:
            continue

        options.append({
            "id": row.option_id,
            "title": row.option_title,
            "is_exclusive": row.is_exclusive,
        })

        if row.is_selected:
            selected_ids.append(row.option_id)

    question = {
        "student_id": student_id,
        "instance_id": instance_id,
        "question_id": first_row.question_id,
        "title": first_row.title,
        "bot_text": first_row.bot_text,
        "answer_type": first_row.answer_type,
        "min_answer": first_row.min_answer,
        "max_answer": first_row.max_answer,
    }

    return {
        "question": question,
        "options": options,
        "selected_ids": (
            selected_ids
            if first_row.answer_type == "multiple"
            else []
        ),
    }


def get_question_options(question_id: int, *, db=None):
    """Получает варианты ответа для вопроса опроса."""

    owns_session = db is None

    if owns_session:
        db = SessionLocal()

    try:
        options = db.scalars(
            select(SurveyInstanceOption)
            .where(SurveyInstanceOption.instance_question_id == question_id)
            .order_by(SurveyInstanceOption.sort_order)
        ).all()

        return [
            {
                "id": option.id,
                "title": option.title,
                "is_exclusive": option.is_exclusive,
            }
            for option in options
        ]

    finally:
        if owns_session:
            db.close()


def get_selected_options(
    max_user_id: int,
    question_id: int,
    *,
    db=None,
):
    """Возвращает ID вариантов, выбранных учеником в черновике."""

    owns_session = db is None

    if owns_session:
        db = SessionLocal()

    try:
        return db.scalars(
            select(SurveyResponseOption.option_id)
            .join(
                SurveyResponse,
                SurveyResponse.id == SurveyResponseOption.response_id,
            )
            .join(
                Student,
                Student.id == SurveyResponse.student_id,
            )
            .join(
                User,
                User.id == Student.user_id,
            )
            .where(
                User.sferum_id == str(max_user_id),
                SurveyResponse.instance_question_id == question_id,
                SurveyResponse.status == "draft",
            )
        ).all()

    finally:
        if owns_session:
            db.close()


def _get_survey_context(db, max_user_id: int, instance_id: int):
    """
    Получает ученика и экземпляр опроса,
    одновременно проверяя доступ и временные границы.

    Экземпляр опроса блокируется на время транзакции.
    Возвращает (student_id, instance) или None.
    """

    enrollment_count = (
        select(func.count(StudentEnrollment.id))
        .where(
            StudentEnrollment.student_id == Student.id,
            StudentEnrollment.class_id == SurveyInstance.class_id,
            StudentEnrollment.start_date <= SurveyInstance.survey_date,
            (
                StudentEnrollment.end_date.is_(None)
                | (StudentEnrollment.end_date >= SurveyInstance.survey_date)
            ),
        )
        .correlate(Student, SurveyInstance)
        .scalar_subquery()
    )

    result = db.execute(
        select(
            Student.id,
            SurveyInstance,
            School.timezone,
            enrollment_count.label("enrollment_count"),
        )
        .select_from(User)
        .join(Student, Student.user_id == User.id)
        .join(
            SurveyInstance,
            SurveyInstance.id == instance_id,
        )
        .join(Class, Class.id == SurveyInstance.class_id)
        .join(School, School.id == Class.school_id)
        .where(
            User.sferum_id == str(max_user_id),
            SurveyInstance.status == "open",
        )
        .with_for_update(read=True, of=SurveyInstance)
    ).first()

    if result is None:
        return None

    student_id, instance, school_timezone, count = result

    # Доступ разрешён только при ровно одном зачислении.
    if count != 1:
        return None

    if not _is_survey_open(instance, school_timezone):
        return None

    return student_id, instance


def _get_first_unfinished_question(db, student_id: int, instance_id: int):
    """
    Находит первый вопрос, который ещё не отправлен учеником.

    Возвращает объект вопроса или None.
    """

    return db.scalar(
        select(SurveyInstanceQuestion)
        .outerjoin(
            SurveyResponse,
            and_(
                SurveyResponse.instance_question_id == SurveyInstanceQuestion.id,
                SurveyResponse.student_id == student_id,
            ),
        )
        .where(
            SurveyInstanceQuestion.instance_id == instance_id,
            (SurveyResponse.id.is_(None) | (SurveyResponse.status == "draft")),
        )
        .order_by(SurveyInstanceQuestion.sort_order)
        .limit(1)
    )


def save_single_answer(
    max_user_id: int,
    instance_id: int,
    question_id: int,
    option_id: int,
    *,
    db=None,
):
    """
    Сохраняет ответ на вопрос с одним вариантом выбора.

    Возвращает:
    - submitted — ответ сохранён;
    - already_submitted — ответ уже отправлен;
    - invalid — данные или условия не прошли проверку.
    """

    owns_session = db is None

    if owns_session:
        db = SessionLocal()

    try:
        with (db.begin() if owns_session else nullcontext()):
            # Проверяем ученика, экземпляр опроса,
            # историческое зачисление и временные границы.
            context = _get_survey_context(
                db,
                max_user_id,
                instance_id,
            )

            if context is None:
                return "invalid"

            student_id, instance = context

            # Одним запросом проверяем существующий ответ
            # и блокируем его от параллельного изменения.
            existing_response = db.scalar(
                select(SurveyResponse)
                .where(
                    SurveyResponse.instance_question_id == question_id,
                    SurveyResponse.student_id == student_id,
                )
                .with_for_update()
            )

            if existing_response is not None:
                if existing_response.status == "submitted":
                    return "already_submitted"

                # Для single-choice черновик не предусмотрен.
                return "invalid"

            # Находим первый незавершённый вопрос.
            first_question = _get_first_unfinished_question(
                db,
                student_id,
                instance.id,
            )

            # Проверяем, что ученик отвечает именно на него.
            if first_question is None:
                return "invalid"

            if first_question.id != question_id:
                return "invalid"

            question = first_question

            # Проверяем тип и ограничения вопроса.
            if question.answer_type != "single":
                return "invalid"

            if question.min_answer != 1 or question.max_answer != 1:
                return "invalid"

            # Проверяем, что вариант принадлежит вопросу.
            option = db.scalar(
                select(SurveyInstanceOption.id).where(
                    SurveyInstanceOption.id == option_id,
                    SurveyInstanceOption.instance_question_id == question.id,
                )
            )

            if option is None:
                return "invalid"

            # Создаём сразу завершённый ответ.
            response = SurveyResponse(
                instance_question_id=question.id,
                student_id=student_id,
                status="submitted",
                submitted_at=datetime.now(timezone.utc),
            )

            db.add(response)
            db.flush()

            db.add(
                SurveyResponseOption(
                    response_id=response.id,
                    option_id=option,
                    instance_question_id=question.id,
                )
            )

        return "submitted"

    except Exception:
        if owns_session:
            db.rollback()
            logger.exception("Ошибка при сохранении ответа на опрос")
            return "invalid"

        raise

    finally:
        if owns_session:
            db.close()


def toggle_multiple_answer(
    max_user_id: int,
    instance_id: int,
    question_id: int,
    option_id: int,
    *,
    db=None,
    question_context: dict | None = None,
    student_id: int | None = None,
):
    """
    Переключает выбранный вариант в черновике multiple-choice.

    Возвращает:
    - saved — изменение сохранено;
    - already_submitted — ответ уже отправлен;
    - limit_reached — достигнут лимит вариантов;
    - invalid — данные или условия не прошли проверку.
    """

    owns_session = db is None

    if owns_session:
        db = SessionLocal()

    try:
        with (db.begin() if owns_session else nullcontext()):
            # Если student_id уже передан из callback,
            # используем его напрямую. Для остальных вызовов
            # сохраняем поиск через User → Student.
            student_id_expr = (
                student_id
                if student_id is not None
                else (
                    select(Student.id)
                    .join(User, User.id == Student.user_id)
                    .where(User.sferum_id == str(max_user_id))
                    .scalar_subquery()
                )
            )

            # Подзапрос находит первый незавершённый вопрос.
            first_question_id = (
                select(SurveyInstanceQuestion.id)
                .outerjoin(
                    SurveyResponse,
                    and_(
                        SurveyResponse.instance_question_id
                        == SurveyInstanceQuestion.id,
                        SurveyResponse.student_id == student_id_expr,
                    ),
                )
                .where(
                    SurveyInstanceQuestion.instance_id == SurveyInstance.id,
                    (
                        SurveyResponse.id.is_(None)
                        | (SurveyResponse.status == "draft")
                    ),
                )
                .order_by(SurveyInstanceQuestion.sort_order)
                .limit(1)
                .scalar_subquery()
            )

            # Повторно проверяем историческое зачисление.
            # Проверку нельзя убирать: оно могло измениться
            # после получения доступного опроса.
            enrollment_count = (
                select(func.count(StudentEnrollment.id))
                .where(
                    StudentEnrollment.student_id == student_id_expr,
                    StudentEnrollment.class_id == SurveyInstance.class_id,
                    StudentEnrollment.start_date <= SurveyInstance.survey_date,
                    (
                        StudentEnrollment.end_date.is_(None)
                        | (
                            StudentEnrollment.end_date
                            >= SurveyInstance.survey_date
                        )
                    ),
                )
                .correlate(SurveyInstance)
                .scalar_subquery()
            )

            # Получаем экземпляр, школу, проверку зачисления,
            # первый вопрос и его варианты одним запросом.
            rows = db.execute(
                select(
                    student_id_expr,
                    SurveyInstance,
                    School.timezone,
                    enrollment_count.label("enrollment_count"),
                    SurveyInstanceQuestion,
                    SurveyInstanceOption,
                )
                .select_from(SurveyInstance)
                .join(Class, Class.id == SurveyInstance.class_id)
                .join(School, School.id == Class.school_id)
                .outerjoin(
                    SurveyInstanceQuestion,
                    SurveyInstanceQuestion.id == first_question_id,
                )
                .outerjoin(
                    SurveyInstanceOption,
                    SurveyInstanceOption.instance_question_id
                    == SurveyInstanceQuestion.id,
                )
                .where(
                    SurveyInstance.id == instance_id,
                    SurveyInstance.status == "open",
                )
                .order_by(SurveyInstanceOption.sort_order)
                .with_for_update(read=True, of=SurveyInstance)
            ).all()

            if not rows:
                return "invalid"

            student_id, instance, school_timezone, count = rows[0][:4]
            question = rows[0][4]

            # Проверяем историческое зачисление.
            if count != 1:
                return "invalid"

            # Проверяем временные границы и часовой пояс.
            if not _is_survey_open(instance, school_timezone):
                return "invalid"

            # Одним запросом находим и блокируем ответ,
            # одновременно загружая выбранные варианты.
            response_rows = db.execute(
                select(
                    SurveyResponse,
                    SurveyResponseOption,
                    SurveyInstanceOption.is_exclusive,
                )
                .outerjoin(
                    SurveyResponseOption,
                    and_(
                        SurveyResponseOption.response_id == SurveyResponse.id,
                        SurveyResponseOption.instance_question_id == question_id,
                    ),
                )
                .outerjoin(
                    SurveyInstanceOption,
                    SurveyInstanceOption.id == SurveyResponseOption.option_id,
                )
                .where(
                    SurveyResponse.instance_question_id == question_id,
                    SurveyResponse.student_id == student_id,
                )
                .with_for_update(of=SurveyResponse)
            ).all()

            response = (
                response_rows[0][0]
                if response_rows
                else None
            )

            if response is not None and response.status == "submitted":
                return "already_submitted"

            # Проверяем, что callback относится именно
            # к первому незавершённому вопросу.
            if question is None or question.id != question_id:
                return "invalid"

            # Извлекаем варианты из результата JOIN.
            options = [
                row[5]
                for row in rows
                if row[5] is not None
            ]

            if question.answer_type != "multiple":
                return "invalid"

            if (
                question.min_answer < 1
                or question.max_answer < question.min_answer
            ):
                return "invalid"

            option = next(
                (item for item in options if item.id == option_id),
                None,
            )

            if option is None:
                return "invalid"

            options_data = [
                {
                    "id": item.id,
                    "title": item.title,
                    "is_exclusive": item.is_exclusive,
                }
                for item in options
            ]

            # Передаём данные уже проверенного текущего вопроса,
            # чтобы callback не выполнял повторный SELECT.
            if question_context is not None:
                question_context.update({
                    "student_id": student_id,
                    "instance_id": instance.id,
                    "question_id": question.id,
                    "options": options_data,
                    "title": question.title,
                    "bot_text": question.bot_text,
                    "answer_type": question.answer_type,
                    "min_answer": question.min_answer,
                    "max_answer": question.max_answer,
                })

            # Используем уже загруженный и заблокированный ответ.
            # Если ответа ещё нет — создаём черновик.
            if response is None:
                response = SurveyResponse(
                    instance_question_id=question.id,
                    student_id=student_id,
                    status="draft",
                )
                db.add(response)
                db.flush()

            elif response.status == "submitted":
                return "already_submitted"

            elif response.status != "draft":
                return "invalid"

            # Используем выбранные варианты, уже загруженные
            # вместе с ответом в предыдущем запросе.
            selected_rows = [
                (row[1], row[2])
                for row in response_rows
                if row[1] is not None
            ]

            selected = [row[0] for row in selected_rows]

            selected_by_option = {
                item.option_id: item
                for item in selected
            }

            selected_ids = [
                item.option_id
                for item in selected
            ]

            exclusive_ids = {
                item.option_id
                for item, is_exclusive in selected_rows
                if is_exclusive
            }

            # Если вариант уже выбран — снимаем выбор.
            if option.id in selected_by_option:
                db.delete(selected_by_option[option.id])
                if question_context is not None:
                    question_context["selected_ids"] = [
                        item_id for item_id in selected_ids
                        if item_id != option.id
                    ]
                return "saved"

            # Обрабатываем эксклюзивный вариант «Никакой».
            if option.is_exclusive:
                db.execute(
                    delete(SurveyResponseOption).where(
                        SurveyResponseOption.response_id == response.id
                    )
                )
                selected_ids = []

            else:
                # Считаем только обычные выбранные варианты.
                # Эксклюзивный вариант не должен влиять на лимит.
                selected_regular_count = sum(
                    1 for item in selected if item.option_id not in exclusive_ids
                )

                if selected_regular_count >= question.max_answer:
                    return "limit_reached"

                # Убираем «Никакой», если он был выбран ранее.
                if exclusive_ids:
                    db.execute(
                        delete(SurveyResponseOption).where(
                            SurveyResponseOption.response_id == response.id,
                            SurveyResponseOption.option_id.in_(exclusive_ids),
                        )
                    )

                    selected_ids = [
                        item_id for item_id in selected_ids
                        if item_id not in exclusive_ids
                    ]

            # Сохраняем новый вариант.
            db.add(
                SurveyResponseOption(
                    response_id=response.id,
                    option_id=option.id,
                    instance_question_id=question.id,
                )
            )

            selected_ids.append(option.id)
            if question_context is not None:
                question_context["selected_ids"] = selected_ids

        return "saved"

    except Exception:
        if owns_session:
            db.rollback()
            logger.exception("Ошибка при сохранении черновика ответа")
            return "invalid"

        raise

    finally:
        if owns_session:
            db.close()


def submit_multiple_answer(
    max_user_id: int,
    instance_id: int,
    question_id: int,
    *,
    db=None,
):
    """
    Завершает ответ на вопрос с несколькими вариантами.

    Возвращает:
    - submitted — ответ успешно отправлен;
    - already_submitted — ответ уже отправлен;
    - incomplete — недостаточно выбранных вариантов;
    - invalid — данные или условия не прошли проверку.
    """

    owns_session = db is None

    if owns_session:
        db = SessionLocal()

    try:
        with (db.begin() if owns_session else nullcontext()):
            # Проверяем ученика, экземпляр опроса,
            # историческое зачисление и временные границы.
            context = _get_survey_context(
                db,
                max_user_id,
                instance_id,
            )

            if context is None:
                return "invalid"

            student_id, instance = context

            # Загружаем ответ и блокируем его от параллельного изменения.
            # Одновременно проверяем, не был ли он уже отправлен.
            response = db.scalar(
                select(SurveyResponse)
                .where(
                    SurveyResponse.instance_question_id == question_id,
                    SurveyResponse.student_id == student_id,
                )
                .with_for_update()
            )

            if response is not None and response.status == "submitted":
                return "already_submitted"

            # Находим первый незавершённый вопрос.
            first_question = _get_first_unfinished_question(
                db,
                student_id,
                instance.id,
            )

            if first_question is None:
                return "invalid"

            if first_question.id != question_id:
                return "invalid"

            question = first_question

            # Проверяем тип и ограничения вопроса.
            if question.answer_type != "multiple":
                return "invalid"

            if question.min_answer < 1 or question.max_answer < question.min_answer:
                return "invalid"

            # Используем уже загруженный и заблокированный ответ.
            if response is None:
                return "incomplete"

            if response.status != "draft":
                return "invalid"

            # Получаем выбранные варианты и одновременно
            # проверяем, что они принадлежат этому вопросу.
            options = db.scalars(
                select(SurveyInstanceOption)
                .join(
                    SurveyResponseOption,
                    SurveyResponseOption.option_id == SurveyInstanceOption.id,
                )
                .where(
                    SurveyResponseOption.response_id == response.id,
                    SurveyResponseOption.instance_question_id == question.id,
                    SurveyInstanceOption.instance_question_id == question.id,
                )
            ).all()

            # Проверяем количество выбранных вариантов.
            if not (question.min_answer <= len(options) <= question.max_answer):
                return "incomplete"

            # Проверяем эксклюзивность варианта «Никакой».
            exclusive_selected = any(option.is_exclusive for option in options)

            if exclusive_selected and len(options) > 1:
                return "invalid"

            # Завершаем ответ.
            response.status = "submitted"
            response.submitted_at = datetime.now(timezone.utc)

        return "submitted"

    except Exception:
        if owns_session:
            db.rollback()
            logger.exception("Ошибка при отправке ответа на опрос")
            return "invalid"

        raise

    finally:
        if owns_session:
            db.close()


def _get_student_survey_notification(
    db,
    max_user_id: int,
    instance_id: int,
    *,
    student_id: int | None = None,
    lock: bool = False,
):
    """
    Находит запись уведомления конкретного ученика
    для указанного экземпляра опроса.
    """

    if student_id is not None:
        query = select(SurveyNotification).where(
            SurveyNotification.student_id == student_id,
            SurveyNotification.instance_id == instance_id,
        )
    else:
        # Обратная совместимость для остальных вызовов.
        query = (
            select(SurveyNotification)
            .join(
                Student,
                Student.id == SurveyNotification.student_id,
            )
            .join(
                User,
                User.id == Student.user_id,
            )
            .where(
                User.sferum_id == str(max_user_id),
                SurveyNotification.instance_id == instance_id,
            )
        )

    if lock:
        query = query.with_for_update()

    return db.scalar(query)


def get_survey_progress(
    max_user_id: int,
    instance_id: int,
) -> str | None:
    """
    Возвращает состояние прохождения опроса учеником.

    Возможные значения:
    - not_started;
    - in_progress;
    - completed;
    - closed.

    Если запись уведомления не найдена, возвращает None.
    """

    db = SessionLocal()

    try:
        notification = _get_student_survey_notification(
            db,
            max_user_id,
            instance_id,
        )

        if notification is None:
            return None

        return notification.progress_status

    except Exception:
        logger.exception(
            "Ошибка при получении состояния прохождения опроса"
        )
        return None

    finally:
        db.close()


def start_survey_progress(
    max_user_id: int,
    instance_id: int,
) -> str | None:
    """
    Переводит прохождение опроса из not_started в in_progress.

    Повторный вызов не сбрасывает существующий прогресс.
    Возвращает актуальное состояние или None, если запись
    уведомления не найдена.
    """

    db = SessionLocal()

    try:
        with db.begin():
            notification = _get_student_survey_notification(
                db,
                max_user_id,
                instance_id,
                lock=True,
            )

            if notification is None:
                return None

            if notification.progress_status == "not_started":
                notification.progress_status = "in_progress"
                notification.started_at = datetime.now(timezone.utc)

            return notification.progress_status

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка при начале прохождения опроса"
        )
        return None

    finally:
        db.close()


def save_survey_question_message_id(
    max_user_id: int,
    instance_id: int,
    message_id: str,
) -> bool:
    """
    Сохраняет ID последнего отправленного сообщения с вопросом MAX.
    """

    if not message_id:
        return False

    db = SessionLocal()

    try:
        with db.begin():
            notification = _get_student_survey_notification(
                db,
                max_user_id,
                instance_id,
                lock=True,
            )

            if notification is None:
                return False

            notification.max_message_id = str(message_id)

        return True

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка при сохранении ID сообщения с вопросом"
        )
        return False

    finally:
        db.close()


def complete_survey_progress(
    max_user_id: int,
    instance_id: int,
) -> bool:
    """
    Отмечает прохождение опроса как завершённое.
    """

    db = SessionLocal()

    try:
        with db.begin():
            notification = _get_student_survey_notification(
                db,
                max_user_id,
                instance_id,
                lock=True,
            )

            if notification is None:
                return False

            if notification.progress_status == "closed":
                return False

            if notification.progress_status != "completed":
                notification.progress_status = "completed"
                notification.completed_at = datetime.now(timezone.utc)

        return True

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка при завершении прохождения опроса"
        )
        return False

    finally:
        db.close()


def process_survey_callback(
    max_user_id: int,
    action: str,
    question_id: int,
    option_id: int | None = None,
):
    """
    Обрабатывает одно нажатие в MAX в рамках одной сессии
    и одной транзакции БД.

    Возвращает словарь:
    - status: результат операции;
    - instance_id: ID экземпляра опроса;
    - question: следующий вопрос или None;
    - options: варианты следующего вопроса;
    - selected_ids: выбранные варианты;
    - completed: завершён ли опрос.
    """

    db = SessionLocal()

    try:
        with db.begin():
            # 1. Проверяем доступность опроса.
            survey = get_available_survey(
                max_user_id,
                db=db,
            )

            if survey is None:
                return {"status": "closed"}

            instance_id = survey["instance_id"]

            # 2. Проверяем состояние прохождения.
            notification = _get_student_survey_notification(
                db,
                max_user_id,
                instance_id,
                student_id=survey["student_id"],
                lock=True,
            )

            progress = (
                notification.progress_status
                if notification is not None
                else None
            )

            if progress != "in_progress":
                return {
                    "status": "closed",
                    "instance_id": instance_id,
                }

            # 3. Сохраняем одиночный ответ.
            if action == "survey":
                if option_id is None:
                    return {"status": "invalid"}

                result = save_single_answer(
                    max_user_id=max_user_id,
                    instance_id=instance_id,
                    question_id=question_id,
                    option_id=option_id,
                    db=db,
                )

                if result != "submitted":
                    return {
                        "status": result,
                        "instance_id": instance_id,
                    }

                message = "Ответ сохранён!"

            # 4. Переключаем вариант multiple-choice.
            elif action == "survey_toggle":
                if option_id is None:
                    return {"status": "invalid"}

                question_context = {}

                result = toggle_multiple_answer(
                    max_user_id=max_user_id,
                    instance_id=instance_id,
                    question_id=question_id,
                    option_id=option_id,
                    db=db,
                    question_context=question_context,
                    student_id=survey["student_id"],
                )

                if result != "saved":
                    return {
                        "status": result,
                        "instance_id": instance_id,
                    }

                db.flush()

                # Используем данные вопроса, уже проверенного
                # внутри toggle_multiple_answer().
                question = question_context

                if (
                    question is None
                    or question["question_id"] != question_id
                ):
                    return {
                        "status": "question_unavailable",
                        "instance_id": instance_id,
                    }

                options = question["options"]

                selected_ids = question["selected_ids"]

                return {
                    "status": "saved",
                    "instance_id": instance_id,
                    "question": question,
                    "options": options,
                    "selected_ids": selected_ids,
                    "completed": False,
                }

            # 5. Отправляем multiple-choice ответ.
            elif action == "survey_done":
                result = submit_multiple_answer(
                    max_user_id=max_user_id,
                    instance_id=instance_id,
                    question_id=question_id,
                    db=db,
                )

                if result != "submitted":
                    return {
                        "status": result,
                        "instance_id": instance_id,
                    }

                message = "Ответ отправлен!"

            else:
                return {"status": "invalid"}

            # 6. Получаем следующий вопрос, варианты и выбранные ответы одним SQL-запросом.
            payload = get_next_question_payload(
                student_id=survey["student_id"],
                instance_id=instance_id,
                db=db,
            )

            # 7. Если вопросов больше нет — завершаем опрос.
            if payload is None:
                completed = False

                if (
                    notification is not None
                    and notification.progress_status != "closed"
                ):
                    notification.progress_status = "completed"
                    notification.completed_at = datetime.now(timezone.utc)
                    completed = True

                return {
                    "status": "submitted",
                    "instance_id": instance_id,
                    "question": None,
                    "options": [],
                    "selected_ids": [],
                    "completed": completed,
                    "message": message,
                }

            return {
                "status": "submitted",
                "instance_id": instance_id,
                "question": payload["question"],
                "options": payload["options"],
                "selected_ids": payload["selected_ids"],
                "completed": False,
                "message": message,
            }

    except Exception:
        logger.exception(
            "Ошибка при обработке callback опроса. "
            "MAX user_id: %s, question_id: %s, action: %s",
            max_user_id,
            question_id,
            action,
        )

        return {"status": "invalid"}

    finally:
        db.close()


def close_survey_progress(
    max_user_id: int,
    instance_id: int,
) -> bool:
    """
    Отмечает прохождение опроса как закрытое.
    """

    db = SessionLocal()

    try:
        with db.begin():
            notification = _get_student_survey_notification(
                db,
                max_user_id,
                instance_id,
                lock=True,
            )

            if notification is None:
                return False

            if notification.progress_status == "closed":
                return True

            notification.progress_status = "closed"
            notification.closed_at = datetime.now(timezone.utc)

        return True

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка при закрытии прохождения опроса"
        )
        return False

    finally:
        db.close()
