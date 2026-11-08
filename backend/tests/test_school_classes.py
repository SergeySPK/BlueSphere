from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from datetime import date as PythonDate
from datetime import datetime
from zoneinfo import ZoneInfo

import main
from models import AIDailyForecast


def test_school_classes_returns_only_accessible_classes(monkeypatch):
    user = SimpleNamespace(id=1)

    classes = [
        SimpleNamespace(id=34, code="1a", name="Класс 1А", school_id=1),
        SimpleNamespace(id=35, code="1b", name="Класс 1Б", school_id=1),
    ]

    # Имитируем успешную проверку доступа к школе.
    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: SimpleNamespace(id=school_id),
    )

    # Пользователь имеет доступ только к классам 34 и 35.
    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"student"}, {34, 35}),
    )

    fake_db = SimpleNamespace(
        scalars=lambda query: SimpleNamespace(all=lambda: classes)
    )

    result = main.get_school_classes(
        school_id=1,
        current_user=user,
        db=fake_db,
    )

    assert "1 класс" in result
    assert len(result["1 класс"]) == 2
    assert result["1 класс"][0].id == "1a"
    assert result["1 класс"][1].id == "1b"


def test_school_classes_returns_empty_when_user_has_no_classes(monkeypatch):
    user = SimpleNamespace(id=1)

    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: SimpleNamespace(id=school_id),
    )

    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"student"}, set()),
    )

    fake_db = SimpleNamespace()

    result = main.get_school_classes(
        school_id=1,
        current_user=user,
        db=fake_db,
    )

    assert result == {}


def test_school_classes_does_not_return_classes_from_another_school(monkeypatch):
    user = SimpleNamespace(id=1)

    school_1_classes = [
        SimpleNamespace(id=34, code="1a", name="Класс 1А", school_id=1),
    ]

    # Пользователь имеет доступ к обеим школам и обоим классам.
    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: SimpleNamespace(id=school_id),
    )

    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"teacher", "admin"}, {34, 80}),
    )

    fake_db = SimpleNamespace(
        scalars=lambda query: SimpleNamespace(all=lambda: school_1_classes)
    )

    result = main.get_school_classes(
        school_id=1,
        current_user=user,
        db=fake_db,
    )

    assert len(result["1 класс"]) == 1
    assert result["1 класс"][0].id == "1a"


def test_user_cannot_access_another_school(monkeypatch):
    user = SimpleNamespace(id=1)

    def deny_school_access(school_id, user, db):
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этой школе",
        )

    monkeypatch.setattr(
        main,
        "require_school_access",
        deny_school_access,
    )

    # Если проверка доступа сработала правильно,
    # до получения классов маршрут не дойдёт.
    def unexpected_get_user_access(user, db):
        pytest.fail("Получение классов не должно вызываться")

    monkeypatch.setattr(
        main,
        "get_user_access",
        unexpected_get_user_access,
    )

    fake_db = SimpleNamespace()

    with pytest.raises(HTTPException) as error:
        main.get_school_classes(
            school_id=2,
            current_user=user,
            db=fake_db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этой школе"


def test_school_schedule_uses_school_and_class_access(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(
        id=34,
        code="1a",
        school_id=1,
    )

    access_calls = []
    schedule_calls = []

    def fake_require_access(school_id, class_code, user, db):
        access_calls.append((school_id, class_code))
        return school_class

    def fake_build_schedule(school_class_arg, date, db, user_arg):
        schedule_calls.append((school_class_arg, date, user_arg))
        return ["расписание"]

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        fake_require_access,
    )
    monkeypatch.setattr(
        main,
        "build_class_schedule",
        fake_build_schedule,
    )

    fake_db = SimpleNamespace()

    result = main.get_school_schedule(
        school_id=1,
        class_code="1a",
        date="2026-10-30",
        current_user=user,
        db=fake_db,
    )

    assert result == ["расписание"]
    assert access_calls == [(1, "1a")]
    assert schedule_calls == [(school_class, "2026-10-30", user)]


def test_school_schedule_denies_access_without_building_schedule(monkeypatch):
    user = SimpleNamespace(id=1)

    def deny_access(school_id, class_code, user, db):
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этому классу",
        )

    def unexpected_build_schedule(school_class, date, db):
        pytest.fail("Расписание не должно запрашиваться без доступа")

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        deny_access,
    )
    monkeypatch.setattr(
        main,
        "build_class_schedule",
        unexpected_build_schedule,
    )

    fake_db = SimpleNamespace()

    with pytest.raises(HTTPException) as error:
        main.get_school_schedule(
            school_id=2,
            class_code="1a",
            date="2026-10-30",
            current_user=user,
            db=fake_db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этому классу"


def test_school_heatmap_uses_school_and_class_access(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(
        id=34,
        code="1a",
        school_id=1,
    )

    access_calls = []
    heatmap_calls = []

    def fake_require_access(school_id, class_code, user, db):
        access_calls.append((school_id, class_code))
        return school_class

    def fake_build_heatmap(
        school_class,
        month,
        current_user_id,
        db,
    ):
        heatmap_calls.append((school_class, month, current_user_id))
        return ["тепловая карта"]

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        fake_require_access,
    )
    monkeypatch.setattr(
        main,
        "build_class_heatmap",
        fake_build_heatmap,
    )

    result = main.get_school_heatmap(
        school_id=1,
        class_code="1a",
        month="10",
        current_user=user,
        db=SimpleNamespace(),
    )

    assert result == ["тепловая карта"]
    assert access_calls == [(1, "1a")]
    assert heatmap_calls == [(school_class, "10", 1)]


def test_school_heatmap_denies_access_without_building_heatmap(monkeypatch):
    user = SimpleNamespace(id=1)

    def deny_access(school_id, class_code, user, db):
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этому классу",
        )

    def unexpected_build_heatmap(*args, **kwargs):
        pytest.fail("Тепловая карта не должна формироваться без доступа")

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        deny_access,
    )
    monkeypatch.setattr(
        main,
        "build_class_heatmap",
        unexpected_build_heatmap,
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_heatmap(
            school_id=2,
            class_code="1a",
            month="10",
            current_user=user,
            db=SimpleNamespace(),
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этому классу"


def test_school_summary_uses_school_and_class_access(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(id=34, code="1a", school_id=1)
    access_calls = []
    summary_calls = []

    def fake_require_access(school_id, class_code, user, db, allowed_roles=None):
        access_calls.append((school_id, class_code, allowed_roles))
        return school_class

    summary_date = PythonDate(2026, 11, 12)

    def fake_build_summary(school_class_arg, target_date, db):
        summary_calls.append(
            (school_class_arg, target_date)
        )
        return "сводка"

    monkeypatch.setattr(main, "require_school_class_access", fake_require_access)
    monkeypatch.setattr(main, "build_class_summary", fake_build_summary)

    result = main.get_school_summary(
        school_id=1,
        class_code="1a",
        date=summary_date,
        current_user=user,
        db=SimpleNamespace(),
    )

    assert result == "сводка"
    assert access_calls == [(1, "1a", None)]
    assert summary_calls == [
        (school_class, summary_date)
    ]


def test_school_summary_denies_access_without_building_summary(monkeypatch):
    user = SimpleNamespace(id=1)

    def deny_access(school_id, class_code, user, db, allowed_roles=None):
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому разделу",
        )

    def unexpected_build_summary(*args, **kwargs):
        pytest.fail("Сводка не должна формироваться без доступа")

    monkeypatch.setattr(main, "require_school_class_access", deny_access)
    monkeypatch.setattr(main, "build_class_summary", unexpected_build_summary)

    with pytest.raises(HTTPException) as error:
        main.get_school_summary(
            school_id=1,
            class_code="1a",
            current_user=user,
            db=SimpleNamespace(),
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вашей роли нет доступа к этому разделу"


def test_school_summary_does_not_restrict_roles(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(id=34, code="1a", school_id=1)
    captured_roles = []

    def fake_require_access(school_id, class_code, user, db, allowed_roles=None):
        captured_roles.append(allowed_roles)
        return school_class

    monkeypatch.setattr(main, "require_school_class_access", fake_require_access)
    monkeypatch.setattr(main, "build_class_summary", lambda school_class, target_date, db: "сводка")

    main.get_school_summary(
        school_id=1,
        class_code="1a",
        current_user=user,
        db=SimpleNamespace(),
    )

    assert captured_roles == [None]


@pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
def test_recommendation_daily_load_accepts_valid_levels(level):
    result = main.RecommendationDailyLoad(
        date=PythonDate(2026, 11, 9),
        day=9,
        level=level,
        source="ai",
    )

    assert result.level == level


def test_school_recommendations_denies_access_without_building(
    monkeypatch,
):
    user = SimpleNamespace(id=1)
    school = SimpleNamespace(id=1)
    school_class = SimpleNamespace(
        id=34,
        code="1a",
        school_id=1,
        academic_year_id=7,
    )

    db = SimpleNamespace(
        scalar=lambda query: school_class,
    )

    def fake_get_user_access(current_user, db):
        assert current_user is user
        return {"student"}, {school_class.id}

    def fake_require_school_access(school_id, user, db):
        assert school_id == 1
        assert user is user
        return school

    def deny_class_access(
        school_id,
        class_code,
        current_user,
        db,
        allowed_roles=None,
    ):
        assert school_id == 1
        assert class_code == "1a"
        assert current_user is user
        assert db is not None
        assert allowed_roles == {"teacher", "admin"}

        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому разделу",
        )

    def unexpected_build(*args, **kwargs):
        pytest.fail(
            "Рекомендации не должны формироваться без доступа"
        )

    monkeypatch.setattr(
        main,
        "get_user_access",
        fake_get_user_access,
    )
    monkeypatch.setattr(
        main,
        "require_school_access",
        fake_require_school_access,
    )
    monkeypatch.setattr(
        main,
        "require_school_class_access",
        deny_class_access,
    )
    monkeypatch.setattr(
        main,
        "build_class_recommendations",
        unexpected_build,
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_recommendations(
            school_id=1,
            class_code="1a",
            month="10",
            current_user=user,
            db=db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == (
        "У вашей роли нет доступа к этому разделу"
    )


def test_recommendation_schema_has_backward_compatible_ai_fields():
    result = main.Recommendation(
        daysToReduce=[9, 10],
        daysToMoveTo=[5, 12],
    )

    payload = result.model_dump(mode="json")

    assert payload["daysToReduce"] == [9, 10]
    assert payload["daysToMoveTo"] == [5, 12]

    assert payload["analysisStatus"] == "not_started"
    assert payload["isStale"] is False
    assert payload["period"] is None
    assert payload["dailyLoads"] == []
    assert payload["recommendations"] == []
    assert payload["dataSource"] == "schedule"


def test_recommendation_daily_load_rejects_invalid_level():
    with pytest.raises(ValidationError):
        main.RecommendationDailyLoad(
            date=PythonDate(2026, 11, 9),
            day=9,
            level=5,
        )


def test_recommendation_schema_serializes_ai_data():
    result = main.Recommendation(
        daysToReduce=[9],
        daysToMoveTo=[5],
        analysisStatus="succeeded",
        isStale=False,
        dailyLoads=[
            main.RecommendationDailyLoad(
                date=PythonDate(2026, 11, 9),
                day=9,
                level=3,
                source="ai",
            ),
        ],
        recommendations=[
            main.RecommendationDetail(
                date=PythonDate(2026, 11, 9),
                kind="class",
                priority="high",
                title="Снизить нагрузку",
                recommendationText=(
                    "Перенести часть контрольных работ."
                ),
                rationale="Высокая прогнозируемая нагрузка.",
            ),
        ],
        dataSource="ai",
    )

    payload = result.model_dump(mode="json")

    assert payload["analysisStatus"] == "succeeded"
    assert payload["isStale"] is False
    assert payload["dataSource"] == "ai"

    assert payload["dailyLoads"] == [
        {
            "date": "2026-11-09",
            "day": 9,
            "level": 3,
            "source": "ai",
        },
    ]

    assert payload["recommendations"][0]["kind"] == "class"
    assert payload["recommendations"][0]["priority"] == "high"
    assert (
        payload["recommendations"][0]["recommendationText"]
        == "Перенести часть контрольных работ."
    )


def _recommendation_run(
    *,
    run_id: int,
    status: str,
    period_start: PythonDate | None = None,
    period_end: PythonDate | None = None,
    scope: str = "class",
    class_id: int | None = 34,
    school_id: int = 1,
    academic_year_id: int = 7,
):
    """Создаёт объект запуска AI-анализа с полями builder."""

    year = PythonDate.today().year

    return SimpleNamespace(
        id=run_id,
        status=status,
        scope=scope,
        class_id=class_id,
        school_id=school_id,
        academic_year_id=academic_year_id,
        period_start=period_start or PythonDate(year, 11, 1),
        period_end=period_end or PythonDate(year, 11, 30),
    )


def _recommendation_row(
    *,
    recommendation_id: int,
    kind: str,
    teacher_id: int | None = None,
    schedule_id: int | None = None,
    recommendation_date: PythonDate | None = None,
):
    """Создаёт строку AIRecommendation."""
    return SimpleNamespace(
        id=recommendation_id,
        date=recommendation_date or PythonDate(2026, 11, 12),
        kind=kind,
        priority="high",
        title=f"Рекомендация {recommendation_id}",
        recommendation_text=f"Текст {recommendation_id}",
        rationale=f"Обоснование {recommendation_id}",
        teacher_id=teacher_id,
        schedule_id=schedule_id,
    )


class _RecommendationFakeDB:
    """Последовательно возвращает результаты запросов scalars()."""

    def __init__(
        self,
        runs,
        daily_loads=None,
        recommendations=None,
        *results,
    ):
        self.calls = 0
        self.execute_calls = 0
        self.queries = []

        self.daily_loads = daily_loads or []
        self.recommendations = recommendations or []

        # Первый запрос получает AI-запуски.
        # Следующие — нагрузки и рекомендации.
        self.results = [
            runs,
            self.daily_loads,
            self.recommendations,
            *results,
        ]

    def scalar(self, statement):
        return "UTC"

    def execute(self, query):
        self.execute_calls += 1

        selected_columns = getattr(query, "selected_columns", None)

        if selected_columns is None:
            pytest.fail(
                "Не удалось определить столбцы SQL-запроса "
                "в _RecommendationFakeDB"
            )

        column_count = len(selected_columns)

        if column_count == 2:
            # Запрос количества уроков по датам:
            # (date, lesson_count).
            rows = [
                (item.date, 1)
                for item in self.daily_loads
            ]

        elif column_count == 3:
            # Запрос сохранённых прогнозов:
            # (date, level, source).
            rows = [
                (item.date, item.level, item.source)
                for item in self.daily_loads
            ]

        else:
            pytest.fail(
                "Неожиданное количество столбцов SQL-запроса "
                f"в _RecommendationFakeDB: {column_count}"
            )

        return SimpleNamespace(all=lambda: rows)

    def scalars(self, query):
        self.queries.append(query)

        if self.calls >= len(self.results):
            pytest.fail(
                "Builder выполнил больше запросов, "
                "чем предусмотрено fake DB"
            )

        rows = self.results[self.calls]
        self.calls += 1

        return SimpleNamespace(all=lambda: rows)


def _build_recommendations(
    db,
    *,
    school_class=None,
    month="11",
    is_admin=False,
    teacher_ids=None,
    teacher_schedule_ids=None,
):
    """Общий вызов builder с тестовыми параметрами."""
    if school_class is None:
        school_class = SimpleNamespace(
            id=34,
            school_id=1,
            academic_year_id=7,
        )

    return main.build_class_recommendations(
        school_class=school_class,
        month=month,
        db=db,
        current_user=SimpleNamespace(id=1),
        is_admin=is_admin,
        teacher_ids=teacher_ids or set(),
        teacher_schedule_ids=teacher_schedule_ids or set(),
    )


def test_build_class_recommendations_returns_schedule_when_no_runs():
    db = _RecommendationFakeDB([])

    result = _build_recommendations(db)

    assert result.analysisStatus == "not_started"
    assert result.isStale is False
    assert result.period is None
    assert result.dailyLoads == []
    assert result.recommendations == []
    assert result.dataSource == "schedule"


def test_build_class_recommendations_returns_successful_ai_data():
    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    daily_load = SimpleNamespace(
        date=PythonDate(2026, 11, 12),
        level=3,
        source="ai",
        reduce_load=None,
        suitable_for_moving=None,
    )

    recommendation = _recommendation_row(
        recommendation_id=20,
        kind="class",
    )

    db = _RecommendationFakeDB(
        [successful_run],
        [daily_load],
        [recommendation],
    )

    result = _build_recommendations(db)

    assert result.analysisStatus == "succeeded"
    assert result.isStale is False
    assert result.dataSource == "ai"

    assert result.period.start == successful_run.period_start
    assert result.period.end == successful_run.period_end

    assert len(result.dailyLoads) == 1
    assert result.dailyLoads[0].date == PythonDate(2026, 11, 12)
    assert result.dailyLoads[0].day == 12
    assert result.dailyLoads[0].level == 3
    assert result.dailyLoads[0].source == "ai"

    assert len(result.recommendations) == 1
    assert result.recommendations[0].kind == "class"
    assert result.recommendations[0].title == "Рекомендация 20"
    assert result.recommendations[0].recommendationText == "Текст 20"
    assert result.recommendations[0].rationale == "Обоснование 20"

    assert result.daysToReduce == []
    assert result.daysToMoveTo == [12]


def test_build_class_recommendations_uses_school_local_date(
    monkeypatch,
):
    local_today = PythonDate(2027, 1, 1)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    db = _RecommendationFakeDB([], [], [])

    result = _build_recommendations(
        db,
        month=None,
    )

    assert result.analysisStatus == "not_started"
    assert result.period is None


def test_build_class_recommendations_prefers_tomorrow(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    tomorrow_run = _recommendation_run(
        run_id=20,
        status="succeeded",
    )
    tomorrow_recommendation = _recommendation_row(
        recommendation_id=200,
        kind="class",
        recommendation_date=PythonDate(2026, 11, 12),
    )

    db = _RecommendationFakeDB(
        [tomorrow_run],
        [],
        [tomorrow_run],
        [tomorrow_recommendation],
    )

    result = _build_recommendations(
        db,
        month=None,
    )

    assert result.analysisStatus == "succeeded"
    assert result.isStale is False
    assert len(result.recommendations) == 1
    assert result.recommendations[0].date == PythonDate(2026, 11, 12)
    assert result.recommendations[0].title == "Рекомендация 200"


def test_build_class_recommendations_uses_newest_run_for_tomorrow(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)
    tomorrow = PythonDate(2026, 11, 12)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    newest_run = _recommendation_run(
        run_id=20,
        status="succeeded",
    )
    older_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    newest_recommendation = _recommendation_row(
        recommendation_id=200,
        kind="class",
        recommendation_date=tomorrow,
    )
    older_recommendation = _recommendation_row(
        recommendation_id=100,
        kind="class",
        recommendation_date=tomorrow,
    )

    db = _RecommendationFakeDB(
        [newest_run, older_run],
        [],
        [newest_run, older_run],
        [newest_recommendation],
        [older_recommendation],
    )

    result = _build_recommendations(
        db,
        month=None,
    )

    assert len(result.recommendations) == 1
    assert result.recommendations[0].title == "Рекомендация 200"
    assert result.recommendations[0].date == tomorrow


def test_build_class_recommendations_reads_school_scope_run_for_class(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)
    tomorrow = PythonDate(2026, 11, 12)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    school_run = _recommendation_run(
        run_id=20,
        status="succeeded",
        scope="school",
        class_id=None,
        school_id=1,
        academic_year_id=7,
        period_start=tomorrow,
        period_end=PythonDate(2026, 11, 25),
    )

    daily_load = SimpleNamespace(
        date=tomorrow,
        level=3,
        source="ai",
        reduce_load=True,
        suitable_for_moving=False,
    )

    recommendation = _recommendation_row(
        recommendation_id=200,
        kind="class",
        recommendation_date=tomorrow,
    )

    db = _RecommendationFakeDB(
        [school_run],
        [daily_load],
        [school_run],
        [recommendation],
    )

    school_class = SimpleNamespace(
        id=34,
        school_id=1,
        academic_year_id=7,
    )

    result = _build_recommendations(
        db,
        school_class=school_class,
        month=None,
    )

    assert result.analysisStatus == "succeeded"
    assert result.isStale is False
    assert result.dataSource == "ai"

    assert len(result.dailyLoads) == 1
    assert result.dailyLoads[0].date == tomorrow
    assert result.dailyLoads[0].level == 3

    assert len(result.recommendations) == 1
    assert result.recommendations[0].date == tomorrow

    assert result.daysToReduce == [12]
    assert result.daysToMoveTo == []

    # Проверяем, что оба запроса допускают школьные запуски.
    for query in (db.queries[0], db.queries[2]):
        compiled = query.compile()
        sql = str(compiled)

        assert "ai_analysis_runs.school_id" in sql
        assert "ai_analysis_runs.academic_year_id" in sql
        assert "ai_analysis_jobs.analysis_date" in sql
        assert "ai_analysis_jobs.created_at" in sql
        assert "ai_analysis_jobs.id" in sql
        assert "school" in compiled.params.values()


def test_build_class_recommendations_does_not_restore_older_run_recommendations(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)
    tomorrow = PythonDate(2026, 11, 12)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    newest_run = _recommendation_run(
        run_id=20,
        status="succeeded",
    )
    older_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    older_recommendation = _recommendation_row(
        recommendation_id=100,
        kind="class",
        recommendation_date=tomorrow,
    )

    db = _RecommendationFakeDB(
        [newest_run, older_run],
        [],
        [newest_run, older_run],
        [],
        [],
        [older_recommendation],
    )

    result = _build_recommendations(
        db,
        month=None,
    )

    assert result.recommendations == []
    assert result.isStale is False

    # Запросили рекомендации только для нового запуска.
    # До результата старого запуска builder не дошёл.
    assert db.calls == 5


@pytest.mark.parametrize(
    ("local_today", "tomorrow"),
    [
        (PythonDate(2026, 11, 30), PythonDate(2026, 12, 1)),
        (PythonDate(2026, 12, 31), PythonDate(2027, 1, 1)),
    ],
)
def test_build_class_recommendations_finds_tomorrow_across_period_boundary(
    monkeypatch,
    local_today,
    tomorrow,
):
    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    tomorrow_run = _recommendation_run(
        run_id=20,
        status="succeeded",
        period_start=tomorrow,
        period_end=tomorrow,
    )
    tomorrow_recommendation = _recommendation_row(
        recommendation_id=200,
        kind="class",
        recommendation_date=tomorrow,
    )

    db = _RecommendationFakeDB(
        [tomorrow_run],
        [],
        [tomorrow_run],
        [tomorrow_recommendation],
    )

    result = _build_recommendations(
        db,
        month=None,
    )

    assert len(result.recommendations) == 1
    assert result.recommendations[0].date == tomorrow

    # Первый запрос получает запуски за диапазон today → tomorrow.
    compiled = db.queries[0].compile()
    bound_dates = {
        value
        for value in compiled.params.values()
        if isinstance(value, PythonDate)
    }

    assert local_today in bound_dates
    assert tomorrow in bound_dates


def test_build_class_recommendations_preserves_teacher_filter_on_today_fallback(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    today_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    recommendations = [
        _recommendation_row(
            recommendation_id=1,
            kind="class",
            recommendation_date=local_today,
        ),
        _recommendation_row(
            recommendation_id=2,
            kind="teacher",
            teacher_id=100,
            recommendation_date=local_today,
        ),
        _recommendation_row(
            recommendation_id=3,
            kind="teacher",
            teacher_id=200,
            recommendation_date=local_today,
        ),
        _recommendation_row(
            recommendation_id=4,
            kind="lesson",
            teacher_id=100,
            schedule_id=500,
            recommendation_date=local_today,
        ),
        _recommendation_row(
            recommendation_id=5,
            kind="lesson",
            teacher_id=100,
            schedule_id=600,
            recommendation_date=local_today,
        ),
    ]

    db = _RecommendationFakeDB(
        [today_run],
        [],
        [],
        [today_run],
        recommendations,
    )

    result = _build_recommendations(
        db,
        month=None,
        is_admin=False,
        teacher_ids={100},
        teacher_schedule_ids={500},
    )

    assert result.isStale is True

    assert [
        item.title
        for item in result.recommendations
    ] == [
        "Рекомендация 1",
        "Рекомендация 2",
        "Рекомендация 4",
    ]


def test_build_class_recommendations_falls_back_to_today(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    today_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )
    today_recommendation = _recommendation_row(
        recommendation_id=100,
        kind="class",
        recommendation_date=local_today,
    )

    db = _RecommendationFakeDB(
        [today_run],
        [],
        [],
        [today_run],
        [today_recommendation],
    )

    result = _build_recommendations(
        db,
        month=None,
    )

    assert result.analysisStatus == "succeeded"
    assert result.isStale is True
    assert len(result.recommendations) == 1
    assert result.recommendations[0].date == local_today
    assert result.recommendations[0].title == "Рекомендация 100"


@pytest.mark.parametrize(
    "latest_status",
    ["queued", "running", "failed"],
)
def test_build_class_recommendations_marks_today_fallback_stale_when_newer_run_exists(
    monkeypatch,
    latest_status,
):
    local_today = PythonDate(2026, 11, 11)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    latest_run = _recommendation_run(
        run_id=20,
        status=latest_status,
    )
    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    daily_load = SimpleNamespace(
        date=local_today,
        level=2,
        source="ai",
        reduce_load=None,
        suitable_for_moving=None,
    )

    today_recommendation = _recommendation_row(
        recommendation_id=100,
        kind="class",
        recommendation_date=local_today,
    )

    db = _RecommendationFakeDB(
        [latest_run, successful_run],
        [daily_load],
        [],
        [successful_run],
        [today_recommendation],
    )

    result = _build_recommendations(
        db,
        month=None,
    )

    assert result.analysisStatus == latest_status
    assert result.isStale is True
    assert result.dataSource == "ai"

    assert len(result.dailyLoads) == 1
    assert result.dailyLoads[0].level == 2

    assert len(result.recommendations) == 1
    assert result.recommendations[0].title == "Рекомендация 100"
    assert result.recommendations[0].date == local_today


def test_build_class_recommendations_returns_empty_when_no_daily_recommendations(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    today_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    db = _RecommendationFakeDB(
        [today_run],
        [],
        [],
        [],
    )

    result = _build_recommendations(
        db,
        month=None,
    )

    assert result.analysisStatus == "succeeded"
    assert result.recommendations == []
    assert result.isStale is False
    assert result.dataSource == "ai"


def test_build_class_recommendations_with_explicit_month_uses_latest_successful_run():
    latest_run = _recommendation_run(
        run_id=20,
        status="succeeded",
    )
    older_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    recommendations = [
        _recommendation_row(
            recommendation_id=200,
            kind="class",
            recommendation_date=PythonDate(2026, 11, 5),
        ),
        _recommendation_row(
            recommendation_id=201,
            kind="class",
            recommendation_date=PythonDate(2026, 11, 20),
        ),
    ]

    db = _RecommendationFakeDB(
        [latest_run, older_run],
        [],
        recommendations,
    )

    result = _build_recommendations(
        db,
        month="11",
    )

    assert result.analysisStatus == "succeeded"
    assert result.isStale is False

    assert [
        item.title
        for item in result.recommendations
    ] == [
        "Рекомендация 200",
        "Рекомендация 201",
    ]

    assert [
        item.date
        for item in result.recommendations
    ] == [
        PythonDate(2026, 11, 5),
        PythonDate(2026, 11, 20),
    ]

    # Явный месяц использует прежний путь без поиска завтра и сегодня.
    assert db.calls == 3


@pytest.mark.parametrize("latest_status", ["queued", "running", "failed"])
def test_build_class_recommendations_marks_previous_success_as_stale(
    latest_status,
):
    latest_run = _recommendation_run(
        run_id=11,
        status=latest_status,
    )
    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    daily_load = SimpleNamespace(
        date=PythonDate(2026, 11, 12),
        level=2,
        source="ai",
        reduce_load=None,
        suitable_for_moving=None,
    )

    db = _RecommendationFakeDB(
        [latest_run, successful_run],
        [daily_load],
        [],
    )

    result = _build_recommendations(db)

    assert result.analysisStatus == latest_status
    assert result.isStale is True
    assert result.dataSource == "ai"
    assert result.period is not None
    assert len(result.dailyLoads) == 1


def test_build_class_recommendations_does_not_use_failed_run_as_ai_data():
    failed_run = _recommendation_run(
        run_id=10,
        status="failed",
    )

    db = _RecommendationFakeDB([failed_run])

    result = _build_recommendations(db)

    assert result.analysisStatus == "failed"
    assert result.isStale is False
    assert result.period is None
    assert result.dailyLoads == []
    assert result.recommendations == []
    assert result.dataSource == "schedule"


@pytest.mark.parametrize("month", ["0", "13", "abc"])
def test_build_class_recommendations_rejects_invalid_month(month):
    db = _RecommendationFakeDB([])

    with pytest.raises(HTTPException) as error:
        _build_recommendations(db, month=month)

    assert error.value.status_code == 400
    assert error.value.detail == (
        "Месяц должен быть указан числом от 01 до 12"
    )


def test_build_class_recommendations_filters_teacher_and_lesson_items():
    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    recommendations = [
        # Рекомендация класса доступна учителю.
        _recommendation_row(
            recommendation_id=1,
            kind="class",
        ),
        # Рекомендация доступного учителя.
        _recommendation_row(
            recommendation_id=2,
            kind="teacher",
            teacher_id=100,
        ),
        # Рекомендация другого учителя.
        _recommendation_row(
            recommendation_id=3,
            kind="teacher",
            teacher_id=200,
        ),
        # Урок доступного расписания и доступного учителя.
        _recommendation_row(
            recommendation_id=4,
            kind="lesson",
            teacher_id=100,
            schedule_id=500,
        ),
        # Урок из чужого расписания.
        _recommendation_row(
            recommendation_id=5,
            kind="lesson",
            teacher_id=100,
            schedule_id=600,
        ),
        # Расписание доступно, но teacher_id чужой.
        _recommendation_row(
            recommendation_id=6,
            kind="lesson",
            teacher_id=200,
            schedule_id=500,
        ),
        # Для lesson без schedule_id доступ не предоставляется.
        _recommendation_row(
            recommendation_id=7,
            kind="lesson",
            teacher_id=100,
            schedule_id=None,
        ),
    ]

    db = _RecommendationFakeDB(
        [successful_run],
        [],
        recommendations,
    )

    result = _build_recommendations(
        db,
        is_admin=False,
        teacher_ids={100},
        teacher_schedule_ids={500},
    )

    assert [item.title for item in result.recommendations] == [
        "Рекомендация 1",
        "Рекомендация 2",
        "Рекомендация 4",
    ]


def test_build_class_recommendations_admin_receives_all_recommendations():
    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    recommendations = [
        _recommendation_row(
            recommendation_id=1,
            kind="teacher",
            teacher_id=200,
        ),
        _recommendation_row(
            recommendation_id=2,
            kind="lesson",
            teacher_id=200,
            schedule_id=600,
        ),
    ]

    db = _RecommendationFakeDB(
        [successful_run],
        [],
        recommendations,
    )

    result = _build_recommendations(
        db,
        is_admin=True,
        teacher_ids={100},
        teacher_schedule_ids={500},
    )

    assert [item.title for item in result.recommendations] == [
        "Рекомендация 1",
        "Рекомендация 2",
    ]


def test_build_class_recommendations_lesson_without_teacher_id_is_allowed_if_schedule_matches():
    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
    )

    recommendation = _recommendation_row(
        recommendation_id=1,
        kind="lesson",
        teacher_id=None,
        schedule_id=500,
    )

    db = _RecommendationFakeDB(
        [successful_run],
        [],
        [recommendation],
    )

    result = _build_recommendations(
        db,
        is_admin=False,
        teacher_ids={100},
        teacher_schedule_ids={500},
    )

    assert len(result.recommendations) == 1
    assert result.recommendations[0].scheduleId == 500
    assert result.recommendations[0].teacherId is None


def test_build_class_heatmap_uses_ai_forecasts_and_preserves_missing_values():
    school_timezone = "Asia/Yekaterinburg"
    today = datetime.now(ZoneInfo(school_timezone)).date()

    forecast_date = PythonDate(today.year, today.month, 1)

    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeDB:
        def __init__(self):
            self.execute_calls = 0

        def scalar(self, query):
            return school_timezone

        def execute(self, query):
            self.execute_calls += 1

            if self.execute_calls == 1:
                # Количество уроков за день.
                return FakeResult([(forecast_date, 2)])

            if self.execute_calls == 2:
                # Сохранённый AI-прогноз.
                return FakeResult([(forecast_date, 2, "ai")])

            # Запрос активных сессий редактирования.
            return FakeResult([])

    db = FakeDB()

    school_class = SimpleNamespace(
        id=34,
        school_id=1,
    )

    result = main.build_class_heatmap(
        school_class=school_class,
        month=f"{today.month:02d}",
        current_user_id=1,
        db=db,
    )

    assert result[0].day == 1
    assert result[0].level == 2

    if len(result) > 1:
        assert result[1].level is None

    assert all(item.is_editing is False for item in result)


def _prepare_recommendations_endpoint(
    monkeypatch,
    *,
    roles,
    school_class=None,
    scalar_results=None,
    builder=None,
):
    user = SimpleNamespace(id=1)
    school = SimpleNamespace(id=1)

    if school_class is None:
        school_class = SimpleNamespace(
            id=34,
            code="1a",
            school_id=1,
            academic_year_id=7,
        )

    scalar_results = list(scalar_results or [])

    def fake_scalars(query):
        if not scalar_results:
            pytest.fail("Неожиданный вызов db.scalars()")

        rows = scalar_results.pop(0)
        return SimpleNamespace(all=lambda: rows)

    db = SimpleNamespace(
        scalar=lambda query: school_class,
        scalars=fake_scalars,
    )

    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: school,
    )
    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda current_user, db: (roles, set()),
    )

    if builder is not None:
        monkeypatch.setattr(
            main,
            "build_class_recommendations",
            builder,
        )

    return user, school_class, db


def test_school_recommendations_denies_admin_from_another_school(
    monkeypatch,
):
    def unexpected_builder(**kwargs):
        pytest.fail(
            "Рекомендации нельзя получать без доступа к школе"
        )

    user, _, db = _prepare_recommendations_endpoint(
        monkeypatch,
        roles={"admin"},
        builder=unexpected_builder,
    )

    def deny_school_access(school_id, user, db):
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этой школе",
        )

    monkeypatch.setattr(
        main,
        "require_school_access",
        deny_school_access,
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_recommendations(
            school_id=2,
            class_code="1a",
            current_user=user,
            db=db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этой школе"


def test_school_recommendations_passes_teacher_access_to_builder(monkeypatch):
    captured = {}

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return "recommendations"

    user, school_class, db = _prepare_recommendations_endpoint(
        monkeypatch,
        roles={"teacher"},
        scalar_results=[
            [100],  # Teacher.id
            [200],  # TeachingAssignment.id
            [],     # TeacherClassAccess.id
            [500, 501],  # Schedule.id
        ],
        builder=fake_builder,
    )

    result = main.get_school_recommendations(
        school_id=1,
        class_code="1a",
        month="11",
        current_user=user,
        db=db,
    )

    assert result == "recommendations"
    assert captured["school_class"] is school_class
    assert captured["month"] == "11"
    assert captured["current_user"] is user
    assert captured["is_admin"] is False
    assert captured["teacher_ids"] == {100}
    assert captured["teacher_schedule_ids"] == {500, 501}


def test_school_recommendations_denies_teacher_without_teacher_record(
    monkeypatch,
):
    def unexpected_builder(**kwargs):
        pytest.fail("Builder не должен вызываться без Teacher.id")

    user, _, db = _prepare_recommendations_endpoint(
        monkeypatch,
        roles={"teacher"},
        scalar_results=[[]],
        builder=unexpected_builder,
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_recommendations(
            school_id=1,
            class_code="1a",
            current_user=user,
            db=db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этому классу"


def test_school_recommendations_denies_teacher_without_class_assignment_or_access(
    monkeypatch,
):
    def unexpected_builder(**kwargs):
        pytest.fail(
            "Builder не должен вызываться без назначения "
            "и без TeacherClassAccess"
        )

    user, _, db = _prepare_recommendations_endpoint(
        monkeypatch,
        roles={"teacher"},
        scalar_results=[
            [100],  # Teacher.id
            [],     # TeachingAssignment.id
            [],     # TeacherClassAccess.id
        ],
        builder=unexpected_builder,
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_recommendations(
            school_id=1,
            class_code="1a",
            current_user=user,
            db=db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этому классу"


def test_school_recommendations_allows_teacher_class_access_without_assignment(
    monkeypatch,
):
    captured = {}

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return "recommendations"

    user, school_class, db = _prepare_recommendations_endpoint(
        monkeypatch,
        roles={"teacher"},
        scalar_results=[
            [100],  # Teacher.id
            [],     # TeachingAssignment.id
            [300],  # TeacherClassAccess.id
        ],
        builder=fake_builder,
    )

    result = main.get_school_recommendations(
        school_id=1,
        class_code="1a",
        current_user=user,
        db=db,
    )

    assert result == "recommendations"
    assert captured["school_class"] is school_class
    assert captured["is_admin"] is False
    assert captured["teacher_ids"] == {100}
    assert captured["teacher_schedule_ids"] == set()


def test_school_recommendations_admin_has_precedence_over_teacher_role(
    monkeypatch,
):
    captured = {}

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return "recommendations"

    user, _, db = _prepare_recommendations_endpoint(
        monkeypatch,
        roles={"admin", "teacher"},
        scalar_results=[],
        builder=fake_builder,
    )

    result = main.get_school_recommendations(
        school_id=1,
        class_code="1a",
        current_user=user,
        db=db,
    )

    assert result == "recommendations"
    assert captured["is_admin"] is True
    assert captured["teacher_ids"] == set()
    assert captured["teacher_schedule_ids"] == set()


def test_school_recommendations_denies_role_without_teacher_or_admin(
    monkeypatch,
):
    def unexpected_builder(**kwargs):
        pytest.fail("Builder не должен вызываться для роли student")

    user, _, db = _prepare_recommendations_endpoint(
        monkeypatch,
        roles={"student"},
        scalar_results=[],
        builder=unexpected_builder,
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_recommendations(
            school_id=1,
            class_code="1a",
            current_user=user,
            db=db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == (
        "У вашей роли нет доступа к этому разделу"
    )


def test_school_recommendations_returns_404_when_class_is_missing(
    monkeypatch,
):
    user = SimpleNamespace(id=1)

    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: SimpleNamespace(id=school_id),
    )
    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda current_user, db: ({"admin"}, set()),
    )

    db = SimpleNamespace(
        scalar=lambda query: None,
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_recommendations(
            school_id=1,
            class_code="missing",
            current_user=user,
            db=db,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Класс не найден"



@pytest.mark.parametrize(
    ("forecast_exists", "expected_has_data"),
    [
        (True, True),
        (False, False),
    ],
)
def test_build_class_summary_has_data_reflects_saved_forecast(
    monkeypatch,
    forecast_exists,
    expected_has_data,
):
    target_date = PythonDate(2026, 11, 12)

    monkeypatch.setattr(
        main,
        "get_effective_daily_loads",
        lambda **kwargs: {
            target_date: (3, "python"),
        },
    )

    class FakeDB:
        def scalar(self, query):
            return 1 if forecast_exists else None

    result = main.build_class_summary(
        school_class=SimpleNamespace(
            id=34,
            school_id=1,
        ),
        target_date=target_date,
        db=FakeDB(),
    )

    assert result.level == 3
    assert result.date == "12.11"
    assert result.has_data is expected_has_data



def test_get_effective_daily_loads_preserves_saved_python_forecast(
    monkeypatch,
):
    target_date = PythonDate(2026, 11, 12)

    monkeypatch.setattr(
        main,
        "get_daily_lesson_counts",
        lambda **kwargs: {target_date: 7},
    )

    class FakeDB:
        def execute(self, query):
            return SimpleNamespace(
                all=lambda: [
                    (target_date, 4, "python"),
                ]
            )

    result = main.get_effective_daily_loads(
        school_class=SimpleNamespace(id=34),
        start_date=target_date,
        end_date=target_date,
        db=FakeDB(),
    )

    # Несмотря на изменившееся расписание (7 уроков),
    # возвращается ранее сохранённый Python-прогноз.
    assert result[target_date] == (4, "python")


def test_get_effective_daily_loads_uses_python_for_missing_forecast(
    monkeypatch,
):
    target_date = PythonDate(2026, 11, 12)

    monkeypatch.setattr(
        main,
        "get_daily_lesson_counts",
        lambda **kwargs: {target_date: 7},
    )

    class FakeDB:
        def execute(self, query):
            return SimpleNamespace(all=lambda: [])

    result = main.get_effective_daily_loads(
        school_class=SimpleNamespace(id=34),
        start_date=target_date,
        end_date=target_date,
        db=FakeDB(),
    )

    assert result[target_date] == (0, "python")


def test_get_effective_daily_loads_returns_none_without_lessons(
    monkeypatch,
):
    target_date = PythonDate(2026, 11, 12)

    monkeypatch.setattr(
        main,
        "get_daily_lesson_counts",
        lambda **kwargs: {},
    )

    class FakeDB:
        def execute(self, query):
            return SimpleNamespace(all=lambda: [])

    result = main.get_effective_daily_loads(
        school_class=SimpleNamespace(id=34),
        start_date=target_date,
        end_date=target_date,
        db=FakeDB(),
    )

    assert result[target_date] == (None, None)


@pytest.mark.parametrize(
    (
        "ai_level",
        "lesson_count",
        "reduce_load",
        "suitable_for_moving",
        "expected_reduce",
        "expected_move",
    ),
    [
        # AI считает день лёгким, но Python видит 7 уроков.
        # AI-флаги отсутствуют — используется Python fallback.
        (4, 7, None, None, [12], []),

        # AI считает день перегруженным, но Python видит 2 урока.
        # AI-флаги отсутствуют — используется Python fallback.
        (0, 2, None, None, [], [12]),

        # AI явно запрещает перенос нагрузки.
        # Python fallback не должен его переопределять.
        (4, 7, False, None, [], []),

        # AI явно разрешает перенос.
        # Python fallback не должен его переопределять.
        (0, 7, None, True, [12], [12]),
    ],
)
def test_recommendations_use_independent_ai_flags_and_python_fallback(
    monkeypatch,
    ai_level,
    lesson_count,
    reduce_load,
    suitable_for_moving,
    expected_reduce,
    expected_move,
):
    target_date = PythonDate(2026, 11, 12)
    local_today = PythonDate(2026, 11, 11)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    # Эффективный уровень тепловой карты приходит от AI.
    monkeypatch.setattr(
        main,
        "get_effective_daily_loads",
        lambda **kwargs: {
            target_date: (ai_level, "ai"),
        },
    )

    # Python fallback получает реальное количество уроков.
    monkeypatch.setattr(
        main,
        "get_daily_lesson_counts",
        lambda **kwargs: {
            target_date: lesson_count,
        },
    )

    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
        period_start=PythonDate(2026, 11, 1),
        period_end=PythonDate(2026, 11, 30),
    )

    daily_load = SimpleNamespace(
        date=target_date,
        level=ai_level,
        source="ai",
        reduce_load=reduce_load,
        suitable_for_moving=suitable_for_moving,
    )

    db = _RecommendationFakeDB(
        [successful_run],
        [daily_load],
        [],
    )

    result = _build_recommendations(db)

    assert result.dailyLoads[0].level == ai_level
    assert result.dailyLoads[0].source == "ai"

    assert result.daysToReduce == expected_reduce
    assert result.daysToMoveTo == expected_move


def test_recommendation_day_lists_include_only_future_dates(
    monkeypatch,
):
    local_today = PythonDate(2026, 11, 11)

    past_date = PythonDate(2026, 11, 10)
    today = local_today
    future_reduce_date = PythonDate(2026, 11, 12)
    future_move_date = PythonDate(2026, 11, 13)

    monkeypatch.setattr(
        main,
        "get_school_local_today",
        lambda db, school_id: local_today,
    )

    dates = [
        past_date,
        today,
        future_reduce_date,
        future_move_date,
    ]

    daily_loads = [
        SimpleNamespace(
            date=target_date,
            level=0 if target_date != future_move_date else 4,
            source="ai",
            reduce_load=None,
            suitable_for_moving=None,
        )
        for target_date in dates
    ]

    monkeypatch.setattr(
        main,
        "get_effective_daily_loads",
        lambda **kwargs: {
            item.date: (item.level, item.source)
            for item in daily_loads
        },
    )

    lesson_counts = {
        past_date: 7,
        today: 7,
        future_reduce_date: 7,
        future_move_date: 2,
    }

    monkeypatch.setattr(
        main,
        "get_daily_lesson_counts",
        lambda **kwargs: lesson_counts,
    )

    successful_run = _recommendation_run(
        run_id=10,
        status="succeeded",
        period_start=PythonDate(2026, 11, 1),
        period_end=PythonDate(2026, 11, 30),
    )

    db = _RecommendationFakeDB(
        [successful_run],
        daily_loads,
        [],
    )

    result = _build_recommendations(db, month="11")

    # История тепловой карты сохраняется полностью.
    assert [
        item.date for item in result.dailyLoads
    ] == dates

    # Прошедший и сегодняшний дни не становятся рекомендациями.
    assert result.daysToReduce == [12]
    assert result.daysToMoveTo == [13]
