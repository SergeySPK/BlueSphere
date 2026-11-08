from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv
from datetime import date as PythonDate, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import calendar

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from survey_service import get_effective_survey_status
from workload import get_daily_lesson_counts, get_load_level
from models import (
    AcademicYear,
    Administrator,
    AIAnalysisJob,
    AIAnalysisRun,
    AIDailyForecast,
    AIDailyLoad,
    AIRecommendation,
    Class,
    EditingSession,
    Recommendation,
    Schedule,
    School,
    Student,
    StudentEnrollment,
    Subject,
    SurveyInstance,
    SurveyInstanceQuestion,
    SurveyInstanceOption,
    SurveyResponse,
    SurveyResponseOption,
    Teacher,
    TeacherClassAccess,
    TeachingAssignment,
    User,
)

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Literal, Optional

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


def is_demo_mode() -> bool:
    value = os.getenv("DEMO_MODE", "false").strip().lower()

    if value not in {"true", "false"}:
        raise RuntimeError("DEMO_MODE должен иметь значение true или false")

    return value == "true"


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


def build_auth_response(user: User, db: Session) -> AuthResponse:
    roles, allowed_class_ids = get_user_access(user, db)

    # Получаем школы, к которым у пользователя есть доступ.
    school_ids = set()

    teacher_school_ids = db.scalars(
        select(Teacher.school_id).where(Teacher.user_id == user.id)
    ).all()

    admin_school_ids = db.scalars(
        select(Administrator.school_id).where(Administrator.user_id == user.id)
    ).all()

    school_ids.update(teacher_school_ids)
    school_ids.update(admin_school_ids)

    student = db.scalar(select(Student).where(Student.user_id == user.id))

    if student is not None:
        student_school_id = db.scalar(
            select(Class.school_id).where(Class.id == student.class_id)
        )

        if student_school_id is not None:
            school_ids.add(student_school_id)

    schools = []

    if school_ids:
        school_records = db.scalars(
            select(School).where(School.id.in_(school_ids)).order_by(School.id)
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

    class_codes = (
        db.scalars(
            select(Class.code)
            .where(Class.id.in_(allowed_class_ids))
            .order_by(Class.code)
        ).all()
        if allowed_class_ids
        else []
    )

    access_token, expires_in = create_access_token(user)

    return AuthResponse(
        sferum_id=user.sferum_id,
        roles=sorted(roles),
        class_ids=class_codes,
        schools=schools,
        access_token=access_token,
        expires_in=expires_in,
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
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
    """Возвращает актуальные роли и доступные классы активных учебных лет."""

    roles: set[str] = set()
    class_ids: set[int] = set()

    teachers = db.scalars(
        select(Teacher).where(Teacher.user_id == user.id)
    ).all()

    if teachers:
        roles.add("teacher")
        teacher_ids = [teacher.id for teacher in teachers]

        # Классы, в которых у учителя есть предметные назначения
        # в активном учебном году.
        assignment_class_ids = db.scalars(
            select(TeachingAssignment.class_id)
            .join(
                Class,
                and_(
                    Class.id == TeachingAssignment.class_id,
                    Class.school_id == TeachingAssignment.school_id,
                    Class.academic_year_id
                    == TeachingAssignment.academic_year_id,
                ),
            )
            .join(
                AcademicYear,
                and_(
                    AcademicYear.id == Class.academic_year_id,
                    AcademicYear.school_id == Class.school_id,
                ),
            )
            .where(
                TeachingAssignment.teacher_id.in_(teacher_ids),
                AcademicYear.is_active.is_(True),
            )
            .distinct()
        ).all()

        class_ids.update(assignment_class_ids)

        # Классы, доступ к которым выдан отдельно,
        # без предметных назначений.
        access_class_ids = db.scalars(
            select(TeacherClassAccess.class_id)
            .join(
                Class,
                and_(
                    Class.id == TeacherClassAccess.class_id,
                    Class.school_id == TeacherClassAccess.school_id,
                    Class.academic_year_id
                    == TeacherClassAccess.academic_year_id,
                ),
            )
            .join(
                AcademicYear,
                and_(
                    AcademicYear.id == Class.academic_year_id,
                    AcademicYear.school_id == Class.school_id,
                ),
            )
            .where(
                TeacherClassAccess.teacher_id.in_(teacher_ids),
                AcademicYear.is_active.is_(True),
            )
            .distinct()
        ).all()

        class_ids.update(access_class_ids)

    # Администратор имеет доступ ко всем классам активного
    # учебного года своих школ.
    admin_school_ids = db.scalars(
        select(Administrator.school_id).where(
            Administrator.user_id == user.id
        )
    ).all()

    if admin_school_ids:
        roles.add("admin")

        admin_class_ids = db.scalars(
            select(Class.id)
            .join(
                AcademicYear,
                and_(
                    AcademicYear.id == Class.academic_year_id,
                    AcademicYear.school_id == Class.school_id,
                ),
            )
            .where(
                Class.school_id.in_(admin_school_ids),
                AcademicYear.is_active.is_(True),
            )
        ).all()

        class_ids.update(admin_class_ids)

    # Ученик получает доступ к собственному классу,
    # если тот относится к активному учебному году.
    student = db.scalar(
        select(Student).where(Student.user_id == user.id)
    )

    if student is not None:
        roles.add("student")

        active_student_class_id = db.scalar(
            select(Class.id)
            .join(
                AcademicYear,
                and_(
                    AcademicYear.id == Class.academic_year_id,
                    AcademicYear.school_id == Class.school_id,
                ),
            )
            .where(
                Class.id == student.class_id,
                AcademicYear.is_active.is_(True),
            )
        )

        if active_student_class_id is not None:
            class_ids.add(active_student_class_id)

    return roles, class_ids


def get_user_school_ids(
    user: User,
    db: Session,
) -> set[int]:
    """Возвращает ID школ, к которым у пользователя есть доступ."""

    school_ids: set[int] = set()

    # Учитель имеет доступ к школе, в которой он зарегистрирован.
    teacher_school_ids = db.scalars(
        select(Teacher.school_id).where(Teacher.user_id == user.id)
    ).all()

    school_ids.update(teacher_school_ids)

    # Администратор имеет доступ к своим школам.
    admin_school_ids = db.scalars(
        select(Administrator.school_id).where(Administrator.user_id == user.id)
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

    school = db.scalar(select(School).where(School.id == school_id))

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


def get_active_school_class(
    db: Session,
    school_id: int,
    class_code: str,
) -> Class | None:
    """Находит класс по коду только в активном учебном году школы."""

    return db.scalar(
        select(Class)
        .join(
            AcademicYear,
            and_(
                AcademicYear.id == Class.academic_year_id,
                AcademicYear.school_id == Class.school_id,
            ),
        )
        .where(
            Class.school_id == school_id,
            Class.code == class_code,
            AcademicYear.is_active.is_(True),
        )
    )


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

    school_class = get_active_school_class(
        db=db,
        school_id=school_id,
        class_code=class_code,
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
    school_class = get_active_school_class(
        db=db,
        school_id=school_id,
        class_code=class_code,
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


def can_access_survey_class(
    user: User,
    school_class: Class,
    survey_date: PythonDate,
    db: Session,
) -> bool:
    """Проверяет доступ пользователя к классу на дату опроса."""

    # Администратор имеет доступ ко всем классам своей школы.
    is_admin = db.scalar(
        select(Administrator.id)
        .where(
            Administrator.user_id == user.id,
            Administrator.school_id == school_class.school_id,
        )
        .limit(1)
    )

    if is_admin is not None:
        return True

    # Учитель может получить доступ через отдельную запись
    # TeacherClassAccess.
    is_teacher_access = db.scalar(
        select(TeacherClassAccess.id)
        .join(
            Teacher,
            Teacher.id == TeacherClassAccess.teacher_id,
        )
        .join(
            AcademicYear,
            and_(
                AcademicYear.id == TeacherClassAccess.academic_year_id,
                AcademicYear.school_id == TeacherClassAccess.school_id,
            ),
        )
        .where(
            Teacher.user_id == user.id,
            TeacherClassAccess.class_id == school_class.id,
            TeacherClassAccess.school_id == school_class.school_id,
            TeacherClassAccess.academic_year_id == school_class.academic_year_id,
            AcademicYear.is_active.is_(True),
        )
        .limit(1)
    )

    if is_teacher_access is not None:
        return True

    # Либо через предметное назначение в активном учебном году.
    is_teacher_assignment = db.scalar(
        select(TeachingAssignment.id)
        .join(
            Teacher,
            Teacher.id == TeachingAssignment.teacher_id,
        )
        .join(
            AcademicYear,
            and_(
                AcademicYear.id
                == TeachingAssignment.academic_year_id,
                AcademicYear.school_id
                == TeachingAssignment.school_id,
            ),
        )
        .where(
            Teacher.user_id == user.id,
            TeachingAssignment.class_id == school_class.id,
            TeachingAssignment.school_id == school_class.school_id,
            TeachingAssignment.academic_year_id
            == school_class.academic_year_id,
            AcademicYear.is_active.is_(True),
        )
        .limit(1)
    )

    if is_teacher_assignment is not None:
        return True

    # У ученика должно быть ровно одно действующее зачисление
    # на дату опроса, и оно должно относиться к выбранному классу.
    student_id = db.scalar(select(Student.id).where(Student.user_id == user.id))

    if student_id is None:
        return False

    enrollment_count = db.scalar(
        select(func.count(StudentEnrollment.id)).where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.start_date <= survey_date,
            (
                StudentEnrollment.end_date.is_(None)
                | (StudentEnrollment.end_date >= survey_date)
            ),
        )
    )

    if enrollment_count != 1:
        return False

    enrollment = db.scalar(
        select(StudentEnrollment.class_id).where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.start_date <= survey_date,
            (
                StudentEnrollment.end_date.is_(None)
                | (StudentEnrollment.end_date >= survey_date)
            ),
        )
    )

    return enrollment == school_class.id


# Разрешённые адреса Flutter-приложения.
# На хостинге FRONTEND_URL задаётся через переменные окружения.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_URL", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
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
    level: Optional[int] = Field(default=None, ge=0, le=4)
    is_editing: bool = False


class ClassStatus(BaseModel):
    level: Optional[int] = None
    date: Optional[str] = None
    has_data: bool = Field(alias="hasData")


class RecommendationPeriod(BaseModel):
    start: PythonDate
    end: PythonDate


class RecommendationDailyLoad(BaseModel):
    date: PythonDate
    day: int
    level: int = Field(ge=0, le=4)
    source: Literal["ai", "python"]


class RecommendationDetail(BaseModel):
    date: PythonDate
    kind: Literal["class", "teacher", "lesson"]
    priority: Literal["low", "normal", "high", "critical"]
    title: str
    recommendationText: str
    rationale: Optional[str] = None
    teacherId: Optional[int] = None
    scheduleId: Optional[int] = None


class Recommendation(BaseModel):
    # Старые поля. Сохраняем для совместимости с текущим Flutter.
    daysToReduce: List[int]
    daysToMoveTo: List[int]

    # Состояние AI-анализа.
    analysisStatus: Literal[
        "not_started",
        "queued",
        "running",
        "succeeded",
        "failed",
    ] = "not_started"

    # True, если возвращаются предыдущие результаты,
    # пока новый анализ выполняется или завершился ошибкой.
    isStale: bool = False

    # Период последнего AI-анализа. Пока анализа нет — null.
    period: Optional[RecommendationPeriod] = None

    # Заполняются после появления сохранённых AI-результатов.
    dailyLoads: List[RecommendationDailyLoad] = Field(default_factory=list)
    recommendations: List[RecommendationDetail] = Field(
        default_factory=list
    )

    # Источник старых списков дней.
    # Сейчас это расписание, а не AI.
    dataSource: Literal["schedule", "ai"] = "schedule"


class UserProfile(BaseModel):
    sferum_id: str
    roles: List[str]
    class_ids: List[str]
    schools: List[AccessibleSchool] = Field(default_factory=list)


class AuthResponse(UserProfile):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DemoAuthRequest(BaseModel):
    sferum_id: str = Field(min_length=1, max_length=100)

    @field_validator("sferum_id")
    @classmethod
    def validate_sferum_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sferum_id не может быть пустым")
        return value


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
    updated_by: Optional[str] = None  # ФИО того, кто менял
    is_editable: bool = False
    is_editing: bool = False
    editor_name: Optional[str] = None


class LessonUpdateRequest(BaseModel):
    lesson_type: str = Field(min_length=1, max_length=150)

    @field_validator("lesson_type")
    @classmethod
    def validate_lesson_type(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Тип урока не может быть пустым")
        return value


class SurveyClass(BaseModel):
    code: str
    name: str


class SurveyDateItem(BaseModel):
    survey_date: PythonDate
    status: str


class SurveyOptionStatistic(BaseModel):
    title: str
    responses_count: int
    percentage: float


class SurveyQuestionStatistic(BaseModel):
    title: str
    answer_type: str
    respondents_count: int
    options: List[SurveyOptionStatistic]


class SurveyStatistics(BaseModel):
    class_code: str
    class_name: str
    survey_date: PythonDate
    status: str
    questions: List[SurveyQuestionStatistic]


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
            part
            for part in (
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
    user = db.scalar(select(User).where(User.sferum_id == sferum_id))

    if user is None:
        raise HTTPException(
            status_code=403,
            detail="Пользователь не зарегистрирован в Blue Sphere",
        )

    return build_auth_response(user, db)


@app.post("/api/demo_auth", response_model=AuthResponse)
async def demo_auth_user(
    request: DemoAuthRequest,
    db: Session = Depends(get_db),
):
    # Демонстрационная авторизация доступна только в DEMO_MODE.
    if not is_demo_mode():
        raise HTTPException(
            status_code=404,
            detail="Endpoint not found",
        )

    user = db.scalar(select(User).where(User.sferum_id == request.sferum_id))

    if user is None or not user.is_demo:
        raise HTTPException(
            status_code=403,
            detail="Демонстрационный пользователь не найден",
        )

    return build_auth_response(user, db)


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
        select(School).where(School.id.in_(allowed_school_ids)).order_by(School.id)
    ).all()

    academic_years = db.scalars(
        select(AcademicYear).where(
            AcademicYear.school_id.in_(allowed_school_ids),
            AcademicYear.is_active.is_(True),
        )
    ).all()

    # Связываем активные учебные годы с соответствующими школами.
    active_years_by_school = {
        academic_year.school_id: academic_year for academic_year in academic_years
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
        .join(
            AcademicYear,
            and_(
                AcademicYear.id == Class.academic_year_id,
                AcademicYear.school_id == Class.school_id,
            ),
        )
        .where(
            Class.school_id == school_id,
            Class.id.in_(allowed_class_ids),
            AcademicYear.is_active.is_(True),
        )
        .order_by(Class.code)
    ).all()

    result: Dict[str, List[SchoolClass]] = {}

    for school_class in classes:
        # Номер параллели берём из публичного кода,
        # например из "5a" получаем "5".
        grade = "".join(
            character for character in school_class.code if character.isdigit()
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


def get_school_local_today(
    db: Session,
    school_id: int,
) -> PythonDate:
    """Возвращает текущую дату в часовом поясе школы."""

    timezone_name = db.scalar(
        select(School.timezone).where(
            School.id == school_id,
        )
    )

    if not timezone_name:
        raise HTTPException(
            status_code=500,
            detail="Для школы не настроен часовой пояс",
        )

    try:
        school_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            status_code=500,
            detail="У школы указан некорректный часовой пояс",
        )

    return datetime.now(timezone.utc).astimezone(school_timezone).date()


def get_effective_daily_loads(
    school_class: Class,
    start_date: PythonDate,
    end_date: PythonDate,
    db: Session,
) -> Dict[PythonDate, tuple[int | None, str | None]]:
    """
    Возвращает эффективный уровень нагрузки по каждой дате.

    Приоритет:
    1. Сохранённый прогноз (AI или Python).
    2. Python-расчёт по расписанию, если прогноза нет.
    3. None, если уроков нет.

    source:
    - ai;
    - python;
    - None, если день без уроков.
    """

    lesson_counts = get_daily_lesson_counts(
        db=db,
        class_id=school_class.id,
        start_date=start_date,
        end_date=end_date,
    )

    forecast_rows = db.execute(
        select(
            AIDailyForecast.date,
            AIDailyForecast.level,
            AIDailyForecast.source,
        ).where(
            AIDailyForecast.class_id == school_class.id,
            AIDailyForecast.date >= start_date,
            AIDailyForecast.date <= end_date,
        )
    ).all()

    forecasts = {
        forecast_date: (level, source)
        for forecast_date, level, source in forecast_rows
    }

    result = {}

    current_date = start_date

    while current_date <= end_date:
        lesson_count = lesson_counts.get(current_date, 0)

        if lesson_count == 0:
            result[current_date] = (None, None)

        else:
            forecast = forecasts.get(current_date)

            if forecast is not None:
                result[current_date] = (
                    forecast[0],
                    forecast[1],
                )
            else:
                result[current_date] = (
                    get_load_level(lesson_count),
                    "python",
                )

        current_date += timedelta(days=1)

    return result


def build_class_heatmap(
    school_class: Class,
    month: str,
    current_user_id: int | None,
    db: Session,
) -> List[LoadDay]:
    """Формирует тепловую карту из сохранённых AI-прогнозов."""

    try:
        month_number = int(month)
        if month_number < 1 or month_number > 12:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Месяц должен быть указан числом от 01 до 12",
        )

    school_local_today = get_school_local_today(
        db,
        school_class.school_id,
    )

    year = school_local_today.year
    days_in_month = calendar.monthrange(year, month_number)[1]

    start_date = PythonDate(year, month_number, 1)
    end_date = PythonDate(year, month_number, days_in_month)

    effective_loads = get_effective_daily_loads(
        school_class=school_class,
        start_date=start_date,
        end_date=end_date,
        db=db,
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
            level=effective_loads[
                PythonDate(year, month_number, day)
            ][0],
            is_editing=day in editing_days,
        )
        for day in range(1, days_in_month + 1)
    ]


@app.get(
    "/api/schools/{school_id}/classes/{class_code}/heatmap",
    response_model=List[LoadDay],
)
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


def build_class_summary(
    school_class: Class,
    target_date: PythonDate | None,
    db: Session,
) -> ClassStatus:
    """Возвращает уровень нагрузки из канонического прогноза на дату."""

    if target_date is None:
        target_date = get_school_local_today(
            db,
            school_class.school_id,
        )

    effective_loads = get_effective_daily_loads(
        school_class=school_class,
        start_date=target_date,
        end_date=target_date,
        db=db,
    )

    level, source = effective_loads[target_date]

    has_saved_forecast = db.scalar(
        select(AIDailyForecast.id).where(
            AIDailyForecast.class_id == school_class.id,
            AIDailyForecast.date == target_date,
        )
    ) is not None

    return ClassStatus(
        level=level,
        date=target_date.strftime("%d.%m"),
        hasData=has_saved_forecast,
    )


@app.get(
    "/api/schools/{school_id}/classes/{class_code}/summary", response_model=ClassStatus
)
def get_school_summary(
    school_id: int,
    class_code: str,
    date: Optional[PythonDate] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает сводку класса выбранной школы."""

    school_class = require_school_class_access(
        school_id=school_id,
        class_code=class_code,
        user=current_user,
        db=db,
    )

    return build_class_summary(school_class, date, db)


@app.get("/api/schools/{school_id}/survey-classes", response_model=List[SurveyClass])
def get_survey_classes(
    school_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает классы, для которых пользователю доступны опросы."""

    school = db.get(School, school_id)

    if school is None:
        raise HTTPException(
            status_code=404,
            detail="Школа не найдена",
        )

    # Получаем классы выбранной школы, для которых созданы опросы.
    classes = db.scalars(
        select(Class)
        .join(
            AcademicYear,
            and_(
                AcademicYear.id == Class.academic_year_id,
                AcademicYear.school_id == Class.school_id,
            ),
        )
        .join(
            SurveyInstance,
            SurveyInstance.class_id == Class.id,
        )
        .where(
            Class.school_id == school_id,
            AcademicYear.is_active.is_(True),
        )
        .distinct()
        .order_by(Class.code)
    ).all()

    result = []

    for school_class in classes:
        # Проверяем доступ хотя бы к одному опросу класса.
        survey_dates = db.scalars(
            select(SurveyInstance.survey_date).where(
                SurveyInstance.class_id == school_class.id,
            )
        ).all()

        has_access = any(
            can_access_survey_class(
                current_user,
                school_class,
                survey_date,
                db,
            )
            for survey_date in survey_dates
        )

        if has_access:
            result.append(
                SurveyClass(
                    code=school_class.code,
                    name=school_class.name,
                )
            )

    return result


@app.get(
    "/api/schools/{school_id}/classes/{class_code}/surveys",
    response_model=List[SurveyDateItem],
)
def get_class_surveys(
    school_id: int,
    class_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает доступные пользователю даты опросов класса."""

    school_class = get_active_school_class(
        db=db,
        school_id=school_id,
        class_code=class_code,
    )

    if school_class is None:
        raise HTTPException(
            status_code=404,
            detail="Класс не найден",
        )

    school_timezone = db.scalar(
        select(School.timezone).where(
            School.id == school_class.school_id,
        )
    )

    surveys = db.scalars(
        select(SurveyInstance)
        .where(SurveyInstance.class_id == school_class.id)
        .order_by(SurveyInstance.survey_date.desc())
    ).all()

    result = []

    for survey in surveys:
        if not can_access_survey_class(
            current_user,
            school_class,
            survey.survey_date,
            db,
        ):
            continue

        result.append(
            SurveyDateItem(
                survey_date=survey.survey_date,
                status=get_effective_survey_status(survey, school_timezone),
            )
        )

    return result


@app.get(
    "/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
    response_model=SurveyStatistics,
)
def get_survey_statistics(
    school_id: int,
    class_code: str,
    survey_date: PythonDate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает агрегированную статистику опроса класса."""

    # Находим класс в выбранной школе.
    school_class = get_active_school_class(
        db=db,
        school_id=school_id,
        class_code=class_code,
    )

    if school_class is None:
        raise HTTPException(
            status_code=404,
            detail="Класс не найден",
        )

    school_timezone = db.scalar(
        select(School.timezone).where(
            School.id == school_class.school_id,
        )
    )

    # Находим опрос класса на указанную дату.
    survey = db.scalar(
        select(SurveyInstance).where(
            SurveyInstance.class_id == school_class.id,
            SurveyInstance.survey_date == survey_date,
        )
    )

    if survey is None:
        raise HTTPException(
            status_code=404,
            detail="Опрос на указанную дату не найден",
        )

    # Проверяем право доступа к опросу.
    if not can_access_survey_class(
        current_user,
        school_class,
        survey.survey_date,
        db,
    ):
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этому опросу",
        )

    # Получаем вопросы в установленном порядке.
    questions = db.scalars(
        select(SurveyInstanceQuestion)
        .where(
            SurveyInstanceQuestion.instance_id == survey.id,
        )
        .order_by(SurveyInstanceQuestion.sort_order)
    ).all()

    question_statistics = []

    for question in questions:
        # Считаем только отправленные ответы.
        respondents_count = (
            db.scalar(
                select(func.count(SurveyResponse.id)).where(
                    SurveyResponse.instance_question_id == question.id,
                    SurveyResponse.status == "submitted",
                )
            )
            or 0
        )

        # Получаем все варианты ответа, включая те,
        # которые никто не выбрал.
        options = db.scalars(
            select(SurveyInstanceOption)
            .where(
                SurveyInstanceOption.instance_question_id == question.id,
            )
            .order_by(SurveyInstanceOption.sort_order)
        ).all()

        option_statistics = []

        for option in options:
            # Считаем количество выборов конкретного варианта
            # только среди отправленных ответов.
            responses_count = (
                db.scalar(
                    select(func.count(SurveyResponseOption.id))
                    .join(
                        SurveyResponse,
                        SurveyResponse.id == SurveyResponseOption.response_id,
                    )
                    .where(
                        SurveyResponseOption.option_id == option.id,
                        SurveyResponseOption.instance_question_id == question.id,
                        SurveyResponse.status == "submitted",
                    )
                )
                or 0
            )

            percentage = (
                round(responses_count / respondents_count * 100, 1)
                if respondents_count > 0
                else 0.0
            )

            option_statistics.append(
                SurveyOptionStatistic(
                    title=option.title,
                    responses_count=responses_count,
                    percentage=percentage,
                )
            )

        question_statistics.append(
            SurveyQuestionStatistic(
                title=question.title,
                answer_type=question.answer_type,
                respondents_count=respondents_count,
                options=option_statistics,
            )
        )

    return SurveyStatistics(
        class_code=school_class.code,
        class_name=school_class.name,
        survey_date=survey.survey_date,
        status=get_effective_survey_status(survey, school_timezone),
        questions=question_statistics,
    )


def build_class_recommendations(
    school_class: Class,
    month: Optional[str],
    db: Session,
    current_user: User,
    *,
    is_admin: bool,
    teacher_ids: set[int],
    teacher_schedule_ids: set[int],
) -> Recommendation:
    """Возвращает AI-рекомендации класса за выбранный месяц."""

    school_local_today = get_school_local_today(
        db,
        school_class.school_id,
    )

    try:
        month_number = (
            int(month)
            if month
            else school_local_today.month
        )

        if not 1 <= month_number <= 12:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Месяц должен быть указан числом от 01 до 12",
        )

    year = school_local_today.year
    days_in_month = calendar.monthrange(year, month_number)[1]

    period_start = PythonDate(year, month_number, 1)
    period_end = PythonDate(year, month_number, days_in_month)

    tomorrow = school_local_today + timedelta(days=1)

    run_window_start = (
        school_local_today
        if month is None
        else period_start
    )
    run_window_end = (
        tomorrow
        if month is None
        else period_end
    )

    runs = db.scalars(
        select(AIAnalysisRun)
        .join(
            AIAnalysisJob,
            AIAnalysisJob.id == AIAnalysisRun.job_id,
        )
        .where(
            AIAnalysisRun.school_id == school_class.school_id,
            AIAnalysisRun.academic_year_id
            == school_class.academic_year_id,
            or_(
                and_(
                    AIAnalysisRun.scope == "class",
                    AIAnalysisRun.class_id == school_class.id,
                ),
                and_(
                    AIAnalysisRun.scope == "school",
                    AIAnalysisRun.class_id.is_(None),
                ),
            ),
            AIAnalysisRun.period_start <= run_window_end,
            AIAnalysisRun.period_end >= run_window_start,
        )
        .order_by(
            AIAnalysisJob.analysis_date.desc(),
            AIAnalysisJob.created_at.desc(),
            AIAnalysisJob.id.desc(),
        )
    ).all()

    latest_run = runs[0] if runs else None

    successful_run = next(
        (run for run in runs if run.status == "succeeded"),
        None,
    )

    analysis_status = (
        latest_run.status
        if latest_run is not None
        else "not_started"
    )

    is_stale = (
        successful_run is not None
        and latest_run is not None
        and latest_run.id != successful_run.id
        and latest_run.status in {"queued", "running", "failed"}
    )

    daily_loads: list[RecommendationDailyLoad] = []
    recommendations: list[RecommendationDetail] = []
    load_rows: list = []

    if successful_run is not None:
        load_rows = db.scalars(
            select(AIDailyLoad)
            .where(
                AIDailyLoad.analysis_run_id == successful_run.id,
                AIDailyLoad.class_id == school_class.id,
                AIDailyLoad.date >= period_start,
                AIDailyLoad.date <= period_end,
            )
            .order_by(AIDailyLoad.date)
        ).all()

        daily_loads = [
            RecommendationDailyLoad(
                date=row.date,
                day=row.date.day,
                level=row.level,
                source=row.source,
            )
            for row in load_rows
        ]

        fallback_used = False

        if month is not None:
            # При явно выбранном месяце сохраняем прежнее поведение:
            # возвращаем все рекомендации успешного запуска за месяц.
            recommendation_rows = db.scalars(
                select(AIRecommendation)
                .where(
                    AIRecommendation.analysis_run_id == successful_run.id,
                    AIRecommendation.class_id == school_class.id,
                    AIRecommendation.date >= period_start,
                    AIRecommendation.date <= period_end,
                )
                .order_by(
                    AIRecommendation.date,
                    AIRecommendation.id,
                )
            ).all()

        else:
            # Без параметра month показываем рекомендации на завтра.
            # Если их нет — используем рекомендации на сегодня.
            recommendation_rows = []

            for target_date in (tomorrow, school_local_today):
                date_runs = db.scalars(
                    select(AIAnalysisRun)
                    .join(
                        AIDailyLoad,
                        AIDailyLoad.analysis_run_id == AIAnalysisRun.id,
                    )
                    .join(
                        AIAnalysisJob,
                        AIAnalysisJob.id == AIAnalysisRun.job_id,
                    )
                    .where(
                        AIAnalysisRun.school_id == school_class.school_id,
                        AIAnalysisRun.academic_year_id
                        == school_class.academic_year_id,
                        or_(
                            and_(
                                AIAnalysisRun.scope == "class",
                                AIAnalysisRun.class_id == school_class.id,
                            ),
                            and_(
                                AIAnalysisRun.scope == "school",
                                AIAnalysisRun.class_id.is_(None),
                            ),
                        ),
                        AIAnalysisRun.status == "succeeded",
                        AIDailyLoad.class_id == school_class.id,
                        AIDailyLoad.date == target_date,
                    )
                    .order_by(
                        AIAnalysisJob.analysis_date.desc(),
                        AIAnalysisJob.created_at.desc(),
                        AIAnalysisJob.id.desc(),
                    )
                ).all()

                if not date_runs:
                    continue

                # Берём только самый новый успешный запуск,
                # который действительно анализировал эту дату.
                date_run = date_runs[0]

                date_recommendations = db.scalars(
                    select(AIRecommendation)
                    .where(
                        AIRecommendation.analysis_run_id == date_run.id,
                        AIRecommendation.class_id == school_class.id,
                        AIRecommendation.date == target_date,
                    )
                    .order_by(
                        AIRecommendation.id,
                    )
                ).all()

                if date_recommendations:
                    recommendation_rows = date_recommendations
                    fallback_used = target_date == school_local_today
                    break

        is_stale = is_stale or fallback_used

        for item in recommendation_rows:
            if not is_admin:
                if item.kind == "class":
                    pass
                elif item.kind == "teacher":
                    if item.teacher_id not in teacher_ids:
                        continue
                elif item.kind == "lesson":
                    if (
                        item.schedule_id is None
                        or item.schedule_id not in teacher_schedule_ids
                    ):
                        continue

                    # Если у рекомендации также указан teacher_id,
                    # он обязан совпадать с учителем назначения.
                    if (
                        item.teacher_id is not None
                        and item.teacher_id not in teacher_ids
                    ):
                        continue

            recommendations.append(
                RecommendationDetail(
                    date=item.date,
                    kind=item.kind,
                    priority=item.priority,
                    title=item.title,
                    recommendationText=item.recommendation_text,
                    rationale=item.rationale,
                    teacherId=item.teacher_id,
                    scheduleId=item.schedule_id,
                )
            )

    effective_loads = get_effective_daily_loads(
        school_class=school_class,
        start_date=period_start,
        end_date=period_end,
        db=db,
    )

    ai_loads_by_date = {
        row.date: row
        for row in load_rows
    }

    daily_loads = []

    days_to_reduce = []
    days_to_move_to = []

    python_lesson_counts = get_daily_lesson_counts(
        db=db,
        class_id=school_class.id,
        start_date=period_start,
        end_date=period_end,
    )

    for target_date in sorted(effective_loads):
        level, source = effective_loads[target_date]
        python_level = get_load_level(
            python_lesson_counts.get(target_date, 0)
        )

        # День без уроков не попадает в dailyLoads
        # и не становится целью переноса.
        if level is None:
            continue

        daily_loads.append(
            RecommendationDailyLoad(
                date=target_date,
                day=target_date.day,
                level=level,
                source=source,
            )
        )

        if target_date <= school_local_today:
            continue

        ai_load = ai_loads_by_date.get(target_date)

        # AI имеет приоритет для каждого признака отдельно.
        if ai_load is not None and ai_load.reduce_load is not None:
            should_reduce = ai_load.reduce_load
        else:
            should_reduce = python_level in (0, 1)

        if (
            ai_load is not None
            and ai_load.suitable_for_moving is not None
        ):
            suitable_for_moving = ai_load.suitable_for_moving
        else:
            suitable_for_moving = python_level in (3, 4)

        if should_reduce:
            days_to_reduce.append(target_date.day)

        if suitable_for_moving:
            days_to_move_to.append(target_date.day)

    return Recommendation(
        daysToReduce=days_to_reduce,
        daysToMoveTo=days_to_move_to,
        analysisStatus=analysis_status,
        isStale=is_stale,
        period=(
            RecommendationPeriod(
                start=successful_run.period_start,
                end=successful_run.period_end,
            )
            if successful_run is not None
            else None
        ),
        dailyLoads=daily_loads,
        recommendations=recommendations,
        dataSource=(
            "ai"
            if successful_run is not None
            else "schedule"
        ),
    )


@app.get(
    "/api/schools/{school_id}/classes/{class_code}/recommendations",
    response_model=Recommendation,
)
def get_school_recommendations(
    school_id: int,
    class_code: str,
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Возвращает AI-рекомендации класса с проверкой ролевого доступа."""

    require_school_access(
        school_id=school_id,
        user=current_user,
        db=db,
    )

    school_class = get_active_school_class(
        db=db,
        school_id=school_id,
        class_code=class_code,
    )

    if school_class is None:
        raise HTTPException(
            status_code=404,
            detail="Класс не найден",
        )

    roles, _ = get_user_access(current_user, db)

    # Ученик не получает рекомендации ни одного вида.
    if not roles.intersection({"teacher", "admin"}):
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому разделу",
        )

    is_admin = "admin" in roles

    teacher_ids: set[int] = set()
    teacher_schedule_ids: set[int] = set()

    # Администратор имеет приоритет над учительской ролью.
    if not is_admin:
        teacher_ids = set(
            db.scalars(
                select(Teacher.id).where(
                    Teacher.user_id == current_user.id,
                    Teacher.school_id == school_id,
                )
            ).all()
        )

        if not teacher_ids:
            raise HTTPException(
                status_code=403,
                detail="У вас нет доступа к этому классу",
            )

        assignment_ids = db.scalars(
            select(TeachingAssignment.id).where(
                TeachingAssignment.school_id == school_id,
                TeachingAssignment.class_id == school_class.id,
                TeachingAssignment.academic_year_id
                == school_class.academic_year_id,
                TeachingAssignment.teacher_id.in_(teacher_ids),
            )
        ).all()

        # Доступ к классу может быть предоставлен отдельно,
        # без назначения учителя на конкретный предмет.
        has_class_access = bool(
            db.scalars(
                select(TeacherClassAccess.id).where(
                    TeacherClassAccess.teacher_id.in_(teacher_ids),
                    TeacherClassAccess.class_id == school_class.id,
                    TeacherClassAccess.school_id == school_id,
                    TeacherClassAccess.academic_year_id
                    == school_class.academic_year_id,
                )
            ).all()
        )

        if not assignment_ids and not has_class_access:
            raise HTTPException(
                status_code=403,
                detail="У вас нет доступа к этому классу",
            )

        # Уроки учителя определяются только назначениями.
        # TeacherClassAccess сам по себе не даёт доступа
        # к персональным рекомендациям по конкретным урокам.
        if assignment_ids:
            teacher_schedule_ids = set(
                db.scalars(
                    select(Schedule.id).where(
                        Schedule.assignment_id.in_(assignment_ids)
                    )
                ).all()
            )

    return build_class_recommendations(
        school_class=school_class,
        month=month,
        db=db,
        current_user=current_user,
        is_admin=is_admin,
        teacher_ids=teacher_ids,
        teacher_schedule_ids=teacher_schedule_ids,
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
    user: User,
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
    EditingEditor = aliased(User)
    now = datetime.now(timezone.utc)

    rows = db.execute(
        select(
            Schedule,
            TeachingAssignment.subgroup,
            Subject.name,
            User.full_name,
            Editor.full_name,
            EditingSession.id,
            EditingEditor.full_name,
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
        .outerjoin(
            EditingSession,
            (EditingSession.schedule_id == Schedule.id)
            & (EditingSession.expires_at > now),
        )
        .outerjoin(
            EditingEditor,
            EditingSession.user_id == EditingEditor.id,
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
                format_teacher_name(editor_full_name) if editor_full_name else None
            ),
            is_editable=can_edit_lesson(schedule, user, db),
            is_editing=editing_session_id is not None,
            editor_name=editing_editor_full_name,
        )
        for (
            schedule,
            subgroup,
            subject_name,
            teacher_full_name,
            editor_full_name,
            editing_session_id,
            editing_editor_full_name,
        ) in rows
    ]


@app.get(
    "/api/schools/{school_id}/classes/{class_code}/schedule",
    response_model=List[Lesson],
)
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

    return build_class_schedule(school_class, date, db, current_user)


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
            TeachingAssignment.school_id == Class.school_id,
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

    school_id = db.scalar(select(Class.school_id).where(Class.id == class_id))

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
    school_id: int,
    class_code: str,
    lesson_id: str,
    user: User,
    db: Session,
) -> tuple[Schedule, User]:
    """
    Находит занятие и проверяет доступ пользователя
    к школе, классу и редактированию конкретного занятия.
    """

    # Сначала проверяем доступ к выбранной школе и классу.
    school_class = require_school_class_access(
        school_id=school_id,
        class_code=class_code,
        user=user,
        db=db,
        allowed_roles={"teacher", "admin"},
    )

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

    # Проверяем, что занятие действительно относится
    # к классу, указанному в URL.
    lesson_class_id = db.scalar(
        select(TeachingAssignment.class_id).where(
            TeachingAssignment.id == lesson.assignment_id
        )
    )

    if lesson_class_id != school_class.id:
        raise HTTPException(
            status_code=404,
            detail="Урок не найден в указанном классе.",
        )

    # Проверяем право редактирования самого занятия.
    if not can_edit_lesson(lesson, user, db):
        raise HTTPException(
            status_code=403,
            detail="У вас нет прав на редактирование этого урока.",
        )

    return lesson, user


@app.put(
    "/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}",
    response_model=Lesson,
)
def update_lesson(
    school_id: int,
    class_code: str,
    lesson_id: str,
    request: LessonUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Изменяет тип занятия в указанном классе."""

    lesson, editor = get_editing_user_and_lesson(
        school_id=school_id,
        class_code=class_code,
        lesson_id=lesson_id,
        user=current_user,
        db=db,
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
    editing_session.expires_at = now + timedelta(seconds=EDITING_SESSION_TTL_SECONDS)

    db.commit()
    db.refresh(lesson)

    return get_lesson_response(db, lesson.id)


@app.post("/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}/editing")
def start_editing(
    school_id: int,
    class_code: str,
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Начинает или возобновляет собственную сессию редактирования."""

    lesson, user = get_editing_user_and_lesson(
        school_id=school_id,
        class_code=class_code,
        lesson_id=lesson_id,
        user=current_user,
        db=db,
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

        session.expires_at = now + timedelta(seconds=EDITING_SESSION_TTL_SECONDS)
        db.commit()

        return {
            "success": True,
            "expires_in": EDITING_SESSION_TTL_SECONDS,
        }

    if session is not None:
        db.delete(session)
        db.flush()

    session = EditingSession(
        schedule_id=lesson.id,
        user_id=user.id,
        expires_at=now + timedelta(seconds=EDITING_SESSION_TTL_SECONDS),
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

    return {
        "success": True,
        "expires_in": EDITING_SESSION_TTL_SECONDS,
    }


@app.put("/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}/editing")
def renew_editing(
    school_id: int,
    class_code: str,
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Продлевает только собственную активную сессию."""

    lesson, user = get_editing_user_and_lesson(
        school_id=school_id,
        class_code=class_code,
        lesson_id=lesson_id,
        user=current_user,
        db=db,
    )

    now = datetime.now(timezone.utc)

    session = db.scalar(
        select(EditingSession)
        .where(EditingSession.schedule_id == lesson.id)
        .with_for_update()
    )

    if session is None or session.user_id != user.id or session.expires_at <= now:
        raise HTTPException(
            status_code=409,
            detail="Активная сессия редактирования не найдена.",
        )

    session.expires_at = now + timedelta(seconds=EDITING_SESSION_TTL_SECONDS)

    db.commit()

    return {
        "success": True,
        "expires_in": EDITING_SESSION_TTL_SECONDS,
    }


@app.delete(
    "/api/schools/{school_id}/classes/{class_code}/schedule/{lesson_id}/editing"
)
def stop_editing(
    school_id: int,
    class_code: str,
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Завершает только собственную сессию редактирования."""

    lesson, user = get_editing_user_and_lesson(
        school_id=school_id,
        class_code=class_code,
        lesson_id=lesson_id,
        user=current_user,
        db=db,
    )

    session = db.scalar(
        select(EditingSession)
        .where(EditingSession.schedule_id == lesson.id)
        .with_for_update()
    )

    if session is not None:
        if session.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="Нельзя завершить чужую сессию редактирования.",
            )

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
            format_teacher_name(editor_full_name) if editor_full_name else None
        ),
    )
