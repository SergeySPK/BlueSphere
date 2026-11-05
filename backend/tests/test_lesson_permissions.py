from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import main
from models import (
    AcademicYear,
    Administrator,
    Class,
    EditingSession,
    School,
    Schedule,
    Student,
    StudentEnrollment,
    Subject,
    Teacher,
    TeachingAssignment,
    User,
)


TEST_DATE = date(2026, 11, 4)
TEST_DATE_STR = TEST_DATE.isoformat()


def get_teacher_user(db_session, teacher):
    """Возвращает пользователя, которому принадлежит учитель."""
    return db_session.get(User, teacher.user_id)


def create_student_user(db_session, school_class, sferum_id):
    """Создаёт ученика, зачисленного в указанный класс."""
    user = User(
        sferum_id=sferum_id,
        full_name="Тестовый ученик",
    )
    db_session.add(user)
    db_session.flush()

    student = Student(
        user_id=user.id,
        class_id=school_class.id,
    )
    db_session.add(student)
    db_session.flush()

    enrollment = StudentEnrollment(
        student_id=student.id,
        class_id=school_class.id,
        start_date=date(2026, 9, 1),
        end_date=None,
    )
    db_session.add(enrollment)
    db_session.flush()

    return user


def create_subgroup_assignment(db_session, data):
    """Создаёт второе назначение того же предмета для другой подгруппы."""
    math_assignment = data["assignments"][0]

    assignment = TeachingAssignment(
        school_id=data["school"].id,
        teacher_id=data["other_teacher"].id,
        class_id=data["class_5a"].id,
        subject_id=math_assignment.subject_id,
        academic_year_id=data["active_year"].id,
        subgroup=1,
    )

    db_session.add(assignment)
    db_session.flush()

    schedule = Schedule(
        assignment_id=assignment.id,
        date=TEST_DATE,
        lesson_number=1,
        room="102",
        lesson_type="Урок",
    )

    db_session.add(schedule)
    db_session.flush()

    return assignment, schedule


# ---------------------------------------------------------------------------
# Проверка can_edit_lesson()
# ---------------------------------------------------------------------------


def test_assigned_teacher_can_edit_own_lesson(
    db_session,
    teacher_transfer_data,
):
    """Учитель может редактировать урок по собственному назначению."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    result = main.can_edit_lesson(
        data["schedule"],
        user,
        db_session,
    )

    assert result is True


def test_teacher_cannot_edit_another_teacher_lesson(
    db_session,
    teacher_transfer_data,
):
    """Учитель не может редактировать урок другого учителя."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["other_teacher"])

    result = main.can_edit_lesson(
        data["schedule"],
        user,
        db_session,
    )

    assert result is False


def test_teacher_can_edit_all_own_assignments(
    db_session,
    teacher_transfer_data,
):
    """
    Учитель может редактировать разные предметы и классы,
    если у него есть соответствующие назначения.
    """
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    # У старого учителя есть назначения:
    # математика в 5А, русский язык в 5А и математика в 5Б.
    own_schedules = []

    for assignment in (
        data["assignments"][1],
        data["assignments"][2],
    ):
        schedule = Schedule(
            assignment_id=assignment.id,
            date=TEST_DATE,
            lesson_number=2,
            room="103",
            lesson_type="Урок",
        )
        db_session.add(schedule)
        db_session.flush()
        own_schedules.append(schedule)

    assert main.can_edit_lesson(
        data["schedule"],
        user,
        db_session,
    ) is True

    for schedule in own_schedules:
        assert main.can_edit_lesson(
            schedule,
            user,
            db_session,
        ) is True


def test_teacher_cannot_edit_lesson_from_another_assignment(
    db_session,
    teacher_transfer_data,
):
    """
    Наличие у учителя других назначений не даёт ему права
    редактировать уроки, не относящиеся к этим назначениям.
    """
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    # Это назначение принадлежит другому учителю.
    other_assignment = data["assignments"][3]

    other_schedule = Schedule(
        assignment_id=other_assignment.id,
        date=TEST_DATE,
        lesson_number=2,
        room="104",
        lesson_type="Урок",
    )
    db_session.add(other_schedule)
    db_session.flush()

    assert main.can_edit_lesson(
        other_schedule,
        user,
        db_session,
    ) is False


def test_teacher_cannot_edit_another_subgroup(
    db_session,
    teacher_transfer_data,
):
    """
    Если один предмет ведут разные учителя в разных подгруппах,
    каждый может редактировать только своё назначение.
    """
    data = teacher_transfer_data

    _, subgroup_schedule = create_subgroup_assignment(
        db_session,
        data,
    )

    first_teacher = get_teacher_user(
        db_session,
        data["old_teacher"],
    )
    second_teacher = get_teacher_user(
        db_session,
        data["other_teacher"],
    )

    # Первый учитель ведёт первую подгруппу.
    assert main.can_edit_lesson(
        data["schedule"],
        first_teacher,
        db_session,
    ) is True

    # Первый учитель не может менять вторую подгруппу.
    assert main.can_edit_lesson(
        subgroup_schedule,
        first_teacher,
        db_session,
    ) is False

    # Второй учитель может менять свою подгруппу.
    assert main.can_edit_lesson(
        subgroup_schedule,
        second_teacher,
        db_session,
    ) is True

    # Второй учитель не может менять первую подгруппу.
    assert main.can_edit_lesson(
        data["schedule"],
        second_teacher,
        db_session,
    ) is False


def test_student_schedule_has_no_editable_lessons(
    db_session,
    teacher_transfer_data,
):
    """В расписании ученика все уроки должны иметь is_editable=False."""
    data = teacher_transfer_data

    student_user = User(
        sferum_id="990000020",
        full_name="Тестовый ученик класса 5А",
    )
    db_session.add(student_user)
    db_session.flush()

    student = Student(
        user_id=student_user.id,
        class_id=data["class_5a"].id,
    )
    db_session.add(student)
    db_session.flush()

    enrollment = StudentEnrollment(
        student_id=student.id,
        class_id=data["class_5a"].id,
        start_date=date(2026, 9, 1),
        end_date=None,
    )
    db_session.add(enrollment)
    db_session.flush()

    result = main.get_school_schedule(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        date=TEST_DATE_STR,
        current_user=student_user,
        db=db_session,
    )

    assert result

    for lesson in result:
        assert lesson.is_editable is False


def test_administrator_can_edit_any_lesson_in_own_school(
    db_session,
    teacher_transfer_data,
):
    """Администратор может редактировать любой урок своей школы."""
    data = teacher_transfer_data

    admin_user = User(
        sferum_id="990000010",
        full_name="Тестовый администратор",
    )
    db_session.add(admin_user)
    db_session.flush()

    administrator = Administrator(
        user_id=admin_user.id,
        school_id=data["school"].id,
        position="Администратор",
    )
    db_session.add(administrator)
    db_session.flush()

    # Урок назначен учителю, но администратор может его редактировать.
    assert main.can_edit_lesson(
        data["schedule"],
        admin_user,
        db_session,
    ) is True

    # Проверяем и урок другого учителя.
    other_schedule = Schedule(
        assignment_id=data["assignments"][3].id,
        date=TEST_DATE,
        lesson_number=2,
        room="106",
        lesson_type="Урок",
    )
    db_session.add(other_schedule)
    db_session.flush()

    assert main.can_edit_lesson(
        other_schedule,
        admin_user,
        db_session,
    ) is True


def test_administrator_cannot_edit_another_school_lesson(
    db_session,
    teacher_transfer_data,
):
    """Администратор не может редактировать уроки чужой школы."""
    data = teacher_transfer_data

    another_school_admin = User(
        sferum_id="990000011",
        full_name="Администратор другой школы",
    )
    db_session.add(another_school_admin)
    db_session.flush()

    # Администратор принадлежит другой школе.
    from models import School

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

    db_session.add(
        Administrator(
            user_id=another_school_admin.id,
            school_id=another_school.id,
            position="Администратор",
        )
    )
    db_session.flush()

    assert main.can_edit_lesson(
        data["schedule"],
        another_school_admin,
        db_session,
    ) is False


def test_student_cannot_edit_lesson(
    db_session,
    teacher_transfer_data,
):
    data = teacher_transfer_data

    student_user = create_student_user(
        db_session,
        data["class_5a"],
        "990000021",
    )

    result = main.can_edit_lesson(
        data["schedule"],
        student_user,
        db_session,
    )

    assert result is False


# ---------------------------------------------------------------------------
# Проверка is_editable в GET расписания
# ---------------------------------------------------------------------------


def test_schedule_returns_is_editable_for_each_lesson(
    db_session,
    teacher_transfer_data,
):
    """
    GET расписания должен возвращать is_editable для каждого урока.
    """
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    # Добавляем ещё один урок, принадлежащий этому учителю.
    own_assignment = data["assignments"][1]

    own_schedule = Schedule(
        assignment_id=own_assignment.id,
        date=TEST_DATE,
        lesson_number=2,
        room="103",
        lesson_type="Урок",
    )
    db_session.add(own_schedule)

    # Добавляем урок другой подгруппы, принадлежащий другому учителю.
    _, other_subgroup_schedule = create_subgroup_assignment(
        db_session,
        data,
    )

    db_session.flush()

    result = main.get_school_schedule(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        date=TEST_DATE_STR,
        current_user=user,
        db=db_session,
    )

    assert len(result) == 3

    editable_by_id = {
        int(lesson.id): lesson.is_editable
        for lesson in result
    }

    assert editable_by_id[data["schedule"].id] is True
    assert editable_by_id[own_schedule.id] is True
    assert editable_by_id[other_subgroup_schedule.id] is False


def test_administrator_schedule_has_all_lessons_editable(
    db_session,
    teacher_transfer_data,
):
    """В расписании администратора все уроки его школы доступны для редактирования."""
    data = teacher_transfer_data

    admin_user = User(
        sferum_id="990000012",
        full_name="Администратор для GET",
    )
    db_session.add(admin_user)
    db_session.flush()

    db_session.add(
        Administrator(
            user_id=admin_user.id,
            school_id=data["school"].id,
            position="Администратор",
        )
    )
    db_session.flush()

    result = main.get_school_schedule(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        date=TEST_DATE_STR,
        current_user=admin_user,
        db=db_session,
    )

    assert result

    for lesson in result:
        assert lesson.is_editable is True


# ---------------------------------------------------------------------------
# Проверка серверной защиты get_editing_user_and_lesson()
# ---------------------------------------------------------------------------


def test_teacher_cannot_get_another_teacher_lesson_for_editing(
    db_session,
    teacher_transfer_data,
):
    """Сервер возвращает 403 при попытке редактировать чужой урок."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["other_teacher"])

    with pytest.raises(HTTPException) as error:
        main.get_editing_user_and_lesson(
            school_id=data["school"].id,
            class_code=data["class_5a"].code,
            lesson_id=str(data["schedule"].id),
            user=user,
            db=db_session,
        )

    assert error.value.status_code == 403


def test_teacher_cannot_edit_lesson_through_another_class_url(
    db_session,
    teacher_transfer_data,
):
    """
    Нельзя подменить class_code в URL и получить доступ к уроку другого класса.
    """
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    # Урок относится к 6А, а в URL указываем 5А.
    other_class_assignment = data["assignments"][3]

    other_class_schedule = Schedule(
        assignment_id=other_class_assignment.id,
        date=TEST_DATE,
        lesson_number=2,
        room="107",
        lesson_type="Урок",
    )
    db_session.add(other_class_schedule)
    db_session.flush()

    with pytest.raises(HTTPException) as error:
        main.get_editing_user_and_lesson(
            school_id=data["school"].id,
            class_code=data["class_5a"].code,
            lesson_id=str(other_class_schedule.id),
            user=user,
            db=db_session,
        )

    assert error.value.status_code == 404


def test_teacher_cannot_edit_lesson_from_another_school(
    db_session,
    teacher_transfer_data,
):
    """Учитель не может редактировать урок другой школы."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    from models import School, AcademicYear, Class, Subject, Teacher

    another_school = School(
        region="Другой регион",
        city="Другой город",
        address="Другой адрес",
        short_name="Школа 2",
        full_name="Вторая тестовая школа",
        timezone="Asia/Yekaterinburg",
    )
    db_session.add(another_school)
    db_session.flush()

    another_year = main.AcademicYear(
        school_id=another_school.id,
        name="2026–2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
        is_active=True,
    )
    db_session.add(another_year)
    db_session.flush()

    another_class = Class(
        school_id=another_school.id,
        academic_year_id=another_year.id,
        code="7a",
        name="7А",
    )
    db_session.add(another_class)
    db_session.flush()

    another_subject = Subject(
        school_id=another_school.id,
        name="Математика",
    )
    db_session.add(another_subject)
    db_session.flush()

    another_teacher_user = User(
        sferum_id="990000013",
        full_name="Учитель другой школы",
    )
    db_session.add(another_teacher_user)
    db_session.flush()

    another_teacher = Teacher(
        user_id=another_teacher_user.id,
        school_id=another_school.id,
    )
    db_session.add(another_teacher)
    db_session.flush()

    another_assignment = TeachingAssignment(
        school_id=another_school.id,
        teacher_id=another_teacher.id,
        class_id=another_class.id,
        subject_id=another_subject.id,
        academic_year_id=another_year.id,
        subgroup=0,
    )
    db_session.add(another_assignment)
    db_session.flush()

    another_schedule = Schedule(
        assignment_id=another_assignment.id,
        date=TEST_DATE,
        lesson_number=1,
        room="201",
        lesson_type="Урок",
    )
    db_session.add(another_schedule)
    db_session.flush()

    assert main.can_edit_lesson(
        another_schedule,
        user,
        db_session,
    ) is False


# ---------------------------------------------------------------------------
# Проверка POST / PUT / DELETE для сессии редактирования
# ---------------------------------------------------------------------------


def test_teacher_can_start_editing_own_lesson(
    db_session,
    teacher_transfer_data,
):
    """Учитель может начать редактирование собственного урока."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    result = main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=user,
        db=db_session,
    )

    editing_session = db_session.scalar(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    )

    assert result["success"] is True
    assert editing_session is not None
    assert editing_session.user_id == user.id


def test_teacher_cannot_start_editing_another_teacher_lesson(
    db_session,
    teacher_transfer_data,
):
    """Учитель не может начать редактирование чужого урока."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["other_teacher"])

    with pytest.raises(HTTPException) as error:
        main.start_editing(
            school_id=data["school"].id,
            class_code=data["class_5a"].code,
            lesson_id=str(data["schedule"].id),
            current_user=user,
            db=db_session,
        )

    assert error.value.status_code == 403

    editing_session = db_session.scalar(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    )

    assert editing_session is None


def test_teacher_can_update_own_lesson_with_active_session(
    db_session,
    teacher_transfer_data,
):
    """Учитель может изменить тип собственного урока при активной сессии."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=user,
        db=db_session,
    )

    editing_session = db_session.scalar(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    )
    old_expires_at = editing_session.expires_at

    request = main.LessonUpdateRequest(
        lesson_type="Контрольная работа",
    )

    result = main.update_lesson(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        request=request,
        current_user=user,
        db=db_session,
    )

    db_session.refresh(data["schedule"])
    db_session.refresh(editing_session)

    assert data["schedule"].lesson_type == "Контрольная работа"
    assert data["schedule"].updated_by_user_id == user.id
    assert result.lesson_type == "Контрольная работа"
    assert editing_session.expires_at > old_expires_at
    assert editing_session.user_id == user.id


def test_teacher_can_reacquire_own_active_editing_session(
    db_session,
    teacher_transfer_data,
):
    """Повторный захват своей активной сессии продлевает её, не создавая новую."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=user,
        db=db_session,
    )

    first_session = db_session.scalar(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    )
    first_session_id = first_session.id
    old_expires_at = first_session.expires_at

    result = main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=user,
        db=db_session,
    )

    sessions = db_session.scalars(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    ).all()

    assert result["success"] is True
    assert len(sessions) == 1
    assert sessions[0].id == first_session_id
    assert sessions[0].user_id == user.id
    assert sessions[0].expires_at > old_expires_at


def test_administrator_can_take_over_expired_editing_session(
    db_session,
    teacher_transfer_data,
):
    """Администратор может захватить урок после истечения чужой сессии."""
    data = teacher_transfer_data
    admin_user = User(
        sferum_id="990000030",
        full_name="Администратор для проверки сессии",
    )
    db_session.add(admin_user)
    db_session.flush()

    db_session.add(
        Administrator(
            user_id=admin_user.id,
            school_id=data["school"].id,
            position="Администратор",
        )
    )
    db_session.flush()

    teacher_user = get_teacher_user(db_session, data["old_teacher"])

    expired_session = EditingSession(
        schedule_id=data["schedule"].id,
        user_id=teacher_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(expired_session)
    db_session.flush()

    old_session_id = expired_session.id

    result = main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=admin_user,
        db=db_session,
    )

    sessions = db_session.scalars(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    ).all()

    assert result["success"] is True
    assert len(sessions) == 1
    assert sessions[0].id != old_session_id
    assert sessions[0].user_id == admin_user.id
    assert sessions[0].expires_at > datetime.now(timezone.utc)


def test_user_cannot_update_lesson_with_expired_session(
    db_session,
    teacher_transfer_data,
):
    """Истёкшая сессия не позволяет изменить урок."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    expired_session = EditingSession(
        schedule_id=data["schedule"].id,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(expired_session)
    db_session.flush()

    request = main.LessonUpdateRequest(
        lesson_type="Контрольная работа",
    )

    with pytest.raises(HTTPException) as error:
        main.update_lesson(
            school_id=data["school"].id,
            class_code=data["class_5a"].code,
            lesson_id=str(data["schedule"].id),
            request=request,
            current_user=user,
            db=db_session,
        )

    assert error.value.status_code == 409

    db_session.refresh(data["schedule"])
    db_session.refresh(expired_session)

    assert data["schedule"].lesson_type == "Урок"
    assert expired_session.user_id == user.id


def test_teacher_cannot_update_another_teacher_lesson(
    db_session,
    teacher_transfer_data,
):
    """Чужой урок нельзя изменить даже при прямом вызове PUT."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["other_teacher"])

    request = main.LessonUpdateRequest(
        lesson_type="Контрольная работа",
    )

    with pytest.raises(HTTPException) as error:
        main.update_lesson(
            school_id=data["school"].id,
            class_code=data["class_5a"].code,
            lesson_id=str(data["schedule"].id),
            request=request,
            current_user=user,
            db=db_session,
        )

    assert error.value.status_code == 403
    assert data["schedule"].lesson_type == "Урок"


def test_teacher_cannot_stop_another_users_editing_session(
    db_session,
    teacher_transfer_data,
):
    """
    Учитель не может завершить сессию редактирования,
    созданную другим пользователем.
    """
    data = teacher_transfer_data

    owner = get_teacher_user(db_session, data["old_teacher"])
    another_user = get_teacher_user(db_session, data["other_teacher"])

    main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=owner,
        db=db_session,
    )

    with pytest.raises(HTTPException) as error:
        main.stop_editing(
            school_id=data["school"].id,
            class_code=data["class_5a"].code,
            lesson_id=str(data["schedule"].id),
            current_user=another_user,
            db=db_session,
        )

    assert error.value.status_code == 403

    editing_session = db_session.scalar(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    )

    assert editing_session is not None
    assert editing_session.user_id == owner.id


def test_administrator_cannot_stop_teacher_editing_session(
    db_session,
    teacher_transfer_data,
):
    """
    Даже администратор, имеющий право редактировать урок,
    не может завершить сессию другого пользователя.
    """
    data = teacher_transfer_data

    teacher_user = get_teacher_user(
        db_session,
        data["old_teacher"],
    )

    admin_user = User(
        sferum_id="990000030",
        full_name="Администратор для проверки сессии",
    )
    db_session.add(admin_user)
    db_session.flush()

    administrator = Administrator(
        user_id=admin_user.id,
        school_id=data["school"].id,
        position="Администратор",
    )
    db_session.add(administrator)
    db_session.flush()

    # Учитель начинает редактирование своего урока.
    main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=teacher_user,
        db=db_session,
    )

    # Администратор имеет право редактировать урок,
    # но не является владельцем текущей сессии.
    with pytest.raises(HTTPException) as error:
        main.stop_editing(
            school_id=data["school"].id,
            class_code=data["class_5a"].code,
            lesson_id=str(data["schedule"].id),
            current_user=admin_user,
            db=db_session,
        )

    assert error.value.status_code == 403

    editing_session = db_session.scalar(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    )

    assert editing_session is not None
    assert editing_session.user_id == teacher_user.id


def test_teacher_can_stop_own_editing_session(
    db_session,
    teacher_transfer_data,
):
    """Учитель может завершить собственную сессию, не удаляя урок."""
    data = teacher_transfer_data
    user = get_teacher_user(db_session, data["old_teacher"])

    main.start_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=user,
        db=db_session,
    )

    result = main.stop_editing(
        school_id=data["school"].id,
        class_code=data["class_5a"].code,
        lesson_id=str(data["schedule"].id),
        current_user=user,
        db=db_session,
    )

    editing_session = db_session.scalar(
        select(EditingSession).where(
            EditingSession.schedule_id == data["schedule"].id
        )
    )

    assert result == {"success": True}
    assert editing_session is None

    # Урок должен остаться в расписании.
    assert db_session.get(Schedule, data["schedule"].id) is not None
