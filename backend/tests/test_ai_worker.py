import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import select

import ai_worker
from ai_queue import enqueue_ai_job
from ai_provider import AIRetryableError, AIProviderIdentity
from ai_schemas import AIAnalysisOutput
from ai_service import AIAnalysisResult
from ai_aggregation import aggregate_period_results
from models import (
    AcademicYear,
    AIAnalysisJob,
    AIAnalysisRun,
    AIDailyForecast,
    AIDailyLoad,
    AIRecommendation,
    Class,
    Schedule,
    School,
    Subject,
    Teacher,
    TeachingAssignment,
    User,
)


def _use_test_session(monkeypatch, db_session):
    """
    Направляет сессии worker в ту же тестовую транзакцию,
    которую использует fixture db_session.
    """

    connection = db_session.connection()

    def session_factory():
        return Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        ai_worker,
        "SessionLocal",
        session_factory,
    )


def _set_ai_config(monkeypatch):
    """Задаёт тестовую конфигурацию без реальных AI-запросов."""

    monkeypatch.setenv(
        "AI_BASE_URL",
        "https://test-ai-provider.example/v1",
    )
    monkeypatch.setenv(
        "AI_TOKEN",
        "test-token",
    )
    monkeypatch.setenv(
        "AI_MODEL",
        "test-model",
    )

    monkeypatch.delenv("AI_FALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("AI_FALLBACK_TOKEN", raising=False)
    monkeypatch.delenv("AI_FALLBACK_MODEL", raising=False)


def _create_class_job(db_session):
    """
    Создаёт минимальную школу, учебный год, класс,
    учителя, назначение, расписание и AI-задачу.
    """

    school = School(
        region="Тестовый регион",
        city="Тестовый город",
        address="Тестовый адрес",
        short_name="AI Worker Test",
        full_name="Школа для тестирования AI Worker",
        timezone="Asia/Yekaterinburg",
    )
    db_session.add(school)
    db_session.flush()

    academic_year = AcademicYear(
        school_id=school.id,
        name="2026–2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
        is_active=True,
    )
    db_session.add(academic_year)
    db_session.flush()

    school_class = Class(
        school_id=school.id,
        academic_year_id=academic_year.id,
        code="ai-worker-test",
        name="Тестовый класс",
    )
    db_session.add(school_class)
    db_session.flush()

    user = User(
        sferum_id="ai-worker-test-teacher",
        full_name="Тестовый учитель",
    )
    db_session.add(user)
    db_session.flush()

    teacher = Teacher(
        user_id=user.id,
        school_id=school.id,
    )
    db_session.add(teacher)
    db_session.flush()

    subject = Subject(
        school_id=school.id,
        name="Математика",
    )
    db_session.add(subject)
    db_session.flush()

    assignment = TeachingAssignment(
        school_id=school.id,
        teacher_id=teacher.id,
        class_id=school_class.id,
        subject_id=subject.id,
        academic_year_id=academic_year.id,
        subgroup=0,
    )
    db_session.add(assignment)
    db_session.flush()

    school_local_today = datetime.now(
        ZoneInfo("Asia/Yekaterinburg")
    ).date()

    scheduled_date = school_local_today + timedelta(days=3)

    schedule = Schedule(
        assignment_id=assignment.id,
        date=scheduled_date,
        lesson_number=1,
        room="101",
        lesson_type="Контрольная работа",
    )
    db_session.add(schedule)
    db_session.flush()

    job = enqueue_ai_job(
        db_session,
        school_id=school.id,
        academic_year_id=academic_year.id,
        class_id=school_class.id,
        scope="class",
        analysis_date=school_local_today,
        period_start=scheduled_date,
        period_end=scheduled_date + timedelta(days=1),
        dedupe_key="ai-worker-test-job",
        trigger="manual",
        max_attempts=3,
    )

    db_session.flush()

    return {
        "school": school,
        "academic_year": academic_year,
        "class": school_class,
        "teacher": teacher,
        "subject": subject,
        "assignment": assignment,
        "schedule": schedule,
        "job": job,
        "scheduled_date": scheduled_date,
    }


def _make_ai_result(target_date, level):
    """Формирует корректный ответ AI для одной даты."""

    return AIAnalysisOutput(
        daily_loads=[
            {
                "date": target_date,
                "level": level,
                "survey_dates_used": [],
            }
        ],
        recommendations=[],
    )


def _make_ai_analysis_result(
    target_date,
    level,
    provider="primary.example",
    model="test-model",
):
    return AIAnalysisResult(
        output=_make_ai_result(target_date, level),
        provider_usages=(
            AIProviderIdentity(
                provider=provider,
                model=model,
            ),
        ),
    )


def test_process_next_ai_job_returns_false_when_queue_is_empty(
    db_session,
    monkeypatch,
):
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    result = asyncio.run(
        ai_worker.process_next_ai_job(
            worker_id="test-worker",
        )
    )

    assert result is False


def test_process_next_ai_job_saves_successful_result(
    db_session,
    monkeypatch,
):
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)

    async def fake_analyze_day(source):
        return _make_ai_analysis_result(
            source.target_date,
            level=1,
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job(
            worker_id="test-worker",
        )
    )

    assert result is True

    db_session.expire_all()

    job = db_session.get(
        AIAnalysisJob,
        data["job"].id,
    )

    assert job.status == "succeeded"
    assert job.attempt_count == 1
    assert job.locked_by is None
    assert job.locked_until is None

    run = (
        db_session.query(AIAnalysisRun)
        .filter_by(job_id=job.id)
        .one()
    )

    assert run.status == "succeeded"
    assert run.provider == "primary.example"
    assert run.model == "test-model"
    assert run.completed_at is not None
    assert run.input_hash
    assert run.prompt_version
    assert run.schema_version

    daily_loads = (
        db_session.query(AIDailyLoad)
        .filter_by(analysis_run_id=run.id)
        .order_by(AIDailyLoad.date)
        .all()
    )

    scheduled_date = data["scheduled_date"]

    assert [
        (item.date, item.level, item.source)
        for item in daily_loads
    ] == [
        (scheduled_date, 1, "ai"),
        (scheduled_date + timedelta(days=1), 4, "python"),
    ]

    forecasts = (
        db_session.query(AIDailyForecast)
        .filter_by(class_id=data["class"].id)
        .order_by(AIDailyForecast.date)
        .all()
    )

    assert [
        (item.date, item.level, item.source, item.analysis_run_id)
        for item in forecasts
    ] == [
        (scheduled_date, 1, "ai", run.id),
        (
            scheduled_date + timedelta(days=1),
            4,
            "python",
            run.id,
        ),
    ]


def test_level_four_with_lessons_is_saved_as_ai_forecast(
    db_session,
    monkeypatch,
):
    """Уровень 4 на учебный день должен иметь источник ai."""

    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)
    analyzed_dates = []

    async def fake_analyze_day(source):
        analyzed_dates.append(source.target_date)

        return _make_ai_analysis_result(
            source.target_date,
            level=4,
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("level-four-worker")
    )

    assert result is True
    assert analyzed_dates == [data["scheduled_date"]]

    db_session.expire_all()

    forecasts = (
        db_session.query(AIDailyForecast)
        .filter_by(class_id=data["class"].id)
        .order_by(AIDailyForecast.date)
        .all()
    )

    assert [
        (item.date, item.level, item.source)
        for item in forecasts
    ] == [
        (data["scheduled_date"], 4, "ai"),
        (data["scheduled_date"] + timedelta(days=1), 4, "python"),
    ]


def test_current_and_past_forecasts_are_not_modified(
    db_session,
    monkeypatch,
):
    """Worker не изменяет прогнозы за сегодняшнюю и прошлую даты."""

    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)

    school_today = datetime.now(
        ZoneInfo(data["school"].timezone)
    ).date()

    yesterday = school_today - timedelta(days=1)

    # Переносим тестовую задачу на вчера и сегодня.
    data["schedule"].date = school_today
    data["job"].period_start = yesterday
    data["job"].period_end = school_today

    db_session.add_all(
        [
            AIDailyForecast(
                class_id=data["class"].id,
                date=yesterday,
                level=1,
                source="ai",
            ),
            AIDailyForecast(
                class_id=data["class"].id,
                date=school_today,
                level=2,
                source="ai",
            ),
        ]
    )

    db_session.flush()

    async def unexpected_ai_call(source):
        raise AssertionError(
            "AI не должен вызываться для сегодняшних "
            "и прошедших дат."
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        unexpected_ai_call,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("immutable-forecast-worker")
    )

    assert result is True

    db_session.expire_all()

    forecasts = (
        db_session.query(AIDailyForecast)
        .filter(
            AIDailyForecast.class_id == data["class"].id,
        )
        .order_by(AIDailyForecast.date)
        .all()
    )

    assert [
        (item.date, item.level, item.source)
        for item in forecasts
    ] == [
        (yesterday, 1, "ai"),
        (school_today, 2, "ai"),
    ]


def test_period_without_lessons_does_not_call_ai(
    db_session,
    monkeypatch,
):
    """Если будущих уроков нет, все дни получают Python level 4."""

    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)

    db_session.delete(data["schedule"])
    db_session.flush()

    ai_calls = []

    async def unexpected_ai_call(source):
        ai_calls.append(source.target_date)
        raise AssertionError(
            "AI не должен вызываться, если в периоде нет уроков."
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        unexpected_ai_call,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("empty-period-worker")
    )

    assert result is True
    assert ai_calls == []

    db_session.expire_all()

    forecasts = (
        db_session.query(AIDailyForecast)
        .filter_by(class_id=data["class"].id)
        .order_by(AIDailyForecast.date)
        .all()
    )

    assert [
        (item.date, item.level, item.source)
        for item in forecasts
    ] == [
        (data["scheduled_date"], 4, "python"),
        (data["scheduled_date"] + timedelta(days=1), 4, "python"),
    ]

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == data["job"].id
        )
    )

    assert run is not None
    assert run.provider is None
    assert run.model is None


def test_retryable_error_returns_job_to_queue(
    db_session,
    monkeypatch,
):
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)

    async def fake_analyze_day(source):
        raise AIRetryableError(
            "Тестовая временная ошибка провайдера."
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job(
            worker_id="test-worker",
        )
    )

    assert result is True

    db_session.expire_all()

    job = db_session.get(
        AIAnalysisJob,
        data["job"].id,
    )

    assert job.status == "queued"
    assert job.attempt_count == 1
    assert job.locked_by is None
    assert job.locked_until is None
    assert "AIRetryableError" in job.last_error

    run = (
        db_session.query(AIAnalysisRun)
        .filter_by(job_id=job.id)
        .one()
    )

    assert run.status == "queued"
    assert run.error_code == "AIRetryableError"
    assert run.completed_at is None


def test_school_scope_processes_all_classes(
    db_session,
    monkeypatch,
):
    """School-задача анализирует каждый класс учебного года."""
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    seed_data = _create_class_job(db_session)

    seed_job = seed_data["job"]
    school = seed_data["school"]
    academic_year = seed_data["academic_year"]
    first_class = seed_data["class"]
    assignment = seed_data["assignment"]

    second_class = Class(
        school_id=school.id,
        academic_year_id=academic_year.id,
        code="ai-worker-test-2",
        name="Второй тестовый класс",
    )
    db_session.add(second_class)
    db_session.flush()

    second_assignment = TeachingAssignment(
        school_id=school.id,
        teacher_id=assignment.teacher_id,
        class_id=second_class.id,
        subject_id=assignment.subject_id,
        academic_year_id=academic_year.id,
        subgroup=0,
    )
    db_session.add(second_assignment)
    db_session.flush()

    db_session.add(
        Schedule(
            assignment_id=second_assignment.id,
            date=seed_data["scheduled_date"],
            lesson_number=1,
            room="102",
            lesson_type="Контрольная работа",
        )
    )

    # Исходная class-задача не должна попасть в обработку.
    seed_job.status = "failed"
    db_session.flush()

    school_local_today = datetime.now(
            ZoneInfo("Asia/Yekaterinburg")
        ).date()

    school_job = enqueue_ai_job(
        db_session,
        school_id=school.id,
        academic_year_id=academic_year.id,
        class_id=None,
        scope="school",
        analysis_date=school_local_today,
        period_start=seed_job.period_start,
        period_end=seed_job.period_end,
        dedupe_key="worker-school-scope-test",
        trigger="manual",
    )
    db_session.flush()

    analyzed_dates = []

    async def fake_analyze_day(source):
        analyzed_dates.append(source.target_date)
        return _make_ai_analysis_result(source.target_date, 1)

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("school-worker")
    )

    assert result is True

    db_session.expire_all()

    saved_job = db_session.get(AIAnalysisJob, school_job.id)
    assert saved_job.status == "succeeded"

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == school_job.id
        )
    )

    assert run is not None
    assert run.scope == "school"
    assert run.class_id is None
    assert run.status == "succeeded"

    class_ids = {
        first_class.id,
        second_class.id,
    }

    loads = (
        db_session.query(AIDailyLoad)
        .filter(
            AIDailyLoad.analysis_run_id == run.id,
            AIDailyLoad.class_id.in_(class_ids),
        )
        .all()
    )

    assert len(loads) == 4
    assert {item.class_id for item in loads} == class_ids
    assert len(analyzed_dates) == 2


def test_lease_loss_does_not_persist_results(
    db_session,
    monkeypatch,
):
    """Worker не сохраняет результаты после потери lease."""
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)
    job_id = data["job"].id

    async def fake_analyze_day(source):
        # Имитируем передачу задания другому worker.
        db = ai_worker.SessionLocal()
        try:
            current_job = db.get(AIAnalysisJob, job_id)
            current_job.locked_by = "replacement-worker"
            db.commit()
        finally:
            db.close()

        return _make_ai_analysis_result(source.target_date, 1)

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("original-worker")
    )

    assert result is True

    db_session.expire_all()

    saved_job = db_session.get(AIAnalysisJob, job_id)
    assert saved_job.status == "running"
    assert saved_job.locked_by == "replacement-worker"

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == job_id
        )
    )

    assert run is not None
    assert run.status == "running"

    loads_count = (
        db_session.query(AIDailyLoad)
        .filter_by(analysis_run_id=run.id)
        .count()
    )
    recommendations_count = (
        db_session.query(AIRecommendation)
        .filter_by(analysis_run_id=run.id)
        .count()
    )

    assert loads_count == 0
    assert recommendations_count == 0


def test_non_retryable_error_fails_job(
    db_session,
    monkeypatch,
):
    """Невосстанавливаемая ошибка завершает задачу."""
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)
    job_id = data["job"].id

    async def fail_analyze_day(source):
        raise ValueError("Invalid AI analysis input")

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fail_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("non-retryable-worker")
    )

    assert result is True

    db_session.expire_all()

    saved_job = db_session.get(AIAnalysisJob, job_id)

    assert saved_job.status == "failed"
    assert saved_job.locked_by is None
    assert saved_job.locked_until is None
    assert "Invalid AI analysis input" in saved_job.last_error

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == job_id
        )
    )

    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "ValueError"


def test_retryable_error_fails_job_after_attempts_exhausted(
    db_session,
    monkeypatch,
):
    """После исчерпания попыток задача завершается ошибкой."""
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)
    job = data["job"]
    job_id = job.id

    job.max_attempts = 1
    db_session.flush()

    async def fail_analyze_day(source):
        raise AIRetryableError(
            "Provider is temporarily unavailable"
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fail_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("exhausted-worker")
    )

    assert result is True

    db_session.expire_all()

    saved_job = db_session.get(AIAnalysisJob, job_id)

    assert saved_job.status == "failed"
    assert saved_job.attempt_count == 1
    assert saved_job.locked_by is None
    assert saved_job.locked_until is None
    assert "temporarily unavailable" in saved_job.last_error

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == job_id
        )
    )

    assert run is not None
    assert run.status == "failed"


def test_persist_success_replaces_previous_results_without_duplicates(
    db_session,
    monkeypatch,
):
    """Повторная запись заменяет результаты того же run."""
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)
    job = data["job"]
    job_id = job.id
    class_id = data["class"].id
    target_date = data["scheduled_date"]

    async def fake_analyze_day(source):
        return _make_ai_analysis_result(source.target_date, 1)

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job("first-worker")
    )
    assert result is True

    db_session.expire_all()

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == job_id
        )
    )
    assert run is not None

    first_count = (
        db_session.query(AIDailyLoad)
        .filter_by(
            analysis_run_id=run.id,
            class_id=class_id,
        )
        .count()
    )
    assert first_count == 2

    saved_job = db_session.get(AIAnalysisJob, job_id)
    saved_job.status = "running"
    saved_job.locked_by = "retry-worker"
    saved_job.locked_until = (
        datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db_session.flush()

    replacement_result = aggregate_period_results(
        period_start=job.period_start,
        period_end=job.period_end,
        scheduled_dates=[target_date],
        day_results=[
            _make_ai_result(target_date, 3),
        ],
    )

    persisted = ai_worker._persist_success(
        job_id=job_id,
        worker_id="retry-worker",
        run_id=run.id,
        aggregated_by_class={
            class_id: replacement_result,
        },
        provider_name="fallback.example",
        model_name="fallback-model",
    )

    assert persisted is True

    db_session.expire_all()

    loads = (
        db_session.query(AIDailyLoad)
        .filter_by(
            analysis_run_id=run.id,
            class_id=class_id,
        )
        .order_by(AIDailyLoad.date)
        .all()
    )

    assert len(loads) == 2

    assert loads[0].date == job.period_start
    assert loads[0].level == 3
    assert loads[0].source == "ai"

    assert loads[1].date == job.period_end
    assert loads[1].level == 4
    assert loads[1].source == "python"

    saved_job = db_session.get(AIAnalysisJob, job_id)
    assert saved_job.status == "succeeded"

    saved_run = db_session.get(AIAnalysisRun, run.id)

    assert saved_run.provider == "fallback.example"
    assert saved_run.model == "fallback-model"


def test_summarize_provider_usage_returns_single_provider():
    usages = [
        AIProviderIdentity(
            provider="primary.example",
            model="model-a",
        ),
        AIProviderIdentity(
            provider="primary.example",
            model="model-a",
        ),
    ]

    assert ai_worker._summarize_provider_usage(usages) == (
        "primary.example",
        "model-a",
    )


def test_summarize_provider_usage_detects_multiple_providers():
    usages = [
        AIProviderIdentity(
            provider="primary.example",
            model="model-a",
        ),
        AIProviderIdentity(
            provider="fallback.example",
            model="model-b",
        ),
    ]

    assert ai_worker._summarize_provider_usage(usages) == (
        "multiple",
        "multiple",
    )


def test_summarize_provider_usage_detects_multiple_models():
    usages = [
        AIProviderIdentity(
            provider="primary.example",
            model="model-a",
        ),
        AIProviderIdentity(
            provider="primary.example",
            model="model-b",
        ),
    ]

    assert ai_worker._summarize_provider_usage(usages) == (
        "primary.example",
        "multiple",
    )


def test_summarize_provider_usage_returns_none_without_requests():
    assert ai_worker._summarize_provider_usage([]) == (None, None)


def test_analyze_with_lease_renews_during_long_ai_call(
    monkeypatch,
):
    """Lease продлевается, пока AI-вызов ещё выполняется."""

    monkeypatch.setattr(
        ai_worker,
        "LEASE_SECONDS",
        0.3,
    )

    renewals = []

    def fake_renew(job_id, worker_id):
        renewals.append((job_id, worker_id))

    async def fake_analyze_day(context):
        await asyncio.sleep(0.35)
        return "analysis-result"

    monkeypatch.setattr(
        ai_worker,
        "_renew_lease",
        fake_renew,
    )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker._analyze_with_lease(
            job_id=123,
            worker_id="heartbeat-worker",
            context=object(),
        )
    )

    assert result == "analysis-result"
    assert len(renewals) >= 2
    assert all(
        item == (123, "heartbeat-worker")
        for item in renewals
    )


def test_analyze_with_lease_cancels_ai_after_lease_loss(
    monkeypatch,
):
    """После потери lease AI-вызов отменяется."""

    monkeypatch.setattr(
        ai_worker,
        "LEASE_SECONDS",
        0.3,
    )

    cancelled = asyncio.Event()

    def fake_renew(job_id, worker_id):
        raise ai_worker.LeaseLostError(
            "Lease was reassigned."
        )

    async def fake_analyze_day(context):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(
        ai_worker,
        "_renew_lease",
        fake_renew,
    )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    async def run_test():
        try:
            await ai_worker._analyze_with_lease(
                job_id=123,
                worker_id="old-worker",
                context=object(),
            )
        except ai_worker.LeaseLostError:
            pass
        else:
            raise AssertionError(
                "Ожидалась LeaseLostError."
            )

        assert cancelled.is_set()

    asyncio.run(run_test())


def test_delayed_job_does_not_analyze_dates_that_have_arrived(
    db_session,
    monkeypatch,
):
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)

    school_today = datetime.now(
        ZoneInfo(data["school"].timezone)
    ).date()

    yesterday = school_today - timedelta(days=1)
    tomorrow = school_today + timedelta(days=1)

    data["job"].analysis_date = yesterday
    data["job"].period_start = yesterday
    data["job"].period_end = tomorrow

    data["schedule"].date = school_today

    db_session.add(
        Schedule(
            assignment_id=data["assignment"].id,
            date=tomorrow,
            lesson_number=2,
            room="102",
            lesson_type="Обычный урок",
        )
    )
    db_session.flush()

    monkeypatch.setattr(
        ai_worker,
        "_get_school_local_today",
        lambda timezone_name: school_today,
    )

    analyzed_dates = []

    async def fake_analyze_day(source):
        analyzed_dates.append(source.target_date)

        return _make_ai_analysis_result(
            source.target_date,
            level=2,
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job(
            "delayed-worker",
        )
    )

    assert result is True
    assert analyzed_dates == [tomorrow]

    db_session.expire_all()

    forecasts = (
        db_session.query(AIDailyForecast)
        .filter_by(class_id=data["class"].id)
        .order_by(AIDailyForecast.date)
        .all()
    )

    assert [
        (item.date, item.level, item.source)
        for item in forecasts
    ] == [
        (tomorrow, 2, "ai"),
    ]


def test_date_that_arrives_during_processing_is_not_analyzed(
    db_session,
    monkeypatch,
):
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)

    target_date = data["scheduled_date"]
    initial_today = target_date - timedelta(days=1)

    # При сборе контекстов дата ещё будущая.
    # Перед первым AI-вызовом наступает полночь.
    current_dates = iter([
        initial_today,
        target_date,
    ])

    monkeypatch.setattr(
        ai_worker,
        "_get_school_local_today",
        lambda timezone_name: next(current_dates),
    )

    monkeypatch.setattr(
        ai_worker,
        "_is_future_school_date",
        lambda db, checked_date, timezone_name: (
            checked_date > target_date
        ),
    )

    analyzed_dates = []

    async def fake_analyze_day(source):
        analyzed_dates.append(source.target_date)

        return _make_ai_analysis_result(
            source.target_date,
            level=1,
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job(
            "midnight-race-worker",
        )
    )

    assert result is True

    # Дата наступила до вызова AI.
    assert analyzed_dates == []

    db_session.expire_all()

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == data["job"].id
        )
    )

    assert run is not None
    assert run.status == "succeeded"
    assert run.provider is None
    assert run.model is None

    daily_loads = (
        db_session.query(AIDailyLoad)
        .filter_by(analysis_run_id=run.id)
        .all()
    )

    recommendations = (
        db_session.query(AIRecommendation)
        .filter_by(analysis_run_id=run.id)
        .all()
    )

    assert [
        (item.date, item.level, item.source)
        for item in daily_loads
    ] == [
        (target_date + timedelta(days=1), 4, "python"),
    ]

    assert all(
        item.date > target_date
        for item in daily_loads
    )

    assert recommendations == []


def test_persist_success_skips_dates_that_are_no_longer_future(
    db_session,
    monkeypatch,
):
    _use_test_session(monkeypatch, db_session)
    _set_ai_config(monkeypatch)

    data = _create_class_job(db_session)

    target_date = data["scheduled_date"]

    async def fake_analyze_day(source):
        return AIAnalysisResult(
            output=AIAnalysisOutput(
                daily_loads=[
                    {
                        "date": source.target_date,
                        "level": 1,
                        "survey_dates_used": [],
                    }
                ],
                recommendations=[
                    {
                        "date": target_date,
                        "kind": "class",
                        "priority": "normal",
                        "title": "Уже наступившая дата",
                        "recommendation_text": (
                            "Эта рекомендация не должна сохраниться."
                        ),
                    },
                    {
                        "date": target_date + timedelta(days=1),
                        "kind": "class",
                        "priority": "normal",
                        "title": "Будущая дата",
                        "recommendation_text": (
                            "Эта рекомендация должна сохраниться."
                        ),
                    },
                ],
            ),
            provider_usages=(
                AIProviderIdentity(
                    provider="primary.example",
                    model="test-model",
                ),
            ),
        )

    monkeypatch.setattr(
        ai_worker,
        "analyze_day_with_metadata",
        fake_analyze_day,
    )

    # До начала обработки дата будущая.
    # Но к моменту сохранения считаем её наступившей.
    monkeypatch.setattr(
        ai_worker,
        "_get_school_local_today",
        lambda timezone_name: target_date - timedelta(days=1),
    )

    # Подменяем непосредственно проверку на этапе INSERT.
    # Это позволяет детерминированно воспроизвести переход
    # даты между AI-анализом и сохранением.
    monkeypatch.setattr(
        ai_worker,
        "_is_future_school_date",
        lambda db, checked_date, timezone_name: (
            checked_date > target_date
        ),
    )

    original_text = ai_worker.text
    forecast_insert_sql = []

    def capture_forecast_insert(statement, *args, **kwargs):
        statement_string = str(statement)

        if "INSERT INTO ai_daily_forecasts" in statement_string:
            forecast_insert_sql.append(statement_string)

        return original_text(statement, *args, **kwargs)

    monkeypatch.setattr(
        ai_worker,
        "text",
        capture_forecast_insert,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job(
            "persist-midnight-race-worker",
        )
    )

    assert result is True

    assert len(forecast_insert_sql) == 1

    forecast_sql = forecast_insert_sql[0]

    assert forecast_sql.count("clock_timestamp()") == 2
    assert "now() AT TIME ZONE :school_timezone" not in forecast_sql

    db_session.expire_all()

    run = db_session.scalar(
        select(AIAnalysisRun).where(
            AIAnalysisRun.job_id == data["job"].id
        )
    )

    assert run is not None
    assert run.status == "succeeded"

    # Результат за наступившую дату не сохранился.
    daily_loads = (
        db_session.query(AIDailyLoad)
        .filter_by(
            analysis_run_id=run.id,
            date=target_date,
        )
        .all()
    )

    recommendations = (
        db_session.query(AIRecommendation)
        .filter_by(
            analysis_run_id=run.id,
            date=target_date,
        )
        .all()
    )

    assert daily_loads == []
    assert recommendations == []

    # Рекомендация на следующую будущую дату сохранилась.
    future_recommendations = (
        db_session.query(AIRecommendation)
        .filter_by(
            analysis_run_id=run.id,
            date=target_date + timedelta(days=1),
        )
        .all()
    )

    assert len(future_recommendations) == 1
    assert future_recommendations[0].title == "Будущая дата"


def test_process_next_ai_job_does_not_claim_job_when_ai_is_disabled(
    monkeypatch,
):
    monkeypatch.setattr(
        ai_worker,
        "get_ai_config_if_configured",
        lambda: None,
    )

    def forbidden_claim(*args, **kwargs):
        raise AssertionError(
            "Worker не должен забирать задания без AI-конфигурации."
        )

    def forbidden_session():
        raise AssertionError(
            "Worker не должен открывать БД без AI-конфигурации."
        )

    monkeypatch.setattr(
        ai_worker,
        "claim_next_ai_job",
        forbidden_claim,
    )
    monkeypatch.setattr(
        ai_worker,
        "SessionLocal",
        forbidden_session,
    )

    result = asyncio.run(
        ai_worker.process_next_ai_job(
            worker_id="test-worker",
        )
    )

    assert result is False
