from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging

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

    return opens_at_utc <= now_utc <= closes_at_utc


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

    if now_utc > closes_at_utc:
        return "closed"

    return "open"


def get_available_survey(max_user_id: int):
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

    db = SessionLocal()

    try:
        # 1. Находим ученика по MAX ID одним запросом.
        student_id = db.scalar(
            select(Student.id)
            .join(User, User.id == Student.user_id)
            .where(User.sferum_id == str(max_user_id))
        )

        if student_id is None:
            return None

        # 2. Получаем открытые опросы и количество
        # подходящих зачислений для каждого из них.
        instances = db.execute(
            select(
                SurveyInstance,
                School.timezone,
                func.count(StudentEnrollment.id).label("enrollment_count"),
            )
            .join(Class, Class.id == SurveyInstance.class_id)
            .join(School, School.id == Class.school_id)
            .outerjoin(
                StudentEnrollment,
                and_(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.class_id == SurveyInstance.class_id,
                    StudentEnrollment.start_date <= SurveyInstance.survey_date,
                    (
                        StudentEnrollment.end_date.is_(None)
                        | (StudentEnrollment.end_date >= SurveyInstance.survey_date)
                    ),
                ),
            )
            .where(SurveyInstance.status == "open")
            .group_by(SurveyInstance.id, School.timezone)
            .order_by(SurveyInstance.survey_date)
        ).all()

        available_instances = []

        # 3. Проверяем каждый экземпляр без дополнительных SQL-запросов.
        for instance, school_timezone, enrollment_count in instances:

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
                }
            )

        if not available_instances:
            return None

        # 4. Получаем количество вопросов сразу для всех
        # подходящих экземпляров одним запросом.
        instance_ids = [item["instance"].id for item in available_instances]

        question_counts = dict(
            db.execute(
                select(
                    SurveyInstanceQuestion.instance_id,
                    func.count(SurveyInstanceQuestion.id),
                )
                .where(SurveyInstanceQuestion.instance_id.in_(instance_ids))
                .group_by(SurveyInstanceQuestion.instance_id)
            ).all()
        )

        # 5. Возвращаем первый доступный экземпляр,
        # у которого есть вопросы.
        for item in available_instances:
            instance = item["instance"]
            questions_count = question_counts.get(instance.id, 0)

            if questions_count == 0:
                continue

            return {
                "instance_id": instance.id,
                "class_id": instance.class_id,
                "survey_date": instance.survey_date,
                "opens_at": item["opens_at"],
                "closes_at": item["closes_at"],
                "questions_count": questions_count,
            }

        return None

    finally:
        db.close()


def get_next_question(max_user_id: int, instance_id: int):
    """
    Возвращает первый вопрос, на который ученик ещё не ответил.

    Если все вопросы отправлены, возвращает None.
    Функция только читает БД.
    """

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
        .with_for_update(of=SurveyInstance)
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
):
    """
    Сохраняет ответ на вопрос с одним вариантом выбора.

    Возвращает:
    - submitted — ответ сохранён;
    - already_submitted — ответ уже отправлен;
    - invalid — данные или условия не прошли проверку.
    """

    db = SessionLocal()

    try:
        with db.begin():
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

            existing_response = db.scalar(
                select(SurveyResponse.id).where(
                    SurveyResponse.instance_question_id == question_id,
                    SurveyResponse.student_id == student_id,
                    SurveyResponse.status == "submitted",
                )
            )

            if existing_response is not None:
                return "already_submitted"

            # Находим первый незавершённый вопрос.
            first_question = _get_first_unfinished_question(
                db,
                student_id,
                instance.id,
            )

            # Проверяем, что ученик отвечает именно на него.
            if first_question is None:
                existing = db.scalar(
                    select(SurveyResponse.id)
                    .join(
                        SurveyInstanceQuestion,
                        SurveyInstanceQuestion.id
                        == SurveyResponse.instance_question_id,
                    )
                    .where(
                        SurveyInstanceQuestion.id == question_id,
                        SurveyResponse.student_id == student_id,
                        SurveyResponse.status == "submitted",
                    )
                )

                return "already_submitted" if existing is not None else "invalid"

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

            # Дополнительная проверка на существующий ответ.
            existing_response = db.scalar(
                select(SurveyResponse)
                .where(
                    SurveyResponse.instance_question_id == question.id,
                    SurveyResponse.student_id == student_id,
                )
                .with_for_update()
            )

            if existing_response is not None:
                if existing_response.status == "submitted":
                    return "already_submitted"

                # Для single-choice черновик не предусмотрен.
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
        db.rollback()
        logger.exception("Ошибка при сохранении ответа на опрос")
        return "invalid"

    finally:
        db.close()


def toggle_multiple_answer(
    max_user_id: int,
    instance_id: int,
    question_id: int,
    option_id: int,
):
    """
    Переключает выбранный вариант в черновике multiple-choice.

    Возвращает:
    - saved — изменение сохранено;
    - already_submitted — ответ уже отправлен;
    - limit_reached — достигнут лимит вариантов;
    - invalid — данные или условия не прошли проверку.
    """

    db = SessionLocal()

    try:
        with db.begin():
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

            existing_response = db.scalar(
                select(SurveyResponse.id).where(
                    SurveyResponse.instance_question_id == question_id,
                    SurveyResponse.student_id == student_id,
                    SurveyResponse.status == "submitted",
                )
            )

            if existing_response is not None:
                return "already_submitted"

            # Находим первый незавершённый вопрос.
            first_question = _get_first_unfinished_question(
                db,
                student_id,
                instance.id,
            )

            if first_question is None:
                existing = db.scalar(
                    select(SurveyResponse.id).where(
                        SurveyResponse.instance_question_id == question_id,
                        SurveyResponse.student_id == student_id,
                        SurveyResponse.status == "submitted",
                    )
                )

                return "already_submitted" if existing is not None else "invalid"

            if first_question.id != question_id:
                return "invalid"

            question = first_question

            # Проверяем тип и ограничения вопроса.
            if question.answer_type != "multiple":
                return "invalid"

            if question.min_answer < 1 or question.max_answer < question.min_answer:
                return "invalid"

            # Проверяем, что вариант принадлежит вопросу.
            option = db.scalar(
                select(SurveyInstanceOption).where(
                    SurveyInstanceOption.id == option_id,
                    SurveyInstanceOption.instance_question_id == question.id,
                )
            )

            if option is None:
                return "invalid"

            # Получаем или создаём черновик.
            response = db.scalar(
                select(SurveyResponse)
                .where(
                    SurveyResponse.instance_question_id == question.id,
                    SurveyResponse.student_id == student_id,
                )
                .with_for_update()
            )

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

            # Получаем уже выбранные варианты.
            selected = db.scalars(
                select(SurveyResponseOption).where(
                    SurveyResponseOption.response_id == response.id
                )
            ).all()

            selected_by_option = {item.option_id: item for item in selected}

            # Если вариант уже выбран — снимаем выбор.
            if option.id in selected_by_option:
                db.delete(selected_by_option[option.id])
                return "saved"

            # Обрабатываем эксклюзивный вариант «Никакой».
            if option.is_exclusive:
                db.execute(
                    delete(SurveyResponseOption).where(
                        SurveyResponseOption.response_id == response.id
                    )
                )

            else:
                # Получаем ID эксклюзивных вариантов,
                # которые уже находятся в черновике.
                exclusive_ids = set(
                    db.scalars(
                        select(SurveyResponseOption.option_id)
                        .join(
                            SurveyInstanceOption,
                            SurveyInstanceOption.id == SurveyResponseOption.option_id,
                        )
                        .where(
                            SurveyResponseOption.response_id == response.id,
                            SurveyInstanceOption.is_exclusive.is_(True),
                        )
                    ).all()
                )

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

            # Сохраняем новый вариант.
            db.add(
                SurveyResponseOption(
                    response_id=response.id,
                    option_id=option.id,
                    instance_question_id=question.id,
                )
            )

        return "saved"

    except Exception:
        db.rollback()
        logger.exception("Ошибка при сохранении черновика ответа")
        return "invalid"

    finally:
        db.close()


def submit_multiple_answer(
    max_user_id: int,
    instance_id: int,
    question_id: int,
):
    """
    Завершает ответ на вопрос с несколькими вариантами.

    Возвращает:
    - submitted — ответ успешно отправлен;
    - already_submitted — ответ уже отправлен;
    - incomplete — недостаточно выбранных вариантов;
    - invalid — данные или условия не прошли проверку.
    """

    db = SessionLocal()

    try:
        with db.begin():
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

            # Сначала проверяем, не был ли этот вопрос уже отправлен.
            existing_response = db.scalar(
                select(SurveyResponse.id).where(
                    SurveyResponse.instance_question_id == question_id,
                    SurveyResponse.student_id == student_id,
                    SurveyResponse.status == "submitted",
                )
            )

            if existing_response is not None:
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

            # Находим черновик и блокируем его.
            response = db.scalar(
                select(SurveyResponse)
                .where(
                    SurveyResponse.instance_question_id == question.id,
                    SurveyResponse.student_id == student_id,
                )
                .with_for_update()
            )

            if response is None:
                return "incomplete"

            if response.status == "submitted":
                return "already_submitted"

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
        db.rollback()
        logger.exception("Ошибка при отправке ответа на опрос")
        return "invalid"

    finally:
        db.close()
