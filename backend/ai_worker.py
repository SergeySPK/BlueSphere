"""Фоновый worker для выполнения задач AI-анализа."""

import asyncio
import hashlib
import json
import logging
import os
import socket
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text

from ai_aggregation import aggregate_period_results
from ai_config import get_ai_config_if_configured
from ai_context import build_ai_analysis_input_for_date, collect_ai_analysis_input
from ai_prompts import AI_PROMPT_VERSION
from ai_provider import AINonRetryableError
from ai_schemas import AIAnalysisOutput
from ai_service import analyze_day_with_metadata
from ai_queue import (
    claim_next_ai_job,
    complete_ai_job,
    extend_ai_job_lease,
    retry_ai_job,
)
from database import SessionLocal
from models import (
    AIAnalysisJob,
    AIAnalysisRun,
    AIDailyLoad,
    AIRecommendation,
    Class,
    Schedule,
    School,
    TeachingAssignment,
)


logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
LEASE_SECONDS = 300
RETRY_DELAY_SECONDS = 60

SCHEMA_VERSION = AIAnalysisOutput.model_fields["schema_version"].default


class LeaseLostError(RuntimeError):
    """Worker потерял аренду задачи и не может продолжать её обработку."""


def _worker_id() -> str:
    configured = os.getenv("AI_WORKER_ID", "").strip()

    if configured:
        return configured[:100]

    return f"{socket.gethostname()}:{os.getpid()}"[:100]


def _job_payload(job: AIAnalysisJob) -> dict:
    """Копирует поля задачи до закрытия сессии после claim."""

    return {
        "id": job.id,
        "school_id": job.school_id,
        "academic_year_id": job.academic_year_id,
        "class_id": job.class_id,
        "scope": job.scope,
        "analysis_date": job.analysis_date,
        "period_start": job.period_start,
        "period_end": job.period_end,
        "attempt_count": job.attempt_count,
    }


def _get_class_ids(db, job: dict) -> list[int]:
    """Возвращает классы, входящие в область анализа."""

    if job["scope"] == "class":
        class_id = db.scalar(
            select(Class.id).where(
                Class.id == job["class_id"],
                Class.school_id == job["school_id"],
                Class.academic_year_id == job["academic_year_id"],
            )
        )

        if class_id is None:
            raise ValueError(
                "Класс задачи не найден в указанной школе "
                "и учебном году."
            )

        return [class_id]

    if job["scope"] != "school":
        raise ValueError(
            f"Неизвестная область анализа: {job['scope']}"
        )

    class_ids = db.scalars(
        select(Class.id)
        .where(
            Class.school_id == job["school_id"],
            Class.academic_year_id == job["academic_year_id"],
        )
        .order_by(Class.id)
    ).all()

    if not class_ids:
        raise ValueError("В школе нет классов для анализа.")

    return list(class_ids)


def _get_school_timezone(db, school_id: int) -> str:
    """Возвращает проверенный часовой пояс школы."""

    timezone_name = db.scalar(
        select(School.timezone).where(
            School.id == school_id,
        )
    )

    if not timezone_name or not timezone_name.strip():
        raise ValueError(
            f"Для школы {school_id} не задан часовой пояс. "
            "Настройте timezone в карточке школы."
        )

    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(
            f"Для школы {school_id} задан некорректный "
            f"часовой пояс: {timezone_name!r}."
        ) from None

    return timezone_name


def _get_school_local_today(
    timezone_name: str,
    now: datetime | None = None,
):
    """Возвращает текущую дату в часовом поясе школы."""

    school_timezone = ZoneInfo(timezone_name)

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(
            "Время now должно содержать часовой пояс."
        )

    return now.astimezone(school_timezone).date()


def _collect_class_contexts(
    db,
    job: dict,
    class_id: int,
    school_local_today,
    progress_callback=None,
):
    """
    Собирает базовый контекст класса один раз,
    затем формирует контексты для каждой будущей даты
    с уроками.
    """

    scheduled_dates = db.scalars(
        select(Schedule.date)
        .join(
            TeachingAssignment,
            TeachingAssignment.id == Schedule.assignment_id,
        )
        .where(
            TeachingAssignment.school_id == job["school_id"],
            TeachingAssignment.academic_year_id
            == job["academic_year_id"],
            TeachingAssignment.class_id == class_id,
            Schedule.date >= job["period_start"],
            Schedule.date <= job["period_end"],
        )
        .distinct()
        .order_by(Schedule.date)
    ).all()

    future_scheduled_dates = [
        target_date
        for target_date in scheduled_dates
        if target_date > school_local_today
    ]

    if not future_scheduled_dates:
        return [], []

    # Не позволяем lease истечь во время обработки
    # большого количества дат.
    if progress_callback is not None:
        progress_callback()

    # Самая поздняя дата позволяет получить всю историю
    # закрытых опросов, потенциально нужную для периода.
    base_context = collect_ai_analysis_input(
        db,
        school_id=job["school_id"],
        class_id=class_id,
        period_start=job["period_start"],
        period_end=job["period_end"],
        target_date=future_scheduled_dates[-1],
        progress_callback=progress_callback,
    )

    contexts = []

    for target_date in future_scheduled_dates:
        if progress_callback is not None:
            progress_callback()

        context = build_ai_analysis_input_for_date(
            base_context,
            target_date,
        )

        contexts.append(context)

    return future_scheduled_dates, contexts


def _build_input_hash(
    contexts_by_class: dict[int, list],
    scheduled_by_class: dict[int, list],
    school_local_today,
) -> str:
    """Хеширует AI-контексты, расписание и версии prompt/schema."""

    payload = {
        "prompt_version": AI_PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "school_local_today": school_local_today.isoformat(),
        "classes": [
            {
                "class_id": class_id,
                "scheduled_dates": [
                    item.isoformat()
                    for item in scheduled_by_class[class_id]
                ],
                "contexts": [
                    context.model_dump(mode="json")
                    for context in contexts
                ],
            }
            for class_id, contexts in sorted(
                contexts_by_class.items()
            )
        ],
    }

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _summarize_provider_usage(
    usages,
) -> tuple[str | None, str | None]:
    """
    Возвращает метаданные провайдера для всего AIAnalysisRun.

    Если использовалась одна комбинация provider/model,
    сохраняет её точные значения.

    Если комбинаций было несколько, возвращает multiple
    для соответствующего поля.
    """

    identities = {
        (usage.provider, usage.model)
        for usage in usages
    }

    if not identities:
        return None, None

    providers = {provider for provider, _ in identities}
    models = {model for _, model in identities}

    provider_name = (
        next(iter(providers))
        if len(providers) == 1
        else "multiple"
    )

    model_name = (
        next(iter(models))
        if len(models) == 1
        else "multiple"
    )

    return provider_name, model_name


def _renew_lease(job_id: int, worker_id: str) -> None:
    """Продлевает аренду задачи."""

    db = SessionLocal()

    try:
        renewed = extend_ai_job_lease(
            db,
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=LEASE_SECONDS,
        )

        if not renewed:
            db.rollback()

            raise LeaseLostError(
                f"Worker потерял lease задачи {job_id}."
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def _analyze_with_lease(
    job_id: int,
    worker_id: str,
    context,
):
    """
    Выполняет AI-анализ, регулярно продлевая lease.

    Если lease потерян или продление завершилось ошибкой,
    отменяет AI-задачу и передаёт управление обработчику ошибки.
    """

    analysis_task = asyncio.create_task(
        analyze_day_with_metadata(context)
    )

    heartbeat_interval = max(
        0.1,
        LEASE_SECONDS / 3,
    )

    try:
        while not analysis_task.done():
            done, _ = await asyncio.wait(
                {analysis_task},
                timeout=heartbeat_interval,
            )

            if done:
                break

            # Выполняется в event loop, пока AI-задача ожидает
            # сетевой ответ. Lease продлевается отдельной сессией.
            _renew_lease(
                job_id,
                worker_id,
            )

        return await analysis_task

    except BaseException:
        # Включая отмену самого worker при завершении процесса.
        # Не оставляем дочерний AI-вызов работать бесконтрольно.
        if not analysis_task.done():
            analysis_task.cancel()

        try:
            await analysis_task
        except BaseException:
            # Исходное исключение должно сохраниться.
            pass

        raise


def _start_or_resume_run(
    job: dict,
    worker_id: str,
    input_hash: str,
) -> int:
    """Создаёт единственный run для job или возобновляет его."""

    _renew_lease(job["id"], worker_id)

    db = SessionLocal()

    try:
        run = db.scalar(
            select(AIAnalysisRun).where(
                AIAnalysisRun.job_id == job["id"]
            )
        )

        now = datetime.now(timezone.utc)

        if run is None:
            run = AIAnalysisRun(
                job_id=job["id"],
                school_id=job["school_id"],
                academic_year_id=job["academic_year_id"],
                class_id=job["class_id"],
                scope=job["scope"],
                status="running",
                period_start=job["period_start"],
                period_end=job["period_end"],
                input_hash=input_hash,
                prompt_version=AI_PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                provider=None,
                model=None,
                started_at=now,
            )

            db.add(run)
            db.flush()

        else:
            # Повторная попытка той же задачи использует
            # существующий AIAnalysisRun.
            run.status = "running"
            run.input_hash = input_hash
            run.prompt_version = AI_PROMPT_VERSION
            run.schema_version = SCHEMA_VERSION
            run.provider = None
            run.model = None
            run.error_code = None
            run.error_message = None
            run.started_at = now
            run.completed_at = None

        run_id = run.id

        db.commit()

        return run_id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def _is_future_school_date(
    db,
    target_date,
    school_timezone: str,
) -> bool:
    """
    Проверяет, что дата ещё не наступила
    в часовом поясе школы.

    Использует clock_timestamp(), а не now():
    now() фиксируется на начало транзакции и
    не подходит для защиты от перехода через полночь.
    """

    return bool(
        db.scalar(
            text(
                """
                SELECT
                    :target_date >
                    (
                        clock_timestamp()
                        AT TIME ZONE :school_timezone
                    )::date
                """
            ),
            {
                "target_date": target_date,
                "school_timezone": school_timezone,
            },
        )
    )


def _persist_success(
    *,
    job_id: int,
    worker_id: str,
    run_id: int,
    aggregated_by_class: dict[int, object],
    provider_name: str | None,
    model_name: str | None,
) -> bool:
    """
    Сохраняет результаты всех классов и завершает job
    в одной транзакции.
    """

    db = SessionLocal()

    try:
        run = db.scalar(
            select(AIAnalysisRun).where(
                AIAnalysisRun.id == run_id,
                AIAnalysisRun.job_id == job_id,
            )
        )

        if run is None:
            raise RuntimeError("AIAnalysisRun не найден.")

        # Для защиты прогнозов используем часовой пояс школы,
        # а не часовой пояс сервера.
        school_timezone = db.scalar(
            select(School.timezone).where(
                School.id == run.school_id,
            )
        )

        if not school_timezone or not school_timezone.strip():
            raise ValueError(
                f"Для школы {run.school_id} не задан часовой пояс."
            )

        try:
            ZoneInfo(school_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"Некорректный часовой пояс школы "
                f"{run.school_id}: {school_timezone!r}."
            ) from None

        run.provider = provider_name
        run.model = model_name

        # Удаляем предыдущие результаты этой попытки.
        # Это делает повторное сохранение идемпотентным.
        db.query(AIDailyLoad).filter(
            AIDailyLoad.analysis_run_id == run_id
        ).delete(synchronize_session=False)

        db.query(AIRecommendation).filter(
            AIRecommendation.analysis_run_id == run_id
        ).delete(synchronize_session=False)

        # Удаляем устаревшие будущие прогнозы этого запуска.
        # Наступившие и прошедшие даты сохраняем неизменными.
        db.execute(
            text(
                """
                DELETE FROM ai_daily_forecasts
                WHERE
                    analysis_run_id = :run_id
                    AND date >
                    (
                        clock_timestamp()
                        AT TIME ZONE :school_timezone
                    )::date
                """
            ),
            {
                "run_id": run_id,
                "school_timezone": school_timezone,
            },
        )

        for class_id, result in aggregated_by_class.items():

            for item in result.daily_loads:
                # Не сохраняем исторические и сегодняшние результаты.
                # Проверка выполняется непосредственно перед INSERT
                # по текущему времени PostgreSQL.
                if not _is_future_school_date(
                    db,
                    item.date,
                    school_timezone,
                ):
                    continue

                db.execute(
                    text(
                        """
                        INSERT INTO ai_daily_loads (
                            analysis_run_id,
                            class_id,
                            date,
                            level,
                            source,
                            reduce_load,
                            suitable_for_moving
                        )
                        SELECT
                            :run_id,
                            :class_id,
                            :target_date,
                            :level,
                            :source,
                            :reduce_load,
                            :suitable_for_moving
                        WHERE
                            :target_date >
                            (
                                clock_timestamp()
                                AT TIME ZONE :school_timezone
                            )::date
                        """
                    ),
                    {
                        "run_id": run_id,
                        "class_id": class_id,
                        "target_date": item.date,
                        "level": item.level,
                        "source": item.source,
                        "reduce_load": item.reduce_load,
                        "suitable_for_moving": item.suitable_for_moving,
                        "school_timezone": school_timezone,
                    },
                )

                # Актуальный прогноз записываем отдельно.
                #
                # INSERT ... SELECT защищает от добавления строки,
                # если дата уже наступила к моменту выполнения SQL.
                #
                # Условие ON CONFLICT защищает существующую запись:
                # сегодняшнюю или прошедшую дату нельзя обновить.
                db.execute(
                    text(
                        """
                        INSERT INTO ai_daily_forecasts (
                            class_id,
                            date,
                            level,
                            source,
                            analysis_run_id,
                            created_at,
                            updated_at
                        )
                        SELECT
                            :class_id,
                            :forecast_date,
                            :level,
                            :source,
                            :run_id,
                            now(),
                            now()
                        WHERE
                            :forecast_date >
                            (clock_timestamp() AT TIME ZONE :school_timezone)::date
                        ON CONFLICT (class_id, date)
                        DO UPDATE SET
                            level = EXCLUDED.level,
                            source = EXCLUDED.source,
                            analysis_run_id = EXCLUDED.analysis_run_id,
                            updated_at = now()
                        WHERE
                            ai_daily_forecasts.date >
                            (clock_timestamp() AT TIME ZONE :school_timezone)::date
                            AND (
                                ai_daily_forecasts.analysis_run_id IS NULL
                                OR ai_daily_forecasts.analysis_run_id = :run_id
                                OR EXISTS (
                                    SELECT 1
                                    FROM ai_analysis_runs AS existing_run
                                    JOIN ai_analysis_jobs AS existing_job
                                        ON existing_job.id = existing_run.job_id
                                    JOIN ai_analysis_jobs AS incoming_job
                                        ON incoming_job.id = :job_id
                                    WHERE
                                        existing_run.id =
                                            ai_daily_forecasts.analysis_run_id
                                        AND (
                                            incoming_job.analysis_date >
                                                existing_job.analysis_date
                                            OR (
                                                incoming_job.analysis_date =
                                                    existing_job.analysis_date
                                                AND (
                                                    incoming_job.created_at >
                                                        existing_job.created_at
                                                    OR (
                                                        incoming_job.created_at =
                                                            existing_job.created_at
                                                        AND incoming_job.id >
                                                            existing_job.id
                                                    )
                                                )
                                            )
                                        )
                                )
                            )
                        """
                    ),
                    {
                        "class_id": class_id,
                        "forecast_date": item.date,
                        "level": item.level,
                        "source": item.source,
                        "run_id": run_id,
                        "job_id": job_id,
                        "school_timezone": school_timezone,
                    },
                )

            for item in result.recommendations:
                # Рекомендации за наступившую дату также запрещено
                # сохранять: API использует их для выдачи результатов.
                if not _is_future_school_date(
                    db,
                    item.date,
                    school_timezone,
                ):
                    continue

                db.execute(
                    text(
                        """
                        INSERT INTO ai_recommendations (
                            analysis_run_id,
                            class_id,
                            teacher_id,
                            schedule_id,
                            date,
                            kind,
                            priority,
                            title,
                            recommendation_text,
                            rationale
                        )
                        SELECT
                            :run_id,
                            :class_id,
                            :teacher_id,
                            :schedule_id,
                            :target_date,
                            :kind,
                            :priority,
                            :title,
                            :recommendation_text,
                            :rationale
                        WHERE
                            :target_date >
                            (
                                clock_timestamp()
                                AT TIME ZONE :school_timezone
                            )::date
                        """
                    ),
                    {
                        "run_id": run_id,
                        "class_id": class_id,
                        "teacher_id": item.teacher_id,
                        "schedule_id": item.schedule_id,
                        "target_date": item.date,
                        "kind": item.kind,
                        "priority": item.priority,
                        "title": item.title,
                        "recommendation_text": item.recommendation_text,
                        "rationale": item.rationale,
                        "school_timezone": school_timezone,
                    },
                )

        run.status = "succeeded"
        run.error_code = None
        run.error_message = None
        run.completed_at = datetime.now(timezone.utc)

        # Если lease истёк или задача уже принадлежит
        # другому worker, откатываем всю транзакцию.
        completed = complete_ai_job(
            db,
            job_id=job_id,
            worker_id=worker_id,
        )

        if not completed:
            db.rollback()
            return False

        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def _record_failure(
    *,
    job_id: int,
    worker_id: str,
    error: Exception,
    run_id: int | None,
) -> bool:
    """Фиксирует retry или окончательную ошибку задачи."""

    db = SessionLocal()

    try:
        retryable = not isinstance(
            error,
            (
                AINonRetryableError,
                ValueError,
                TypeError,
            ),
        )

        accepted = retry_ai_job(
            db,
            job_id=job_id,
            worker_id=worker_id,
            error=f"{type(error).__name__}: {error}",
            retry_delay_seconds=RETRY_DELAY_SECONDS,
            retryable=retryable,
        )

        if not accepted:
            db.rollback()
            return False

        job = db.get(AIAnalysisJob, job_id)

        if run_id is not None:
            run = db.scalar(
                select(AIAnalysisRun).where(
                    AIAnalysisRun.id == run_id,
                    AIAnalysisRun.job_id == job_id,
                )
            )

            if run is not None:
                run.status = (
                    "queued"
                    if job.status == "queued"
                    else "failed"
                )

                run.error_code = type(error).__name__[:50]
                run.error_message = str(error)[:5000]

                run.completed_at = (
                    datetime.now(timezone.utc)
                    if job.status == "failed"
                    else None
                )

        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def process_next_ai_job(
    worker_id: str | None = None,
) -> bool:
    """
    Захватывает и выполняет одну задачу.

    Возвращает:
    - True, если задача была захвачена;
    - False, если доступных задач нет.
    """

    if get_ai_config_if_configured() is None:
        return False

    worker_id = worker_id or _worker_id()

    # Захват и commit выполняются до любых сетевых вызовов.
    db = SessionLocal()

    try:
        job = claim_next_ai_job(
            db,
            worker_id=worker_id,
            lease_seconds=LEASE_SECONDS,
        )

        if job is None:
            db.commit()
            return False

        payload = _job_payload(job)

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    run_id = None
    provider_usages = []

    try:
        # Собираем контексты в отдельной короткой транзакции.
        db = SessionLocal()

        try:
            class_ids = _get_class_ids(db, payload)

            school_timezone = _get_school_timezone(
                db,
                payload["school_id"],
            )

            school_local_today = _get_school_local_today(
                school_timezone,
            )

            contexts_by_class = {}
            scheduled_by_class = {}

            for class_id in class_ids:
                # Не даём lease истечь во время сбора контекста.
                _renew_lease(payload["id"], worker_id)

                scheduled, contexts = _collect_class_contexts(
                    db,
                    payload,
                    class_id,
                    school_local_today,
                    progress_callback=lambda: _renew_lease(
                        payload["id"],
                        worker_id,
                    ),
                )

                scheduled_by_class[class_id] = scheduled
                contexts_by_class[class_id] = contexts

        finally:
            db.close()

        input_hash = _build_input_hash(
            contexts_by_class,
            scheduled_by_class,
            school_local_today,
        )

        _renew_lease(payload["id"], worker_id)

        run_id = _start_or_resume_run(
            payload,
            worker_id,
            input_hash,
        )

        aggregated_by_class = {}

        for class_id in class_ids:
            day_results = []
            analyzed_dates = set()

            for context in contexts_by_class[class_id]:
                # Продлеваем lease перед каждым дневным анализом.
                # Это защищает длинную серию коротких AI-запросов.
                _renew_lease(payload["id"], worker_id)

                # Дата могла наступить, пока worker анализировал
                # предыдущий класс или предыдущий день.
                current_school_date = _get_school_local_today(
                    school_timezone,
                )

                if context.target_date <= current_school_date:
                    logger.info(
                        "Пропускаем AI-анализ наступившей даты: "
                        "job_id=%s, class_id=%s, target_date=%s, "
                        "school_today=%s",
                        payload["id"],
                        class_id,
                        context.target_date,
                        current_school_date,
                    )
                    continue

                analysis_result = await _analyze_with_lease(
                    job_id=payload["id"],
                    worker_id=worker_id,
                    context=context,
                )

                day_results.append(analysis_result.output)
                analyzed_dates.add(context.target_date)
                provider_usages.extend(
                    analysis_result.provider_usages
                )

            # В агрегатор передаём только те даты с уроками,
            # для которых действительно получили AI-результат.
            # Иначе агрегатор справедливо посчитает пропущенную
            # дату отсутствующим AI-результатом и выбросит ошибку.
            eligible_scheduled_dates = [
                target_date
                for target_date in scheduled_by_class[class_id]
                if target_date in analyzed_dates
            ]

            _renew_lease(payload["id"], worker_id)

            aggregated_by_class[class_id] = (
                aggregate_period_results(
                    period_start=payload["period_start"],
                    period_end=payload["period_end"],
                    scheduled_dates=eligible_scheduled_dates,
                    day_results=day_results,
                )
            )

        provider_name, model_name = _summarize_provider_usage(provider_usages)

        _renew_lease(payload["id"], worker_id)

        persisted = _persist_success(
            job_id=payload["id"],
            worker_id=worker_id,
            run_id=run_id,
            aggregated_by_class=aggregated_by_class,
            provider_name=provider_name,
            model_name=model_name,
        )

        if not persisted:
            raise LeaseLostError(
                "Worker потерял lease перед сохранением "
                f"задачи {payload['id']}."
            )

        logger.info(
            "AI job %s завершена. Run ID: %s, классов: %s",
            payload["id"],
            run_id,
            len(class_ids),
        )

        return True

    except LeaseLostError:
        # Новый владелец lease отвечает за продолжение задачи.
        logger.warning(
            "Worker %s потерял lease задачи %s.",
            worker_id,
            payload["id"],
        )

        return True

    except Exception as error:
        logger.exception(
            "Ошибка выполнения AI job %s",
            payload["id"],
        )

        try:
            _record_failure(
                job_id=payload["id"],
                worker_id=worker_id,
                error=error,
                run_id=run_id,
            )

        except Exception:
            logger.exception(
                "Не удалось зафиксировать ошибку AI job %s",
                payload["id"],
            )

        return True


async def run_worker_forever() -> None:
    """Основной цикл отдельного процесса AI-worker."""

    worker_id = _worker_id()

    logger.info(
        "AI worker запущен: %s",
        worker_id,
    )

    if get_ai_config_if_configured() is None:
        logger.warning(
            "AI worker запущен в режиме ожидания: "
            "AI-провайдер не настроен. "
            "Для включения AI настройте переменные окружения "
            "и перезапустите worker."
        )

        while True:
            await asyncio.sleep(60)

    while True:
        try:
            processed = await process_next_ai_job(worker_id)

            if not processed:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception("Ошибка цикла AI worker")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format=(
            "%(asctime)s [%(levelname)s] "
            "%(name)s: %(message)s"
        ),
    )

    asyncio.run(run_worker_forever())
