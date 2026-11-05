import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import main
from models import (
    AcademicYear,
    Class,
    EditingSession,
    School,
    Schedule,
    Subject,
    Teacher,
    TeachingAssignment,
    User,
)


def test_user_cannot_renew_another_users_session(monkeypatch):
    user = SimpleNamespace(id=1)
    lesson = SimpleNamespace(id=10)

    editing_session = SimpleNamespace(
        schedule_id=10,
        user_id=2,
        expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )

    fake_db = SimpleNamespace(
        scalar=lambda query: editing_session,
    )

    monkeypatch.setattr(
        main,
        "get_editing_user_and_lesson",
        lambda school_id, class_code, lesson_id, user, db: (lesson, user),
    )

    with pytest.raises(HTTPException) as error:
        main.renew_editing(1, "1a", "10", user, fake_db)

    assert error.value.status_code == 409
    assert error.value.detail == "Активная сессия редактирования не найдена."


def test_user_cannot_delete_another_users_session(monkeypatch):
    user = SimpleNamespace(id=1)
    lesson = SimpleNamespace(id=10)

    editing_session = SimpleNamespace(
        schedule_id=10,
        user_id=2,
    )

    deleted_sessions = []
    commits = []

    fake_db = SimpleNamespace(
        scalar=lambda query: editing_session,
        delete=lambda session: deleted_sessions.append(session),
        commit=lambda: commits.append(True),
    )

    monkeypatch.setattr(
        main,
        "get_editing_user_and_lesson",
        lambda school_id, class_code, lesson_id, user, db: (lesson, user),
    )

    with pytest.raises(HTTPException) as error:
        main.stop_editing(1, "1a", "10", user, fake_db)

    assert error.value.status_code == 403
    assert error.value.detail == (
        "Нельзя завершить чужую сессию редактирования."
    )
    assert deleted_sessions == []
    assert commits == []


def test_editing_rejects_lesson_from_another_class(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(id=34)
    lesson = SimpleNamespace(id=10, assignment_id=20)

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        lambda **kwargs: school_class,
    )

    monkeypatch.setattr(
        main,
        "can_edit_lesson",
        lambda *args: pytest.fail("Проверка прав редактирования не должна вызываться"),
    )

    fake_db = SimpleNamespace(
        get=lambda model, lesson_id: lesson,
        scalar=lambda query: 35,
    )

    with pytest.raises(HTTPException) as error:
        main.get_editing_user_and_lesson(
            school_id=1,
            class_code="1a",
            lesson_id="10",
            user=user,
            db=fake_db,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Урок не найден в указанном классе."


def test_editing_denies_access_to_class(monkeypatch):
    user = SimpleNamespace(id=1)

    def deny_access(**kwargs):
        raise HTTPException(
            status_code=403,
            detail="Нет доступа к классу",
        )

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        deny_access,
    )

    def unexpected_get(*args):
        pytest.fail("Урок не должен запрашиваться без доступа к классу")

    fake_db = SimpleNamespace(get=unexpected_get)

    with pytest.raises(HTTPException) as error:
        main.get_editing_user_and_lesson(
            school_id=2,
            class_code="1a",
            lesson_id="10",
            user=user,
            db=fake_db,
        )

    assert error.value.status_code == 403


def test_editing_denies_user_without_lesson_permissions(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(id=34)
    lesson = SimpleNamespace(id=10, assignment_id=20)

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        lambda **kwargs: school_class,
    )

    monkeypatch.setattr(
        main,
        "can_edit_lesson",
        lambda lesson, user, db: False,
    )

    fake_db = SimpleNamespace(
        get=lambda model, lesson_id: lesson,
        scalar=lambda query: 34,
    )

    with pytest.raises(HTTPException) as error:
        main.get_editing_user_and_lesson(
            school_id=1,
            class_code="1a",
            lesson_id="10",
            user=user,
            db=fake_db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == ("У вас нет прав на редактирование этого урока.")


def test_editing_rejects_non_numeric_lesson_id(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(id=34)

    monkeypatch.setattr(
        main,
        "require_school_class_access",
        lambda **kwargs: school_class,
    )

    def unexpected_get(*args):
        pytest.fail("Запрос к БД не должен выполняться с нечисловым ID")

    fake_db = SimpleNamespace(get=unexpected_get)

    with pytest.raises(HTTPException) as error:
        main.get_editing_user_and_lesson(
            school_id=1,
            class_code="1a",
            lesson_id="abc",
            user=user,
            db=fake_db,
        )

    assert error.value.status_code == 400
    assert error.value.detail == "ID урока должен быть числом."


def test_user_cannot_start_editing_another_users_active_session(monkeypatch):
    user = SimpleNamespace(id=1)
    lesson = SimpleNamespace(id=10)

    editing_session = SimpleNamespace(
        schedule_id=10,
        user_id=2,
        expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )

    monkeypatch.setattr(
        main,
        "get_editing_user_and_lesson",
        lambda school_id, class_code, lesson_id, user, db: (lesson, user),
    )

    commits = []

    fake_db = SimpleNamespace(
        scalar=lambda query: editing_session,
        commit=lambda: commits.append(True),
    )

    with pytest.raises(HTTPException) as error:
        main.start_editing(1, "1a", "10", user, fake_db)

    assert error.value.status_code == 409
    assert error.value.detail == ("Этот урок уже редактирует другой пользователь.")
    assert commits == []


def test_user_cannot_update_lesson_without_active_session(monkeypatch):
    user = SimpleNamespace(id=1)
    lesson = SimpleNamespace(
        id=10,
        lesson_type="обычный",
        updated_by_user_id=None,
    )

    monkeypatch.setattr(
        main,
        "get_editing_user_and_lesson",
        lambda school_id, class_code, lesson_id, user, db: (lesson, user),
    )

    commits = []

    fake_db = SimpleNamespace(
        scalar=lambda query: None,
        commit=lambda: commits.append(True),
    )

    request = SimpleNamespace(lesson_type="контрольная")

    with pytest.raises(HTTPException) as error:
        main.update_lesson(
            1,
            "1a",
            "10",
            request,
            user,
            fake_db,
        )

    assert error.value.status_code == 409
    assert error.value.detail == ("Нет активной сессии редактирования этого урока.")
    assert lesson.lesson_type == "обычный"
    assert lesson.updated_by_user_id is None
    assert commits == []


def test_user_cannot_renew_expired_session(monkeypatch):
    user = SimpleNamespace(id=1)
    lesson = SimpleNamespace(id=10)

    editing_session = SimpleNamespace(
        schedule_id=10,
        user_id=1,
        expires_at=datetime.now(UTC) - timedelta(seconds=60),
    )

    monkeypatch.setattr(
        main,
        "get_editing_user_and_lesson",
        lambda school_id, class_code, lesson_id, user, db: (lesson, user),
    )

    commits = []

    fake_db = SimpleNamespace(
        scalar=lambda query: editing_session,
        commit=lambda: commits.append(True),
    )

    with pytest.raises(HTTPException) as error:
        main.renew_editing(1, "1a", "10", user, fake_db)

    assert error.value.status_code == 409
    assert error.value.detail == "Активная сессия редактирования не найдена."
    assert commits == []


def test_editing_routes_use_school_class_paths():
    expected_routes = {
        ("PUT", "/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}"),
        (
            "POST",
            "/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}/editing",
        ),
        (
            "PUT",
            "/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}/editing",
        ),
        (
            "DELETE",
            "/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}/editing",
        ),
    }

    actual_routes = {
        (method, route.path)
        for route in main.app.routes
        if hasattr(route, "methods")
        for method in route.methods
        if method in {"PUT", "POST", "DELETE"} and "/schedule/" in route.path
    }

    assert actual_routes == expected_routes


def test_concurrent_editing_session_creation_allows_only_one_user(monkeypatch):
    """
    Два пользователя одновременно захватывают один урок.

    Проверяем, что PostgreSQL обеспечивает уникальность EditingSession:
    один запрос завершается успешно, второй получает HTTP 409.
    """
    database_url = os.getenv("TEST_DATABASE_URL")

    assert database_url, "Не задан TEST_DATABASE_URL"

    database_url_parsed = make_url(database_url)

    assert database_url_parsed.database == "bluesphere_restore_test"
    assert database_url_parsed.get_backend_name() == "postgresql"
    assert database_url_parsed.query.get("host") == "/var/run/postgresql"

    engine = create_engine(
        database_url,
        pool_size=2,
        max_overflow=0,
    )

    school_id = None
    schedule_id = None
    user_ids = []

    try:
        # ---------------------------------------------------------
        # 1. Создаём данные и фиксируем их отдельной транзакцией.
        # ---------------------------------------------------------

        suffix = uuid4().hex[:10]

        with Session(engine) as setup_db:
            school = School(
                region="Тестовый регион",
                city="Тестовый город",
                address="Тестовый адрес",
                short_name=f"Школа гонки {suffix}",
                full_name=f"Школа для теста конкурентности {suffix}",
                timezone="UTC",
            )
            setup_db.add(school)
            setup_db.flush()

            academic_year = AcademicYear(
                school_id=school.id,
                name=f"Тестовый год {suffix}",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 8, 31),
                is_active=True,
            )
            setup_db.add(academic_year)
            setup_db.flush()

            school_class = Class(
                school_id=school.id,
                academic_year_id=academic_year.id,
                code="9a",
                name="9А",
            )
            setup_db.add(school_class)
            setup_db.flush()

            user_1 = User(
                sferum_id=f"991{suffix}",
                full_name="Учитель для конкурентного теста 1",
            )
            user_2 = User(
                sferum_id=f"992{suffix}",
                full_name="Учитель для конкурентного теста 2",
            )
            setup_db.add_all([user_1, user_2])
            setup_db.flush()

            teacher_1 = Teacher(
                user_id=user_1.id,
                school_id=school.id,
            )
            teacher_2 = Teacher(
                user_id=user_2.id,
                school_id=school.id,
            )
            setup_db.add_all([teacher_1, teacher_2])
            setup_db.flush()

            subject = Subject(
                school_id=school.id,
                name=f"Тестовый предмет {suffix}",
            )
            setup_db.add(subject)
            setup_db.flush()

            assignment = TeachingAssignment(
                school_id=school.id,
                teacher_id=teacher_1.id,
                class_id=school_class.id,
                subject_id=subject.id,
                academic_year_id=academic_year.id,
                subgroup=0,
            )
            setup_db.add(assignment)
            setup_db.flush()

            schedule = Schedule(
                assignment_id=assignment.id,
                date=date(2026, 11, 5),
                lesson_number=1,
                room="101",
                lesson_type="Урок",
            )
            setup_db.add(schedule)
            setup_db.flush()

            school_id = school.id
            schedule_id = schedule.id
            user_ids = [user_1.id, user_2.id]

            setup_db.commit()

        # ---------------------------------------------------------
        # 2. Изолируем проверку прав.
        #
        # Права уже покрыты отдельными тестами. Здесь проверяем
        # исключительно конкурентную работу с EditingSession.
        # ---------------------------------------------------------

        users = [
            SimpleNamespace(id=user_ids[0]),
            SimpleNamespace(id=user_ids[1]),
        ]
        lesson = SimpleNamespace(id=schedule_id)

        monkeypatch.setattr(
            main,
            "get_editing_user_and_lesson",
            lambda school_id, class_code, lesson_id, user, db: (
                lesson,
                user,
            ),
        )

        # ---------------------------------------------------------
        # 3. Синхронизируем два запроса после SELECT ... FOR UPDATE.
        #
        # Оба запроса должны успеть увидеть отсутствие EditingSession
        # до того, как любой из них начнёт INSERT.
        # ---------------------------------------------------------

        barrier = Barrier(2)

        def synchronize_session_lookup(
            connection,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ):
            normalized_statement = statement.lower()

            if (
                "from editing_sessions" in normalized_statement
                and "for update" in normalized_statement
            ):
                barrier.wait(timeout=10)

        event.listen(
            engine,
            "after_cursor_execute",
            synchronize_session_lookup,
        )

        # ---------------------------------------------------------
        # 4. Каждый поток использует собственную SQLAlchemy Session.
        # ---------------------------------------------------------

        def try_start_editing(user):
            with Session(engine) as db:
                try:
                    main.start_editing(
                        school_id=school_id,
                        class_code="9a",
                        lesson_id=str(schedule_id),
                        current_user=user,
                        db=db,
                    )
                    return {
                        "user_id": user.id,
                        "status": "success",
                    }

                except HTTPException as error:
                    return {
                        "user_id": user.id,
                        "status": "http_error",
                        "status_code": error.status_code,
                    }

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(try_start_editing, user)
                    for user in users
                ]

                results = [future.result(timeout=20) for future in futures]

        finally:
            event.remove(
                engine,
                "after_cursor_execute",
                synchronize_session_lookup,
            )

        # ---------------------------------------------------------
        # 5. Проверяем результаты конкурентных запросов.
        # ---------------------------------------------------------

        successful_results = [
            result
            for result in results
            if result["status"] == "success"
        ]

        conflict_results = [
            result
            for result in results
            if result["status"] == "http_error"
            and result["status_code"] == 409
        ]

        assert len(successful_results) == 1, results
        assert len(conflict_results) == 1, results

        winning_user_id = successful_results[0]["user_id"]

        # ---------------------------------------------------------
        # 6. Проверяем фактическое состояние PostgreSQL.
        # ---------------------------------------------------------

        with Session(engine) as verification_db:
            sessions = verification_db.scalars(
                select(EditingSession).where(
                    EditingSession.schedule_id == schedule_id
                )
            ).all()

            assert len(sessions) == 1
            assert sessions[0].user_id == winning_user_id
            assert sessions[0].expires_at > datetime.now(UTC)

    finally:
        # ---------------------------------------------------------
        # 7. Удаляем временные данные.
        # ---------------------------------------------------------

        if schedule_id is not None:
            with Session(engine) as cleanup_db:
                cleanup_db.execute(
                    delete(EditingSession).where(
                        EditingSession.schedule_id == schedule_id
                    )
                )
                cleanup_db.commit()

        if school_id is not None:
            with Session(engine) as cleanup_db:
                cleanup_db.execute(
                    delete(School).where(School.id == school_id)
                )
                cleanup_db.commit()

        if user_ids:
            with Session(engine) as cleanup_db:
                cleanup_db.execute(
                    delete(User).where(User.id.in_(user_ids))
                )
                cleanup_db.commit()

        engine.dispose()
