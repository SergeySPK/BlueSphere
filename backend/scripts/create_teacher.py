import sys
from pathlib import Path

# Добавляем папку backend в пути поиска модулей Python.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from scripts.user_mode import get_or_create_user, is_demo_mode, validate_database_mode
from database import engine
from models import (
    AcademicYear,
    Class,
    School,
    Subject,
    Teacher,
    TeacherClassAccess,
    TeachingAssignment,
    User,
)


def normalize_class_code(value: str) -> str:
    """Приводит обозначение класса к формату кодов в БД."""

    value = "".join(value.upper().split())

    translation = str.maketrans({
        "А": "a",
        "Б": "b",
        "В": "v",
        "Г": "g",
        "A": "a",
        "B": "b",
        "V": "v",
        "G": "g",
    })

    return value.translate(translation)


def create_demo_teacher(
    db: Session,
    school_id: int,
    sferum_id: str,
    full_name: str,
) -> tuple[User, Teacher, School, bool]:
    """
    Создаёт демонстрационного учителя без привязки к классам.

    Не изменяет TeacherClassAccess, TeachingAssignment и Schedule.

    Возвращает пользователя, учителя, школу и признак создания пользователя.
    """

    if not is_demo_mode():
        raise ValueError(
            "Создание демонстрационного учителя возможно "
            "только при DEMO_MODE=true."
        )

    school = db.get(School, school_id)

    if school is None:
        raise ValueError(f"Школа с ID {school_id} не найдена.")

    existing_teacher = db.scalar(
        select(Teacher)
        .join(User, User.id == Teacher.user_id)
        .where(
            User.sferum_id == sferum_id,
            Teacher.school_id == school_id,
        )
    )

    if existing_teacher is not None:
        raise ValueError(
            "Этот пользователь уже является учителем "
            f"школы {school_id}."
        )

    user, created = get_or_create_user(
        db,
        sferum_id,
        full_name,
    )

    teacher = Teacher(
        user_id=user.id,
        school_id=school_id,
    )

    db.add(teacher)
    db.flush()

    return user, teacher, school, created


def transfer_selected_classes(
    db: Session,
    school_id: int,
    academic_year_id: int,
    teacher_id: int,
    subject_id: int,
    selected_class_ids: list[int],
) -> int:
    """
    Передаёт новому учителю выбранный предмет в выбранных классах.

    Переносятся все подгруппы выбранного предмета.
    Существующие права доступа других учителей сохраняются.
    Новому учителю добавляются права на выбранные классы.

    Возвращает количество перенесённых назначений.
    """

    if not selected_class_ids:
        raise ValueError("Необходимо выбрать хотя бы один класс.")

    if len(selected_class_ids) != len(set(selected_class_ids)):
        raise ValueError("В списке классов есть повторения.")

    # Проверяем активный учебный год.
    academic_year = db.scalar(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.school_id == school_id,
            AcademicYear.is_active.is_(True),
        )
    )

    if academic_year is None:
        raise ValueError(
            "Указанный учебный год не существует "
            "или больше не является активным."
        )

    # Проверяем принадлежность учителя школе.
    teacher = db.scalar(
        select(Teacher).where(
            Teacher.id == teacher_id,
            Teacher.school_id == school_id,
        )
    )

    if teacher is None:
        raise ValueError(
            "Учитель не найден или не принадлежит указанной школе."
        )

    # Проверяем существование предмета в школе.
    subject = db.scalar(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.school_id == school_id,
        )
    )

    if subject is None:
        raise ValueError(
            "Предмет не найден или не принадлежит указанной школе."
        )

    # Проверяем выбранные классы.
    classes = db.scalars(
        select(Class).where(
            Class.id.in_(selected_class_ids),
            Class.school_id == school_id,
            Class.academic_year_id == academic_year_id,
        )
    ).all()

    if len(classes) != len(selected_class_ids):
        raise ValueError(
            "Один или несколько выбранных классов "
            "не принадлежат школе или учебному году."
        )

    # Получаем назначения только выбранного предмета
    # в выбранных классах и активном учебном году.
    selected_assignments = db.scalars(
        select(TeachingAssignment).where(
            TeachingAssignment.school_id == school_id,
            TeachingAssignment.academic_year_id == academic_year_id,
            TeachingAssignment.subject_id == subject_id,
            TeachingAssignment.class_id.in_(selected_class_ids),
        )
    ).all()

    if not selected_assignments:
        raise ValueError(
            "В выбранных классах нет назначений "
            "по указанному предмету."
        )

    # Проверяем конфликты с уже существующими назначениями
    # нового учителя по этому предмету.
    for assignment in selected_assignments:
        conflicting_assignment_id = db.scalar(
            select(TeachingAssignment.id).where(
                TeachingAssignment.school_id == school_id,
                TeachingAssignment.teacher_id == teacher_id,
                TeachingAssignment.class_id == assignment.class_id,
                TeachingAssignment.subject_id == subject_id,
                TeachingAssignment.academic_year_id == academic_year_id,
                TeachingAssignment.subgroup == assignment.subgroup,
                TeachingAssignment.id != assignment.id,
            )
        )

        if conflicting_assignment_id is not None:
            raise ValueError(
                "Обнаружен конфликт предметных назначений: "
                f"class_id={assignment.class_id}, "
                f"subject_id={subject_id}, "
                f"subgroup={assignment.subgroup}. "
                "Новый учитель уже имеет такое назначение."
            )

    # Получаем уже существующие права нового учителя.
    existing_access_class_ids = set(
        db.scalars(
            select(TeacherClassAccess.class_id).where(
                TeacherClassAccess.teacher_id == teacher_id,
                TeacherClassAccess.school_id == school_id,
                TeacherClassAccess.academic_year_id == academic_year_id,
                TeacherClassAccess.class_id.in_(selected_class_ids),
            )
        ).all()
    )

    # Добавляем только отсутствующие права.
    # Права остальных учителей не удаляем и не изменяем.
    for class_item in classes:
        if class_item.id not in existing_access_class_ids:
            db.add(
                TeacherClassAccess(
                    teacher_id=teacher_id,
                    class_id=class_item.id,
                    school_id=school_id,
                    academic_year_id=academic_year_id,
                )
            )

    # Переносим только выбранный предмет.
    # ID назначений остаются прежними, поэтому расписание
    # продолжает ссылаться на те же TeachingAssignment.
    result = db.execute(
        update(TeachingAssignment)
        .where(
            TeachingAssignment.school_id == school_id,
            TeachingAssignment.academic_year_id == academic_year_id,
            TeachingAssignment.subject_id == subject_id,
            TeachingAssignment.class_id.in_(selected_class_ids),
        )
        .values(teacher_id=teacher_id)
    )

    db.flush()

    return result.rowcount or 0


def grant_class_access(
    db: Session,
    school_id: int,
    academic_year_id: int,
    teacher_id: int,
    selected_class_ids: list[int],
) -> int:
    """Выдаёт учителю доступ к выбранным классам без изменения назначений."""

    if not selected_class_ids:
        raise ValueError("Необходимо выбрать хотя бы один класс.")

    if len(selected_class_ids) != len(set(selected_class_ids)):
        raise ValueError("В списке классов обнаружены повторения.")

    active_year = db.scalar(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.school_id == school_id,
            AcademicYear.is_active.is_(True),
        )
    )

    if active_year is None:
        raise ValueError(
            "Указанный учебный год не является активным для этой школы."
        )

    teacher = db.scalar(
        select(Teacher).where(
            Teacher.id == teacher_id,
            Teacher.school_id == school_id,
        )
    )

    if teacher is None:
        raise ValueError(
            "Учитель не найден или не принадлежит указанной школе."
        )

    classes = db.scalars(
        select(Class).where(
            Class.id.in_(selected_class_ids),
            Class.school_id == school_id,
            Class.academic_year_id == academic_year_id,
        )
    ).all()

    if len(classes) != len(selected_class_ids):
        raise ValueError(
            "Один или несколько классов не принадлежат "
            "указанной школе или учебному году."
        )

    existing_accesses = db.scalars(
        select(TeacherClassAccess).where(
            TeacherClassAccess.teacher_id == teacher_id,
            TeacherClassAccess.class_id.in_(selected_class_ids),
            TeacherClassAccess.school_id == school_id,
            TeacherClassAccess.academic_year_id == academic_year_id,
        )
    ).all()

    if existing_accesses:
        raise ValueError(
            "У учителя уже есть доступ к одному или нескольким выбранным классам."
        )

    for school_class in classes:
        db.add(
            TeacherClassAccess(
                teacher_id=teacher_id,
                class_id=school_class.id,
                school_id=school_id,
                academic_year_id=academic_year_id,
            )
        )

    db.flush()

    return len(classes)


def main():
    validate_database_mode(engine)

    print("=== Добавление учителя BlueSphere ===")

    sferum_id = input("MAX user_id учителя: ").strip()
    full_name = input("ФИО учителя: ").strip()
    school_id_input = input("ID школы (например, 1): ").strip()

    if not sferum_id or not full_name or not school_id_input:
        print("Ошибка: все поля обязательны.")
        return

    try:
        school_id = int(school_id_input)
    except ValueError:
        print("Ошибка: ID школы должен быть целым числом.")
        return

    # DEMO_MODE: создаём демонстрационного учителя
    # без привязки к классам и реальному расписанию.
    if is_demo_mode():
        try:
            with Session(engine) as db:
                with db.begin():
                    user, teacher, school, created = create_demo_teacher(
                        db=db,
                        school_id=school_id,
                        sferum_id=sferum_id,
                        full_name=full_name,
                    )

                print("\nДемонстрационный учитель успешно добавлен.")
                print(f"Режим: DEMO")
                print(f"ФИО: {user.full_name}")
                print(f"MAX user_id: {user.sferum_id}")
                print(f"ID пользователя в БД: {user.id}")
                print(f"ID учителя: {teacher.id}")
                print(f"Школа: {school.short_name or school.full_name}")
                print("Классы не назначались.")
                print("Предметные назначения и расписание не изменялись.")

                if created:
                    print("Создана новая демонстрационная учётная запись.")
                else:
                    print("Использована существующая демонстрационная учётная запись.")

        except ValueError as error:
            print(f"\nОшибка: {error}")
            print("Изменения в базе данных не сохранены.")

        return

    # Сначала получаем активный учебный год и список классов.
    # На этом этапе база данных не изменяется.
    with Session(engine) as db:
        school = db.get(School, school_id)

        if school is None:
            print(f"Ошибка: школа с ID {school_id} не найдена.")
            return

        academic_year = db.scalar(
            select(AcademicYear).where(
                AcademicYear.school_id == school_id,
                AcademicYear.is_active.is_(True),
            )
        )

        if academic_year is None:
            print(
                f"Ошибка: у школы {school_id} "
                "не найден активный учебный год."
            )
            return

        available_classes = db.scalars(
            select(Class)
            .where(
                Class.school_id == school_id,
                Class.academic_year_id == academic_year.id,
            )
            .order_by(Class.code)
        ).all()

        if not available_classes:
            print("Ошибка: в активном учебном году нет классов.")
            return

        print(f"\nШкола: {school.short_name or school.full_name}")
        print(f"Активный учебный год: {academic_year.name}")
        print("\nДоступные классы:")

        for class_item in available_classes:
            print(f"  {class_item.name} (код: {class_item.code})")

    print("\nВыберите действие:")
    print("1 — Передать выбранный предмет новому учителю.")
    print("    Будут перенесены все подгруппы выбранного предмета.")
    print("2 — Только выдать доступ к выбранным классам.")
    print("    Предметные назначения и расписание останутся без изменений.")

    action = input("\nВаш выбор (1 или 2): ").strip()

    if action not in ("1", "2"):
        print("Ошибка: необходимо выбрать 1 или 2.")
        return

    class_input = input(
        "\nВведите классы "
        "(через запятую, например 5А, 5Б): "
    ).strip()

    if not class_input:
        print("Ошибка: необходимо указать хотя бы один класс.")
        return

    requested_codes = [
        normalize_class_code(code)
        for code in class_input.split(",")
        if code.strip()
    ]

    if not requested_codes:
        print("Ошибка: не удалось распознать список классов.")
        return

    if len(requested_codes) != len(set(requested_codes)):
        print("Ошибка: в списке есть повторяющиеся классы.")
        return

    # Предварительно проверяем выбранные классы
    # по списку, который получили до начала транзакции.
    available_classes_by_code = {
        normalize_class_code(class_item.code): class_item
        for class_item in available_classes
    }

    missing_codes = [
        code
        for code in requested_codes
        if code not in available_classes_by_code
    ]

    if missing_codes:
        print("Ошибка: не найдены классы: " + ", ".join(missing_codes))
        return

    selected_class_names = [
        available_classes_by_code[code].name
        for code in requested_codes
    ]

    selected_class_ids = [
        available_classes_by_code[code].id
        for code in requested_codes
    ]

    selected_subjects = []

    if action == "1":
        with Session(engine) as db:
            # Получаем ID активного учебного года.
            academic_year = db.scalar(
                select(AcademicYear).where(
                    AcademicYear.school_id == school_id,
                    AcademicYear.is_active.is_(True),
                )
            )

            if academic_year is None:
                print("Ошибка: у школы нет активного учебного года.")
                return

            academic_year_id = academic_year.id

            # Получаем предметы, по которым есть назначения
            # в выбранных классах текущего учебного года.
            selected_subjects = db.execute(
                select(
                    Subject.id,
                    Subject.name,
                    func.count(TeachingAssignment.id).label("assignment_count"),
                )
                .join(
                    TeachingAssignment,
                    TeachingAssignment.subject_id == Subject.id,
                )
                .where(
                    Subject.school_id == school_id,
                    TeachingAssignment.school_id == school_id,
                    TeachingAssignment.academic_year_id == academic_year_id,
                    TeachingAssignment.class_id.in_(selected_class_ids),
                )
                .group_by(Subject.id, Subject.name)
                .order_by(Subject.name)
            ).all()

        if not selected_subjects:
            print("Ошибка: в выбранных классах нет предметных назначений.")
            return

        print("\nПредметы, доступные для переноса:")

        for index, subject in enumerate(selected_subjects, start=1):
            print(
                f"{index} — {subject.name} "
                f"(назначений: {subject.assignment_count})"
            )

        subject_choice = input(
            "\nВыберите предмет по номеру: "
        ).strip()

        if not subject_choice.isdigit():
            print("Ошибка: необходимо ввести номер предмета.")
            return

        subject_index = int(subject_choice) - 1

        if not 0 <= subject_index < len(selected_subjects):
            print("Ошибка: предмет с таким номером отсутствует.")
            return

        selected_subject_id = selected_subjects[subject_index].id
        selected_subject_name = selected_subjects[subject_index].name
        selected_assignment_count = (
            selected_subjects[subject_index].assignment_count
        )

    print("\nВыбранные классы:")
    for class_name in selected_class_names:
        print(f"  {class_name}")

    if action == "1":
        print("\nВНИМАНИЕ!")
        print(f"Новый учитель: {full_name}")
        print(f"Предмет: {selected_subject_name}")
        print(f"Количество назначений: {selected_assignment_count}")
        print("Выбранные классы:")

        for class_name in selected_class_names:
            print(f"  {class_name}")

        print("\nБудут перенесены все подгруппы выбранного предмета.")
        print("Назначения других предметов останутся без изменений.")
        print("Существующие права доступа других учителей сохранятся.")
        print("ID назначений и связанное расписание сохранятся.")

        confirmation = input(
            '\nДля подтверждения введите "ДА": '
        ).strip().upper()

        if confirmation != "ДА":
            print("Операция отменена. Изменения не сохранены.")
            return

    if action == "2":
        print("\nВНИМАНИЕ!")
        print("Будет создан новый учитель и выдан доступ к указанным классам.")
        print("Предметные назначения не изменятся.")
        print("Расписание не изменится.")
        print("Права доступа других учителей не изменятся.")

        confirmation = input(
            '\nДля подтверждения введите "ДА": '
        ).strip().upper()

        if confirmation != "ДА":
            print("Операция отменена. Изменения не сохранены.")
            return

    # Все изменения выполняются в одной транзакции.
    # При любой ошибке SQLAlchemy автоматически откатит изменения.
    try:
        with Session(engine) as db:
            with db.begin():
                school = db.get(School, school_id)

                if school is None:
                    raise ValueError(
                        f"Школа с ID {school_id} больше не существует."
                    )

                academic_year = db.scalar(
                    select(AcademicYear).where(
                        AcademicYear.school_id == school_id,
                        AcademicYear.is_active.is_(True),
                    )
                )

                if academic_year is None:
                    raise ValueError(
                        "У школы больше нет активного учебного года."
                    )

                classes = db.scalars(
                    select(Class).where(
                        Class.school_id == school_id,
                        Class.academic_year_id == academic_year.id,
                    )
                ).all()

                classes_by_code = {
                    normalize_class_code(class_item.code): class_item
                    for class_item in classes
                }

                missing_codes = [
                    code
                    for code in requested_codes
                    if code not in classes_by_code
                ]

                if missing_codes:
                    raise ValueError(
                        "Не найдены классы: "
                        + ", ".join(missing_codes)
                    )

                selected_classes = [
                    classes_by_code[code]
                    for code in requested_codes
                ]

                selected_class_ids = [
                    class_item.id
                    for class_item in selected_classes
                ]

                # Проверяем, не зарегистрирован ли пользователь
                # учителем этой школы.
                existing_teacher = db.scalar(
                    select(Teacher)
                    .join(User, User.id == Teacher.user_id)
                    .where(
                        User.sferum_id == sferum_id,
                        Teacher.school_id == school_id,
                    )
                )

                if existing_teacher is not None:
                    raise ValueError(
                        "Этот пользователь уже является учителем "
                        f"школы {school_id}."
                    )

                user, created = get_or_create_user(
                    db,
                    sferum_id,
                    full_name,
                )

                teacher = Teacher(
                    user_id=user.id,
                    school_id=school_id,
                )

                db.add(teacher)
                db.flush()

                if action == "1":
                    moved_assignments = transfer_selected_classes(
                        db=db,
                        school_id=school_id,
                        academic_year_id=academic_year.id,
                        teacher_id=teacher.id,
                        subject_id=selected_subject_id,
                        selected_class_ids=selected_class_ids,
                    )
                    granted_count = None
                else:
                    granted_count = grant_class_access(
                        db=db,
                        school_id=school_id,
                        academic_year_id=academic_year.id,
                        teacher_id=teacher.id,
                        selected_class_ids=selected_class_ids,
                    )
                    moved_assignments = None

                db.flush()

                # Выход из db.begin() выполнит COMMIT.
                # При исключении произойдёт ROLLBACK.

            print("\nУчитель успешно добавлен.")
            print(f"ФИО: {user.full_name}")
            print(f"ID пользователя в БД: {user.id}")
            print(f"ID учителя: {teacher.id}")
            print(f"Школа: {school.short_name or school.full_name}")
            print(f"Учебный год: {academic_year.name}")

            print("\nВыбранные классы:")
            for class_item in selected_classes:
                print(f"  {class_item.name}")

            if action == "1":
                print(
                    "\nКоличество перенесённых назначений: "
                    f"{moved_assignments}"
                )
                print("Права доступа нового учителя к выбранным классам проверены.")
                print("Существующие права других учителей сохранены.")
                print("Расписание и ID назначений сохранены.")
            else:
                print(
                    "\nКоличество классов, к которым выдан доступ: "
                    f"{granted_count}"
                )
                print("Предметные назначения не изменялись.")
                print("Расписание не изменялось.")
                print("Права доступа других учителей не изменялись.")

            if created:
                print("Создана новая учётная запись пользователя.")
            else:
                print("Использована существующая учётная запись.")

    except ValueError as error:
        print(f"\nОшибка: {error}")
        print("Изменения в базе данных не сохранены.")


if __name__ == "__main__":
    main()