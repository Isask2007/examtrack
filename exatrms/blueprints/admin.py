"""Administrator routes: records, marks, results, analytics, reports and logs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from ..extensions import db, login_manager
from ..models import (
    AuditLog,
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
from ..pdf import generate_exam_report_pdf, generate_marksheet_pdf
from ..utils import (
    admin_required,
    audit,
    calculate_grade,
    current_academic_year,
    paginate,
    parse_date,
    parse_decimal,
    recalculate_exam_results,
    recalculate_result,
    to_float,
    update_ranks,
    valid_email,
    valid_name,
    valid_password,
    valid_phone,
    valid_username,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
def require_admin():
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if current_user.role != "admin":
        abort(403)


def _active_choices(model, label_attr: str = "name"):
    return model.query.filter_by(is_active=True).order_by(getattr(model, label_attr)).all()


def _checked(field: str) -> bool:
    return request.form.get(field) == "on"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route("/dashboard")
def dashboard():
    stats = {
        "students": Student.query.filter_by(is_active=True).count(),
        "courses": Course.query.filter_by(is_active=True).count(),
        "subjects": Subject.query.filter_by(is_active=True).count(),
        "exams": Examination.query.filter_by(is_active=True).count(),
        "published": Examination.query.filter_by(is_published=True).count(),
        "results": Result.query.count(),
        "pass_rate": 0,
    }
    all_results = Result.query.count()
    if all_results:
        passed = Result.query.filter_by(status="pass").count()
        stats["pass_rate"] = round(passed / all_results * 100, 1)

    recent_results = (
        Result.query.order_by(Result.calculated_at.desc()).limit(6).all()
    )
    recent_activity = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(6).all()
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_results=recent_results,
        recent_activity=recent_activity,
    )


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
@admin_bp.route("/students")
def students():
    query = Student.query.order_by(Student.student_code)
    search = request.args.get("q", "").strip()
    course_id = request.args.get("course_id", type=int)
    semester_id = request.args.get("semester_id", type=int)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Student.first_name.like(like),
                Student.last_name.like(like),
                Student.student_code.like(like),
                Student.email.like(like),
            )
        )
    if course_id:
        query = query.filter_by(course_id=course_id)
    if semester_id:
        query = query.filter_by(semester_id=semester_id)

    return render_template(
        "admin/students.html",
        students_page=paginate(query),
        courses=_active_choices(Course),
        semesters=_active_choices(Semester, "number"),
        search=search,
        course_id=course_id,
        semester_id=semester_id,
    )


def _handle_student_form(student: Student | None):
    """Validate and save create/edit student form. Returns redirect or None."""
    is_new = student is None
    form = request.form
    values = {
        "username": form.get("username", "").strip(),
        "email": form.get("email", "").strip().lower(),
        "password": form.get("password", ""),
        "student_code": form.get("student_code", "").strip().upper(),
        "first_name": form.get("first_name", "").strip(),
        "last_name": form.get("last_name", "").strip(),
        "phone": form.get("phone", "").strip(),
        "gender": form.get("gender", "").strip(),
        "date_of_birth": parse_date(form.get("date_of_birth", "")),
        "address": form.get("address", "").strip(),
        "admission_date": parse_date(form.get("admission_date", "")),
        "course_id": form.get("course_id", type=int),
        "semester_id": form.get("semester_id", type=int),
        "is_active": _checked("is_active"),
    }
    errors = []

    if not valid_username(values["username"]):
        errors.append("Username must be 3-50 characters (letters, numbers, . _ -).")
    if not valid_email(values["email"]):
        errors.append("Enter a valid email address.")
    if is_new and not valid_password(values["password"]):
        errors.append("Password must be at least 8 characters with letters and numbers.")
    if not is_new and values["password"] and not valid_password(values["password"]):
        errors.append("New password must be at least 8 characters with letters and numbers.")
    if not values["student_code"]:
        errors.append("Student code is required.")
    if not valid_name(values["first_name"]) or not valid_name(values["last_name"]):
        errors.append("Enter a valid first and last name.")
    if not valid_phone(values["phone"]):
        errors.append("Enter a valid phone number or leave it blank.")
    if not values["admission_date"]:
        errors.append("Enter a valid admission date.")
    if not Course.query.get(values["course_id"]):
        errors.append("Select a valid course.")
    if not Semester.query.get(values["semester_id"]):
        errors.append("Select a valid semester.")

    existing_user = User.query.filter_by(username=values["username"]).first()
    if existing_user and (is_new or existing_user.id != student.user_id):
        errors.append("That username is already in use.")
    existing_email = User.query.filter_by(email=values["email"]).first()
    if existing_email and (is_new or existing_email.id != student.user_id):
        errors.append("That email is already in use.")
    existing_code = Student.query.filter_by(student_code=values["student_code"]).first()
    if existing_code and (is_new or existing_code.id != student.id):
        errors.append("That student code is already in use.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return None

    try:
        if is_new:
            user = User(
                username=values["username"],
                email=values["email"],
                password_hash=generate_password_hash(values["password"]),
                role="student",
                is_active=values["is_active"],
            )
            db.session.add(user)
            db.session.flush()
            student = Student(user_id=user.id)
        else:
            user = student.user
            user.username = values["username"]
            user.email = values["email"]
            user.is_active = values["is_active"]
            if values["password"]:
                user.password_hash = generate_password_hash(values["password"])

        student.student_code = values["student_code"]
        student.first_name = values["first_name"]
        student.last_name = values["last_name"]
        student.email = values["email"]
        student.phone = values["phone"] or None
        student.gender = values["gender"] or None
        student.date_of_birth = values["date_of_birth"]
        student.address = values["address"] or None
        student.admission_date = values["admission_date"] or date.today()
        student.course_id = values["course_id"]
        student.semester_id = values["semester_id"]
        student.is_active = values["is_active"]

        db.session.add(student)
        audit(
            "CREATE_STUDENT" if is_new else "UPDATE_STUDENT",
            "student",
            student.id,
            f"{student.student_code} - {student.full_name}",
        )
        db.session.commit()
        flash("Student saved successfully.", "success")
        return redirect(url_for("admin.student_detail", id=student.id))
    except IntegrityError:
        db.session.rollback()
        flash("A database conflict occurred (duplicate code, username or email).", "danger")
        return None


@admin_bp.route("/students/new", methods=["GET", "POST"])
def student_new():
    if request.method == "POST":
        response = _handle_student_form(None)
        if response:
            return response
    return render_template(
        "admin/student_form.html",
        student=None,
        courses=_active_choices(Course),
        semesters=_active_choices(Semester, "number"),
        form=request.form,
    )


@admin_bp.route("/students/<int:id>/edit", methods=["GET", "POST"])
def student_edit(id: int):
    student = Student.query.get_or_404(id)
    if request.method == "POST":
        response = _handle_student_form(student)
        if response:
            return response
    return render_template(
        "admin/student_form.html",
        student=student,
        courses=_active_choices(Course),
        semesters=_active_choices(Semester, "number"),
        form=request.form,
    )


@admin_bp.route("/students/<int:id>")
def student_detail(id: int):
    student = Student.query.get_or_404(id)
    results = (
        Result.query.filter_by(student_id=id)
        .order_by(Result.calculated_at.desc())
        .all()
    )
    marks = Mark.query.filter_by(student_id=id).order_by(Mark.created_at.desc()).limit(20).all()
    return render_template(
        "admin/student_detail.html", student=student, results=results, marks=marks
    )


@admin_bp.route("/students/<int:id>/delete", methods=["POST"])
def student_delete(id: int):
    student = Student.query.get_or_404(id)
    if student.marks.count() or student.results.count():
        flash(
            "This student has academic records. Deactivate the account instead of deleting it.",
            "warning",
        )
        return redirect(url_for("admin.student_detail", id=id))
    user = student.user
    audit("DELETE_STUDENT", "student", id, student.student_code)
    if user:
        db.session.delete(user)
    else:
        db.session.delete(student)
    db.session.commit()
    flash("Student removed successfully.", "success")
    return redirect(url_for("admin.students"))


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
@admin_bp.route("/courses")
def courses():
    query = Course.query.order_by(Course.code)
    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(
            or_(Course.name.like(f"%{search}%"), Course.code.like(f"%{search}%"))
        )
    return render_template("admin/courses.html", courses_page=paginate(query), search=search)


@admin_bp.route("/courses/new", methods=["GET", "POST"], endpoint="course_new")
@admin_bp.route("/courses/<int:id>/edit", methods=["GET", "POST"], endpoint="course_edit")
def course_form(id: int | None = None):
    course = Course.query.get_or_404(id) if id else None
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        name = request.form.get("name", "").strip()
        duration = request.form.get("duration_years", type=int)
        errors = []
        if not code or len(code) > 20:
            errors.append("Course code is required (max 20 characters).")
        if not valid_name(name):
            errors.append("Enter a valid course name.")
        if not duration or not 1 <= duration <= 6:
            errors.append("Duration must be between 1 and 6 years.")
        duplicate = Course.query.filter_by(code=code).first()
        if duplicate and (not course or duplicate.id != course.id):
            errors.append("That course code already exists.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not course:
                course = Course()
            course.code = code
            course.name = name
            course.duration_years = duration
            course.description = request.form.get("description", "").strip() or None
            course.is_active = _checked("is_active")
            db.session.add(course)
            audit("CREATE_COURSE" if not id else "UPDATE_COURSE", "course", course.id, code)
            db.session.commit()
            flash("Course saved successfully.", "success")
            return redirect(url_for("admin.courses"))

    return render_template("admin/course_form.html", course=course, form=request.form)


@admin_bp.route("/courses/<int:id>/delete", methods=["POST"])
def course_delete(id: int):
    course = Course.query.get_or_404(id)
    if course.students.count() or course.subjects.count() or course.examinations.count():
        flash("Course is in use. Deactivate it instead of deleting it.", "warning")
    else:
        audit("DELETE_COURSE", "course", id, course.code)
        db.session.delete(course)
        db.session.commit()
        flash("Course deleted.", "success")
    return redirect(url_for("admin.courses"))


# ---------------------------------------------------------------------------
# Semesters
# ---------------------------------------------------------------------------
@admin_bp.route("/semesters")
def semesters():
    query = Semester.query.order_by(Semester.academic_year.desc(), Semester.number)
    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(Semester.academic_year.like(f"%{search}%"))
    return render_template("admin/semesters.html", semesters_page=paginate(query), search=search)


@admin_bp.route("/semesters/new", methods=["GET", "POST"], endpoint="semester_new")
@admin_bp.route("/semesters/<int:id>/edit", methods=["GET", "POST"], endpoint="semester_edit")
def semester_form(id: int | None = None):
    semester = Semester.query.get_or_404(id) if id else None
    if request.method == "POST":
        number = request.form.get("number", type=int)
        year = request.form.get("academic_year", "").strip()
        errors = []
        if not number or not 1 <= number <= 12:
            errors.append("Semester number must be between 1 and 12.")
        if not year:
            errors.append("Academic year is required.")
        duplicate = Semester.query.filter_by(number=number, academic_year=year).first()
        if duplicate and (not semester or duplicate.id != semester.id):
            errors.append("That semester already exists for this academic year.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not semester:
                semester = Semester()
            semester.number = number
            semester.academic_year = year
            semester.is_active = _checked("is_active")
            db.session.add(semester)
            audit("CREATE_SEMESTER" if not id else "UPDATE_SEMESTER", "semester", semester.id, semester.label)
            db.session.commit()
            flash("Semester saved successfully.", "success")
            return redirect(url_for("admin.semesters"))

    return render_template("admin/semester_form.html", semester=semester, form=request.form)


@admin_bp.route("/semesters/<int:id>/delete", methods=["POST"])
def semester_delete(id: int):
    semester = Semester.query.get_or_404(id)
    if semester.students.count() or semester.subjects.count() or semester.examinations.count():
        flash("Semester is in use. Deactivate it instead of deleting it.", "warning")
    else:
        audit("DELETE_SEMESTER", "semester", id, semester.label)
        db.session.delete(semester)
        db.session.commit()
        flash("Semester deleted.", "success")
    return redirect(url_for("admin.semesters"))


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------
@admin_bp.route("/subjects")
def subjects():
    query = Subject.query.order_by(Subject.code)
    search = request.args.get("q", "").strip()
    course_id = request.args.get("course_id", type=int)
    semester_id = request.args.get("semester_id", type=int)
    if search:
        query = query.filter(
            or_(Subject.name.like(f"%{search}%"), Subject.code.like(f"%{search}%"))
        )
    if course_id:
        query = query.filter_by(course_id=course_id)
    if semester_id:
        query = query.filter_by(semester_id=semester_id)

    return render_template(
        "admin/subjects.html",
        subjects_page=paginate(query),
        courses=_active_choices(Course),
        semesters=_active_choices(Semester, "number"),
        search=search,
        course_id=course_id,
        semester_id=semester_id,
    )


@admin_bp.route("/subjects/new", methods=["GET", "POST"], endpoint="subject_new")
@admin_bp.route("/subjects/<int:id>/edit", methods=["GET", "POST"], endpoint="subject_edit")
def subject_form(id: int | None = None):
    subject = Subject.query.get_or_404(id) if id else None
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        name = request.form.get("name", "").strip()
        course_id = request.form.get("course_id", type=int)
        semester_id = request.form.get("semester_id", type=int)
        credits = request.form.get("credits", type=int)
        errors = []
        if not code:
            errors.append("Subject code is required.")
        if not valid_name(name):
            errors.append("Enter a valid subject name.")
        if not Course.query.get(course_id):
            errors.append("Select a valid course.")
        if not Semester.query.get(semester_id):
            errors.append("Select a valid semester.")
        if not credits or not 1 <= credits <= 10:
            errors.append("Credits must be between 1 and 10.")
        duplicate = Subject.query.filter_by(code=code).first()
        if duplicate and (not subject or duplicate.id != subject.id):
            errors.append("That subject code already exists.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not subject:
                subject = Subject()
            subject.code = code
            subject.name = name
            subject.course_id = course_id
            subject.semester_id = semester_id
            subject.credits = credits
            subject.description = request.form.get("description", "").strip() or None
            subject.is_active = _checked("is_active")
            db.session.add(subject)
            audit("CREATE_SUBJECT" if not id else "UPDATE_SUBJECT", "subject", subject.id, code)
            db.session.commit()
            flash("Subject saved successfully.", "success")
            return redirect(url_for("admin.subjects"))

    return render_template(
        "admin/subject_form.html",
        subject=subject,
        courses=_active_choices(Course),
        semesters=_active_choices(Semester, "number"),
        form=request.form,
    )


@admin_bp.route("/subjects/<int:id>/delete", methods=["POST"])
def subject_delete(id: int):
    subject = Subject.query.get_or_404(id)
    if subject.marks.count():
        flash("Subject has recorded marks. Deactivate it instead of deleting it.", "warning")
    else:
        audit("DELETE_SUBJECT", "subject", id, subject.code)
        db.session.delete(subject)
        db.session.commit()
        flash("Subject deleted.", "success")
    return redirect(url_for("admin.subjects"))


# ---------------------------------------------------------------------------
# Examinations
# ---------------------------------------------------------------------------
@admin_bp.route("/exams")
def exams():
    query = Examination.query.order_by(Examination.created_at.desc())
    course_id = request.args.get("course_id", type=int)
    semester_id = request.args.get("semester_id", type=int)
    published = request.args.get("published", "")
    if course_id:
        query = query.filter_by(course_id=course_id)
    if semester_id:
        query = query.filter_by(semester_id=semester_id)
    if published in {"yes", "no"}:
        query = query.filter_by(is_published=(published == "yes"))

    return render_template(
        "admin/exams.html",
        exams_page=paginate(query),
        courses=_active_choices(Course),
        semesters=_active_choices(Semester, "number"),
        course_id=course_id,
        semester_id=semester_id,
        published=published,
    )


@admin_bp.route("/exams/new", methods=["GET", "POST"], endpoint="exam_new")
@admin_bp.route("/exams/<int:id>/edit", methods=["GET", "POST"], endpoint="exam_edit")
def exam_form(id: int | None = None):
    exam = Examination.query.get_or_404(id) if id else None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        exam_type = request.form.get("exam_type", "Midterm")
        course_id = request.form.get("course_id", type=int)
        semester_id = request.form.get("semester_id", type=int)
        academic_year = request.form.get("academic_year", "").strip()
        max_marks = parse_decimal(request.form.get("max_marks", ""))
        start_date = parse_date(request.form.get("start_date", ""))
        end_date = parse_date(request.form.get("end_date", ""))
        errors = []
        if len(name) < 3:
            errors.append("Examination name must be at least 3 characters.")
        if exam_type not in {"Quiz", "Midterm", "Final", "Practical"}:
            errors.append("Select a valid examination type.")
        if not Course.query.get(course_id):
            errors.append("Select a valid course.")
        if not Semester.query.get(semester_id):
            errors.append("Select a valid semester.")
        if not academic_year:
            errors.append("Academic year is required.")
        if max_marks is None or max_marks <= 0:
            errors.append("Maximum marks must be greater than zero.")
        if start_date and end_date and end_date < start_date:
            errors.append("End date cannot be before the start date.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not exam:
                exam = Examination()
                exam.is_published = False
            exam.name = name
            exam.exam_type = exam_type
            exam.course_id = course_id
            exam.semester_id = semester_id
            exam.academic_year = academic_year
            exam.max_marks = max_marks
            exam.start_date = start_date
            exam.end_date = end_date
            exam.is_active = _checked("is_active")
            db.session.add(exam)
            audit("CREATE_EXAM" if not id else "UPDATE_EXAM", "examination", exam.id, name)
            db.session.commit()
            flash("Examination saved successfully.", "success")
            return redirect(url_for("admin.exams"))

    return render_template(
        "admin/exam_form.html",
        exam=exam,
        courses=_active_choices(Course),
        semesters=_active_choices(Semester, "number"),
        form=request.form,
        default_year=current_academic_year(),
    )


@admin_bp.route("/exams/<int:id>/delete", methods=["POST"])
def exam_delete(id: int):
    exam = Examination.query.get_or_404(id)
    if exam.marks.count() or exam.results.count():
        flash("Examination has marks/results. Deactivate it instead of deleting it.", "warning")
    else:
        audit("DELETE_EXAM", "examination", id, exam.name)
        db.session.delete(exam)
        db.session.commit()
        flash("Examination deleted.", "success")
    return redirect(url_for("admin.exams"))


def _set_exam_publication(exam: Examination, publish: bool):
    exam.is_published = publish
    exam.published_at = datetime.utcnow() if publish else None
    for result in exam.results:
        result.published_at = exam.published_at
        result.published_by = current_user.id if publish else None
    recalculate_exam_results(exam.id)
    audit(
        "PUBLISH_RESULTS" if publish else "UNPUBLISH_RESULTS",
        "examination",
        exam.id,
        f"{exam.name} ({exam.course.code})",
    )
    db.session.commit()
    flash("Results published. Students can now view them." if publish else "Results hidden from students.", "success")


@admin_bp.route("/exams/<int:id>/publish", methods=["POST"])
def exam_publish(id: int):
    _set_exam_publication(Examination.query.get_or_404(id), True)
    return redirect(request.referrer or url_for("admin.exams"))


@admin_bp.route("/exams/<int:id>/unpublish", methods=["POST"])
def exam_unpublish(id: int):
    _set_exam_publication(Examination.query.get_or_404(id), False)
    return redirect(request.referrer or url_for("admin.exams"))


# ---------------------------------------------------------------------------
# Marks entry
# ---------------------------------------------------------------------------
@admin_bp.route("/marks", methods=["GET", "POST"])
def marks():
    exam_id = request.args.get("exam_id", type=int) or request.form.get("exam_id", type=int)
    student_id = request.args.get("student_id", type=int) or request.form.get("student_id", type=int)
    exam = Examination.query.get(exam_id) if exam_id else None
    subjects = exam.subject_query.order_by(Subject.code).all() if exam else []
    students_query = exam.student_query.order_by(Student.student_code) if exam else Student.query.order_by(Student.student_code)
    if student_id:
        students_query = students_query.filter_by(id=student_id)
    students = students_query.all()

    existing = {}
    if exam and students and subjects:
        for mark in Mark.query.filter_by(examination_id=exam.id).all():
            existing[(mark.student_id, mark.subject_id)] = mark

    if request.method == "POST":
        if not exam:
            flash("Select an examination first.", "danger")
            return redirect(url_for("admin.marks"))
        if not students or not subjects:
            flash("No students or subjects match this examination.", "warning")
            return redirect(url_for("admin.marks", exam_id=exam.id, student_id=student_id))

        max_marks = Decimal(str(exam.max_marks))
        pending = []
        errors = []
        for student in students:
            for subject in subjects:
                field = f"mark_{student.id}_{subject.id}"
                raw = request.form.get(field, "").strip()
                if not raw:
                    continue
                value = parse_decimal(raw)
                if value is None or value < 0 or value > max_marks:
                    errors.append(f"{student.student_code} / {subject.code}: enter a value between 0 and {max_marks}.")
                    continue
                pending.append((student, subject, value))

        if errors:
            for error in errors[:10]:
                flash(error, "danger")
            if len(errors) > 10:
                flash(f"...and {len(errors) - 10} more invalid entries.", "danger")
        else:
            changed_students = set()
            for student, subject, value in pending:
                mark = existing.get((student.id, subject.id))
                if not mark:
                    mark = Mark(
                        student_id=student.id,
                        subject_id=subject.id,
                        examination_id=exam.id,
                    )
                    db.session.add(mark)
                mark.marks_obtained = value
                mark.max_marks = max_marks
                mark.percentage = round(value / max_marks * 100, 2) if max_marks else Decimal("0")
                grade, points, status = calculate_grade(to_float(mark.percentage))
                mark.grade = grade
                mark.grade_points = Decimal(str(points))
                mark.status = status
                mark.entered_by = current_user.id
                mark.remarks = None
                changed_students.add(student.id)

            db.session.flush()
            for sid in changed_students:
                recalculate_result(sid, exam.id)
            db.session.flush()
            update_ranks(exam.id)
            audit(
                "ENTER_MARKS",
                "examination",
                exam.id,
                f"{len(pending)} marks saved for {exam.name}",
            )
            db.session.commit()
            flash(f"{len(pending)} mark entries saved and results recalculated.", "success")
            return redirect(url_for("admin.marks", exam_id=exam.id, student_id=student_id))

    return render_template(
        "admin/marks.html",
        exams=Examination.query.order_by(Examination.created_at.desc()).all(),
        students=students,
        subjects=subjects,
        exam=exam,
        existing=existing,
        student_id=student_id,
    )


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@admin_bp.route("/results")
def results():
    query = Result.query.join(Result.student).join(Result.examination)
    exam_id = request.args.get("exam_id", type=int)
    course_id = request.args.get("course_id", type=int)
    status = request.args.get("status", "")
    search = request.args.get("q", "").strip()

    if exam_id:
        query = query.filter(Result.examination_id == exam_id)
    if course_id:
        query = query.filter(Student.course_id == course_id)
    if status in {"pass", "fail"}:
        query = query.filter(Result.status == status)
    if search:
        query = query.filter(
            or_(
                Student.first_name.like(f"%{search}%"),
                Student.last_name.like(f"%{search}%"),
                Student.student_code.like(f"%{search}%"),
            )
        )
    query = query.order_by(Examination.created_at.desc(), Result.rank.asc())

    return render_template(
        "admin/results.html",
        results_page=paginate(query),
        exams=Examination.query.order_by(Examination.created_at.desc()).all(),
        courses=_active_choices(Course),
        exam_id=exam_id,
        course_id=course_id,
        status=status,
        search=search,
    )


@admin_bp.route("/results/<int:id>")
def result_detail(id: int):
    result = Result.query.get_or_404(id)
    marks = (
        Mark.query.filter_by(student_id=result.student_id, examination_id=result.examination_id)
        .join(Mark.subject)
        .order_by(Subject.code)
        .all()
    )
    return render_template("admin/result_detail.html", result=result, marks=marks)


@admin_bp.route("/results/recalculate/<int:exam_id>", methods=["POST"])
def results_recalculate(exam_id: int):
    exam = Examination.query.get_or_404(exam_id)
    count = recalculate_exam_results(exam.id)
    audit("RECALCULATE_RESULTS", "examination", exam.id, f"{count} results recalculated")
    db.session.commit()
    flash(f"Recalculated {count} results for {exam.name}.", "success")
    return redirect(request.referrer or url_for("admin.results"))


# ---------------------------------------------------------------------------
# Analytics + JSON APIs
# ---------------------------------------------------------------------------
@admin_bp.route("/analytics")
def analytics():
    exams = Examination.query.order_by(Examination.created_at.desc()).all()
    selected_exam_id = request.args.get("exam_id", type=int)
    selected_exam = (
        Examination.query.get(selected_exam_id)
        if selected_exam_id
        else (exams[0] if exams else None)
    )
    return render_template(
        "admin/analytics.html", exams=exams, selected_exam=selected_exam
    )


@admin_bp.route("/api/exam-performance")
def api_exam_performance():
    exams = Examination.query.order_by(Examination.created_at).all()
    labels, pass_data, fail_data, avg_data = [], [], [], []
    for exam in exams:
        results = Result.query.filter_by(examination_id=exam.id).all()
        if not results:
            continue
        passed = sum(1 for r in results if r.status == "pass")
        labels.append(exam.name)
        pass_data.append(round(passed / len(results) * 100, 1))
        fail_data.append(round((len(results) - passed) / len(results) * 100, 1))
        avg_data.append(round(sum(to_float(r.percentage) for r in results) / len(results), 1))
    return jsonify(
        {
            "labels": labels,
            "datasets": [
                {"label": "Pass %", "data": pass_data, "backgroundColor": "#0f9f6e", "borderColor": "#0f9f6e", "borderRadius": 6},
                {"label": "Fail %", "data": fail_data, "backgroundColor": "#f43f5e", "borderColor": "#f43f5e", "borderRadius": 6},
                {"label": "Average %", "data": avg_data, "backgroundColor": "#4f46e5", "borderColor": "#4f46e5", "borderRadius": 6},
            ],
        }
    )


@admin_bp.route("/api/course-distribution")
def api_course_distribution():
    courses = Course.query.filter_by(is_active=True).order_by(Course.code).all()
    labels = [c.code for c in courses]
    data = [Student.query.filter_by(course_id=c.id, is_active=True).count() for c in courses]
    return jsonify(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "Students",
                    "data": data,
                    "backgroundColor": ["#4f46e5", "#0ea5a4", "#f59e0b", "#f43f5e", "#8b5cf6", "#14b8a6"],
                    "borderWidth": 0,
                }
            ],
        }
    )


@admin_bp.route("/api/subject-performance")
def api_subject_performance():
    exam_id = request.args.get("exam_id", type=int)
    exam = Examination.query.get(exam_id) if exam_id else Examination.query.order_by(Examination.created_at.desc()).first()
    labels, data = [], []
    if exam:
        for subject in exam.subject_query.order_by(Subject.code):
            marks = Mark.query.filter_by(examination_id=exam.id, subject_id=subject.id).all()
            if marks:
                labels.append(subject.code)
                data.append(round(sum(to_float(m.percentage) for m in marks) / len(marks), 1))
    return jsonify(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "Average %",
                    "data": data,
                    "backgroundColor": "#0ea5a4",
                    "borderColor": "#0ea5a4",
                    "borderRadius": 6,
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@admin_bp.route("/notifications")
def notifications():
    query = Notification.query.order_by(Notification.created_at.desc())
    return render_template(
        "admin/notifications.html", notifications_page=paginate(query)
    )


@admin_bp.route("/notifications/new", methods=["GET", "POST"], endpoint="notification_new")
@admin_bp.route("/notifications/<int:id>/edit", methods=["GET", "POST"], endpoint="notification_edit")
def notification_form(id: int | None = None):
    notification = Notification.query.get_or_404(id) if id else None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        audience = request.form.get("audience", "all")
        user_id = request.form.get("user_id", type=int)
        errors = []
        if len(title) < 3:
            errors.append("Title must be at least 3 characters.")
        if len(message) < 5:
            errors.append("Message must be at least 5 characters.")
        if audience not in {"all", "students", "admins", "specific"}:
            errors.append("Select a valid audience.")
        if audience == "specific" and not User.query.get(user_id):
            errors.append("Select a user for a specific notification.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            if not notification:
                notification = Notification()
                notification.created_by = current_user.id
            notification.title = title
            notification.message = message
            notification.audience = audience
            notification.user_id = user_id if audience == "specific" else None
            notification.is_active = _checked("is_active")
            db.session.add(notification)
            audit("CREATE_NOTIFICATION" if not id else "UPDATE_NOTIFICATION", "notification", notification.id, title)
            db.session.commit()
            flash("Notification saved successfully.", "success")
            return redirect(url_for("admin.notifications"))

    return render_template(
        "admin/notification_form.html",
        notification=notification,
        users=User.query.filter_by(is_active=True).order_by(User.username).all(),
        form=request.form,
    )


@admin_bp.route("/notifications/<int:id>/delete", methods=["POST"])
def notification_delete(id: int):
    notification = Notification.query.get_or_404(id)
    audit("DELETE_NOTIFICATION", "notification", id, notification.title)
    db.session.delete(notification)
    db.session.commit()
    flash("Notification deleted.", "success")
    return redirect(url_for("admin.notifications"))


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
@admin_bp.route("/audit-logs")
def audit_logs():
    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    action = request.args.get("action", "").strip()
    user_id = request.args.get("user_id", type=int)
    if action:
        query = query.filter(AuditLog.action.like(f"%{action}%"))
    if user_id:
        query = query.filter_by(user_id=user_id)
    return render_template(
        "admin/audit_logs.html",
        logs_page=paginate(query),
        users=User.query.order_by(User.username).all(),
        action=action,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# PDF reports
# ---------------------------------------------------------------------------
@admin_bp.route("/reports")
def reports():
    return render_template(
        "admin/reports.html",
        exams=Examination.query.order_by(Examination.created_at.desc()).all(),
        students=Student.query.filter_by(is_active=True).order_by(Student.student_code).all(),
    )


@admin_bp.route("/reports/exam/<int:exam_id>.pdf")
def exam_report_pdf(exam_id: int):
    exam = Examination.query.get_or_404(exam_id)
    results = Result.query.filter_by(examination_id=exam.id).all()
    if not results:
        flash("No results available for this examination yet.", "warning")
        return redirect(url_for("admin.reports"))
    pdf = generate_exam_report_pdf(exam, results)
    audit("DOWNLOAD_REPORT", "examination", exam.id, "Exam result report PDF")
    db.session.commit()
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"result-report-{exam.course.code}-{exam.id}.pdf",
    )


@admin_bp.route("/reports/marksheet/<int:student_id>/<int:exam_id>.pdf")
def marksheet_pdf(student_id: int, exam_id: int):
    student = Student.query.get_or_404(student_id)
    exam = Examination.query.get_or_404(exam_id)
    result = Result.query.filter_by(student_id=student_id, examination_id=exam_id).first_or_404()
    marks = (
        Mark.query.filter_by(student_id=student_id, examination_id=exam_id)
        .join(Mark.subject)
        .order_by(Subject.code)
        .all()
    )
    pdf = generate_marksheet_pdf(student, exam, result, marks)
    audit("DOWNLOAD_MARKSHEET", "student", student.id, f"{student.student_code} / {exam.name}")
    db.session.commit()
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"marksheet-{student.student_code}-{exam.id}.pdf",
    )
