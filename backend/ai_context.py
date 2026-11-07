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
            "Нагрузку пустого дня должен выставить Python (level=4)."
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

    surveys = []

    for instance in survey_instances:
        effective_status = get_effective_survey_status(
            instance,
            school.timezone,
            now=now,
        )

        # Не передаём открытые и отменённые опросы.
        if effective_status != "closed":
            continue

        questions = db.scalars(
            select(SurveyInstanceQuestion)
            .where(
                SurveyInstanceQuestion.instance_id == instance.id,
            )
            .order_by(SurveyInstanceQuestion.sort_order)
        ).all()

        question_aggregates = []

        for question in questions:
            # Зачисление должно действовать именно на дату опроса.
            eligible_enrollment = (
                (StudentEnrollment.start_date <= instance.survey_date)
                & (
                    or_(
                        StudentEnrollment.end_date.is_(None),
                        StudentEnrollment.end_date >= instance.survey_date,
                    )
                )
            )

            # Количество учеников с отправленным ответом.
            # DISTINCT защищает подсчёт от размножения строк
            # при соединении с историей зачислений.
            respondents_count = (
                db.scalar(
                    select(
                        func.count(
                            func.distinct(SurveyResponse.student_id)
                        )
                    )
                    .select_from(SurveyResponse)
                    .join(
                        StudentEnrollment,
                        StudentEnrollment.student_id
                        == SurveyResponse.student_id,
                    )
                    .where(
                        SurveyResponse.instance_question_id == question.id,
                        SurveyResponse.status == "submitted",
                        StudentEnrollment.class_id == class_id,
                        eligible_enrollment,
                    )
                )
                or 0
            )

            options = db.scalars(
                select(SurveyInstanceOption)
                .where(
                    SurveyInstanceOption.instance_question_id
                    == question.id,
                )
                .order_by(SurveyInstanceOption.sort_order)
            ).all()

            option_aggregates = []

            for option in options:
                responses_count = (
                    db.scalar(
                        select(
                            func.count(
                                func.distinct(SurveyResponseOption.response_id)
                            )
                        )
                        .select_from(SurveyResponseOption)
                        .join(
                            SurveyResponse,
                            SurveyResponse.id
                            == SurveyResponseOption.response_id,
                        )
                        .join(
                            StudentEnrollment,
                            StudentEnrollment.student_id
                            == SurveyResponse.student_id,
                        )
                        .where(
                            SurveyResponseOption.option_id == option.id,
                            SurveyResponseOption.instance_question_id
                            == question.id,
                            SurveyResponse.status == "submitted",
                            StudentEnrollment.class_id == class_id,
                            eligible_enrollment,
                        )
                    )
                    or 0
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
