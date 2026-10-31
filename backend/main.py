from pathlib import Path
from dotenv import load_dotenv
from datetime import date as PythonDate, datetime, timedelta, timezone
import calendar

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import (
    AcademicYear,
    Administrator,
    Class,
    EditingSession,
    Recommendation,
    Schedule,
    School,
    Student,
    Subject,
    Survey,
    Teacher,
    TeachingAssignment,
    User,
)

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional

import hashlib
import jwt
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_FILE)

app = FastAPI(title="Blue Sphere API", docs_url="/docs", redoc_url=None)

JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_SECONDS = 60 * 60
JWT_ISSUER = "blue-sphere-api"

bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(user: User) -> tuple[str, int]:
    secret_key = os.getenv("JWT_SECRET_KEY")

    if not secret_key:
        raise HTTPException(
            status_code=500,
            detail="Авторизация API не настроена",
        )

    now = int(time.time())
    expires_in = JWT_ACCESS_TOKEN_EXPIRE_SECONDS

    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + expires_in,
        "iss": JWT_ISSUER,
    }

    token = jwt.encode(
        payload,
        secret_key,
        algorithm=JWT_ALGORITHM,
    )

    return token, expires_in


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    secret_key = os.getenv("JWT_SECRET_KEY")

    if not secret_key:
        raise HTTPException(
            status_code=500,
            detail="Авторизация API не настроена",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss"]},
        )

        user_id = int(payload["sub"])
        if user_id <= 0:
            raise ValueError("Некорректный идентификатор")

    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Токен недействителен или устарел",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Пользователь больше не существует",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_user_access(
    user: User,
    db: Session,
) -> tuple[set[str], set[int]]:
    """Возвращает актуальные роли пользователя и доступные ему классы."""

    roles: set[str] = set()
    class_ids: set[int] = set()

    # Учитель может иметь назначения в нескольких школах.
    teachers = db.scalars(
        select(Teacher).where(Teacher.user_id == user.id)
    ).all()

    if teachers:
        roles.add("teacher")

        teacher_ids = [teacher.id for teacher in teachers]

        assigned_class_ids = db.scalars(
            select(TeachingAssignment.class_id).where(
                TeachingAssignment.teacher_id.in_(teacher_ids)
            )
        ).all()

        class_ids.update(assigned_class_ids)

    # Администратор имеет доступ к классам своих школ.
    admin_school_ids = db.scalars(
        select(Administrator.school_id).where(
            Administrator.user_id == user.id
        )
    ).all()

    if admin_school_ids:
        roles.add("admin")

        admin_class_ids = db.scalars(
            select(Class.id).where(
                Class.school_id.in_(admin_school_ids)
            )
        ).all()

        class_ids.update(admin_class_ids)

    # Ученик имеет доступ только к собственному классу.
    student = db.scalar(
        select(Student).where(Student.user_id == user.id)
    )

    if student is not None:
        roles.add("student")
        class_ids.add(student.class_id)

    return roles, class_ids


def get_user_school_ids(
    user: User,
    db: Session,
) -> set[int]:
    """Возвращает ID школ, к которым у пользователя есть доступ."""

    school_ids: set[int] = set()

    # Учитель имеет доступ к школе, в которой он зарегистрирован.
    teacher_school_ids = db.scalars(
        select(Teacher.school_id).where(
            Teacher.user_id == user.id
        )
    ).all()

    school_ids.update(teacher_school_ids)

    # Администратор имеет доступ к своим школам.
    admin_school_ids = db.scalars(
        select(Administrator.school_id).where(
            Administrator.user_id == user.id
        )
    ).all()

    school_ids.update(admin_school_ids)

    # Ученик получает доступ к школе своего текущего класса.
    student_school_id = db.scalar(
        select(Class.school_id)
        .join(Student, Student.class_id == Class.id)
        .where(Student.user_id == user.id)
    )

    if student_school_id is not None:
        school_ids.add(student_school_id)

    return school_ids


def require_school_access(
    school_id: int,
    user: User,
    db: Session,
) -> School:
    """Проверяет доступ пользователя к школе."""

    school = db.scalar(
        select(School).where(School.id == school_id)
    )

    if school is None:
        raise HTTPException(
            status_code=404,
            detail="Школа не найдена",
        )

    allowed_school_ids = get_user_school_ids(user, db)

    if school_id not in allowed_school_ids:
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этой школе",
        )

    return school


def require_class_access(
    class_code: str,
    user: User,
    db: Session,
    allowed_roles: set[str] | None = None,
) -> Class:
    """Находит класс в единственной доступной школе и проверяет права."""

    school_ids = get_user_school_ids(user, db)

    if not school_ids:
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этой школе",
        )

    if len(school_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="Для работы с несколькими школами используйте новый маршрут с school_id",
        )

    school_id = next(iter(school_ids))

    school_class = db.scalar(
        select(Class).where(
            Class.school_id == school_id,
            Class.code == class_code,
        )
    )

    if school_class is None:
        raise HTTPException(
            status_code=404,
            detail="Класс не найден",
        )

    roles, class_ids = get_user_access(user, db)

    if allowed_roles is not None and not roles.intersection(allowed_roles):
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому разделу",
        )

    if school_class.id not in class_ids:
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этому классу",
        )

    return school_class


def require_school_class_access(
    school_id: int,
    class_code: str,
    user: User,
    db: Session,
    allowed_roles: set[str] | None = None,
) -> Class:
    """Находит класс внутри конкретной школы и проверяет права доступа."""

    # Проверяем, что пользователь имеет доступ к школе.
    require_school_access(school_id, user, db)

    # Ищем класс одновременно по школе и публичному коду.
    school_class = db.scalar(
        select(Class).where(
            Class.school_id == school_id,
            Class.code == class_code,
        )
    )

    if school_class is None:
        raise HTTPException(
            status_code=404,
            detail="Класс не найден",
        )

    roles, class_ids = get_user_access(user, db)

    if allowed_roles is not None and not roles.intersection(allowed_roles):
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому разделу",
        )

    if school_class.id not in class_ids:
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этому классу",
        )

    return school_class


# Разрешённые адреса Flutter-приложения.
# На хостинге API_BASE_URL задаётся через переменные окружения.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("API_BASE_URL", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. МОДЕЛИ ДАННЫХ
# ==========================================

class SchoolClass(BaseModel):
    id: str
    name: str

class ActiveAcademicYear(BaseModel):
    id: int
    name: str

class AccessibleSchool(BaseModel):
    id: int
    name: str
    active_academic_year: Optional[ActiveAcademicYear] = None

class LoadDay(BaseModel):
    day: int
    level: int  # 0 — перегруз, 4 — пусто
    is_editing: bool = False

class ClassStatus(BaseModel):
    level: Optional[int] = None
    date: Optional[str] = None
    has_data: bool = Field(alias="hasData")

class Recommendation(BaseModel):
    daysToReduce: List[int]
    daysToMoveTo: List[int]

class UserProfile(BaseModel):
    sferum_id: str
    roles: List[str]
    class_ids: List[str]
    schools: List[AccessibleSchool] = Field(default_factory=list)

class AuthResponse(UserProfile):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class AuthRequest(BaseModel):
    init_data: str

# Модели для работы с расписанием дня
class Lesson(BaseModel):
    id: str
    lesson_number: int
    subject_name: str
    teacher_name: str
    room: str
    lesson_type: str
    subgroup: int = 0
    updated_by: Optional[str] = None # ФИО того, кто менял

class LessonUpdateRequest(BaseModel):
    lesson_type: str = Field(min_length=1, max_length=150)

    @field_validator("lesson_type")
    @classmethod
    def validate_lesson_type(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Тип урока не может быть пустым")
        return value


def validate_max_init_data(init_data: str) -> dict:
    """Проверяет подпись и срок действия initData от MAX."""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(
            status_code=500,
            detail="Авторизация MAX не настроена",
        )

    if not init_data or len(init_data) > 20_000:
        raise HTTPException(
            status_code=401,
            detail="Некорректные данные авторизации",
        )

    # Поддерживаем строку initData и строку с WebAppData из URL-фрагмента.
    try:
        outer_params = parse_qsl(
            init_data,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Некорректные данные авторизации",
        )

    outer_keys = [key for key, _ in outer_params]
    if len(outer_keys) != len(set(outer_keys)):
        raise HTTPException(
            status_code=401,
            detail="Повторяющиеся параметры авторизации",
        )

    outer_data = dict(outer_params)
    if "WebAppData" in outer_data:
        init_data = outer_data["WebAppData"]

    try:
        params = parse_qsl(
            init_data,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Некорректные данные авторизации",
        )

    keys = [key for key, _ in params]
    if len(keys) != len(set(keys)):
        raise HTTPException(
            status_code=401,
            detail="Повторяющиеся параметры авторизации",
        )

    data = dict(params)
    received_hash = data.pop("hash", None)

    if not received_hash:
        raise HTTPException(
            status_code=401,
            detail="Отсутствует подпись MAX",
        )

    # Формируем строку подписи по алгоритму из документации MAX.
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(data.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(
            status_code=401,
            detail="Подпись MAX недействительна",
        )

    # Ограничиваем срок использования данных одним часом.
    try:
        auth_date = int(data["auth_date"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Некорректная дата авторизации",
        )

    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > 3600:
        raise HTTPException(
            status_code=401,
            detail="Данные авторизации устарели",
        )

    try:
        user_data = json.loads(data["user"])
        max_user_id = str(user_data["id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="В данных MAX отсутствует пользователь",
        )

    return {
        "sferum_id": max_user_id,
        "full_name": " ".join(
            part for part in (
                user_data.get("first_name"),
                user_data.get("last_name"),
            )
            if isinstance(part, str) and part.strip()
        ).strip(),
    }


# ==========================================
# 2. ЭНДПОИНТЫ (API)
# ==========================================

@app.get("/")
async def root():
    return {"message": "Blue Sphere API is running!"}


@app.post("/api/auth", response_model=AuthResponse)
async def auth_user(
    request: AuthRequest,
    db: Session = Depends(get_db),
):
    # Проверяем подлинность данных, полученных от MAX.
    verified_user = validate_max_init_data(request.init_data)
    sferum_id = verified_user["sferum_id"]

    # Вход через MAX не означает автоматическую регистрацию.
    user = db.scalar(
        select(User).where(User.sferum_id == sferum_id)
    )

    if user is None:
        raise HTTPException(
            status_code=403,
            detail="Пользователь не зарегистрирован в Blue Sphere",
        )

    # Получаем актуальные роли и числовые ID доступных классов.
    roles, allowed_class_ids = get_user_access(user, db)

    # Получаем школы, к которым у пользователя есть доступ.
    school_ids = set()

    teacher_school_ids = db.scalars(
        select(Teacher.school_id).where(
            Teacher.user_id == user.id
        )
    ).all()

    admin_school_ids = db.scalars(
        select(Administrator.school_id).where(
            Administrator.user_id == user.id
        )
    ).all()

    school_ids.update(teacher_school_ids)
    school_ids.update(admin_school_ids)

    # Для ученика определяем школу по его текущему классу.
    student = db.scalar(
        select(Student).where(Student.user_id == user.id)
    )

    if student is not None:
        student_school_id = db.scalar(
            select(Class.school_id).where(
                Class.id == student.class_id
            )
        )

        if student_school_id is not None:
            school_ids.add(student_school_id)

    # Получаем информацию о доступных школах.
    schools = []

    if school_ids:
        school_records = db.scalars(
            select(School)
            .where(School.id.in_(school_ids))
            .order_by(School.id)
        ).all()

        for school in school_records:
            active_year = db.scalar(
                select(AcademicYear).where(
                    AcademicYear.school_id == school.id,
                    AcademicYear.is_active.is_(True),
                )
            )

            schools.append(
                AccessibleSchool(
                    id=school.id,
                    name=school.full_name,
                    active_academic_year=(
                        ActiveAcademicYear(
                            id=active_year.id,
                            name=active_year.name,
                        )
                        if active_year is not None
                        else None
                    ),
                )
            )

    # Преобразуем числовые ID классов в публичные коды.
    # Старый frontend продолжает получать class_ids вида "5а".
    class_codes = db.scalars(
        select(Class.code)
        .where(Class.id.in_(allowed_class_ids))
        .order_by(Class.code)
    ).all() if allowed_class_ids else []

    access_token, expires_in = create_access_token(user)

    return AuthResponse(
        sferum_id=user.sferum_id,
        roles=sorted(roles),
        class_ids=class_codes,
        schools=schools,
        access_token=access_token,
        expires_in=expires_in,
    )


@app.get("/api/schools", response_model=List[AccessibleSchool])
def get_schools(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает школы, доступные авторизованному пользователю."""

    allowed_school_ids = get_user_school_ids(current_user, db)

    if not allowed_school_ids:
        return []

    schools = db.scalars(
        select(School)
        .where(School.id.in_(allowed_school_ids))
        .order_by(School.id)
    ).all()

    academic_years = db.scalars(
        select(AcademicYear).where(
            AcademicYear.school_id.in_(allowed_school_ids),
            AcademicYear.is_active.is_(True),
        )
    ).all()

    # Связываем активные учебные годы с соответствующими школами.
    active_years_by_school = {
        academic_year.school_id: academic_year
        for academic_year in academic_years
    }

    result = []

    for school in schools:
        active_year = active_years_by_school.get(school.id)

        result.append(
            AccessibleSchool(
                id=school.id,
                name=school.full_name,
                active_academic_year=(
                    ActiveAcademicYear(
                        id=active_year.id,
                        name=active_year.name,
                    )
                    if active_year is not None
                    else None
                ),
            )
        )

    return result


@app.get(
    "/api/schools/{school_id}/classes",
    response_model=Dict[str, List[SchoolClass]],
)
def get_school_classes(
    school_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает доступные пользователю классы выбранной школы."""

    # Сначала проверяем доступ к самой школе.
    require_school_access(school_id, current_user, db)

    # Получаем классы, доступные пользователю по его ролям.
    _, allowed_class_ids = get_user_access(current_user, db)

    if not allowed_class_ids:
        return {}

    # Оставляем только классы выбранной школы,
    # к которым у пользователя есть доступ.
    classes = db.scalars(
        select(Class)
        .where(
            Class.school_id == school_id,
            Class.id.in_(allowed_class_ids),
        )
        .order_by(Class.code)
    ).all()

    result: Dict[str, List[SchoolClass]] = {}

    for school_class in classes:
        # Номер параллели берём из публичного кода,
        # например из "5a" получаем "5".
        grade = "".join(
            character
            for character in school_class.code
            if character.isdigit()
        )

        if not grade:
            continue

        group_name = f"{grade} класс"

        result.setdefault(group_name, []).append(
            SchoolClass(
                id=school_class.code,
                name=school_class.name,
            )
        )

    return result


@app.get("/api/classes", response_model=Dict[str, List[SchoolClass]])
def get_classes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает классы, доступные авторизованному пользователю."""

    allowed_school_ids = get_user_school_ids(current_user, db)

    # Старый маршрут оставляем только для пользователей,
    # у которых есть доступ ровно к одной школе.
    if len(allowed_school_ids) != 1:
        raise HTTPException(
            status_code=400,
            detail="Для получения классов укажи школу",
        )

    school_id = next(iter(allowed_school_ids))

    _, allowed_class_ids = get_user_access(current_user, db)

    if not allowed_class_ids:
        return {}

    classes = db.scalars(
        select(Class)
        .where(
            Class.school_id == school_id,
            Class.id.in_(allowed_class_ids),
        )
        .order_by(Class.code)
    ).all()

    result: Dict[str, List[SchoolClass]] = {}

    for school_class in classes:
        grade = "".join(
            character
            for character in school_class.code
            if character.isdigit()
        )

        if not grade:
            continue

        group_name = f"{grade} класс"

        result.setdefault(group_name, []).append(
            SchoolClass(
                id=school_class.code,
                name=school_class.name,
            )
        )

    return result


def get_daily_lesson_counts(
    db: Session,
    class_id: int,
    start_date: PythonDate,
    end_date: PythonDate,
) -> Dict[PythonDate, int]:
    """Считает уроки по дням, не удваивая уроки разных подгрупп."""

    rows = db.execute(
        select(
            Schedule.date,
            func.count(func.distinct(Schedule.lesson_number)),
        )
        .join(
            TeachingAssignment,
            Schedule.assignment_id == TeachingAssignment.id,
        )
        .where(
            TeachingAssignment.class_id == class_id,
            Schedule.date >= start_date,
            Schedule.date <= end_date,
        )
        .group_by(Schedule.date)
    ).all()

    return {day: count for day, count in rows}


def get_load_level(lesson_count: int) -> int:
    """Переводит количество уроков в уровень нагрузки от 0 до 4."""

    if lesson_count >= 7:
        return 0
    if lesson_count == 6:
        return 1
    if lesson_count == 5:
        return 2
    if lesson_count == 4:
        return 3
    return 4


def build_class_heatmap(
    school_class: Class,
    month: str,
    current_user_id: int | None,
    db: Session,
) -> List[LoadDay]:
    """Формирует тепловую карту нагрузки класса за месяц."""

    try:
        month_number = int(month)
        if month_number < 1 or month_number > 12:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Месяц должен быть указан числом от 01 до 12",
        )

    year = PythonDate.today().year
    days_in_month = calendar.monthrange(year, month_number)[1]
    start_date = PythonDate(year, month_number, 1)
    end_date = PythonDate(year, month_number, days_in_month)

    counts = get_daily_lesson_counts(
        db, school_class.id, start_date, end_date
    )

    now = datetime.now(timezone.utc)

    editing_query = (
        select(Schedule.date, EditingSession.user_id)
        .join(
            TeachingAssignment,
            Schedule.assignment_id == TeachingAssignment.id,
        )
        .join(
            EditingSession,
            EditingSession.schedule_id == Schedule.id,
        )
        .where(
            TeachingAssignment.class_id == school_class.id,
            Schedule.date >= start_date,
            Schedule.date <= end_date,
            EditingSession.expires_at > now,
        )
    )

    if current_user_id is not None:
        editing_query = editing_query.where(
            EditingSession.user_id != current_user_id
        )

    editing_rows = db.execute(editing_query).all()
    editing_days = {row.date.day for row in editing_rows}

    return [
        LoadDay(
            day=day,
            level=get_load_level(
                counts.get(PythonDate(year, month_number, day), 0)
            ),
            is_editing=day in editing_days,
        )
        for day in range(1, days_in_month + 1)
    ]


@app.get("/api/classes/{class_id}/heatmap", response_model=List[LoadDay])
def get_heatmap(
    class_id: str,
    month: str = "09",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Старый маршрут получения тепловой карты."""

    school_class = require_class_access(
        class_code=class_id,
        user=current_user,
        db=db,
    )

    return build_class_heatmap(
        school_class=school_class,
        month=month,
        current_user_id=current_user.id,
        db=db,
    )


@app.get("/api/schools/{school_id}/classes/{class_code}/heatmap", response_model=List[LoadDay])
def get_school_heatmap(
    school_id: int,
    class_code: str,
    month: str = "09",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает тепловую карту класса выбранной школы."""

    school_class = require_school_class_access(
        school_id=school_id,
        class_code=class_code,
        user=current_user,
        db=db,
    )

    return build_class_heatmap(
        school_class=school_class,
        month=month,
        current_user_id=current_user.id,
        db=db,
    )


def build_class_summary(school_class: Class, db: Session) -> ClassStatus:
    """Формирует сводку по последнему реальному опросу класса."""

    survey_result = db.execute(
        select(
            Survey.date,
            func.avg(Survey.score),
        )
        .where(Survey.class_id == school_class.id)
        .group_by(Survey.date)
        .order_by(Survey.date.desc())
        .limit(1)
    ).first()

    if survey_result is None:
        return ClassStatus(
            level=None,
            date=None,
            hasData=False,
        )

    survey_date, average_score = survey_result

    return ClassStatus(
        level=round(float(average_score)),
        date=survey_date.strftime("%d.%m"),
        hasData=True,
    )


@app.get("/api/classes/{class_id}/summary", response_model=ClassStatus)
def get_summary(
    class_id: str,
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Старый маршрут получения сводки класса."""

    school_class = require_class_access(
        class_code=class_id,
        user=current_user,
        db=db,
        allowed_roles={"teacher", "admin"},
    )

    return build_class_summary(school_class, db)


@app.get("/api/schools/{school_id}/classes/{class_code}/summary", response_model=ClassStatus)
def get_school_summary(
    school_id: int,
    class_code: str,
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает сводку класса выбранной школы."""

    school_class = require_school_class_access(
        school_id=school_id,
        class_code=class_code,
        user=current_user,
        db=db,
        allowed_roles={"teacher", "admin"},
    )

    return build_class_summary(school_class, db)



def build_class_recommendations(
    school_class: Class,
    month: Optional[str],
    db: Session,
) -> Recommendation:
    """Рассчитывает рекомендации на основе реального расписания."""

    try:
        month_number = int(month) if month else PythonDate.today().month

        if month_number < 1 or month_number > 12:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Месяц должен быть указан числом от 01 до 12",
        )

    year = PythonDate.today().year
    days_in_month = calendar.monthrange(year, month_number)[1]
    start_date = PythonDate(year, month_number, 1)
    end_date = PythonDate(year, month_number, days_in_month)

    counts = get_daily_lesson_counts(
        db, school_class.id, start_date, end_date
    )

    # Рекомендации формируются только по дням,
    # для которых в расписании есть уроки.
    scheduled_days = {
        day.day: count
        for day, count in counts.items()
        if count > 0
    }

    if len(scheduled_days) < 2:
        return Recommendation(
            daysToReduce=[],
            daysToMoveTo=[],
        )

    # Дни с максимальной и минимальной нагрузкой.
    max_count = max(scheduled_days.values())
    min_count = min(scheduled_days.values())

    days_to_reduce = sorted(
        day for day, count in scheduled_days.items()
        if count == max_count
    )
    days_to_move_to = sorted(
        day for day, count in scheduled_days.items()
        if count == min_count
    )

    # Если нагрузка одинакова во все дни,
    # рекомендации не имеют смысла.
    if max_count == min_count:
        days_to_reduce = []
        days_to_move_to = []

    return Recommendation(
        daysToReduce=days_to_reduce,
        daysToMoveTo=days_to_move_to,
    )


@app.get("/api/classes/{class_id}/recommendations", response_model=Recommendation)
def get_recommendations(
    class_id: str,
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Старый маршрут получения рекомендаций."""

    school_class = require_class_access(
        class_code=class_id,
        user=current_user,
        db=db,
        allowed_roles={"teacher", "admin"},
    )

    return build_class_recommendations(
        school_class=school_class,
        month=month,
        db=db,
    )


@app.get("/api/schools/{school_id}/classes/{class_code}/recommendations", response_model=Recommendation)
def get_school_recommendations(
    school_id: int,
    class_code: str,
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает рекомендации для класса выбранной школы."""

    school_class = require_school_class_access(
        school_id=school_id,
        class_code=class_code,
        user=current_user,
        db=db,
        allowed_roles={"teacher", "admin"},
    )

    return build_class_recommendations(
        school_class=school_class,
        month=month,
        db=db,
    )


# ==========================================
# 3. РАСПИСАНИЕ И РЕДАКТИРОВАНИЕ УРОКОВ (НОВОЕ)
# ==========================================


def format_teacher_name(full_name: str) -> str:
    """Преобразует полное ФИО в формат Фамилия И.О."""
    parts = full_name.split()

    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."

    return full_name


def build_class_schedule(
    school_class: Class,
    date: str,
    db: Session,
) -> List[Lesson]:
    """Формирует расписание класса на указанную дату."""

    try:
        requested_date = PythonDate.fromisoformat(date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Неверный формат даты. Используй YYYY-MM-DD.",
        )

    Editor = aliased(User)

    rows = db.execute(
        select(
            Schedule,
            TeachingAssignment.subgroup,
            Subject.name,
            User.full_name,
            Editor.full_name,
        )
        .join(
            TeachingAssignment,
            Schedule.assignment_id == TeachingAssignment.id,
        )
        .join(
            Subject,
            TeachingAssignment.subject_id == Subject.id,
        )
        .join(
            Teacher,
            TeachingAssignment.teacher_id == Teacher.id,
        )
        .join(
            User,
            Teacher.user_id == User.id,
        )
        .outerjoin(
            Editor,
            Schedule.updated_by_user_id == Editor.id,
        )
        .where(
            TeachingAssignment.class_id == school_class.id,
            Schedule.date == requested_date,
        )
        .order_by(
            Schedule.lesson_number,
            TeachingAssignment.subgroup,
        )
    ).all()

    return [
        Lesson(
            id=str(schedule.id),
            lesson_number=schedule.lesson_number,
            subject_name=subject_name,
            teacher_name=format_teacher_name(teacher_full_name),
            room=schedule.room,
            lesson_type=schedule.lesson_type,
            subgroup=subgroup,
            updated_by=(
                format_teacher_name(editor_full_name)
                if editor_full_name
                else None
            ),
        )
        for (
            schedule,
            subgroup,
            subject_name,
            teacher_full_name,
            editor_full_name,
        ) in rows
    ]


@app.get("/api/classes/{class_id}/schedule", response_model=List[Lesson])
def get_schedule(
    class_id: str,
    date: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Старый маршрут получения расписания."""

    school_class = require_class_access(
        class_code=class_id,
        user=current_user,
        db=db,
    )

    return build_class_schedule(school_class, date, db)


@app.get("/api/schools/{school_id}/classes/{class_code}/schedule", response_model=List[Lesson])
def get_school_schedule(
    school_id: int,
    class_code: str,
    date: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает расписание класса выбранной школы."""

    school_class = require_school_class_access(
        school_id=school_id,
        class_code=class_code,
        user=current_user,
        db=db,
    )

    return build_class_schedule(school_class, date, db)


@app.put("/api/schedule/{lesson_id}", response_model=Lesson)
def update_lesson(
    lesson_id: str,
    request: LessonUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Изменяет тип урока и сохраняет пользователя, который внёс изменение."""
    try:
        numeric_lesson_id = int(lesson_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="ID урока должен быть числом.",
        )

    lesson = db.get(Schedule, numeric_lesson_id)

    if lesson is None:
        raise HTTPException(
            status_code=404,
            detail="Урок не найден.",
        )

    editor = current_user

    if not can_edit_lesson(lesson, editor, db):
        raise HTTPException(
            status_code=403,
            detail="У вас нет прав на редактирование этого урока.",
        )

    now = datetime.now(timezone.utc)

    editing_session = db.scalar(
        select(EditingSession)
        .where(EditingSession.schedule_id == lesson.id)
        .with_for_update()
    )

    if (
        editing_session is None
        or editing_session.user_id != editor.id
        or editing_session.expires_at <= now
    ):
        raise HTTPException(
            status_code=409,
            detail="Нет активной сессии редактирования этого урока.",
        )
    
    lesson.lesson_type = request.lesson_type
    lesson.updated_by_user_id = editor.id

    # Продлеваем сессию после успешного изменения урока.
    editing_session.expires_at = now + timedelta(
        seconds=EDITING_SESSION_TTL_SECONDS
    )

    db.commit()
    db.refresh(lesson)

    return get_lesson_response(db, lesson.id)


EDITING_SESSION_TTL_SECONDS = 60


def can_edit_lesson(
    lesson: Schedule,
    user: User,
    db: Session,
) -> bool:
    """Проверяет право учителя или администратора редактировать урок."""

    # Проверяем, является ли пользователь учителем этого урока.
    assignment = db.scalar(
        select(TeachingAssignment)
        .join(
            Teacher,
            TeachingAssignment.teacher_id == Teacher.id,
        )
        .join(
            Class,
            TeachingAssignment.class_id == Class.id,
        )
        .where(
            TeachingAssignment.id == lesson.assignment_id,
            Teacher.user_id == user.id,
            Teacher.school_id == Class.school_id,
            TeachingAssignment.academic_year_id == Class.academic_year_id,
        )
    )

    if assignment is not None:
        return True

    # Получаем класс, к которому относится урок.
    class_id = db.scalar(
        select(TeachingAssignment.class_id).where(
            TeachingAssignment.id == lesson.assignment_id
        )
    )

    if class_id is None:
        return False

    school_id = db.scalar(
        select(Class.school_id).where(Class.id == class_id)
    )

    if school_id is None:
        return False

    # Проверяем, является ли пользователь администратором этой школы.
    administrator = db.scalar(
        select(Administrator.id).where(
            Administrator.user_id == user.id,
            Administrator.school_id == school_id,
        )
    )

    return administrator is not None


def get_editing_user_and_lesson(
    lesson_id: str,
    user: User,
    db: Session,
):
    """Находит урок и проверяет, что пользователь ведёт этот урок."""

    try:
        numeric_lesson_id = int(lesson_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="ID урока должен быть числом.",
        )

    lesson = db.get(Schedule, numeric_lesson_id)
    if lesson is None:
        raise HTTPException(
            status_code=404,
            detail="Урок не найден.",
        )

    if not can_edit_lesson(lesson, user, db):
        raise HTTPException(
            status_code=403,
            detail="У вас нет прав на редактирование этого урока.",
        )

    return lesson, user


@app.post("/api/schedule/{lesson_id}/editing")
def start_editing(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Начинает или возобновляет собственную сессию редактирования."""

    lesson, user = get_editing_user_and_lesson(
        lesson_id, current_user, db
    )

    now = datetime.now(timezone.utc)

    session = db.scalar(
        select(EditingSession)
        .where(EditingSession.schedule_id == lesson.id)
        .with_for_update()
    )

    if session is not None and session.expires_at > now:
        if session.user_id != user.id:
            raise HTTPException(
                status_code=409,
                detail="Этот урок уже редактирует другой пользователь.",
            )

        session.expires_at = now + timedelta(
            seconds=EDITING_SESSION_TTL_SECONDS
        )
        db.commit()
        return {"success": True, "expires_in": EDITING_SESSION_TTL_SECONDS}

    if session is not None:
        db.delete(session)
        db.flush()

    session = EditingSession(
        schedule_id=lesson.id,
        user_id=user.id,
        expires_at=now + timedelta(
            seconds=EDITING_SESSION_TTL_SECONDS
        ),
    )
    db.add(session)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Этот урок уже редактирует другой пользователь.",
        )

    return {"success": True, "expires_in": EDITING_SESSION_TTL_SECONDS}


@app.put("/api/schedule/{lesson_id}/editing")
def renew_editing(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Продлевает только собственную активную сессию."""

    lesson, user = get_editing_user_and_lesson(
        lesson_id, current_user, db
    )

    now = datetime.now(timezone.utc)

    session = db.scalar(
        select(EditingSession)
        .where(EditingSession.schedule_id == lesson.id)
        .with_for_update()
    )

    if (
        session is None
        or session.user_id != user.id
        or session.expires_at <= now
    ):
        raise HTTPException(
            status_code=409,
            detail="Активная сессия редактирования не найдена.",
        )

    session.expires_at = now + timedelta(
        seconds=EDITING_SESSION_TTL_SECONDS
    )
    db.commit()

    return {"success": True, "expires_in": EDITING_SESSION_TTL_SECONDS}


@app.delete("/api/schedule/{lesson_id}/editing")
def stop_editing(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Завершает только собственную сессию редактирования."""

    lesson, user = get_editing_user_and_lesson(
        lesson_id, current_user, db
    )

    session = db.scalar(
        select(EditingSession)
        .where(EditingSession.schedule_id == lesson.id)
        .with_for_update()
    )

    if session is not None and session.user_id == user.id:
        db.delete(session)
        db.commit()

    return {"success": True}


def get_lesson_response(db: Session, lesson_id: int) -> Lesson:
    """Формирует ответ API для одного урока из связанных записей БД."""
    Editor = aliased(User)

    row = db.execute(
        select(Schedule, Subject.name, User.full_name, Editor.full_name)
        .join(
            TeachingAssignment,
            Schedule.assignment_id == TeachingAssignment.id,
        )
        .join(
            Subject,
            TeachingAssignment.subject_id == Subject.id,
        )
        .join(
            Teacher,
            TeachingAssignment.teacher_id == Teacher.id,
        )
        .join(
            User,
            Teacher.user_id == User.id,
        )
        .outerjoin(
            Editor,
            Schedule.updated_by_user_id == Editor.id,
        )
        .where(Schedule.id == lesson_id)
    ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Урок не найден.")

    schedule, subject_name, teacher_full_name, editor_full_name = row

    return Lesson(
        id=str(schedule.id),
        lesson_number=schedule.lesson_number,
        subject_name=subject_name,
        teacher_name=format_teacher_name(teacher_full_name),
        room=schedule.room,
        lesson_type=schedule.lesson_type,
        updated_by=(
            format_teacher_name(editor_full_name)
            if editor_full_name
            else None
        ),
    )
