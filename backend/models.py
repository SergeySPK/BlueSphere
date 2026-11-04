from datetime import date as PythonDate, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class School(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(150))
    city: Mapped[str] = mapped_column(String(150))
    address: Mapped[str] = mapped_column(String(255))
    short_name: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AcademicYear(Base):
    __tablename__ = "academic_years"
    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "id",
            name="uq_academic_years_school_id",
        ),
        Index(
            "uq_academic_years_one_active_per_school",
            "school_id",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[PythonDate] = mapped_column(Date)
    end_date: Mapped[PythonDate] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Class(Base):
    __tablename__ = "classes"

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "academic_year_id",
            "code",
            name="uq_classes_school_year_code",
        ),
        UniqueConstraint(
            "id",
            "school_id",
            "academic_year_id",
            name="uq_classes_id_school_year",
        ),
        ForeignKeyConstraint(
            ["school_id", "academic_year_id"],
            ["academic_years.school_id", "academic_years.id"],
            name="fk_classes_school_academic_year",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))

    academic_year_id: Mapped[int] = mapped_column(Integer)

    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(50))


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "school_id",
            name="uq_subjects_id_school",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(150))


class AcademicPeriod(Base):
    __tablename__ = "academic_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[PythonDate] = mapped_column(Date)
    end_date: Mapped[PythonDate] = mapped_column(Date)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    sferum_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    is_demo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )


class Teacher(Base):
    __tablename__ = "teachers"
    __table_args__ = (
        UniqueConstraint("user_id", "school_id"),
        UniqueConstraint(
            "id",
            "school_id",
            name="uq_teachers_id_school",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))


class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"

    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_student_enrollments_dates",
        ),
        Index(
            "uq_student_enrollments_active_student",
            "student_id",
            unique=True,
            postgresql_where=text("end_date IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE")
    )

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))

    start_date: Mapped[PythonDate] = mapped_column(Date)
    end_date: Mapped[PythonDate | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Administrator(Base):
    __tablename__ = "administrators"
    __table_args__ = (UniqueConstraint("user_id", "school_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    position: Mapped[str] = mapped_column(String(100))


class TeacherClassAccess(Base):
    __tablename__ = "teacher_class_accesses"

    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "class_id",
            name="uq_teacher_class_access_teacher_class",
        ),
        ForeignKeyConstraint(
            ["teacher_id", "school_id"],
            ["teachers.id", "teachers.school_id"],
            name="fk_teacher_class_access_teacher_school",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["class_id", "school_id", "academic_year_id"],
            ["classes.id", "classes.school_id", "classes.academic_year_id"],
            name="fk_teacher_class_access_class_school_year",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    teacher_id: Mapped[int] = mapped_column(Integer)
    class_id: Mapped[int] = mapped_column(Integer)
    school_id: Mapped[int] = mapped_column(Integer)
    academic_year_id: Mapped[int] = mapped_column(Integer)


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"

    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "class_id",
            "subject_id",
            "academic_year_id",
            "subgroup",
        ),
        CheckConstraint(
            "subgroup IN (0, 1, 2)",
            name="ck_teaching_assignments_subgroup",
        ),
        ForeignKeyConstraint(
            ["teacher_id", "school_id"],
            ["teachers.id", "teachers.school_id"],
            name="fk_assignments_teacher_school",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["subject_id", "school_id"],
            ["subjects.id", "subjects.school_id"],
            name="fk_assignments_subject_school",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["class_id", "school_id", "academic_year_id"],
            ["classes.id", "classes.school_id", "classes.academic_year_id"],
            name="fk_assignments_class_school_year",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))

    teacher_id: Mapped[int] = mapped_column(Integer)

    class_id: Mapped[int] = mapped_column(Integer)

    subject_id: Mapped[int] = mapped_column(Integer)

    academic_year_id: Mapped[int] = mapped_column(Integer)

    subgroup: Mapped[int] = mapped_column(Integer, default=0)


class Schedule(Base):
    __tablename__ = "schedule"
    __table_args__ = (
        UniqueConstraint("assignment_id", "date", "lesson_number"),
        CheckConstraint("lesson_number > 0", name="ck_schedule_lesson_number_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_assignments.id", ondelete="CASCADE")
    )
    date: Mapped[PythonDate] = mapped_column(Date)
    lesson_number: Mapped[int] = mapped_column(Integer)
    room: Mapped[str] = mapped_column(String(50))
    lesson_type: Mapped[str] = mapped_column(String(150))
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )


class EditingSession(Base):
    """Активная сессия редактирования урока."""

    __tablename__ = "editing_sessions"
    __table_args__ = (UniqueConstraint("schedule_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedule.id", ondelete="CASCADE"),
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (
        UniqueConstraint("student_id", "date"),
        CheckConstraint("score BETWEEN 0 AND 4", name="ck_surveys_score_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE")
    )
    date: Mapped[PythonDate] = mapped_column(Date)
    score: Mapped[int] = mapped_column(Integer)


class SurveyDraft(Base):
    __tablename__ = "survey_drafts"
    __table_args__ = (
        UniqueConstraint("student_id", "date"),
        CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 4",
            name="ck_survey_drafts_score_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE")
    )
    date: Mapped[PythonDate] = mapped_column(Date)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SurveySubject(Base):
    __tablename__ = "survey_subjects"
    __table_args__ = (UniqueConstraint("survey_id", "subject_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("surveys.id", ondelete="CASCADE"))
    subject_name: Mapped[str] = mapped_column(String(150))


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"
    __table_args__ = (
        CheckConstraint(
            "answer_type IN ('single', 'multiple')",
            name="ck_survey_questions_answer_type",
        ),
        CheckConstraint(
            "options_source IN ('static', 'subjects')",
            name="ck_survey_questions_options_source",
        ),
        CheckConstraint(
            "min_answer >= 1 AND max_answer >= min_answer",
            name="ck_survey_questions_answer_limits",
        ),
        CheckConstraint(
            "(answer_type = 'single' AND min_answer = 1 AND max_answer = 1) "
            "OR answer_type = 'multiple'",
            name="ck_survey_questions_single_limits",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    bot_text: Mapped[str] = mapped_column(Text)
    answer_type: Mapped[str] = mapped_column(String(20))
    options_source: Mapped[str] = mapped_column(
        String(30),
        default="static",
    )
    min_answer: Mapped[int] = mapped_column(Integer, default=1)
    max_answer: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SurveyQuestionOption(Base):
    __tablename__ = "survey_question_options"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "sort_order",
            name="uq_survey_question_options_order",
        ),
        UniqueConstraint(
            "question_id",
            "title",
            name="uq_survey_question_options_title",
        ),
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_survey_question_options_title_not_empty",
        ),
        Index(
            "uq_survey_question_options_one_exclusive",
            "question_id",
            unique=True,
            postgresql_where=text("is_exclusive IS TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("survey_questions.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(150))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_exclusive: Mapped[bool] = mapped_column(Boolean, default=False)


class SurveyInstance(Base):
    __tablename__ = "survey_instances"
    __table_args__ = (
        UniqueConstraint(
            "class_id",
            "survey_date",
            name="uq_survey_instances_class_date",
        ),
        CheckConstraint(
            "closes_at > opens_at",
            name="ck_survey_instances_dates",
        ),
        CheckConstraint(
            "status IN ('open', 'closed', 'cancelled')",
            name="ck_survey_instances_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"),
        index=True,
    )
    survey_date: Mapped[PythonDate] = mapped_column(Date)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class SurveyNotification(Base):
    __tablename__ = "survey_notifications"

    __table_args__ = (
        CheckConstraint(
            "progress_status IN ('not_started', 'in_progress', 'completed', 'closed')",
            name="ck_survey_notifications_progress_status",
        ),
        UniqueConstraint(
            "instance_id",
            "student_id",
            name="uq_survey_notifications_instance_student",
        ),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed')",
            name="ck_survey_notifications_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_survey_notifications_attempt_count",
        ),
        Index(
            "ix_survey_notifications_status",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    instance_id: Mapped[int] = mapped_column(
        ForeignKey("survey_instances.id", ondelete="CASCADE"),
        index=True,
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Состояние прохождения опроса конкретным учеником.
    progress_status: Mapped[str] = mapped_column(
        String(20),
        default="not_started",
        server_default="not_started",
    )

    # ID последнего сообщения с вопросом в MAX.
    # Нужен планировщику, чтобы закрыть сообщение в 18:00.
    max_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class SurveyInstanceQuestion(Base):
    __tablename__ = "survey_instance_questions"
    __table_args__ = (
        UniqueConstraint(
            "instance_id",
            "sort_order",
            name="uq_survey_instance_questions_order",
        ),
        CheckConstraint(
            "answer_type IN ('single', 'multiple')",
            name="ck_survey_instance_questions_answer_type",
        ),
        CheckConstraint(
            "min_answer >= 1 AND max_answer >= min_answer",
            name="ck_survey_instance_questions_answer_limits",
        ),
        CheckConstraint(
            "(answer_type = 'single' AND min_answer = 1 AND max_answer = 1) "
            "OR answer_type = 'multiple'",
            name="ck_survey_instance_questions_single_limits",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("survey_instances.id", ondelete="CASCADE"),
        index=True,
    )
    source_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("survey_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    bot_text: Mapped[str] = mapped_column(Text)
    answer_type: Mapped[str] = mapped_column(String(20))
    min_answer: Mapped[int] = mapped_column(Integer)
    max_answer: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer)


class SurveyInstanceOption(Base):
    __tablename__ = "survey_instance_options"
    __table_args__ = (
        UniqueConstraint(
            "instance_question_id",
            "sort_order",
            name="uq_survey_instance_options_order",
        ),
        UniqueConstraint(
            "id",
            "instance_question_id",
            name="uq_survey_instance_options_id_question",
        ),
        UniqueConstraint(
            "instance_question_id",
            "title",
            name="uq_survey_instance_options_title",
        ),
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_survey_instance_options_title_not_empty",
        ),
        Index(
            "uq_survey_instance_options_one_exclusive",
            "instance_question_id",
            unique=True,
            postgresql_where=text("is_exclusive IS TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_question_id: Mapped[int] = mapped_column(
        ForeignKey("survey_instance_questions.id", ondelete="CASCADE"),
        index=True,
    )
    source_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("survey_question_options.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(150))
    sort_order: Mapped[int] = mapped_column(Integer)
    is_exclusive: Mapped[bool] = mapped_column(Boolean, default=False)


class SurveyResponse(Base):
    __tablename__ = "survey_responses"
    __table_args__ = (
        UniqueConstraint(
            "instance_question_id",
            "student_id",
            name="uq_survey_responses_question_student",
        ),
        UniqueConstraint(
            "id",
            "instance_question_id",
            name="uq_survey_responses_id_question",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted')",
            name="ck_survey_responses_status",
        ),
        CheckConstraint(
            "(status = 'draft' AND submitted_at IS NULL) "
            "OR (status = 'submitted' AND submitted_at IS NOT NULL)",
            name="ck_survey_responses_submission_time",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_question_id: Mapped[int] = mapped_column(
        ForeignKey("survey_instance_questions.id", ondelete="CASCADE"),
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class SurveyResponseOption(Base):
    __tablename__ = "survey_response_options"
    __table_args__ = (
        UniqueConstraint(
            "response_id",
            "option_id",
            name="uq_survey_response_options_selection",
        ),
        ForeignKeyConstraint(
            ["response_id", "instance_question_id"],
            [
                "survey_responses.id",
                "survey_responses.instance_question_id",
            ],
            name="fk_response_options_response_question",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["option_id", "instance_question_id"],
            [
                "survey_instance_options.id",
                "survey_instance_options.instance_question_id",
            ],
            name="fk_response_options_option_question",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    response_id: Mapped[int] = mapped_column(Integer, index=True)

    option_id: Mapped[int] = mapped_column(Integer, index=True)

    instance_question_id: Mapped[int] = mapped_column(Integer, index=True)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    date_generated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    recommendation_text: Mapped[str] = mapped_column(Text)
    days_to_reduce: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    days_to_move_to: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
