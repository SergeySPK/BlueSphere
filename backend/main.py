from datetime import date as PythonDate, datetime, timedelta, timezone
import calendar

from fastapi import FastAPI, Depends, HTTPException, Response, status, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import (
    AcademicYear,
    Administrator,
    AuthTicket,
    Class,
    EditingSession,
    Recommendation,
    Schedule,
    Student,
    Subject,
    Survey,
    Teacher,
    TeachingAssignment,
    User,
)

from pydantic import BaseModel, Field
from typing import List, Dict, Optional

import hashlib
import jwt
import secrets
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

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


# Разрешённые адреса Flutter-приложения.
# На хостинге API_BASE_URL задаётся через переменные окружения.
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "API_BASE_URL",
    ).split(",")
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


class AuthResponse(UserProfile):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthRequest(BaseModel):
    init_data: str


class AuthTicketCreateRequest(BaseModel):
    max_user_id: str = Field(min_length=1, max_length=100)


class AuthTicketCreateResponse(BaseModel):
    ticket: str
    expires_in: int


class AuthTicketExchangeRequest(BaseModel):
    ticket: str = Field(min_length=1, max_length=200)


class AuthTicketExchangeResponse(AuthResponse):
    pass


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
    lesson_type: str


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



def build_auth_response(user: User, db: Session) -> AuthResponse:
    """Формирует профиль пользователя и выдаёт JWT."""

    roles = []
    class_ids = set()

    # Учитель: определяем роль и классы по назначениям.
    teacher = db.scalar(
        select(Teacher).where(Teacher.user_id == user.id)
    )

    if teacher is not None:
        roles.append("teacher")

        teacher_class_ids = db.scalars(
            select(TeachingAssignment.class_id)
            .where(TeachingAssignment.teacher_id == teacher.id)
        ).all()

        class_ids.update(teacher_class_ids)

    # Администратор: определяем роль и доступные ему классы.
    admin_school_ids = db.scalars(
        select(Administrator.school_id)
        .where(Administrator.user_id == user.id)
    ).all()

    if admin_school_ids:
        roles.append("admin")

        admin_class_ids = db.scalars(
            select(Class.id)
            .where(Class.school_id.in_(admin_school_ids))
        ).all()

        class_ids.update(admin_class_ids)

    # Ученик: доступ к своему классу.
    student = db.scalar(
        select(Student).where(Student.user_id == user.id)
    )

    if student is not None:
        roles.append("student")
        class_ids.add(student.class_id)

    access_token, expires_in = create_access_token(user)

    return AuthResponse(
        sferum_id=user.sferum_id,
        roles=roles,
        class_ids=sorted(class_ids),
        access_token=access_token,
        expires_in=expires_in,
    )



@app.post("/api/auth", response_model=AuthResponse)
async def auth_user(
    request: AuthRequest,
    db: Session = Depends(get_db),
):
    verified_user = validate_max_init_data(request.init_data)
    sferum_id = verified_user["sferum_id"]

    user = db.scalar(
        select(User).where(User.sferum_id == sferum_id)
    )

    if user is None:
        raise HTTPException(
            status_code=403,
            detail="Пользователь не зарегистрирован в Blue Sphere",
        )

    return build_auth_response(user, db)



AUTH_TICKET_EXPIRE_SECONDS = 60


@app.post(
    "/api/auth/ticket",
    response_model=AuthTicketCreateResponse,
)
def create_auth_ticket(
    request: AuthTicketCreateRequest,
    x_bot_secret: Optional[str] = Header(
        default=None,
        alias="X-Bot-Secret",
    ),
    db: Session = Depends(get_db),
):
    """Создаёт одноразовый билет для доверенного бота."""

    expected_secret = os.getenv("BOT_INTERNAL_SECRET")

    if (
        not expected_secret
        or not x_bot_secret
        or not hmac.compare_digest(x_bot_secret, expected_secret)
    ):
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав",
        )

    user = db.scalar(
        select(User).where(User.sferum_id == request.max_user_id)
    )

    if user is None:
        raise HTTPException(
            status_code=403,
            detail="Пользователь не зарегистрирован в Blue Sphere",
        )

    raw_ticket = secrets.token_urlsafe(32)
    ticket_hash = hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)

    ticket_record = AuthTicket(
        ticket_hash=ticket_hash,
        user_id=user.id,
        expires_at=now + timedelta(seconds=AUTH_TICKET_EXPIRE_SECONDS),
    )

    try:
        db.add(ticket_record)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Не удалось создать билет авторизации",
        )

    return AuthTicketCreateResponse(
        ticket=raw_ticket,
        expires_in=AUTH_TICKET_EXPIRE_SECONDS,
    )


@app.post(
    "/api/auth/ticket/exchange",
    response_model=AuthTicketExchangeResponse,
)
def exchange_auth_ticket(
    request: AuthTicketExchangeRequest,
    db: Session = Depends(get_db),
):
    """Однократно обменивает билет на JWT."""

    ticket_hash = hashlib.sha256(
        request.ticket.encode("utf-8")
    ).hexdigest()

    now = datetime.now(timezone.utc)

    # Одно атомарное обновление не позволяет погасить билет дважды.
    result = db.execute(
        update(AuthTicket)
        .where(
            AuthTicket.ticket_hash == ticket_hash,
            AuthTicket.used_at.is_(None),
            AuthTicket.expires_at > now,
        )
        .values(used_at=now)
        .returning(AuthTicket.user_id)
    )

    user_id = result.scalar_one_or_none()

    if user_id is None:
        db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Билет недействителен, истёк или уже использован",
        )

    user = db.get(User, user_id)

    if user is None:
        db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Пользователь не найден",
        )

    # Сначала фиксируем погашение билета в БД.
    db.commit()

    return build_auth_response(user, db)



@app.get("/api/classes", response_model=Dict[str, List[SchoolClass]])
def get_classes(db: Session = Depends(get_db)):
    """
    Возвращает список классов из PostgreSQL,
    сгруппированных по параллелям.
    """
    classes = db.scalars(
        select(Class).order_by(Class.id)
    ).all()

    result: Dict[str, List[SchoolClass]] = {}

    for school_class in classes:
        # ID "5a" соответствует параллели "5 класс".
        grade = "".join(
            character
            for character in school_class.id
            if character.isdigit()
        )

        if not grade:
            continue

        group_name = f"{grade} класс"

        result.setdefault(group_name, []).append(
            SchoolClass(
                id=school_class.id,
                name=school_class.name,
            )
        )

    return result


def get_daily_lesson_counts(
    db: Session,
    class_id: str,
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


@app.get("/api/classes/{class_id}/heatmap", response_model=List[LoadDay])
def get_heatmap(
    class_id: str,
    month: str = "09",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает нагрузку и активное редактирование по дням месяца."""

    if not db.get(Class, class_id):
        raise HTTPException(status_code=404, detail="Класс не найден")

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
        db, class_id, start_date, end_date
    )

    current_user_id = None
    current_user_id = current_user.id

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
            TeachingAssignment.class_id == class_id,
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


@app.get("/api/classes/{class_id}/summary", response_model=ClassStatus)
def get_summary(
    class_id: str,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Возвращает результат последнего реального опроса класса."""

    if not db.get(Class, class_id):
        raise HTTPException(status_code=404, detail="Класс не найден")

    survey_result = db.execute(
        select(
            Survey.date,
            func.avg(Survey.score),
        )
        .where(Survey.class_id == class_id)
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


@app.get(
    "/api/classes/{class_id}/recommendations",
    response_model=Recommendation,
)
def get_recommendations(
    class_id: str,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Рассчитывает рекомендации на основе реального расписания."""

    if not db.get(Class, class_id):
        raise HTTPException(status_code=404, detail="Класс не найден")

    month_number = int(month) if month else PythonDate.today().month

    if month_number < 1 or month_number > 12:
        raise HTTPException(
            status_code=400,
            detail="Месяц должен быть указан числом от 01 до 12",
        )

    year = PythonDate.today().year
    days_in_month = calendar.monthrange(year, month_number)[1]
    start_date = PythonDate(year, month_number, 1)
    end_date = PythonDate(year, month_number, days_in_month)

    counts = get_daily_lesson_counts(
        db, class_id, start_date, end_date
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


# ==========================================
# 3. РАСПИСАНИЕ И РЕДАКТИРОВАНИЕ УРОКОВ (НОВОЕ)
# ==========================================


def format_teacher_name(full_name: str) -> str:
    """Преобразует полное ФИО в формат Фамилия И.О."""
    parts = full_name.split()

    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."

    return full_name


@app.get("/api/classes/{class_id}/schedule", response_model=List[Lesson])
def get_schedule(
    class_id: str,
    date: str,
    db: Session = Depends(get_db),
):
    """Возвращает расписание класса на указанную дату из PostgreSQL."""
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
            TeachingAssignment.class_id == class_id,
            Schedule.date == requested_date,
        )
        .order_by(Schedule.lesson_number, TeachingAssignment.subgroup)
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

    assignment = db.scalar(
        select(TeachingAssignment)
        .join(
            Teacher,
            TeachingAssignment.teacher_id == Teacher.id,
        )
        .where(
            TeachingAssignment.id == lesson.assignment_id,
            Teacher.user_id == editor.id,
        )
    )

    if assignment is None:
        raise HTTPException(
            status_code=403,
            detail="Вы можете редактировать только свои уроки.",
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

    assignment = db.scalar(
        select(TeachingAssignment)
        .join(
            Teacher,
            TeachingAssignment.teacher_id == Teacher.id,
        )
        .where(
            TeachingAssignment.id == lesson.assignment_id,
            Teacher.user_id == user.id,
        )
    )

    if assignment is None:
        raise HTTPException(
            status_code=403,
            detail="Вы можете редактировать только свои уроки.",
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
