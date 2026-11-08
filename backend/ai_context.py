from collections.abc import Callable
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ai_schemas import AIAnalysisInput
from models import (
    AcademicYear,
    Class as SchoolClass,
    School,
    Schedule,
    Subject,
    StudentEnrollment,
    SurveyInstance,
    SurveyInstanceOption,
    SurveyInstanceQuestion,
    SurveyResponse,
    SurveyResponseOption,
    TeachingAssignment,
)
from survey_service import get_effective_survey_status


def collect_ai_analysis_input(
    db: Session,
    *,
    school_id: int,
    class_id: int,
    period_start: date,
    period_end: date,
    target_date: date,
    now: datetime | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> AIAnalysisInput:
    """
    Формирует контекст AI-анализа на основе данных класса.

    В контекст включаются агрегированные результаты опросов
    за период с начала соответствующего учебного года
    по целевую дату анализа включительно.

    Результаты используются только в агрегированном виде:
    индивидуальные ответы и идентификаторы учеников
    не передаются в AI-контекст.
    """

    if period_end < period_start:
        raise ValueError("Некорректный период анализа")

    if not period_start <= target_date <= period_end:
        raise ValueError("target_date находится вне периода анализа")

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now должен содержать часовой пояс")

    # -----------------------------------------------------
    # 1. Школа и её часовой пояс
    # -----------------------------------------------------

    school = db.scalar(
        select(School).where(School.id == school_id)
    )

    if school is None:
        raise ValueError(f"Школа {school_id} не найдена")

    if not school.timezone:
        raise ValueError(
            f"У школы {school_id} не указан часовой пояс"
        )

    # -----------------------------------------------------
    # 2. Активный учебный год и класс
    # -----------------------------------------------------

    academic_years = db.scalars(
        select(AcademicYear).where(
            AcademicYear.school_id == school_id,
            AcademicYear.is_active.is_(True),
        )
    ).all()

    if len(academic_years) != 1:
        raise ValueError(
            f"Для школы {school_id} должен существовать "
            "ровно один активный учебный год"
        )

    academic_year = academic_years[0]

    if (
        period_start < academic_year.start_date
        or period_end > academic_year.end_date
    ):
        raise ValueError(
            "Период анализа выходит за границы активного учебного года"
        )

    school_class = db.scalar(
        select(SchoolClass).where(
            SchoolClass.id == class_id,
            SchoolClass.school_id == school_id,
            SchoolClass.academic_year_id == academic_year.id,
        )
    )

    if school_class is None:
        raise ValueError(
            f"Класс {class_id} не принадлежит школе "
            f"{school_id} или активному учебному году"
        )

    # -----------------------------------------------------
    # 3. Все назначения учителей класса
    # -----------------------------------------------------

    assignment_rows = db.execute(
        select(
            TeachingAssignment,
            Subject.name,
        )
        .join(
            Subject,
            Subject.id == TeachingAssignment.subject_id,
        )
        .where(
            TeachingAssignment.school_id == school_id,
            TeachingAssignment.class_id == class_id,
            TeachingAssignment.academic_year_id == academic_year.id,
        )
        .order_by(
            TeachingAssignment.teacher_id,
            TeachingAssignment.subject_id,
            TeachingAssignment.subgroup,
        )
    ).all()

    assignments = [
        {
            "assignment_id": assignment.id,
            "teacher_id": assignment.teacher_id,
            "subject_id": assignment.subject_id,
            "subject_name": subject_name,
            "subgroup": assignment.subgroup,
        }
        for assignment, subject_name in assignment_rows
    ]

    assignment_by_id = {
        item["assignment_id"]: item
        for item in assignments
    }

    # -----------------------------------------------------
    # 4. Расписание класса в пределах периода
    # -----------------------------------------------------

    schedule_rows = db.execute(
        select(
            Schedule,
            TeachingAssignment,
            Subject.name,
        )
        .join(
            TeachingAssignment,
            TeachingAssignment.id == Schedule.assignment_id,
        )
        .join(
            Subject,
            Subject.id == TeachingAssignment.subject_id,
        )
        .where(
            TeachingAssignment.school_id == school_id,
            TeachingAssignment.class_id == class_id,
            TeachingAssignment.academic_year_id == academic_year.id,
            Schedule.date >= period_start,
            Schedule.date <= period_end,
        )
        .order_by(
            Schedule.date,
            Schedule.lesson_number,
            Schedule.id,
        )
    ).all()

    lessons = []

    for schedule, assignment, subject_name in schedule_rows:
        # Дополнительная защита от несогласованного расписания.
        if assignment.id not in assignment_by_id:
            raise ValueError(
                f"Урок {schedule.id} ссылается на назначение, "
                "отсутствующее в контексте класса"
            )

        lessons.append(
            {
                "schedule_id": schedule.id,
                "assignment_id": assignment.id,
                "date": schedule.date,
                "lesson_number": schedule.lesson_number,
                "lesson_type": schedule.lesson_type,
                "subject_id": assignment.subject_id,
                "subject_name": subject_name,
                "teacher_id": assignment.teacher_id,
                "subgroup": assignment.subgroup,
            }
        )

    if not any(lesson["date"] == target_date for lesson in lessons):
        raise ValueError(
            f"На {target_date} нет уроков. "
            "AI-контекст для дня без уроков не формируется."
        )

    # -----------------------------------------------------
    # 5. Закрытые опросы до целевой даты
    # -----------------------------------------------------

    survey_instances = db.scalars(
        select(SurveyInstance)
        .where(
            SurveyInstance.class_id == class_id,
            SurveyInstance.survey_date >= academic_year.start_date,
            SurveyInstance.survey_date < target_date,
        )
        .order_by(SurveyInstance.survey_date)
    ).all()

    # Определяем закрытые опросы.
    # Периодический callback не позволяет lease истечь,
    # если в истории класса накопилось много опросов.
    closed_instances = []

    for index, instance in enumerate(survey_instances, start=1):
        if (
            progress_callback is not None
            and index % 25 == 0
        ):
            progress_callback()

        effective_status = get_effective_survey_status(
            instance,
            school.timezone,
            now=now,
        )

        if effective_status == "closed":
            closed_instances.append(instance)

    surveys = []

    if closed_instances:
        closed_instance_ids = [
            instance.id
            for instance in closed_instances
        ]

        # Все вопросы всех закрытых опросов одним запросом.
        question_rows = db.scalars(
            select(SurveyInstanceQuestion)
            .where(
                SurveyInstanceQuestion.instance_id.in_(
                    closed_instance_ids
                )
            )
            .order_by(
                SurveyInstanceQuestion.instance_id,
                SurveyInstanceQuestion.sort_order,
            )
        ).all()

        question_ids = [
            question.id
            for question in question_rows
        ]

        # Все варианты ответов одним запросом.
        option_rows = []

        if question_ids:
            option_rows = db.scalars(
                select(SurveyInstanceOption)
                .where(
                    SurveyInstanceOption.instance_question_id.in_(
                        question_ids
                    )
                )
                .order_by(
                    SurveyInstanceOption.instance_question_id,
                    SurveyInstanceOption.sort_order,
                )
            ).all()

        # Группируем вопросы по опросам.
        questions_by_instance = {}

        for question in question_rows:
            questions_by_instance.setdefault(
                question.instance_id,
                [],
            ).append(question)

        # Группируем варианты ответов по вопросам.
        options_by_question = {}

        for option in option_rows:
            options_by_question.setdefault(
                option.instance_question_id,
                [],
            ).append(option)

        # -------------------------------------------------
        # Количество респондентов по каждому вопросу.
        # Учитываются только отправленные ответы учеников,
        # зачисление которых действовало на дату опроса.
        # DISTINCT защищает от дублирования при наличии
        # нескольких подходящих записей зачисления.
        # -------------------------------------------------

        respondents_by_question = {}

        if question_ids:
            respondent_rows = db.execute(
                select(
                    SurveyResponse.instance_question_id,
                    func.count(
                        func.distinct(SurveyResponse.student_id)
                    ),
                )
                .select_from(SurveyResponse)
                .join(
                    SurveyInstanceQuestion,
                    SurveyInstanceQuestion.id
                    == SurveyResponse.instance_question_id,
                )
                .join(
                    SurveyInstance,
                    SurveyInstance.id
                    == SurveyInstanceQuestion.instance_id,
                )
                .join(
                    StudentEnrollment,
                    StudentEnrollment.student_id
                    == SurveyResponse.student_id,
                )
                .where(
                    SurveyInstanceQuestion.id.in_(question_ids),
                    SurveyResponse.status == "submitted",
                    StudentEnrollment.class_id == class_id,
                    StudentEnrollment.start_date
                    <= SurveyInstance.survey_date,
                    or_(
                        StudentEnrollment.end_date.is_(None),
                        StudentEnrollment.end_date
                        >= SurveyInstance.survey_date,
                    ),
                )
                .group_by(
                    SurveyResponse.instance_question_id
                )
            ).all()

            respondents_by_question = {
                question_id: count
                for question_id, count in respondent_rows
            }

        # -------------------------------------------------
        # Количество ответов по каждой паре:
        # question_id + option_id.
        # Вместо отдельного COUNT для каждого варианта
        # выполняется одна групповая агрегация.
        # -------------------------------------------------

        responses_by_question_option = {}

        if question_ids:
            option_response_rows = db.execute(
                select(
                    SurveyResponseOption.instance_question_id,
                    SurveyResponseOption.option_id,
                    func.count(
                        func.distinct(
                            SurveyResponseOption.response_id
                        )
                    ),
                )
                .select_from(SurveyResponseOption)
                .join(
                    SurveyResponse,
                    SurveyResponse.id
                    == SurveyResponseOption.response_id,
                )
                .join(
                    SurveyInstanceQuestion,
                    SurveyInstanceQuestion.id
                    == SurveyResponseOption.instance_question_id,
                )
                .join(
                    SurveyInstance,
                    SurveyInstance.id
                    == SurveyInstanceQuestion.instance_id,
                )
                .join(
                    StudentEnrollment,
                    StudentEnrollment.student_id
                    == SurveyResponse.student_id,
                )
                .where(
                    SurveyInstanceQuestion.id.in_(question_ids),
                    SurveyResponse.status == "submitted",
                    StudentEnrollment.class_id == class_id,
                    StudentEnrollment.start_date
                    <= SurveyInstance.survey_date,
                    or_(
                        StudentEnrollment.end_date.is_(None),
                        StudentEnrollment.end_date
                        >= SurveyInstance.survey_date,
                    ),
                )
                .group_by(
                    SurveyResponseOption.instance_question_id,
                    SurveyResponseOption.option_id,
                )
            ).all()

            responses_by_question_option = {
                (question_id, option_id): count
                for question_id, option_id, count
                in option_response_rows
            }

        # -------------------------------------------------
        # Собираем готовую структуру контекста в Python.
        # SQL-запросы больше не выполняются внутри циклов
        # вопросов и вариантов ответов.
        # -------------------------------------------------

        for instance in closed_instances:
            question_aggregates = []

            for question in questions_by_instance.get(
                instance.id,
                [],
            ):
                respondents_count = (
                    respondents_by_question.get(question.id, 0)
                )

                option_aggregates = []

                for option in options_by_question.get(
                    question.id,
                    [],
                ):
                    responses_count = (
                        responses_by_question_option.get(
                            (question.id, option.id),
                            0,
                        )
                    )

                    percentage = (
                        round(
                            responses_count / respondents_count * 100,
                            1,
                        )
                        if respondents_count > 0
                        else 0.0
                    )

                    option_aggregates.append(
                        {
                            "title": option.title,
                            "responses_count": responses_count,
                            "percentage": percentage,
                        }
                    )

                question_aggregates.append(
                    {
                        "title": question.title,
                        "answer_type": question.answer_type,
                        "respondents_count": respondents_count,
                        "options": option_aggregates,
                    }
                )

            surveys.append(
                {
                    "survey_date": instance.survey_date,
                    "status": "closed",
                    "questions": question_aggregates,
                }
            )


    # -----------------------------------------------------
    # 6. Строгая валидация готового контекста
    # -----------------------------------------------------

    return AIAnalysisInput.model_validate(
        {
            "school_id": school_id,
            "academic_year_id": academic_year.id,
            "class_id": class_id,
            "period_start": period_start,
            "period_end": period_end,
            "target_date": target_date,
            "school_timezone": school.timezone,
            "assignments": assignments,
            "lessons": lessons,
            "surveys": surveys,
        }
    )


def build_ai_analysis_input_for_date(
    base_context: AIAnalysisInput,
    target_date: date,
) -> AIAnalysisInput:
    """
    Создаёт контекст конкретной даты из заранее собранного
    контекста класса.

    Расписание и назначения переиспользуются.
    В историю попадают только закрытые опросы,
    проведённые строго до целевой даты.
    """

    if not (
        base_context.period_start
        <= target_date
        <= base_context.period_end
    ):
        raise ValueError(
            "target_date находится вне периода анализа"
        )

    lessons_for_date = [
        lesson
        for lesson in base_context.lessons
        if lesson.date == target_date
    ]

    if not lessons_for_date:
        raise ValueError(
            f"На {target_date} нет уроков. "
            "Контекст AI для пустого дня не создаётся."
        )

    surveys_before_target = [
        survey
        for survey in base_context.surveys
        if survey.survey_date < target_date
    ]

    return AIAnalysisInput.model_validate(
        {
            **base_context.model_dump(),
            "target_date": target_date,
            "surveys": surveys_before_target,
        }
    )
