"""Создание/обновление трёх шаблонов опроса Blue Sphere.

Запуск из каталога backend:
    python scripts/seed_survey_questions.py

Скрипт идемпотентный: повторный запуск обновляет эти шаблоны и
варианты первого вопроса, не создавая дубликаты.
"""

from pathlib import Path
import sys

# Добавляем корень backend в sys.path, чтобы импорты работали при запуске
# файла по пути scripts/seed_survey_questions.py.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from user_mode import validate_database_mode
from database import engine, SessionLocal
from models import SurveyQuestion, SurveyQuestionOption

QUESTIONS = [
    {
        "title": "Общая оценка состояния учеников после учебного дня",
        "bot_text": "Оцените своё состояние после учебного дня:",
        "answer_type": "single",
        "options_source": "static",
        "min_answer": 1,
        "max_answer": 1,
        "sort_order": 1,
        "options": [
            "Отлично",
            "Хорошо",
            "Удовлетворительно",
            "Неудовлетворительно",
            "Плохо",
        ],
    },
    {
        "title": "Предметы, на которых сегодня ученикам было больше всего тревожно",
        "bot_text": (
            "Выберите предмет(ы) (не более двух), на которых вам было "
            "сегодня больше всего тревожно:"
        ),
        "answer_type": "multiple",
        "options_source": "subjects",
        "min_answer": 1,
        "max_answer": 2,
        "sort_order": 2,
        "options": [],
    },
    {
        "title": "Предметы, на которых сегодня ученикам было наиболее легко",
        "bot_text": (
            "Выберите предмет(ы) (не более двух), которые для вас были "
            "сегодня наиболее лёгкими:"
        ),
        "answer_type": "multiple",
        "options_source": "subjects",
        "min_answer": 1,
        "max_answer": 2,
        "sort_order": 3,
        "options": [],
    },
]


def seed_questions() -> None:
    validate_database_mode(engine)
    db = SessionLocal()

    try:
        for data in QUESTIONS:
            options = data["options"]
            question_data = {
                key: value for key, value in data.items() if key != "options"
            }

            # Для этих трёх начальных шаблонов sort_order служит стабильным
            # идентификатором. Если запись уже существует, обновляем её.
            question = (
                db.query(SurveyQuestion)
                .filter(SurveyQuestion.sort_order == data["sort_order"])
                .one_or_none()
            )

            if question is None:
                question = SurveyQuestion(**question_data)
                db.add(question)
                db.flush()
            else:
                for field, value in question_data.items():
                    setattr(question, field, value)

            # У динамических вопросов варианты будут создаваться из расписания
            # при создании экземпляра опроса. У первого вопроса варианты статические.
            existing_options = (
                db.query(SurveyQuestionOption)
                .filter(SurveyQuestionOption.question_id == question.id)
                .all()
            )

            if options:
                by_title = {option.title: option for option in existing_options}

                for order, title in enumerate(options, start=1):
                    option = by_title.get(title)
                    if option is None:
                        option = SurveyQuestionOption(
                            question_id=question.id,
                            title=title,
                            sort_order=order,
                            is_exclusive=False,
                        )
                        db.add(option)
                    else:
                        option.sort_order = order
                        option.is_exclusive = False

                # Удаляем устаревшие варианты, чтобы после повторного запуска
                # у первого вопроса оставался ровно заданный список.
                allowed_titles = set(options)
                for option in existing_options:
                    if option.title not in allowed_titles:
                        db.delete(option)
            else:
                # У вопросов по предметам не должно быть статических вариантов.
                for option in existing_options:
                    db.delete(option)

        db.commit()

        print("Шаблоны опроса успешно сохранены.")
        for question in (
            db.query(SurveyQuestion).order_by(SurveyQuestion.sort_order).all()
        ):
            option_count = (
                db.query(SurveyQuestionOption)
                .filter(SurveyQuestionOption.question_id == question.id)
                .count()
            )
            print(
                f"{question.sort_order}. {question.title} "
                f"| тип: {question.answer_type} "
                f"| источник вариантов: {question.options_source} "
                f"| вариантов в шаблоне: {option_count}"
            )

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_questions()
