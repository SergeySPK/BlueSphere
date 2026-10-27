from datetime import date as PythonDate
import calendar

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session, aliased

from database import SessionLocal
from models import (
    AcademicYear,
    Administrator,
    Class,
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
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

app = FastAPI(title="Blue Sphere API", docs_url="/docs", redoc_url=None)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Разрешённые адреса Flutter-приложения.
# На хостинге FRONTEND_ORIGINS задаётся через переменные окружения.
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
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
    level: int # 0 - перегруз, 4 - пусто

class ClassStatus(BaseModel):
    level: Optional[int] = None
    date: Optional[str] = None
    has_data: bool = Field(alias="hasData")

class Recommendation(BaseModel):
    daysToReduce: List[int]
    daysToMoveTo: List[int]

class UserProfile(BaseModel):
    sferum_id: str
    roles: List[str] # Массив ролей: ["teacher", "admin"]
    class_ids: List[str] # Список ID классов, к которым привязан пользователь

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
    lesson_type: str
    updated_by_sferum_id: str


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



@app.post("/api/auth", response_model=UserProfile)
async def auth_user(
    request: AuthRequest,
    db: Session = Depends(get_db),
):
    # Сначала проверяем подлинность данных, полученных от MAX.
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

    return UserProfile(
        sferum_id=user.sferum_id,
        roles=roles,
        class_ids=sorted(class_ids),
    )



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
    db: Session = Depends(get_db),
):
    """Возвращает нагрузку по расписанию за выбранный месяц."""

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

    return [
        LoadDay(
            day=day,
            level=get_load_level(counts.get(
                PythonDate(year, month_number, day), 0
            )),
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

    editor = db.scalar(
        select(User).where(
            User.sferum_id == request.updated_by_sferum_id
        )
    )

    if editor is None:
        raise HTTPException(
            status_code=404,
            detail="Пользователь, изменяющий урок, не найден.",
        )

    lesson.lesson_type = request.lesson_type
    lesson.updated_by_user_id = editor.id

    db.commit()
    db.refresh(lesson)

    return get_lesson_response(db, lesson.id)


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
