from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

import main


def create_fake_db(class_code, class_id):
    school_class = SimpleNamespace(
        id=class_id,
        code=class_code,
    )

    return SimpleNamespace(scalar=lambda query: school_class)


def test_user_cannot_access_another_class(monkeypatch):
    user = SimpleNamespace(id=1)
    fake_db = create_fake_db("2a", 35)

    monkeypatch.setattr(
        main,
        "get_user_school_ids",
        lambda user, db: {1},
    )

    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"student"}, {34}),
    )

    with pytest.raises(HTTPException) as error:
        main.require_class_access("2a", user, fake_db)

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этому классу"


def test_user_can_access_own_class(monkeypatch):
    user = SimpleNamespace(id=1)
    fake_db = create_fake_db("1a", 34)

    monkeypatch.setattr(
        main,
        "get_user_school_ids",
        lambda user, db: {1},
    )

    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"student"}, {34}),
    )

    school_class = main.require_class_access("1a", user, fake_db)

    assert school_class.id == 34
    assert school_class.code == "1a"


def test_user_can_access_class_in_selected_school(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(
        id=34,
        code="1a",
        school_id=1,
    )

    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: SimpleNamespace(id=school_id),
    )
    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"teacher"}, {34}),
    )

    fake_db = SimpleNamespace(
        scalar=lambda query: school_class,
    )

    result = main.require_school_class_access(
        school_id=1,
        class_code="1a",
        user=user,
        db=fake_db,
    )

    assert result.id == 34
    assert result.school_id == 1


def test_student_cannot_access_teacher_admin_section(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(
        id=34,
        code="1a",
        school_id=1,
    )

    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: SimpleNamespace(id=school_id),
    )
    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"student"}, {34}),
    )

    fake_db = SimpleNamespace(
        scalar=lambda query: school_class,
    )

    with pytest.raises(HTTPException) as error:
        main.require_school_class_access(
            school_id=1,
            class_code="1a",
            user=user,
            db=fake_db,
            allowed_roles={"teacher", "admin"},
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вашей роли нет доступа к этому разделу"


def test_teacher_cannot_access_unassigned_class_in_selected_school(
    monkeypatch,
):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(
        id=35,
        code="2a",
        school_id=1,
    )

    monkeypatch.setattr(
        main,
        "require_school_access",
        lambda school_id, user, db: SimpleNamespace(id=school_id),
    )
    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"teacher"}, {34}),
    )

    fake_db = SimpleNamespace(
        scalar=lambda query: school_class,
    )

    with pytest.raises(HTTPException) as error:
        main.require_school_class_access(
            school_id=1,
            class_code="2a",
            user=user,
            db=fake_db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этому классу"


def test_user_without_schools_cannot_access_old_class_route(monkeypatch):
    user = SimpleNamespace(id=1)
    fake_db = create_fake_db("1a", 34)

    monkeypatch.setattr(
        main,
        "get_user_school_ids",
        lambda user, db: set(),
    )

    with pytest.raises(HTTPException) as error:
        main.require_class_access("1a", user, fake_db)

    assert error.value.status_code == 403
    assert error.value.detail == "У вас нет доступа к этой школе"


def test_user_with_multiple_schools_cannot_use_old_class_route(monkeypatch):
    user = SimpleNamespace(id=1)
    fake_db = create_fake_db("1a", 34)

    monkeypatch.setattr(
        main,
        "get_user_school_ids",
        lambda user, db: {1, 2},
    )

    with pytest.raises(HTTPException) as error:
        main.require_class_access("1a", user, fake_db)

    assert error.value.status_code == 400
    assert error.value.detail == (
        "Для работы с несколькими школами используйте новый маршрут с school_id"
    )


def test_old_class_access_query_filters_by_school_and_code(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(
        id=34,
        code="1a",
        school_id=1,
    )

    monkeypatch.setattr(
        main,
        "get_user_school_ids",
        lambda user, db: {1},
    )
    monkeypatch.setattr(
        main,
        "get_user_access",
        lambda user, db: ({"student"}, {34}),
    )

    captured = {}

    def fake_scalar(query):
        captured["query"] = query
        return school_class

    fake_db = SimpleNamespace(scalar=fake_scalar)

    result = main.require_class_access("1a", user, fake_db)

    compiled_query = captured["query"].compile(
        dialect=postgresql.dialect()
    )

    assert result.id == 34
    assert "classes.school_id" in str(compiled_query)
    assert "classes.code" in str(compiled_query)
    assert 1 in compiled_query.params.values()
    assert "1a" in compiled_query.params.values()
