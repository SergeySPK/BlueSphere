from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta

from ai_schemas import AIAnalysisOutput


@dataclass(frozen=True)
class AggregatedDailyLoad:
    date: Date
    level: int
    source: str
    survey_dates_used: tuple[Date, ...]


@dataclass(frozen=True)
class AIPeriodAnalysisResult:
    period_start: Date
    period_end: Date
    days_to_reduce: tuple[int, ...]
    days_to_move_to: tuple[int, ...]
    daily_loads: tuple[AggregatedDailyLoad, ...]
    recommendations: tuple


class AIAnalysisAggregationError(ValueError):
    """Ошибка при объединении дневных результатов AI-анализа."""


_PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}

_KIND_ORDER = {
    "class": 0,
    "teacher": 1,
    "lesson": 2,
}


def _date_range(start: Date, end: Date) -> list[Date]:
    """Возвращает все календарные даты периода включительно."""
    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]


def _recommendation_key(recommendation) -> tuple:
    """Ключ для удаления точных дубликатов рекомендаций."""
    return (
        recommendation.date,
        recommendation.kind,
        recommendation.priority,
        recommendation.title,
        recommendation.recommendation_text,
        recommendation.rationale,
        recommendation.teacher_id,
        recommendation.schedule_id,
    )


def aggregate_period_results(
    *,
    period_start: Date,
    period_end: Date,
    scheduled_dates: Iterable[Date],
    day_results: Sequence[AIAnalysisOutput],
) -> AIPeriodAnalysisResult:
    """
    Объединяет результаты анализа отдельных дней.

    scheduled_dates — даты, на которые в расписании есть уроки.
    day_results — проверенные результаты analyze_day() для этих дат.

    Даты без уроков получают level=4 и source="python".
    Они не включаются в days_to_move_to.
    """

    if period_end < period_start:
        raise AIAnalysisAggregationError(
            "Конец периода не может быть раньше его начала."
        )

    scheduled_date_set = set(scheduled_dates)

    for scheduled_date in scheduled_date_set:
        if not isinstance(scheduled_date, Date):
            raise AIAnalysisAggregationError(
                "Все элементы scheduled_dates должны быть датами."
            )

        if not period_start <= scheduled_date <= period_end:
            raise AIAnalysisAggregationError(
                f"Дата расписания {scheduled_date} вне периода анализа."
            )

    results_by_date = {}

    for result in day_results:
        if not isinstance(result, AIAnalysisOutput):
            raise AIAnalysisAggregationError(
                "Все результаты должны быть экземплярами AIAnalysisOutput."
            )

        if len(result.daily_loads) != 1:
            raise AIAnalysisAggregationError(
                "Каждый дневной результат должен содержать "
                "ровно одну запись daily_loads."
            )

        daily_load = result.daily_loads[0]
        result_date = daily_load.date

        if result_date in results_by_date:
            raise AIAnalysisAggregationError(
                f"Повторяется результат анализа за {result_date}."
            )

        if result_date not in scheduled_date_set:
            raise AIAnalysisAggregationError(
                f"Получен AI-результат за дату {result_date}, "
                "на которую нет уроков в расписании."
            )

        results_by_date[result_date] = result

    missing_dates = scheduled_date_set - set(results_by_date)

    if missing_dates:
        missing_text = ", ".join(
            item.isoformat()
            for item in sorted(missing_dates)
        )
        raise AIAnalysisAggregationError(
            f"Нет результатов AI-анализа за даты: {missing_text}."
        )

    daily_loads = []
    days_to_reduce = []
    days_to_move_to = []

    recommendations_by_key = {}

    for current_date in _date_range(period_start, period_end):
        result = results_by_date.get(current_date)

        if result is None:
            # Даты без уроков обрабатываются Python.
            daily_loads.append(
                AggregatedDailyLoad(
                    date=current_date,
                    level=4,
                    source="python",
                    survey_dates_used=(),
                )
            )
            continue

        item = result.daily_loads[0]

        daily_loads.append(
            AggregatedDailyLoad(
                date=item.date,
                level=item.level,
                source="ai",
                survey_dates_used=tuple(item.survey_dates_used),
            )
        )

        if item.level in (0, 1):
            days_to_reduce.append(current_date.day)

        elif item.level in (3, 4):
            days_to_move_to.append(current_date.day)

        for recommendation in result.recommendations:
            key = _recommendation_key(recommendation)
            recommendations_by_key[key] = recommendation

    recommendations = sorted(
        recommendations_by_key.values(),
        key=lambda item: (
            item.date,
            _PRIORITY_ORDER[item.priority],
            _KIND_ORDER[item.kind],
            item.title,
        ),
    )

    return AIPeriodAnalysisResult(
        period_start=period_start,
        period_end=period_end,
        days_to_reduce=tuple(days_to_reduce),
        days_to_move_to=tuple(days_to_move_to),
        daily_loads=tuple(daily_loads),
        recommendations=tuple(recommendations),
    )
