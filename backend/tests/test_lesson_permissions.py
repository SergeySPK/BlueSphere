from types import SimpleNamespace
from sqlalchemy.dialects import postgresql

import main


def test_assigned_teacher_can_edit_lesson(monkeypatch):
    lesson = SimpleNamespace(assignment_id=10)
    user = SimpleNamespace(id=1)

    assignment = SimpleNamespace(id=10)

    def fake_scalar(query):
        return assignment

    fake_db = SimpleNamespace(scalar=fake_scalar)

    result = main.can_edit_lesson(lesson, user, fake_db)

    assert result is True


def test_unassigned_teacher_cannot_edit_lesson(monkeypatch):
    lesson = SimpleNamespace(assignment_id=10)
    user = SimpleNamespace(id=2)

    calls = 0

    def fake_scalar(query):
        nonlocal calls
        calls += 1

        # Назначение учителя не найдено.
        if calls == 1:
            return None

        # Класс и школа существуют, но администратор не найден.
        if calls == 2:
            return 34

        if calls == 3:
            return 1

        return None

    fake_db = SimpleNamespace(scalar=fake_scalar)

    result = main.can_edit_lesson(lesson, user, fake_db)

    assert result is False


def test_administrator_of_another_school_cannot_edit_lesson():
    lesson = SimpleNamespace(assignment_id=10)
    user = SimpleNamespace(id=2)

    calls = 0

    def fake_scalar(query):
        nonlocal calls
        calls += 1

        if calls == 1:
            return None  # Учитель не назначен на урок.

        if calls == 2:
            return 34

        if calls == 3:
            return 1  # Школа класса имеет ID 1.

        return None  # Пользователь не администратор этой школы.

    fake_db = SimpleNamespace(scalar=fake_scalar)

    result = main.can_edit_lesson(lesson, user, fake_db)

    assert result is False


def test_teacher_edit_query_checks_school_match():
    lesson = SimpleNamespace(assignment_id=10)
    user = SimpleNamespace(id=1)

    captured = {}

    def fake_scalar(query):
        captured["query"] = query
        return SimpleNamespace(id=10)

    fake_db = SimpleNamespace(scalar=fake_scalar)

    result = main.can_edit_lesson(lesson, user, fake_db)

    sql = str(captured["query"].compile(dialect=postgresql.dialect()))

    assert result is True
    assert "teachers.school_id = classes.school_id" in sql


def test_teacher_edit_query_checks_academic_year_match():
    lesson = SimpleNamespace(assignment_id=10)
    user = SimpleNamespace(id=1)

    captured = {}

    def fake_scalar(query):
        captured["query"] = query
        return SimpleNamespace(id=10)

    fake_db = SimpleNamespace(scalar=fake_scalar)

    result = main.can_edit_lesson(lesson, user, fake_db)

    sql = str(captured["query"].compile(dialect=postgresql.dialect()))

    assert result is True
    assert "teaching_assignments.academic_year_id = classes.academic_year_id" in sql
