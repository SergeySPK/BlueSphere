from datetime import date

import pytest

from ai_aggregation import (
    AIAnalysisAggregationError,
    aggregate_period_results,
)
from ai_schemas import AIAnalysisOutput


def make_result(
    target_date: date,
    level: int,
    recommendations: list | None = None,
    reduce_load: bool | None = None,
    suitable_for_moving: bool | None = None,
) -> AIAnalysisOutput:
    return AIAnalysisOutput(
        daily_loads=[
            {
                "date": target_date,
                "level": level,
                "survey_dates_used": [],
                "reduce_load": reduce_load,
                "suitable_for_moving": suitable_for_moving,
            }
        ],
        recommendations=recommendations or [],
    )


def make_recommendation(
    *,
    target_date: date,
    title: str = "Разгрузить день",
    priority: str = "normal",
) -> dict:
    return {
        "date": target_date,
        "kind": "class",
        "priority": priority,
        "title": title,
        "recommendation_text": (
            "**Рекомендация:**\\n\\n"
            "Рассмотреть более равномерное распределение нагрузки."
        ),
        "rationale": "В этот день высокая нагрузка.",
        "teacher_id": None,
        "schedule_id": None,
    }


def test_aggregates_load_levels_and_date_lists():
    result = aggregate_period_results(
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 7),
        scheduled_dates=[
            date(2026, 11, 2),
            date(2026, 11, 3),
            date(2026, 11, 5),
            date(2026, 11, 6),
            date(2026, 11, 7),
        ],
        day_results=[
            # AI-флаг имеет приоритет над уровнем:
            # уровень 0, но AI не просит разгружать день.
            make_result(
                date(2026, 11, 2),
                0,
                reduce_load=False,
                suitable_for_moving=False,
            ),
            # AI рекомендует разгрузить день.
            make_result(
                date(2026, 11, 3),
                1,
                reduce_load=True,
                suitable_for_moving=False,
            ),
            # Нет AI-флагов — должны работать Python-пороги.
            make_result(
                date(2026, 11, 5),
                2,
            ),
            # AI рекомендует перенести нагрузку на этот день.
            make_result(
                date(2026, 11, 6),
                3,
                reduce_load=False,
                suitable_for_moving=True,
            ),
            # Уровень 4, но AI явно не рекомендует перенос.
            make_result(
                date(2026, 11, 7),
                4,
                reduce_load=False,
                suitable_for_moving=False,
            ),
        ],
    )

    assert result.days_to_reduce == (3,)
    assert result.days_to_move_to == (6,)

    assert [
        (item.date, item.level, item.source)
        for item in result.daily_loads
    ] == [
        (date(2026, 11, 2), 0, "ai"),
        (date(2026, 11, 3), 1, "ai"),
        (date(2026, 11, 5), 2, "ai"),
        (date(2026, 11, 6), 3, "ai"),
        (date(2026, 11, 7), 4, "ai"),
    ]


def test_empty_days_are_not_move_targets():
    result = aggregate_period_results(
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 4),
        scheduled_dates=[
            date(2026, 11, 2),
            date(2026, 11, 4),
        ],
        day_results=[
            make_result(date(2026, 11, 2), 0),
            make_result(date(2026, 11, 4), 1),
        ],
    )

    assert result.days_to_reduce == (2, 4)
    assert result.days_to_move_to == ()

    # 3 ноября нет уроков — эта дата не должна создавать прогноз.
    assert [
        item.date for item in result.daily_loads
    ] == [
        date(2026, 11, 2),
        date(2026, 11, 4),
    ]


def test_level_two_is_not_in_either_date_list():
    result = aggregate_period_results(
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 2),
        scheduled_dates=[date(2026, 11, 2)],
        day_results=[make_result(date(2026, 11, 2), 2)],
    )

    assert result.days_to_reduce == ()
    assert result.days_to_move_to == ()


def test_recommendations_are_deduplicated_and_sorted():
    first = make_recommendation(
        target_date=date(2026, 11, 3),
        title="Обычная рекомендация",
    )
    duplicate = make_recommendation(
        target_date=date(2026, 11, 3),
        title="Обычная рекомендация",
    )
    critical = make_recommendation(
        target_date=date(2026, 11, 3),
        title="Важная рекомендация",
        priority="critical",
    )

    result = aggregate_period_results(
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 3),
        scheduled_dates=[
            date(2026, 11, 2),
            date(2026, 11, 3),
        ],
        day_results=[
            make_result(
                date(2026, 11, 2),
                2,
                [first, critical],
            ),
            make_result(
                date(2026, 11, 3),
                2,
                [duplicate],
            ),
        ],
    )

    assert len(result.recommendations) == 2
    assert result.recommendations[0].priority == "critical"
    assert result.recommendations[1].title == "Обычная рекомендация"


def test_missing_scheduled_day_result_is_rejected():
    with pytest.raises(
        AIAnalysisAggregationError,
        match="Нет результатов",
    ):
        aggregate_period_results(
            period_start=date(2026, 11, 2),
            period_end=date(2026, 11, 3),
            scheduled_dates=[
                date(2026, 11, 2),
                date(2026, 11, 3),
            ],
            day_results=[
                make_result(date(2026, 11, 2), 2),
            ],
        )


def test_duplicate_day_result_is_rejected():
    with pytest.raises(
        AIAnalysisAggregationError,
        match="Повторяется результат",
    ):
        aggregate_period_results(
            period_start=date(2026, 11, 2),
            period_end=date(2026, 11, 2),
            scheduled_dates=[date(2026, 11, 2)],
            day_results=[
                make_result(date(2026, 11, 2), 2),
                make_result(date(2026, 11, 2), 3),
            ],
        )


def test_result_for_unscheduled_day_is_rejected():
    with pytest.raises(
        AIAnalysisAggregationError,
        match="на которую нет уроков",
    ):
        aggregate_period_results(
            period_start=date(2026, 11, 2),
            period_end=date(2026, 11, 3),
            scheduled_dates=[date(2026, 11, 2)],
            day_results=[
                make_result(date(2026, 11, 2), 2),
                make_result(date(2026, 11, 3), 3),
            ],
        )


def test_invalid_period_is_rejected():
    with pytest.raises(
        AIAnalysisAggregationError,
        match="Конец периода",
    ):
        aggregate_period_results(
            period_start=date(2026, 11, 3),
            period_end=date(2026, 11, 2),
            scheduled_dates=[],
            day_results=[],
        )


def test_recommendations_from_all_days_are_combined():
    first = make_recommendation(
        target_date=date(2026, 11, 2),
        title="Рекомендация первого дня",
    )
    second = make_recommendation(
        target_date=date(2026, 11, 3),
        title="Рекомендация второго дня",
    )

    result = aggregate_period_results(
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 3),
        scheduled_dates=[
            date(2026, 11, 2),
            date(2026, 11, 3),
        ],
        day_results=[
            make_result(date(2026, 11, 2), 2, [first]),
            make_result(date(2026, 11, 3), 2, [second]),
        ],
    )

    assert [
        item.title
        for item in result.recommendations
    ] == [
        "Рекомендация первого дня",
        "Рекомендация второго дня",
    ]


def test_python_fallback_uses_load_levels_when_ai_flags_are_missing():
    result = aggregate_period_results(
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 4),
        scheduled_dates=[
            date(2026, 11, 2),
            date(2026, 11, 3),
            date(2026, 11, 4),
        ],
        day_results=[
            make_result(date(2026, 11, 2), 0),
            make_result(date(2026, 11, 3), 2),
            make_result(date(2026, 11, 4), 4),
        ],
    )

    assert result.days_to_reduce == (2,)
    assert result.days_to_move_to == (4,)
