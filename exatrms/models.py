"""Database models for ExamTrack.

All tables use MySQL through Flask-SQLAlchemy with explicit primary keys and
foreign keys. Related records are protected with RESTRICT where deleting a
parent would destroy academic history.
"""

from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Index

from .extensions import db

ROLE_ADMIN = "admin"
ROLE_STUDENT = "student"

RESULT_PASS = "pass"
RESULT_FAIL = "fail"


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum(ROLE_ADMIN, ROLE_STUDENT, name="user_role"),
        nullable=False,
        default=ROLE_STUDENT,
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # One user owns at most one student profile.
    student = db.relationship(
        "Student",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
    entered_marks = db.relationship("Mark", backref="entered_by_user")
    audit_logs = db.relationship("AuditLog", backref="actor")
    published_results = db.relationship("Result", backref="publisher")
    notification_reads = db.relationship(
        "NotificationRead", backref="reader", cascade="all, delete-orphan"
    )
    owned_notifications = db.relationship(
        "Notification",
        foreign_keys="Notification.user_id",
        backref="recipient",
        cascade="all, delete-orphan",
    )
    created_notifications = db.relationship(
        "Notification",
        foreign_keys="Notification.created_by",
        backref="creator",
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"

    @property
    def display_name(self) -> str:
        if self.student:
            return self.student.full_name
        return self.username.replace("_", " ").title()


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    duration_years = db.Column(db.Integer, nullable=False, default=3)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    students = db.relationship("Student", backref="course", lazy="dynamic")
    subjects = db.relationship("Subject", backref="course", lazy="dynamic")
    examinations = db.relationship("Examination", backref="course", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Course {self.code}>"


class Semester(db.Model):
    __tablename__ = "semesters"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    students = db.relationship("Student", backref="semester", lazy="dynamic")
    subjects = db.relationship("Subject", backref="semester", lazy="dynamic")
    examinations = db.relationship("Examination", backref="semester", lazy="dynamic")

    __table_args__ = (
        db.UniqueConstraint(
            "number", "academic_year", name="uq_semester_number_year"
        ),
    )

    def __repr__(self) -> str:
        return f"<Semester {self.number} ({self.academic_year})>"

    @property
    def label(self) -> str:
        return f"Semester {self.number} · {self.academic_year}"


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    student_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True)
    gender = db.Column(db.String(10), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    address = db.Column(db.Text, nullable=True)
    admission_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    semester_id = db.Column(
        db.Integer, db.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    marks = db.relationship(
        "Mark", backref="student", cascade="all, delete-orphan", lazy="dynamic"
    )
    results = db.relationship(
        "Result", backref="student", cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Student {self.student_code}>"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    semester_id = db.Column(
        db.Integer, db.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False
    )
    credits = db.Column(db.Integer, nullable=False, default=3)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    marks = db.relationship("Mark", backref="subject", lazy="dynamic")

    __table_args__ = (
        db.UniqueConstraint("code", name="uq_subject_code"),
        Index("ix_subject_course_semester", "course_id", "semester_id"),
    )

    def __repr__(self) -> str:
        return f"<Subject {self.code}>"


class Examination(db.Model):
    __tablename__ = "examinations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    exam_type = db.Column(
        db.Enum("Quiz", "Midterm", "Final", "Practical", name="exam_type"),
        nullable=False,
        default="Midterm",
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    semester_id = db.Column(
        db.Integer, db.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False
    )
    academic_year = db.Column(db.String(20), nullable=False)
    max_marks = db.Column(db.Numeric(6, 2), nullable=False, default=100)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_published = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    published_at = db.Column(db.DateTime, nullable=True)

    marks = db.relationship(
        "Mark", backref="examination", cascade="all, delete-orphan", lazy="dynamic"
    )
    results = db.relationship(
        "Result", backref="examination", cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Examination {self.name}>"

    @property
    def subject_query(self):
        return Subject.query.filter_by(
            course_id=self.course_id, semester_id=self.semester_id, is_active=True
        )

    @property
    def student_query(self):
        return Student.query.filter_by(
            course_id=self.course_id, semester_id=self.semester_id, is_active=True
        )


class Mark(db.Model):
    __tablename__ = "marks"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    examination_id = db.Column(
        db.Integer,
        db.ForeignKey("examinations.id", ondelete="CASCADE"),
        nullable=False,
    )
    marks_obtained = db.Column(db.Numeric(6, 2), nullable=False)
    max_marks = db.Column(db.Numeric(6, 2), nullable=False, default=100)
    percentage = db.Column(db.Numeric(5, 2), nullable=False)
    grade = db.Column(db.String(4), nullable=False)
    grade_points = db.Column(db.Numeric(4, 2), nullable=False)
    status = db.Column(
        db.Enum(RESULT_PASS, RESULT_FAIL, name="mark_status"),
        nullable=False,
        default=RESULT_PASS,
    )
    remarks = db.Column(db.String(255), nullable=True)
    entered_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "subject_id",
            "examination_id",
            name="uq_mark_student_subject_exam",
        ),
        Index("ix_mark_exam_student", "examination_id", "student_id"),
    )

    def __repr__(self) -> str:
        return f"<Mark student={self.student_id} subject={self.subject_id}>"


class Result(db.Model):
    __tablename__ = "results"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    examination_id = db.Column(
        db.Integer,
        db.ForeignKey("examinations.id", ondelete="CASCADE"),
        nullable=False,
    )
    obtained_marks = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    total_marks = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    percentage = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    grade = db.Column(db.String(4), nullable=False, default="F")
    gpa = db.Column(db.Numeric(4, 2), nullable=False, default=0)
    status = db.Column(
        db.Enum(RESULT_PASS, RESULT_FAIL, name="result_status"),
        nullable=False,
        default=RESULT_FAIL,
    )
    rank = db.Column(db.Integer, nullable=True)
    calculated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    published_at = db.Column(db.DateTime, nullable=True)
    published_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "examination_id", name="uq_result_student_exam"
        ),
        Index("ix_result_exam_status", "examination_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Result student={self.student_id} exam={self.examination_id}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    audience = db.Column(
        db.Enum("all", "students", "admins", "specific", name="notification_audience"),
        nullable=False,
        default="all",
        index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    reads = db.relationship(
        "NotificationRead", backref="notification", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Notification {self.title}>"


class NotificationRead(db.Model):
    __tablename__ = "notification_reads"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    notification_id = db.Column(
        db.Integer,
        db.ForeignKey("notifications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    read_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<NotificationRead user={self.user_id} n={self.notification_id}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action}>"
