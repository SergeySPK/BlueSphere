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
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )
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

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )

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
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(150))


class AcademicPeriod(Base):
    __tablename__ = "academic_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[PythonDate] = mapped_column(Date)
    end_date: Mapped[PythonDate] = mapped_column(Date)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    sferum_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))


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
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE")
    )


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

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE")
    )

    start_date: Mapped[PythonDate] = mapped_column(Date)
    end_date: Mapped[PythonDate | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Administrator(Base):
    __tablename__ = "administrators"
    __table_args__ = (
        UniqueConstraint("user_id", "school_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )
    position: Mapped[str] = mapped_column(String(100))


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

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )

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
    __table_args__ = (
        UniqueConstraint("schedule_id"),
    )

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
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE")
    )
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
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE")
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE")
    )
    date: Mapped[PythonDate] = mapped_column(Date)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SurveySubject(Base):
    __tablename__ = "survey_subjects"
    __table_args__ = (
        UniqueConstraint("survey_id", "subject_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE")
    )
    subject_name: Mapped[str] = mapped_column(String(150))


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE")
    )
    date_generated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    recommendation_text: Mapped[str] = mapped_column(Text)
    days_to_reduce: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list
    )
    days_to_move_to: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list
    )
