from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import main


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

    result = main.stop_editing(1, "1a", "10", user, fake_db)

    assert result == {"success": True}
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
