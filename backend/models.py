from datetime import date as PythonDate, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import CheckConstraint
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

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[PythonDate] = mapped_column(Date)
    end_date: Mapped[PythonDate] = mapped_column(Date)


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE")
    )
    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(50))


class Subject(Base):
    __tablename__ = "subjects"

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
    class_id: Mapped[str] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE")
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
        CheckConstraint("subgroup IN (0, 1, 2)", name="ck_teaching_assignments_subgroup"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE")
    )
    class_id: Mapped[str] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE")
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE")
    )
    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.id", ondelete="CASCADE")
    )
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


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (
        UniqueConstraint("student_id", "date"),
        CheckConstraint("score BETWEEN 0 AND 4", name="ck_surveys_score_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[str] = mapped_column(
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
    class_id: Mapped[str] = mapped_column(
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
    class_id: Mapped[str] = mapped_column(
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
