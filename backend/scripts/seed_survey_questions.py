import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from database import SessionLocal, engine
from models import SurveyQuestion, SurveyQuestionOption
from user_mode import validate_database_mode


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
        "title": (
            "Предметы, на которых ученикам было больше всего тревожно"
        ),
        "bot_text": (
            "Выберите предмет(ы), на которых вам сегодня было "
            "больше всего тревожно:"
        ),
        "answer_type": "multiple",
        "options_source": "subjects",
        "min_answer": 1,
        "max_answer": 2,
        "sort_order": 2,
        "options": [],
    },
    {
        "title": (
            "Предметы, на которых ученикам было наиболее легко"
        ),
        "bot_text": (
            "Выберите предмет(ы), которые для вас сегодня "
            "были наиболее лёгкими:"
        ),
        "answer_type": "multiple",
        "options_source": "subjects",
        "min_answer": 1,
        "max_answer": 2,
        "sort_order": 3,
        "options": [],
    },
    {
        "title": "Общая оценка заинтерисованности учеников в сегодняшних уроках",
        "bot_text": "Как вы оцениваете свою заинтерисованность в сегоднящних уроках:",
        "answer_type": "single",
        "options_source": "static",
        "min_answer": 1,
        "max_answer": 1,
        "sort_order": 4,
        "options": [
            "Очень интересно",
            "В целом интересно",
            "Затрудняюсь ответить",
            "Немного интересно",
            "Вообще не интересно",
        ],
    },
]


def seed_questions():
    validate_database_mode(engine)

    with SessionLocal() as session:
        try:
            created_questions = 0
            created_options = 0

            for data in QUESTIONS:
                question = session.scalar(
                    select(SurveyQuestion).where(
                        SurveyQuestion.title == data["title"]
                    )
                )

                if question is None:
                    question = SurveyQuestion(
                        title=data["title"],
                        bot_text=data["bot_text"],
                        answer_type=data["answer_type"],
                        options_source=data["options_source"],
                        min_answer=data["min_answer"],
                        max_answer=data["max_answer"],
                        sort_order=data["sort_order"],
                        is_active=True,
                    )
                    session.add(question)
                    session.flush()
                    created_questions += 1
                elif question.sort_order != data["sort_order"]:
                    question.sort_order = data["sort_order"]

                # Существующий вопрос не перезаписываем:
                # он мог быть изменён администратором.
                if data["options_source"] != "static":
                    continue

                existing_options = session.scalars(
                    select(SurveyQuestionOption).where(
                        SurveyQuestionOption.question_id == question.id
                    )
                ).all()

                existing_by_title = {
                    option.title: option
                    for option in existing_options
                }

                for order, title in enumerate(
                    data["options"],
                    start=1,
                ):
                    option = existing_by_title.get(title)

                    if option is None:
                        session.add(
                            SurveyQuestionOption(
                                question_id=question.id,
                                title=title,
                                sort_order=order,
                                is_exclusive=False,
                            )
                        )
                        created_options += 1

            session.commit()

            print("Базовые шаблоны опроса проверены.")
            print(f"Создано шаблонов: {created_questions}")
            print(f"Создано вариантов: {created_options}")
            print("Порядок базовых вопросов синхронизирован с настройками скрипта.")
            print(
                "Остальные настройки существующих вопросов и дополнительные "
                "вопросы не изменялись."
            )

        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    seed_questions()
