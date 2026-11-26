"""Flask CLI commands: database initialisation and optional demo seeding."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import click
from werkzeug.security import generate_password_hash

from .config import Config
from .extensions import db
from .models import (
    Course,
    Examination,
    Mark,
    Notification,
    Result,
    Semester,
    Student,
    Subject,
    User,
)
from .utils import (
    calculate_grade,
    current_academic_year,
    recalculate_exam_results,
)

COURSES = [
    ("BSCIT", "Bachelor of Science in Information Technology", 3),
    ("BCA", "Bachelor of Computer Applications", 3),
    ("BSCCS", "Bachelor of Science in Computer Science", 3),
]

SUBJECTS_BY_SEMESTER = {
    1: [
        ("IT101", "Programming in C", 3),
        ("IT102", "Digital Logic", 3),
        ("IT103", "Business Communication", 2),
        ("IT104", "Computer Fundamentals", 3),
    ],
    2: [
        ("IT201", "Data Structures", 4),
        ("IT202", "Object Oriented Programming", 4),
        ("IT203", "Discrete Mathematics", 3),
        ("IT204", "Web Technologies", 3),
    ],
    3: [
        ("IT301", "Database Management Systems", 4),
        ("IT302", "Operating Systems", 4),
        ("IT303", "Computer Networks", 3),
        ("IT304", "Software Engineering", 3),
    ],
}

DEMO_STUDENTS = [
    ("STU001", "Aarav", "Sharma", "aarav.sharma@example.com"),
    ("STU002", "Diya", "Verma", "diya.verma@example.com"),
    ("STU003", "Rohan", "Patel", "rohan.patel@example.com"),
    ("STU004", "Meera", "Iyer", "meera.iyer@example.com"),
    ("STU005", "Arjun", "Nair", "arjun.nair@example.com"),
    ("STU006", "Sneha", "Reddy", "sneha.reddy@example.com"),
    ("STU007", "Kabir", "Singh", "kabir.singh@example.com"),
    ("STU008", "Ananya", "Das", "ananya.das@example.com"),
]


def _get_or_create(model, defaults: dict | None = None, **kwargs):
    """Find or create a record, applying required defaults before flush."""
    instance = model.query.filter_by(**kwargs).first()
    if instance:
        return instance, False
    instance = model(**kwargs)
    for key, value in (defaults or {}).items():
        setattr(instance, key, value)
    db.session.add(instance)
    db.session.flush()
    return instance, True


def _seed_reference_data(year: str):
    created = {"courses": 0, "semesters": 0, "subjects": 0}

    courses = {}
    for code, name, duration in COURSES:
        course, is_new = _get_or_create(
            Course,
            defaults={"name": name, "duration_years": duration, "is_active": True},
            code=code,
        )
        course.name = name
        course.duration_years = duration
        course.is_active = True
        if is_new:
            created["courses"] += 1
        courses[code] = course

    semesters = {}
    for number in range(1, 9):
        semester, is_new = _get_or_create(
            Semester, number=number, academic_year=year
        )
        if is_new:
            created["semesters"] += 1
        semesters[number] = semester

    for course_code, course in courses.items():
        for semester_number, subject_rows in SUBJECTS_BY_SEMESTER.items():
            semester = semesters[semester_number]
            for code, name, credits in subject_rows:
                # BCA/BSCCS get a prefixed code so codes stay globally unique.
                subject_code = code if course_code == "BSCIT" else f"{course_code}-{code}"
                subject, is_new = _get_or_create(
                    Subject,
                    defaults={
                        "name": name,
                        "course_id": course.id,
                        "semester_id": semester.id,
                        "credits": credits,
                        "is_active": True,
                    },
                    code=subject_code,
                )
                subject.name = name
                subject.course_id = course.id
                subject.semester_id = semester.id
                subject.credits = credits
                subject.is_active = True
                if is_new:
                    created["subjects"] += 1

    return courses, semesters, created


def _seed_admin():
    username = Config.ADMIN_USERNAME
    existing = User.query.filter_by(username=username).first()
    if existing:
        return False, Config.ADMIN_PASSWORD
    admin = User(
        username=username,
        email=Config.ADMIN_EMAIL,
        password_hash=generate_password_hash(Config.ADMIN_PASSWORD),
        role="admin",
        is_active=True,
    )
    db.session.add(admin)
    db.session.flush()
    return True, Config.ADMIN_PASSWORD


def _seed_demo(courses, semesters, year: str):
    course = courses["BSCIT"]
    semester = semesters[1]

    exam_rows = [
        ("BSc IT Semester 1 - Midterm", "Midterm", date(int(year[:4]), 9, 20), False),
        ("BSc IT Semester 1 - Final", "Final", date(int(year[:4]) + 1, 1, 15), True),
    ]
    exams = []
    for name, exam_type, start_date, publish in exam_rows:
        exam, _ = _get_or_create(
            Examination,
            defaults={
                "exam_type": exam_type,
                "max_marks": Decimal("100"),
                "start_date": start_date,
                "end_date": start_date,
                "is_active": True,
            },
            name=name,
            course_id=course.id,
            semester_id=semester.id,
            academic_year=year,
        )
        exam.max_marks = Decimal("100")
        exam.start_date = start_date
        exam.end_date = start_date
        exams.append((exam, publish))

    demo_users = []
    students = []
    for index, (code, first, last, email) in enumerate(DEMO_STUDENTS, start=1):
        username = f"student{index}"
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash("Student@123"),
                role="student",
                is_active=True,
            )
            db.session.add(user)
            db.session.flush()
        student = Student.query.filter_by(student_code=code).first()
        if not student:
            student = Student(
                user_id=user.id,
                student_code=code,
                first_name=first,
                last_name=last,
                email=email,
                phone=f"98765{40000 + index}",
                gender="Female" if index % 2 == 0 else "Male",
                date_of_birth=date(2004 + (index % 3), 3 + (index % 9), 5 + (index % 20)),
                address="Demo Student Hostel, College Campus",
                admission_date=date(int(year[:4]), 7, 10),
                course_id=course.id,
                semester_id=semester.id,
                is_active=True,
            )
            db.session.add(student)
            db.session.flush()
        demo_users.append((user.username, email))
        students.append(student)

    subjects = (
        Subject.query.filter_by(course_id=course.id, semester_id=semester.id, is_active=True)
        .order_by(Subject.code)
        .all()
    )

    marks_written = 0
    for exam, publish in exams:
        for student_index, student in enumerate(students):
            for subject_index, subject in enumerate(subjects):
                mark = Mark.query.filter_by(
                    student_id=student.id,
                    subject_id=subject.id,
                    examination_id=exam.id,
                ).first()
                if mark:
                    continue
                # Deterministic sample scores between 38 and 96.
                obtained = 38 + ((student_index * 7 + subject_index * 11) % 59)
                grade, points, status = calculate_grade(obtained)
                mark = Mark(
                    student_id=student.id,
                    subject_id=subject.id,
                    examination_id=exam.id,
                    marks_obtained=Decimal(str(obtained)),
                    max_marks=Decimal("100"),
                    percentage=Decimal(str(obtained)),
                    grade=grade,
                    grade_points=Decimal(str(points)),
                    status=status,
                    remarks="",
                )
                db.session.add(mark)
                marks_written += 1

    db.session.flush()
    for exam, publish in exams:
        recalculate_exam_results(exam.id)
        exam.is_published = publish
        if publish:
            exam.published_at = datetime.utcnow()
            results = Result.query.filter_by(examination_id=exam.id).all()
            for result in results:
                result.published_at = exam.published_at

    admin = User.query.filter_by(username=Config.ADMIN_USERNAME).first()
    has_notice = Notification.query.filter_by(title="Final examination results published").first()
    if not has_notice:
        db.session.add(
            Notification(
                title="Final examination results published",
                message="Semester 1 final examination results are now available on your dashboard. Download your digital marksheet from the Results page.",
                audience="students",
                created_by=admin.id if admin else None,
                is_active=True,
            )
        )

    return marks_written, demo_users


def register_commands(app) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """Create all MySQL tables defined by the models."""
        db.create_all()
        click.echo("Database tables created/verified successfully.")

    @app.cli.command("seed")
    @click.option(
        "--demo",
        is_flag=True,
        help="Also create sample students, marks, results and a published exam.",
    )
    def seed_command(demo: bool):
        """Seed admin, courses, semesters, subjects and optional demo data."""
        year = current_academic_year()
        admin_created, admin_password = _seed_admin()
        courses, semesters, counts = _seed_reference_data(year)
        db.session.commit()

        click.echo(f"Academic year: {year}")
        click.echo(f"Admin account: {Config.ADMIN_USERNAME} / {admin_password}" + (" (created)" if admin_created else " (already exists)"))
        click.echo(
            f"Reference data ready: {len(courses)} courses, {len(semesters)} semesters, "
            f"{Subject.query.count()} subjects."
        )

        if demo:
            marks_written, demo_users = _seed_demo(courses, semesters, year)
            db.session.commit()
            click.echo(f"Demo data ready: {len(demo_users)} students, {marks_written} marks written, results published.")
            click.echo("Student logins: student1 ... student8 / Student@123")
        else:
            click.echo("Tip: run 'flask --app app seed --demo' to add sample students and marks.")
