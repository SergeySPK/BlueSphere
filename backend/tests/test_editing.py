from datetime import datetime, timedelta, timezone
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
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )

    fake_db = SimpleNamespace(
        scalar=lambda query: editing_session,
    )

    monkeypatch.setattr(
        main,
        "get_editing_user_and_lesson",
        lambda lesson_id, user, db: (lesson, user),
    )

    with pytest.raises(HTTPException) as error:
        main.renew_editing("10", user, fake_db)

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
        lambda lesson_id, user, db: (lesson, user),
    )

    result = main.stop_editing("10", user, fake_db)

    assert result == {"success": True}
    assert deleted_sessions == []
    assert commits == []