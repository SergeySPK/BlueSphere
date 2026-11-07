import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from threading import Event

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from ai_queue import (
    enqueue_ai_job,
    claim_next_ai_job,
    extend_ai_job_lease,
    complete_ai_job,
    retry_ai_job,
)
from models import (
    AIAnalysisJob,
    School,
    AcademicYear,
    Class,
)


def enqueue_test_job(db_session, survey_test_data, **overrides):
    """Создаёт тестовую задачу AI-анализа."""
    data = {
        "school_id": survey_test_data["school"].id,
        "academic_year_id": survey_test_data["academic_year"].id,
        "class_id": survey_test_data["class"].id,
        "scope": "class",
        "analysis_date": date(2026, 11, 1),
        "period_start": date(2026, 11, 1),
        "period_end": date(2026, 11, 30),
        "dedupe_key": "test-ai-job-001",
        "trigger": "manual",
        "max_attempts": 3,
    }
    data.update(overrides)

    return enqueue_ai_job(db_session, **data)


@pytest.fixture
def committed_ai_job_data():
    """
    Создаёт задачу в отдельной зафиксированной транзакции,
    доступной нескольким независимым PostgreSQL-сессиям.
    """
    engine = create_engine(os.environ["TEST_DATABASE_URL"])

    school_id = None
    job_id = None

    try:
        with Session(engine) as db:
            school = School(
                region="Тестовый регион",
                city="Тестовый город",
                address="Тестовый адрес",
                short_name="Очередь AI",
                full_name="Тестовая школа для очереди AI",
                timezone="Asia/Yekaterinburg",
            )
            db.add(school)
            db.flush()

            academic_year = AcademicYear(
                school_id=school.id,
                name="Тестовый учебный год",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 8, 31),
                is_active=True,
            )
            db.add(academic_year)
            db.flush()

            school_class = Class(
                school_id=school.id,
                academic_year_id=academic_year.id,
                code="ai-queue",
                name="Тестовый класс",
            )
            db.add(school_class)
            db.flush()

            school_local_today = datetime.now(
                        ZoneInfo("Asia/Yekaterinburg")
                    ).date()

            job = enqueue_ai_job(
                db,
                school_id=school.id,
                academic_year_id=academic_year.id,
                class_id=school_class.id,
                scope="class",
                analysis_date=school_local_today,
                period_start=date(2026, 11, 1),
                period_end=date(2026, 11, 30),
                dedupe_key=f"concurrent-ai-job-{school.id}",
                trigger="manual",
                max_attempts=3,
            )

            db.commit()

            school_id = school.id
            job_id = job.id

        yield {
            "engine": engine,
            "school_id": school_id,
            "job_id": job_id,
        }

    finally:
        if school_id is not None:
            with Session(engine) as db:
                db.execute(
                    delete(School).where(School.id == school_id)
                )
                db.commit()

        engine.dispose()


def test_enqueue_creates_job(db_session, survey_test_data):
    job = enqueue_test_job(db_session, survey_test_data)

    db_session.flush()

    assert job.id is not None
    assert job.status == "queued"
    assert job.attempt_count == 0
    assert job.max_attempts == 3
    assert job.scope == "class"


def test_enqueue_duplicate_returns_existing_job(
    db_session,
    survey_test_data,
):
    first = enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    second = enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    assert first.id == second.id

    jobs = (
        db_session.query(AIAnalysisJob)
        .filter_by(dedupe_key="test-ai-job-001")
        .all()
    )
    assert len(jobs) == 1


def test_enqueue_rejects_different_payload_for_same_key(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    with pytest.raises(ValueError):
        enqueue_test_job(
            db_session,
            survey_test_data,
            period_start=date(2026, 10, 1),
            dedupe_key="test-ai-job-001",
        )


def test_claim_changes_status_and_increments_attempt(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    job = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert job is not None
    assert job.status == "running"
    assert job.attempt_count == 1
    assert job.locked_by == "worker-1"
    assert job.locked_until is not None


def test_claim_does_not_take_job_with_active_lease(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    first = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=300,
    )

    assert first is not None

    second = claim_next_ai_job(
        db_session,
        worker_id="worker-2",
        lease_seconds=300,
    )

    assert second is None


def test_expired_job_can_be_claimed_again(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    first = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert first is not None

    first.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()

    second = claim_next_ai_job(
        db_session,
        worker_id="worker-2",
        lease_seconds=60,
    )

    assert second is not None
    assert second.id == first.id
    assert second.locked_by == "worker-2"
    assert second.attempt_count == 2


def test_extend_lease_only_by_owner(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    job = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert job is not None

    assert extend_ai_job_lease(
        db_session,
        job_id=job.id,
        worker_id="worker-1",
        lease_seconds=120,
    ) is True

    assert extend_ai_job_lease(
        db_session,
        job_id=job.id,
        worker_id="worker-2",
        lease_seconds=120,
    ) is False


def test_retry_returns_job_to_queue(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    job = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert job is not None

    result = retry_ai_job(
        db_session,
        job_id=job.id,
        worker_id="worker-1",
        error="Temporary provider error",
        retry_delay_seconds=30,
    )

    assert result is True
    assert job.status == "queued"
    assert job.locked_by is None
    assert job.locked_until is None
    assert job.last_error == "Temporary provider error"


def test_retry_exhaustion_marks_job_failed(
    db_session,
    survey_test_data,
):
    enqueue_test_job(
        db_session,
        survey_test_data,
        max_attempts=1,
    )
    db_session.flush()

    job = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert job is not None
    assert job.attempt_count == 1

    result = retry_ai_job(
        db_session,
        job_id=job.id,
        worker_id="worker-1",
        error="Permanent error",
        retry_delay_seconds=0,
    )

    assert result is True
    assert job.status == "failed"


def test_complete_marks_job_succeeded(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    job = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert job is not None

    result = complete_ai_job(
        db_session,
        job_id=job.id,
        worker_id="worker-1",
    )

    assert result is True
    assert job.status == "succeeded"
    assert job.locked_by is None
    assert job.locked_until is None


def test_another_worker_cannot_complete_job(
    db_session,
    survey_test_data,
):
    enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    job = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert job is not None

    result = complete_ai_job(
        db_session,
        job_id=job.id,
        worker_id="worker-2",
    )

    assert result is False
    assert job.status == "running"
    assert job.locked_by == "worker-1"


@pytest.mark.parametrize("lease_seconds", [0, -1, True])
def test_extend_lease_rejects_invalid_duration(
    db_session,
    survey_test_data,
    lease_seconds,
):
    with pytest.raises(ValueError):
        extend_ai_job_lease(
            db_session,
            job_id=1,
            worker_id="worker-1",
            lease_seconds=lease_seconds,
        )


@pytest.mark.parametrize("retry_delay_seconds", [-1, True])
def test_retry_rejects_invalid_delay(
    db_session,
    survey_test_data,
    retry_delay_seconds,
):
    job = enqueue_test_job(db_session, survey_test_data)
    db_session.flush()

    claimed = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
    )

    assert claimed is not None

    with pytest.raises(ValueError):
        retry_ai_job(
            db_session,
            job_id=job.id,
            worker_id="worker-1",
            error="Temporary error",
            retry_delay_seconds=retry_delay_seconds,
        )


def test_queue_rejects_naive_datetime(
    db_session,
    survey_test_data,
):
    with pytest.raises(ValueError):
        claim_next_ai_job(
            db_session,
            worker_id="worker-1",
            now=datetime(2026, 11, 6, 12, 0, 0),
        )


def test_expired_job_with_exhausted_attempts_becomes_failed(
    db_session,
    survey_test_data,
):
    job = enqueue_test_job(
        db_session,
        survey_test_data,
        max_attempts=1,
    )
    db_session.flush()

    claimed = claim_next_ai_job(
        db_session,
        worker_id="worker-1",
        lease_seconds=60,
    )

    assert claimed is not None
    assert claimed.attempt_count == 1

    claimed.locked_until = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    db_session.flush()

    result = claim_next_ai_job(
        db_session,
        worker_id="worker-2",
    )

    db_session.refresh(job)

    assert result is None
    assert job.status == "failed"
    assert job.locked_by is None
    assert job.locked_until is None
    assert job.last_error is not None


def test_two_workers_do_not_claim_same_locked_job(
    committed_ai_job_data,
):
    """
    Первый worker удерживает блокировку задачи.
    Второй worker должен пропустить заблокированную строку.
    """
    engine = committed_ai_job_data["engine"]
    job_id = committed_ai_job_data["job_id"]

    first_worker_claimed = Event()
    release_first_worker = Event()

    def first_worker():
        with Session(engine) as db:
            job = claim_next_ai_job(
                db,
                worker_id="concurrent-worker-1",
                lease_seconds=300,
            )

            assert job is not None
            assert job.id == job_id

            first_worker_claimed.set()

            if not release_first_worker.wait(timeout=10):
                raise TimeoutError(
                    "Не дождались разрешения завершить первую транзакцию."
                )

            result = (job.id, job.locked_by, job.attempt_count)

            db.commit()
            return result

    def second_worker():
        if not first_worker_claimed.wait(timeout=10):
            raise TimeoutError(
                "Первый worker не захватил задачу вовремя."
            )

        with Session(engine) as db:
            job = claim_next_ai_job(
                db,
                worker_id="concurrent-worker-2",
                lease_seconds=300,
            )

            db.commit()
            return job

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first_worker)

        try:
            assert first_worker_claimed.wait(timeout=10)

            second_future = executor.submit(second_worker)
            second = second_future.result(timeout=10)

        finally:
            release_first_worker.set()

        first = first_future.result(timeout=10)

    assert first == (
        job_id,
        "concurrent-worker-1",
        1,
    )
    assert second is None

    # После фиксации первой транзакции задача всё ещё занята:
    # активная аренда не позволяет забрать её повторно.
    with Session(engine) as db:
        third = claim_next_ai_job(
            db,
            worker_id="concurrent-worker-3",
            lease_seconds=300,
        )
        db.commit()

    assert third is None


def test_previous_worker_cannot_modify_reclaimed_job(
    committed_ai_job_data,
):
    """
    После истечения аренды другой worker забирает задачу.
    Предыдущий владелец больше не может продлевать,
    завершать или возвращать её в очередь.
    """
    engine = committed_ai_job_data["engine"]
    job_id = committed_ai_job_data["job_id"]

    first_claim_time = datetime.now(timezone.utc)

    # Первый worker получает задачу.
    with Session(engine) as db:
        first = claim_next_ai_job(
            db,
            worker_id="old-worker",
            lease_seconds=60,
            now=first_claim_time,
        )

        assert first is not None
        assert first.id == job_id

        db.commit()

    # Имитируем истечение аренды.
    second_claim_time = first_claim_time + timedelta(seconds=61)

    # Второй worker повторно получает ту же задачу.
    with Session(engine) as db:
        second = claim_next_ai_job(
            db,
            worker_id="new-worker",
            lease_seconds=300,
            now=second_claim_time,
        )

        assert second is not None
        assert second.id == job_id
        assert second.locked_by == "new-worker"
        assert second.attempt_count == 2

        db.commit()

    # Старый worker больше не владелец задачи.
    old_worker_action_time = second_claim_time + timedelta(seconds=1)

    with Session(engine) as db:
        assert extend_ai_job_lease(
            db,
            job_id=job_id,
            worker_id="old-worker",
            lease_seconds=300,
            now=old_worker_action_time,
        ) is False

        assert complete_ai_job(
            db,
            job_id=job_id,
            worker_id="old-worker",
            now=old_worker_action_time,
        ) is False

        assert retry_ai_job(
            db,
            job_id=job_id,
            worker_id="old-worker",
            error="Ошибка от старого worker",
            retry_delay_seconds=30,
            now=old_worker_action_time,
        ) is False

        db.commit()

    # Проверяем, что состояние нового владельца не изменилось.
    with Session(engine) as db:
        job = db.get(AIAnalysisJob, job_id)

        assert job is not None
        assert job.status == "running"
        assert job.locked_by == "new-worker"
        assert job.attempt_count == 2
        assert job.last_error is None
