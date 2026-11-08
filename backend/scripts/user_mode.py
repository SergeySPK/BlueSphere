import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User


def is_demo_mode() -> bool:
    value = os.getenv("DEMO_MODE", "false").strip().lower()

    if value not in {"true", "false"}:
        raise ValueError(
            "Некорректное значение DEMO_MODE. "
            "Допустимы только true и false."
        )

    return value == "true"


def get_or_create_user(
    session: Session,
    sferum_id: str,
    full_name: str,
) -> tuple[User, bool]:
    demo_mode = is_demo_mode()

    user = session.scalar(
        select(User).where(User.sferum_id == sferum_id)
    )

    if user is not None:
        if user.is_demo != demo_mode:
            raise ValueError(
                f"Пользователь {sferum_id} уже существует "
                "в другом режиме DEMO_MODE."
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
    demo_mode = is_demo_mode()

    user = session.scalar(
        select(User).where(User.sferum_id == sferum_id)
    )

    if user is not None and user.is_demo != demo_mode:
        raise ValueError(
            f"Пользователь {sferum_id} принадлежит другому режиму."
        )

    return user


def validate_database_mode(engine) -> None:
    demo_mode = is_demo_mode()
    mode_name = "DEMO" if demo_mode else "PRODUCTION"
    database_name = engine.url.database or "не определена"

    print(
        f"[{mode_name}] Проверка режима пройдена. "
        f"Целевая БД: {database_name}"
    )
