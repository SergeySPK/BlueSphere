from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models import AIAnalysisJob, AIAnalysisRun


def _normalize_now(now: datetime | None = None) -> datetime:
    """Возвращает время в UTC и отклоняет naive datetime."""
    if now is None:
        return datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now должен содержать информацию о временной зоне.")

    return now.astimezone(timezone.utc)


def _validate_worker_id(worker_id: str) -> None:
    if (
        not isinstance(worker_id, str)
        or not worker_id.strip()
        or len(worker_id) > 100
    ):
        raise ValueError("Некорректный worker_id.")


def _validate_lease_seconds(lease_seconds: int) -> None:
    if (
        not isinstance(lease_seconds, int)
        or isinstance(lease_seconds, bool)
        or lease_seconds < 1
    ):
        raise ValueError("lease_seconds должен быть положительным целым числом.")


def _validate_retry_delay(retry_delay_seconds: int) -> None:
    if (
        not isinstance(retry_delay_seconds, int)
        or isinstance(retry_delay_seconds, bool)
        or retry_delay_seconds < 0
    ):
        raise ValueError(
            "retry_delay_seconds должен быть неотрицательным целым числом."
        )


def enqueue_ai_job(
    db: Session,
    *,
    school_id: int,
    academic_year_id: int,
    class_id: int | None,
    scope: str,
    analysis_date: date,
    period_start: date,
    period_end: date,
    dedupe_key: str,
    trigger: str,
    max_attempts: int = 5,
    available_at: datetime | None = None,
) -> AIAnalysisJob:
    """Создаёт задачу или возвращает уже существующую по dedupe_key."""

    if scope not in {"class", "school"}:
        raise ValueError("Недопустимый scope.")

    if (scope == "class") != (class_id is not None):
        raise ValueError("class_id не соответствует scope.")

    if period_end < period_start:
        raise ValueError("Некорректный период.")

    if not dedupe_key or len(dedupe_key) > 160:
        raise ValueError("Некорректный dedupe_key.")

    if max_attempts < 1:
        raise ValueError("max_attempts должен быть положительным.")

    now = datetime.now(timezone.utc)

    stmt = (
        insert(AIAnalysisJob)
        .values(
            school_id=school_id,
            academic_year_id=academic_year_id,
            class_id=class_id,
            scope=scope,
            analysis_date=analysis_date,
            period_start=period_start,
            period_end=period_end,
            dedupe_key=dedupe_key,
            trigger=trigger,
            max_attempts=max_attempts,
            available_at=available_at or now,
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"],
        )
        .returning(AIAnalysisJob.id)
    )

    job_id = db.scalar(stmt)

    if job_id is None:
        job = db.scalar(
            select(AIAnalysisJob).where(
                AIAnalysisJob.dedupe_key == dedupe_key
            )
        )

        if job is None:
            raise RuntimeError("Не удалось получить существующую задачу.")

        expected = (
            school_id,
            academic_year_id,
            class_id,
            scope,
            analysis_date,
            period_start,
            period_end,
            trigger,
        )
        actual = (
            job.school_id,
            job.academic_year_id,
            job.class_id,
            job.scope,
            job.analysis_date,
            job.period_start,
            job.period_end,
            job.trigger,
        )

        if actual != expected:
            raise ValueError(
                "dedupe_key уже используется другой задачей."
            )

        return job

    return db.get(AIAnalysisJob, job_id)


def claim_next_ai_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> AIAnalysisJob | None:
    """Атомарно захватывает одну доступную задачу."""

    _validate_worker_id(worker_id)
    _validate_lease_seconds(lease_seconds)

    now = _normalize_now(now)

    # Задачи с исчерпанными попытками и истёкшей арендой
    # больше не должны возвращаться в очередь.
    failed_job_ids = db.scalars(
        update(AIAnalysisJob)
        .where(
            AIAnalysisJob.status == "running",
            AIAnalysisJob.locked_until <= now,
            AIAnalysisJob.attempt_count >= AIAnalysisJob.max_attempts,
        )
        .values(
            status="failed",
            locked_by=None,
            locked_until=None,
            last_error="Истекла аренда после исчерпания попыток.",
            updated_at=now,
        )
        .returning(AIAnalysisJob.id)
    ).all()

    if failed_job_ids:
        db.execute(
            update(AIAnalysisRun)
            .where(
                AIAnalysisRun.job_id.in_(failed_job_ids),
                AIAnalysisRun.status.in_(("queued", "running")),
            )
            .values(
                status="failed",
                error_code="LeaseExpired",
                error_message=(
                    "Аренда AI-задачи истекла после исчерпания "
                    "допустимого количества попыток."
                ),
                completed_at=now,
            )
        )

    job = db.scalar(
        select(AIAnalysisJob)
        .where(
            AIAnalysisJob.attempt_count < AIAnalysisJob.max_attempts,
            or_(
                (
                    (AIAnalysisJob.status == "queued")
                    & (AIAnalysisJob.available_at <= now)
                ),
                (
                    (AIAnalysisJob.status == "running")
                    & (AIAnalysisJob.locked_until <= now)
                ),
            ),
        )
        .order_by(
            AIAnalysisJob.available_at,
            AIAnalysisJob.created_at,
            AIAnalysisJob.id,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    if job is None:
        return None

    job.status = "running"
    job.attempt_count += 1
    job.locked_by = worker_id
    job.locked_until = now + timedelta(seconds=lease_seconds)
    job.updated_at = now

    db.flush()
    return job


def extend_ai_job_lease(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> bool:
    """Продлевает аренду только её действующему владельцу."""

    _validate_worker_id(worker_id)
    _validate_lease_seconds(lease_seconds)

    now = _normalize_now(now)

    result = db.execute(
        update(AIAnalysisJob)
        .where(
            AIAnalysisJob.id == job_id,
            AIAnalysisJob.status == "running",
            AIAnalysisJob.locked_by == worker_id,
            AIAnalysisJob.locked_until > now,
        )
        .values(
            locked_until=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )

    return result.rowcount == 1


def complete_ai_job(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    now: datetime | None = None,
) -> bool:
    """Завершает задачу при условии, что lease ещё принадлежит worker."""

    _validate_worker_id(worker_id)

    now = _normalize_now(now)

    result = db.execute(
        update(AIAnalysisJob)
        .where(
            AIAnalysisJob.id == job_id,
            AIAnalysisJob.status == "running",
            AIAnalysisJob.locked_by == worker_id,
            AIAnalysisJob.locked_until > now,
        )
        .values(
            status="succeeded",
            locked_by=None,
            locked_until=None,
            last_error=None,
            updated_at=now,
        )
    )

    return result.rowcount == 1


def retry_ai_job(
    db: Session,
    *,
    job_id: int,
    worker_id: str,
    error: str,
    retry_delay_seconds: int = 60,
    retryable: bool = True,
    now: datetime | None = None,
) -> bool:
    """Возвращает задачу в очередь или окончательно завершает её."""

    _validate_worker_id(worker_id)
    _validate_retry_delay(retry_delay_seconds)

    if not isinstance(error, str):
        raise TypeError("error должен быть строкой.")

    now = _normalize_now(now)

    job = db.scalar(
        select(AIAnalysisJob)
        .where(
            AIAnalysisJob.id == job_id,
            AIAnalysisJob.status == "running",
            AIAnalysisJob.locked_by == worker_id,
            AIAnalysisJob.locked_until > now,
        )
        .with_for_update()
    )

    if job is None:
        return False

    should_retry = (
        retryable
        and job.attempt_count < job.max_attempts
    )

    job.status = "queued" if should_retry else "failed"
    job.available_at = (
        now + timedelta(seconds=retry_delay_seconds)
        if should_retry
        else job.available_at
    )
    job.locked_by = None
    job.locked_until = None
    job.last_error = error[:10000]
    job.updated_at = now

    db.flush()
    return True
