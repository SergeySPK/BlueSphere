from datetime import date as Date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


# =========================================================
# ВХОДНЫЕ ДАННЫЕ
# =========================================================


class AITeachingAssignment(StrictSchema):
    """Назначение учителя в классе на текущий учебный год."""

    assignment_id: int = Field(gt=0)
    teacher_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    subject_name: str = Field(min_length=1, max_length=150)
    subgroup: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def validate_text(self):
        if not self.subject_name.strip():
            raise ValueError("subject_name не может быть пустым")
        return self


class AIScheduleLesson(StrictSchema):
    schedule_id: int = Field(gt=0)
    assignment_id: int = Field(gt=0)

    date: Date
    lesson_number: int = Field(ge=1)
    lesson_type: str = Field(min_length=1, max_length=150)

    subject_id: int = Field(gt=0)
    subject_name: str = Field(min_length=1, max_length=150)

    teacher_id: int = Field(gt=0)
    subgroup: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def validate_text(self):
        if not self.lesson_type.strip():
            raise ValueError("lesson_type не может быть пустым")

        if not self.subject_name.strip():
            raise ValueError("subject_name не может быть пустым")

        return self


class AISurveyOptionAggregate(StrictSchema):
    title: str = Field(min_length=1, max_length=150)
    responses_count: int = Field(ge=0)
    percentage: float = Field(ge=0, le=100)


class AISurveyQuestionAggregate(StrictSchema):
    title: str = Field(min_length=1, max_length=255)
    answer_type: Literal["single", "multiple"]
    respondents_count: int = Field(ge=0)
    options: list[AISurveyOptionAggregate]


class AISurveyAggregate(StrictSchema):
    survey_date: Date

    # В AI передаются только завершённые опросы.
    status: Literal["closed"]

    questions: list[AISurveyQuestionAggregate]


class AIAnalysisInput(StrictSchema):
    schema_version: Literal["1.0"] = "1.0"

    school_id: int = Field(gt=0)
    academic_year_id: int = Field(gt=0)
    class_id: int = Field(gt=0)

    period_start: Date
    period_end: Date

    # Одна целевая дата на один запрос.
    target_date: Date

    school_timezone: str = Field(min_length=1, max_length=100)

    assignments: list[AITeachingAssignment]
    lessons: list[AIScheduleLesson]
    surveys: list[AISurveyAggregate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input(self):
        if self.period_end < self.period_start:
            raise ValueError("Некорректный период анализа")

        if not self.period_start <= self.target_date <= self.period_end:
            raise ValueError("target_date находится вне периода анализа")

        if not self.school_timezone.strip():
            raise ValueError("Не указан часовой пояс школы")

        try:
            ZoneInfo(self.school_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"Некорректный часовой пояс: {self.school_timezone}"
            ) from None

        # Проверяем назначения учителей.
        assignment_ids = [
            assignment.assignment_id
            for assignment in self.assignments
        ]

        if len(assignment_ids) != len(set(assignment_ids)):
            raise ValueError("Повторяются assignment_id")

        for assignment in self.assignments:
            if not assignment.subject_name.strip():
                raise ValueError("subject_name не может быть пустым")

        assignments_by_id = {
            assignment.assignment_id: assignment
            for assignment in self.assignments
        }

        # Проверяем уроки и их соответствие назначениям.
        lesson_ids = [
            lesson.schedule_id
            for lesson in self.lessons
        ]

        if len(lesson_ids) != len(set(lesson_ids)):
            raise ValueError("Повторяются schedule_id")

        for lesson in self.lessons:
            if not self.period_start <= lesson.date <= self.period_end:
                raise ValueError(
                    f"Урок {lesson.schedule_id} вне периода анализа"
                )

            assignment = assignments_by_id.get(lesson.assignment_id)

            if assignment is None:
                raise ValueError(
                    f"Для урока {lesson.schedule_id} "
                    f"не найдено назначение {lesson.assignment_id}"
                )

            if (
                lesson.teacher_id != assignment.teacher_id
                or lesson.subject_id != assignment.subject_id
                or lesson.subject_name != assignment.subject_name
                or lesson.subgroup != assignment.subgroup
            ):
                raise ValueError(
                    f"Данные урока {lesson.schedule_id} "
                    "не соответствуют TeachingAssignment"
                )

        # В запрос для target_date нельзя передать опросы
        # за эту дату или более поздние даты.
        survey_dates = [
            survey.survey_date
            for survey in self.surveys
        ]

        if len(survey_dates) != len(set(survey_dates)):
            raise ValueError("Повторяются даты опросов")

        for survey in self.surveys:
            if survey.survey_date >= self.target_date:
                raise ValueError(
                    f"Опрос от {survey.survey_date} нельзя передавать "
                    f"для анализа {self.target_date}"
                )

        return self


# =========================================================
# ВЫХОДНЫЕ ДАННЫЕ
# =========================================================


class AIDailyLoadOutput(StrictSchema):
    date: Date

    # 0 — перегрузка, 4 — лёгкая нагрузка.
    level: int = Field(ge=0, le=4)

    # Нужно ли снизить нагрузку в этот день.
    reduce_load: bool | None = None

    # Подходит ли день для переноса уроков на него.
    suitable_for_moving: bool | None = None

    # Даты опросов, которые модель учитывала.
    survey_dates_used: list[Date] = Field(default_factory=list)


class AIRecommendationOutput(StrictSchema):
    date: Date

    kind: Literal["class", "teacher", "lesson"]

    priority: Literal["low", "normal", "high", "critical"] = "normal"

    title: str = Field(min_length=1, max_length=200)
    recommendation_text: str = Field(min_length=1, max_length=10000)
    rationale: str | None = Field(default=None, max_length=10000)

    teacher_id: int | None = Field(default=None, gt=0)
    schedule_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_kind_references(self):
        if self.kind == "class":
            if self.teacher_id is not None or self.schedule_id is not None:
                raise ValueError(
                    "Рекомендация класса не должна ссылаться "
                    "на учителя или урок"
                )

        elif self.kind == "teacher":
            if self.teacher_id is None:
                raise ValueError(
                    "Для рекомендации учителю обязателен teacher_id"
                )

            if self.schedule_id is not None:
                raise ValueError(
                    "Рекомендация учителю не должна ссылаться "
                    "на конкретный урок"
                )

        elif self.kind == "lesson":
            if self.schedule_id is None:
                raise ValueError(
                    "Для рекомендации уроку обязателен schedule_id"
                )

        if not self.title.strip():
            raise ValueError("Заголовок рекомендации пуст")

        if not self.recommendation_text.strip():
            raise ValueError("Текст рекомендации пуст")

        return self


class AIAnalysisOutput(StrictSchema):
    schema_version: Literal["1.0"] = "1.0"

    # Один запрос — одна целевая дата.
    daily_loads: list[AIDailyLoadOutput]
    recommendations: list[AIRecommendationOutput]

    @model_validator(mode="after")
    def validate_daily_loads(self):
        if len(self.daily_loads) != 1:
            raise ValueError(
                "Ответ должен содержать нагрузку ровно для одной даты"
            )

        dates = [
            item.date
            for item in self.daily_loads
        ]

        if len(dates) != len(set(dates)):
            raise ValueError("Повторяются даты дневной нагрузки")

        return self


# =========================================================
# ПРОВЕРКА ОТВЕТА С УЧЁТОМ ИСХОДНОГО КОНТЕКСТА
# =========================================================


def validate_ai_output_against_input(
    output: AIAnalysisOutput,
    source: AIAnalysisInput,
) -> AIAnalysisOutput:
    """Проверяет ссылки и даты, которые нельзя проверить по JSON-схеме."""

    schedule_by_id = {
        lesson.schedule_id: lesson
        for lesson in source.lessons
    }

    known_teacher_ids = {
        assignment.teacher_id
        for assignment in source.assignments
    }

    scheduled_dates = {
        lesson.date
        for lesson in source.lessons
    }

    known_survey_dates = {
        survey.survey_date
        for survey in source.surveys
    }

    # Нагрузка.
    daily_load = output.daily_loads[0]

    if daily_load.date != source.target_date:
        raise ValueError(
            f"Ожидалась нагрузка для {source.target_date}, "
            f"получена {daily_load.date}"
        )

    if daily_load.date not in scheduled_dates:
        raise ValueError(
            f"Для даты {daily_load.date} нет уроков. "
            "Пустые дни должны обрабатываться Python."
        )

    if len(daily_load.survey_dates_used) != len(
        set(daily_load.survey_dates_used)
    ):
        raise ValueError(
            f"Повторяются даты опросов для {daily_load.date}"
        )

    for survey_date in daily_load.survey_dates_used:
        if survey_date not in known_survey_dates:
            raise ValueError(
                f"Неизвестная дата опроса: {survey_date}"
            )

        if survey_date >= daily_load.date:
            raise ValueError(
                f"Опрос от {survey_date} не может влиять "
                f"на нагрузку за {daily_load.date}"
            )

    # Рекомендации.
    for recommendation in output.recommendations:
        if not (
            source.period_start
            <= recommendation.date
            <= source.period_end
        ):
            raise ValueError(
                f"Дата рекомендации {recommendation.date} "
                "вне периода анализа"
            )

        if recommendation.kind == "teacher":
            if recommendation.teacher_id not in known_teacher_ids:
                raise ValueError(
                    f"Неизвестный teacher_id: "
                    f"{recommendation.teacher_id}"
                )

        elif recommendation.kind == "lesson":
            lesson = schedule_by_id.get(recommendation.schedule_id)

            if lesson is None:
                raise ValueError(
                    f"Неизвестный schedule_id: "
                    f"{recommendation.schedule_id}"
                )

            if lesson.date != recommendation.date:
                raise ValueError(
                    "Дата рекомендации не совпадает "
                    "с датой указанного урока"
                )

            if (
                recommendation.teacher_id is not None
                and recommendation.teacher_id != lesson.teacher_id
            ):
                raise ValueError(
                    "teacher_id не соответствует указанному уроку"
                )

    return output
