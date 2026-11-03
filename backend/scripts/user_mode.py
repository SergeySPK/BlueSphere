import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User

PROTECTED_DATABASES = {"bluesphere_restore_test"}


def is_demo_mode() -> bool:
    """
    Режим определяется исключительно переменной DEMO_MODE.

    Если переменная не задана, используется false.
    Допустимые значения: true и false.
    """
    value = os.getenv("DEMO_MODE", "false").strip().lower()

    if value not in {"true", "false"}:
        raise ValueError(
            "Некорректное значение DEMO_MODE. " "Допустимы только true и false."
        )

    return value == "true"


def get_or_create_user(
    session: Session,
    sferum_id: str,
    full_name: str,
) -> tuple[User, bool]:
    """Находит пользователя или создаёт его в текущем режиме."""

    demo_mode = is_demo_mode()

    user = session.scalar(select(User).where(User.sferum_id == sferum_id))

    if user is not None:
        if user.is_demo != demo_mode:
            expected = "демонстрационному" if demo_mode else "рабочему"
            actual = "демонстрационному" if user.is_demo else "рабочему"

            raise ValueError(
                f"Пользователь уже принадлежит режиму «{actual}», "
                f"а скрипт запущен в режиме «{expected}»."
            )

        return user, False

    user = User(
        sferum_id=sferum_id,
        full_name=full_name,
        is_demo=demo_mode,
    )

    session.add(user)
    session.flush()

    return user, True


def get_user_by_sferum_id(
    session: Session,
    sferum_id: str,
) -> User | None:
    """Находит пользователя и проверяет соответствие DEMO_MODE."""

    demo_mode = is_demo_mode()

    user = session.scalar(select(User).where(User.sferum_id == sferum_id))

    if user is not None and user.is_demo != demo_mode:
        expected = "демонстрационному" if demo_mode else "рабочему"
        actual = "демонстрационному" if user.is_demo else "рабочему"

        raise ValueError(
            f"Пользователь {sferum_id} принадлежит режиму "
            f"«{actual}», но скрипт запущен в режиме «{expected}»."
        )

    return user


def validate_database_mode(engine) -> None:
    """
    Проверяет настройки режима и защищает отдельную тестовую БД.

    Название базы не определяет режим.
    Единственный переключатель режима — DEMO_MODE.

    bluesphere_restore_test запрещена для скриптов заполнения
    и изменения данных независимо от режима.
    """

    demo_mode = is_demo_mode()
    database_name = engine.url.database

    if database_name in PROTECTED_DATABASES:
        raise RuntimeError(
            f"База {database_name} защищена. " "Запуск скриптов для неё запрещён."
        )

    mode_name = "DEMO" if demo_mode else "PRODUCTION"

    print(
        f"[{mode_name}] Проверка режима пройдена. "
        f"Целевая БД: {database_name or 'не определена'}"
    )
