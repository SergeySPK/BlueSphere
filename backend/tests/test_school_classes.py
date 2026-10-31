from types import SimpleNamespace
import pytest
from fastapi import HTTPException

import main


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

    def fake_build_schedule(school_class_arg, date, db):
        schedule_calls.append((school_class_arg, date))
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
    assert schedule_calls == [(school_class, "2026-10-30")]


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
        heatmap_calls.append(
            (school_class, month, current_user_id)
        )
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

    def fake_require_access(
        school_id, class_code, user, db, allowed_roles=None
    ):
        access_calls.append((school_id, class_code, allowed_roles))
        return school_class

    def fake_build_summary(school_class_arg, db):
        summary_calls.append(school_class_arg)
        return "сводка"

    monkeypatch.setattr(
        main, "require_school_class_access", fake_require_access
    )
    monkeypatch.setattr(
        main, "build_class_summary", fake_build_summary
    )

    result = main.get_school_summary(
        school_id=1,
        class_code="1a",
        current_user=user,
        db=SimpleNamespace(),
    )

    assert result == "сводка"
    assert access_calls == [(1, "1a", {"teacher", "admin"})]
    assert summary_calls == [school_class]


def test_school_summary_denies_access_without_building_summary(monkeypatch):
    user = SimpleNamespace(id=1)

    def deny_access(
        school_id, class_code, user, db, allowed_roles=None
    ):
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому разделу",
        )

    def unexpected_build_summary(*args, **kwargs):
        pytest.fail("Сводка не должна формироваться без доступа")

    monkeypatch.setattr(
        main, "require_school_class_access", deny_access
    )
    monkeypatch.setattr(
        main, "build_class_summary", unexpected_build_summary
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_summary(
            school_id=1,
            class_code="1a",
            current_user=user,
            db=SimpleNamespace(),
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вашей роли нет доступа к этому разделу"


def test_school_summary_passes_only_teacher_and_admin_roles(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(id=34, code="1a", school_id=1)
    captured_roles = []

    def fake_require_access(
        school_id, class_code, user, db, allowed_roles=None
    ):
        captured_roles.append(allowed_roles)
        return school_class

    monkeypatch.setattr(
        main, "require_school_class_access", fake_require_access
    )
    monkeypatch.setattr(
        main, "build_class_summary", lambda school_class, db: "сводка"
    )

    main.get_school_summary(
        school_id=1,
        class_code="1a",
        current_user=user,
        db=SimpleNamespace(),
    )

    assert captured_roles == [{"teacher", "admin"}]


def test_school_recommendations_uses_school_and_class_access(monkeypatch):
    user = SimpleNamespace(id=1)
    school_class = SimpleNamespace(id=34, code="1a", school_id=1)

    access_calls = []
    recommendations_calls = []

    def fake_require_access(
        school_id, class_code, user, db, allowed_roles=None
    ):
        access_calls.append((school_id, class_code, allowed_roles))
        return school_class

    def fake_build_recommendations(school_class, month, db):
        recommendations_calls.append((school_class, month))
        return "рекомендации"

    monkeypatch.setattr(
        main, "require_school_class_access", fake_require_access
    )
    monkeypatch.setattr(
        main, "build_class_recommendations", fake_build_recommendations
    )

    result = main.get_school_recommendations(
        school_id=1,
        class_code="1a",
        month="10",
        current_user=user,
        db=SimpleNamespace(),
    )

    assert result == "рекомендации"
    assert access_calls == [(1, "1a", {"teacher", "admin"})]
    assert recommendations_calls == [(school_class, "10")]


def test_school_recommendations_denies_access_without_building(monkeypatch):
    user = SimpleNamespace(id=1)

    def deny_access(
        school_id, class_code, user, db, allowed_roles=None
    ):
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому разделу",
        )

    def unexpected_build(*args, **kwargs):
        pytest.fail("Рекомендации не должны формироваться без доступа")

    monkeypatch.setattr(
        main, "require_school_class_access", deny_access
    )
    monkeypatch.setattr(
        main, "build_class_recommendations", unexpected_build
    )

    with pytest.raises(HTTPException) as error:
        main.get_school_recommendations(
            school_id=1,
            class_code="1a",
            month="10",
            current_user=user,
            db=SimpleNamespace(),
        )

    assert error.value.status_code == 403
    assert error.value.detail == "У вашей роли нет доступа к этому разделу"