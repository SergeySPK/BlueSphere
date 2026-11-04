import pytest

from sqlalchemy import select
from sqlalchemy.orm import Session as SQLAlchemySession

from models import (
    TeachingAssignment,
    TeacherClassAccess,
    Schedule,
    School,
    Teacher,
    User,
)

import scripts.create_teacher as create_teacher_script
from scripts.create_teacher import create_demo_teacher, grant_class_access, transfer_selected_classes


def test_transfer_selected_classes(teacher_transfer_data, db_session):
    """Переносит только выбранный предмет и сохраняет старые права."""

    data = teacher_transfer_data

    moved_count = transfer_selected_classes(
        db=db_session,
        school_id=data["school"].id,
        academic_year_id=data["active_year"].id,
        teacher_id=data["new_teacher"].id,
        subject_id=data["assignments"][0].subject_id,
        selected_class_ids=[
            data["class_5a"].id,
            data["class_5b"].id,
        ],
    )

    assert moved_count == 2

    assignments = db_session.scalars(
        select(TeachingAssignment)
    ).all()

    assignments_by_id = {
        assignment.id: assignment
        for assignment in assignments
    }

    # Математика в 5А и 5Б перешла новому учителю.
    for index in (0, 2):
        assignment = data["assignments"][index]
        assert assignments_by_id[assignment.id].teacher_id == data["new_teacher"].id

    # Русский язык в 5А не изменился.
    assert (
        assignments_by_id[data["assignments"][1].id].teacher_id
        == data["old_teacher"].id
    )

    # Назначение 6А не изменилось.
    assert (
        assignments_by_id[data["assignments"][3].id].teacher_id
        == data["other_teacher"].id
    )

    # Назначение прошлого учебного года не изменилось.
    assert (
        assignments_by_id[data["assignments"][4].id].teacher_id
        == data["old_teacher"].id
    )

    # Новый учитель получил доступ к выбранным классам.
    accesses = db_session.scalars(
        select(TeacherClassAccess)
    ).all()

    access_pairs = {
        (access.teacher_id, access.class_id)
        for access in accesses
    }

    assert (
        data["new_teacher"].id,
        data["class_5a"].id,
    ) in access_pairs

    assert (
        data["new_teacher"].id,
        data["class_5b"].id,
    ) in access_pairs

    # Старые права учителей сохраняются.
    assert (
        data["old_teacher"].id,
        data["class_5a"].id,
    ) in access_pairs

    assert (
        data["old_teacher"].id,
        data["class_5b"].id,
    ) in access_pairs

    assert (
        data["other_teacher"].id,
        data["class_5a"].id,
    ) in access_pairs

    # Доступ старого учителя к 6А сохраняется.
    assert (
        data["old_teacher"].id,
        data["class_6a"].id,
    ) in access_pairs

    # Права прошлого учебного года сохраняются.
    old_year_access = db_session.scalar(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == data["old_teacher"].id,
            TeacherClassAccess.class_id == data["old_class_5a"].id,
        )
    )

    assert old_year_access is not None

    # Расписание и ID назначения сохраняются.
    schedule = db_session.get(Schedule, data["schedule"].id)

    assert schedule is not None
    assert schedule.assignment_id == data["assignments"][0].id

    scheduled_assignment = db_session.get(
        TeachingAssignment,
        schedule.assignment_id,
    )

    assert scheduled_assignment.teacher_id == data["new_teacher"].id


def test_transfer_rejects_class_from_another_year(
    teacher_transfer_data,
    db_session,
):
    """Проверяет отказ при передаче класса другого учебного года."""

    data = teacher_transfer_data

    with pytest.raises(ValueError):
        transfer_selected_classes(
            db=db_session,
            school_id=data["school"].id,
            academic_year_id=data["active_year"].id,
            teacher_id=data["new_teacher"].id,
            subject_id=data["assignments"][0].subject_id,
            selected_class_ids=[
                data["old_class_5a"].id,
            ],
        )

    # Права доступа не должны измениться.
    old_access = db_session.scalar(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == data["old_teacher"].id,
            TeacherClassAccess.class_id == data["class_5a"].id,
        )
    )

    assert old_access is not None


def test_transfer_rolls_back_with_outer_transaction(
    teacher_transfer_data,
    db_session,
):
    """Проверяет откат переноса при отмене внешней транзакции."""

    data = teacher_transfer_data

    with pytest.raises(RuntimeError):
        with db_session.begin_nested():
            transfer_selected_classes(
                db=db_session,
                school_id=data["school"].id,
                academic_year_id=data["active_year"].id,
                teacher_id=data["new_teacher"].id,
                subject_id=data["assignments"][0].subject_id,
                selected_class_ids=[
                    data["class_5a"].id,
                    data["class_5b"].id,
                ],
            )

            # Имитируем ошибку на следующем этапе операции.
            raise RuntimeError("Искусственная ошибка для проверки отката")

    # После отката назначения должны остаться у старого учителя.
    for index in (0, 2):
        assignment = data["assignments"][index]

        current_assignment = db_session.get(
            TeachingAssignment,
            assignment.id,
        )

        assert current_assignment.teacher_id == data["old_teacher"].id

    # Новые права доступа должны исчезнуть.
    new_accesses = db_session.scalars(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == data["new_teacher"].id,
        )
    ).all()

    assert new_accesses == []

    # Старые права должны восстановиться.
    old_access = db_session.scalar(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == data["old_teacher"].id,
            TeacherClassAccess.class_id == data["class_5a"].id,
        )
    )

    assert old_access is not None


def test_transfer_rejects_teacher_from_another_school(
    teacher_transfer_data,
    db_session,
):
    """Нельзя передать классы учителю другой школы."""

    data = teacher_transfer_data

    another_school = School(
        region="Другой регион",
        city="Другой город",
        address="Другой адрес",
        short_name="Другая школа",
        full_name="Другая тестовая школа",
        timezone="Asia/Yekaterinburg",
    )
    db_session.add(another_school)
    db_session.flush()

    another_user = User(
        sferum_id="990000004",
        full_name="Учитель другой школы",
    )
    db_session.add(another_user)
    db_session.flush()

    another_teacher = Teacher(
        user_id=another_user.id,
        school_id=another_school.id,
    )
    db_session.add(another_teacher)
    db_session.flush()

    with pytest.raises(ValueError, match="не принадлежит"):
        transfer_selected_classes(
            db=db_session,
            school_id=data["school"].id,
            academic_year_id=data["active_year"].id,
            teacher_id=another_teacher.id,
            subject_id=data["assignments"][0].subject_id,
            selected_class_ids=[data["class_5a"].id],
        )


def test_transfer_rejects_nonexistent_teacher(
    teacher_transfer_data,
    db_session,
):
    """Нельзя передать классы несуществующему учителю."""

    data = teacher_transfer_data

    with pytest.raises(ValueError, match="Учитель не найден"):
        transfer_selected_classes(
            db=db_session,
            school_id=data["school"].id,
            academic_year_id=data["active_year"].id,
            teacher_id=999999999,
            subject_id=data["assignments"][0].subject_id,
            selected_class_ids=[data["class_5a"].id],
        )


def test_transfer_rejects_duplicate_classes(
    teacher_transfer_data,
    db_session,
):
    """Нельзя передать один класс несколько раз."""

    data = teacher_transfer_data

    with pytest.raises(ValueError, match="повторения"):
        transfer_selected_classes(
            db=db_session,
            school_id=data["school"].id,
            academic_year_id=data["active_year"].id,
            teacher_id=data["new_teacher"].id,
            subject_id=data["assignments"][0].subject_id,
            selected_class_ids=[
                data["class_5a"].id,
                data["class_5a"].id,
            ],
        )


def test_transfer_rejects_conflicting_assignments(
    teacher_transfer_data,
    db_session,
):
    """Перенос отменяется, если у нового учителя уже есть такое назначение."""

    data = teacher_transfer_data

    # Создаём назначение нового учителя по математике
    # в классе 5А, где математикой уже занимается старый учитель.
    conflict = TeachingAssignment(
        school_id=data["school"].id,
        teacher_id=data["new_teacher"].id,
        class_id=data["class_5a"].id,
        subject_id=data["assignments"][0].subject_id,
        academic_year_id=data["active_year"].id,
        subgroup=0,
    )
    db_session.add(conflict)
    db_session.flush()

    with pytest.raises(ValueError, match="конфликт"):
        transfer_selected_classes(
            db=db_session,
            school_id=data["school"].id,
            academic_year_id=data["active_year"].id,
            teacher_id=data["new_teacher"].id,
            subject_id=data["assignments"][0].subject_id,
            selected_class_ids=[
                data["class_5a"].id,
                data["class_5b"].id,
            ],
        )

    # Старое назначение не должно быть перенесено.
    original_assignment = db_session.get(
        TeachingAssignment,
        data["assignments"][0].id,
    )

    assert original_assignment.teacher_id == data["old_teacher"].id

    # Старые права доступа должны остаться.
    old_access = db_session.scalar(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == data["old_teacher"].id,
            TeacherClassAccess.class_id == data["class_5a"].id,
        )
    )

    assert old_access is not None


def test_create_demo_teacher_without_class_assignments(
    teacher_transfer_data,
    db_session,
    monkeypatch,
):
    """Демонстрационный учитель создаётся без изменения расписания и назначений."""

    data = teacher_transfer_data

    monkeypatch.setenv("DEMO_MODE", "true")

    assignments_before = db_session.scalars(
        select(TeachingAssignment)
    ).all()

    accesses_before = db_session.scalars(
        select(TeacherClassAccess)
    ).all()

    schedules_before = db_session.scalars(
        select(Schedule)
    ).all()

    user, teacher, school, created = create_demo_teacher(
        db=db_session,
        school_id=data["school"].id,
        sferum_id="demo_teacher_1",
        full_name="Демонстрационный Учитель",
    )

    assert created is True
    assert user.is_demo is True
    assert user.sferum_id == "demo_teacher_1"
    assert user.full_name == "Демонстрационный Учитель"

    assert teacher.user_id == user.id
    assert teacher.school_id == school.id
    assert school.id == data["school"].id

    # Количество предметных назначений не изменилось.
    assignments_after = db_session.scalars(
        select(TeachingAssignment)
    ).all()

    assert len(assignments_after) == len(assignments_before)

    # Права доступа к классам не изменились.
    accesses_after = db_session.scalars(
        select(TeacherClassAccess)
    ).all()

    assert len(accesses_after) == len(accesses_before)

    # Расписание не изменилось.
    schedules_after = db_session.scalars(
        select(Schedule)
    ).all()

    assert len(schedules_after) == len(schedules_before)


def test_create_demo_teacher_requires_demo_mode(
    teacher_transfer_data,
    db_session,
    monkeypatch,
):
    """Нельзя создать демонстрационного учителя в рабочем режиме."""

    data = teacher_transfer_data

    monkeypatch.setenv("DEMO_MODE", "false")

    with pytest.raises(ValueError, match="DEMO_MODE=true"):
        create_demo_teacher(
            db=db_session,
            school_id=data["school"].id,
            sferum_id="demo_teacher_2",
            full_name="Другой Демонстрационный Учитель",
        )


def test_main_demo_mode_does_not_transfer_classes(
    teacher_transfer_data,
    db_session,
    monkeypatch,
    capsys,
):
    """main() создаёт demo_teacher и не запускает перенос классов."""

    data = teacher_transfer_data

    monkeypatch.setenv("DEMO_MODE", "true")

    monkeypatch.setattr(
        create_teacher_script,
        "validate_database_mode",
        lambda engine: None,
    )

    monkeypatch.setattr(
        create_teacher_script,
        "is_demo_mode",
        lambda: True,
    )

    # Подменяем Session тестовой сессией.
    # Подключения к рабочей базе не будет.
    monkeypatch.setattr(
        create_teacher_script,
        "Session",
        lambda engine: SQLAlchemySession(
            bind=db_session.get_bind(),
            join_transaction_mode="create_savepoint",
        ),
    )

    # Если main() попытается выполнить перенос, тест завершится ошибкой.
    monkeypatch.setattr(
        create_teacher_script,
        "transfer_selected_classes",
        lambda **kwargs: pytest.fail(
            "В DEMO_MODE нельзя вызывать перенос классов."
        ),
    )

    answers = iter([
        "demo_teacher_3",
        "Третий Демонстрационный Учитель",
        str(data["school"].id),
    ])

    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    create_teacher_script.main()

    output = capsys.readouterr().out

    assert "Демонстрационный учитель успешно добавлен." in output
    assert "Классы не назначались." in output
    assert "расписание не изменялись." in output

    user = db_session.scalar(
        select(User).where(User.sferum_id == "demo_teacher_3")
    )

    assert user is not None
    assert user.is_demo is True

    teacher = db_session.scalar(
        select(Teacher).where(Teacher.user_id == user.id)
    )

    assert teacher is not None
    assert teacher.school_id == data["school"].id

    # У демонстрационного учителя нет прав доступа к классам.
    demo_accesses = db_session.scalars(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == teacher.id,
        )
    ).all()

    assert demo_accesses == []


def test_main_production_mode_transfers_selected_classes(
    teacher_transfer_data,
    db_session,
    monkeypatch,
    capsys,
):
    """main() в рабочем режиме переносит выбранные классы."""

    data = teacher_transfer_data

    monkeypatch.setenv("DEMO_MODE", "false")

    monkeypatch.setattr(
        create_teacher_script,
        "validate_database_mode",
        lambda engine: None,
    )

    # Все обращения main() к Session направляем в тестовую БД.
    # begin() использует вложенную транзакцию, чтобы тестовая
    # сессия могла работать внутри транзакции фикстуры.
    session_calls = 0

    class TestSessionContext:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc_value, traceback):
            self.session.close()
            return False


    def test_session_factory(engine):
        nonlocal session_calls
        session_calls += 1

        connection = db_session.connection()

        test_session = SQLAlchemySession(
            bind=connection,
            expire_on_commit=False,
        )

        return TestSessionContext(test_session)


    monkeypatch.setattr(
        create_teacher_script,
        "Session",
        test_session_factory,
    )

    answers = iter([
        "990000099",
        "Реальный Тестовый Учитель",
        str(data["school"].id),
        "1",
        "5А, 5Б",
        "1",
        "ДА",
    ])

    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    create_teacher_script.main()

    # Обновляем объекты из БД после изменений через отдельную сессию.
    db_session.expire_all()

    output = capsys.readouterr().out

    assert "Учитель успешно добавлен." in output
    assert "Количество перенесённых назначений: 2" in output
    assert "права других учителей сохранены." in output

    # Пользователь создан в рабочем режиме.
    user = db_session.scalar(
        select(User).where(User.sferum_id == "990000099")
    )

    assert user is not None
    assert user.is_demo is False

    # Учитель создан для нужной школы.
    teacher = db_session.scalar(
        select(Teacher).where(Teacher.user_id == user.id)
    )

    assert teacher is not None
    assert teacher.school_id == data["school"].id

    # Назначения 5А и 5Б перешли новому учителю.
    for index in (0, 2):
        assignment = data["assignments"][index]

        current_assignment = db_session.get(
            TeachingAssignment,
            assignment.id,
        )

        assert current_assignment.teacher_id == teacher.id

    # Назначение 6А осталось у прежнего учителя.
    assignment_6a = db_session.get(
        TeachingAssignment,
        data["assignments"][3].id,
    )

    assert assignment_6a.teacher_id == data["other_teacher"].id

    russian_assignment = db_session.get(
        TeachingAssignment,
        data["assignments"][1].id,
    )

    assert russian_assignment.teacher_id == data["old_teacher"].id

    # Назначение прошлого учебного года не изменилось.
    old_assignment = db_session.get(
        TeachingAssignment,
        data["assignments"][4].id,
    )

    assert old_assignment.teacher_id == data["old_teacher"].id

    # Новый учитель получил доступ к 5А и 5Б.
    new_accesses = db_session.scalars(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == teacher.id,
        )
    ).all()

    new_access_class_ids = {
        access.class_id for access in new_accesses
    }

    assert new_access_class_ids == {
        data["class_5a"].id,
        data["class_5b"].id,
    }

    access_pairs = {
        (access.teacher_id, access.class_id)
        for access in db_session.scalars(
            select(TeacherClassAccess)
        ).all()
    }

    assert (
        data["old_teacher"].id,
        data["class_5a"].id,
    ) in access_pairs

    assert (
        data["old_teacher"].id,
        data["class_5b"].id,
    ) in access_pairs

    # Расписание сохранило прежнюю ссылку на назначение.
    schedule = db_session.get(Schedule, data["schedule"].id)

    assert schedule is not None
    assert schedule.assignment_id == data["assignments"][0].id

    scheduled_assignment = db_session.get(
        TeachingAssignment,
        schedule.assignment_id,
    )

    assert scheduled_assignment.teacher_id == teacher.id


def test_grant_class_access_does_not_change_assignments_or_schedule(
    teacher_transfer_data,
    db_session,
):
    """Выдача доступа не меняет назначения, расписание и права других учителей."""

    data = teacher_transfer_data

    assignments_before = {
        assignment.id: assignment.teacher_id
        for assignment in db_session.scalars(
            select(TeachingAssignment)
        ).all()
    }

    schedules_before = {
        schedule.id: schedule.assignment_id
        for schedule in db_session.scalars(
            select(Schedule)
        ).all()
    }

    accesses_before = {
        (access.teacher_id, access.class_id)
        for access in db_session.scalars(
            select(TeacherClassAccess)
        ).all()
    }

    granted_count = grant_class_access(
        db=db_session,
        school_id=data["school"].id,
        academic_year_id=data["active_year"].id,
        teacher_id=data["new_teacher"].id,
        selected_class_ids=[
            data["class_5a"].id,
            data["class_5b"].id,
        ],
    )

    assert granted_count == 2

    assignments_after = {
        assignment.id: assignment.teacher_id
        for assignment in db_session.scalars(
            select(TeachingAssignment)
        ).all()
    }

    schedules_after = {
        schedule.id: schedule.assignment_id
        for schedule in db_session.scalars(
            select(Schedule)
        ).all()
    }

    assert assignments_after == assignments_before
    assert schedules_after == schedules_before

    accesses_after = {
        (access.teacher_id, access.class_id)
        for access in db_session.scalars(
            select(TeacherClassAccess)
        ).all()
    }

    expected_accesses = accesses_before | {
        (data["new_teacher"].id, data["class_5a"].id),
        (data["new_teacher"].id, data["class_5b"].id),
    }

    assert accesses_after == expected_accesses


def test_grant_class_access_rejects_class_from_another_year(
    teacher_transfer_data,
    db_session,
):
    """Нельзя выдать доступ к классу другого учебного года."""

    data = teacher_transfer_data

    with pytest.raises(ValueError, match="не принадлежат"):
        grant_class_access(
            db=db_session,
            school_id=data["school"].id,
            academic_year_id=data["active_year"].id,
            teacher_id=data["new_teacher"].id,
            selected_class_ids=[data["old_class_5a"].id],
        )


def test_grant_class_access_rejects_duplicate_classes(
    teacher_transfer_data,
    db_session,
):
    """Нельзя выдать доступ к одному классу несколько раз."""

    data = teacher_transfer_data

    with pytest.raises(ValueError, match="повторения"):
        grant_class_access(
            db=db_session,
            school_id=data["school"].id,
            academic_year_id=data["active_year"].id,
            teacher_id=data["new_teacher"].id,
            selected_class_ids=[
                data["class_5a"].id,
                data["class_5a"].id,
            ],
        )



def test_main_production_mode_grants_access_without_transfer(
    teacher_transfer_data,
    db_session,
    monkeypatch,
    capsys,
):
    """main() выдаёт доступ, не меняя назначения и расписание."""

    data = teacher_transfer_data

    monkeypatch.setenv("DEMO_MODE", "false")

    monkeypatch.setattr(
        create_teacher_script,
        "validate_database_mode",
        lambda engine: None,
    )

    class TestSessionContext:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc_value, traceback):
            self.session.close()
            return False

    def test_session_factory(engine):
        connection = db_session.connection()

        test_session = SQLAlchemySession(
            bind=connection,
            expire_on_commit=False,
        )

        return TestSessionContext(test_session)

    monkeypatch.setattr(
        create_teacher_script,
        "Session",
        test_session_factory,
    )

    # Сохраняем исходное состояние назначений и расписания.
    assignments_before = {
        assignment.id: assignment.teacher_id
        for assignment in db_session.scalars(
            select(TeachingAssignment)
        ).all()
    }

    schedules_before = {
        schedule.id: schedule.assignment_id
        for schedule in db_session.scalars(
            select(Schedule)
        ).all()
    }

    accesses_before = {
        (access.teacher_id, access.class_id)
        for access in db_session.scalars(
            select(TeacherClassAccess)
        ).all()
    }

    answers = iter([
        "990000098",
        "Учитель Только Доступ",
        str(data["school"].id),
        "2",
        "5А, 5Б",
        "ДА",
    ])

    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    create_teacher_script.main()

    db_session.expire_all()

    output = capsys.readouterr().out

    assert "Учитель успешно добавлен." in output
    assert "Количество классов, к которым выдан доступ: 2" in output
    assert "Предметные назначения не изменялись." in output
    assert "Расписание не изменялось." in output

    # Находим созданного учителя.
    user = db_session.scalar(
        select(User).where(
            User.sferum_id == "990000098"
        )
    )

    assert user is not None
    assert user.is_demo is False

    teacher = db_session.scalar(
        select(Teacher).where(
            Teacher.user_id == user.id
        )
    )

    assert teacher is not None

    # Все предметные назначения остались прежними.
    assignments_after = {
        assignment.id: assignment.teacher_id
        for assignment in db_session.scalars(
            select(TeachingAssignment)
        ).all()
    }

    assert assignments_after == assignments_before

    # Расписание не изменилось.
    schedules_after = {
        schedule.id: schedule.assignment_id
        for schedule in db_session.scalars(
            select(Schedule)
        ).all()
    }

    assert schedules_after == schedules_before

    # Появились только два новых права доступа.
    accesses_after = {
        (access.teacher_id, access.class_id)
        for access in db_session.scalars(
            select(TeacherClassAccess)
        ).all()
    }

    expected_accesses = accesses_before | {
        (teacher.id, data["class_5a"].id),
        (teacher.id, data["class_5b"].id),
    }

    assert accesses_after == expected_accesses



def test_main_production_mode_cancels_access_grant(
    teacher_transfer_data,
    db_session,
    monkeypatch,
    capsys,
):
    """Отмена подтверждения не должна изменять базу данных."""

    data = teacher_transfer_data

    monkeypatch.setenv("DEMO_MODE", "false")

    monkeypatch.setattr(
        create_teacher_script,
        "validate_database_mode",
        lambda engine: None,
    )

    class TestSessionContext:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc_value, traceback):
            self.session.close()
            return False

    def test_session_factory(engine):
        connection = db_session.connection()

        test_session = SQLAlchemySession(
            bind=connection,
            expire_on_commit=False,
        )

        return TestSessionContext(test_session)

    monkeypatch.setattr(
        create_teacher_script,
        "Session",
        test_session_factory,
    )

    user_count_before = len(
        db_session.scalars(select(User)).all()
    )

    teacher_count_before = len(
        db_session.scalars(select(Teacher)).all()
    )

    accesses_before = {
        (access.teacher_id, access.class_id)
        for access in db_session.scalars(
            select(TeacherClassAccess)
        ).all()
    }

    answers = iter([
        "990000097",
        "Отменённый Учитель",
        str(data["school"].id),
        "2",
        "5А, 5Б",
        "НЕТ",
    ])

    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    create_teacher_script.main()

    db_session.expire_all()

    output = capsys.readouterr().out

    assert "Операция отменена." in output

    # Пользователь и учитель не должны появиться.
    assert len(db_session.scalars(select(User)).all()) == user_count_before
    assert len(db_session.scalars(select(Teacher)).all()) == teacher_count_before

    assert db_session.scalar(
        select(User).where(User.sferum_id == "990000097")
    ) is None

    # Права доступа не изменились.
    accesses_after = {
        (access.teacher_id, access.class_id)
        for access in db_session.scalars(
            select(TeacherClassAccess)
        ).all()
    }

    assert accesses_after == accesses_before
