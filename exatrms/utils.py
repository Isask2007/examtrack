"""Shared helpers: grading, validation, auditing, access control, analytics."""

from __future__ import annotations

import re
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import abort, current_app, has_request_context, request, session, url_for
from flask_login import current_user
from sqlalchemy import or_

from .extensions import db, login_manager
from .models import (
    AuditLog,
    Mark,
    Notification,
    NotificationRead,
    Result,
    Subject,
)

# ---------------------------------------------------------------------------
# Grading rules (can be changed in one place)
# ---------------------------------------------------------------------------
PASS_PERCENTAGE = 35.0

GRADE_SCALE = (
    (90.0, "O", 10.0),
    (80.0, "A+", 9.0),
    (70.0, "A", 8.0),
    (60.0, "B+", 7.0),
    (50.0, "B", 6.0),
    (40.0, "C", 5.0),
    (35.0, "D", 4.0),
    (0.0, "F", 0.0),
)


def to_float(value) -> float:
    """Convert Decimal/None database values to plain floats for charts/JSON."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def round2(value) -> float:
    return round(to_float(value), 2)


def calculate_grade(percentage: float) -> tuple[str, float, str]:
    """Return (letter grade, grade point, pass/fail) for a percentage."""
    percentage = to_float(percentage)
    for threshold, grade, points in GRADE_SCALE:
        if percentage >= threshold:
            status = "pass" if percentage >= PASS_PERCENTAGE else "fail"
            return grade, points, status
    return "F", 0.0, "fail"


def current_academic_year(today: date | None = None) -> str:
    today = today or date.today()
    if today.month >= 6:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    return f"{today.year - 1}-{str(today.year)[-2:]}"


# ---------------------------------------------------------------------------
# Access control and auditing
# ---------------------------------------------------------------------------
def role_required(*roles: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


admin_required = role_required("admin")
student_required = role_required("student")


def audit(
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: str | None = None,
) -> AuditLog:
    """Stage an audit record in the current session (caller commits)."""
    entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    if has_request_context():
        entry.ip_address = request.remote_addr
        user_agent = request.headers.get("User-Agent", "")
        entry.user_agent = user_agent[:255]
    db.session.add(entry)
    return entry


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,50}$")
NAME_RE = re.compile(r"^[A-Za-zÀ-ÿ' .-]{2,80}$")
PHONE_RE = re.compile(r"^[0-9+\-() ]{7,20}$")


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))


def valid_username(value: str) -> bool:
    return bool(USERNAME_RE.match(value.strip()))


def valid_name(value: str) -> bool:
    return bool(NAME_RE.match(value.strip()))


def valid_phone(value: str) -> bool:
    return not value.strip() or bool(PHONE_RE.match(value.strip()))


def valid_password(value: str) -> bool:
    return (
        len(value) >= 8
        and bool(re.search(r"[A-Za-z]", value))
        and bool(re.search(r"\d", value))
    )


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_decimal(value: str) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


# ---------------------------------------------------------------------------
# Result calculation
# ---------------------------------------------------------------------------
def recalculate_result(student_id: int, examination_id: int) -> Result | None:
    """Recalculate one student's result from stored marks (never hardcoded)."""
    marks = Mark.query.filter_by(
        student_id=student_id, examination_id=examination_id
    ).all()

    existing = Result.query.filter_by(
        student_id=student_id, examination_id=examination_id
    ).first()

    if not marks:
        if existing:
            db.session.delete(existing)
        return None

    obtained = sum((Decimal(str(m.marks_obtained)) for m in marks), Decimal("0"))
    total = sum((Decimal(str(m.max_marks)) for m in marks), Decimal("0"))
    percentage = float(obtained / total * 100) if total else 0.0
    grade, _, status = calculate_grade(percentage)

    weighted_points = 0.0
    credits = 0
    for mark in marks:
        subject = Subject.query.get(mark.subject_id)
        credit = subject.credits if subject else 0
        weighted_points += to_float(mark.grade_points) * credit
        credits += credit

    gpa = weighted_points / credits if credits else 0.0
    if any(m.status == "fail" for m in marks):
        status = "fail"

    result = existing or Result(student_id=student_id, examination_id=examination_id)
    result.obtained_marks = obtained
    result.total_marks = total
    result.percentage = round(percentage, 2)
    result.grade = grade
    result.gpa = round(gpa, 2)
    result.status = status
    db.session.add(result)
    return result


def update_ranks(examination_id: int) -> None:
    """Assign dense ranks using percentage then obtained marks as tie-breaker."""
    results = (
        Result.query.filter_by(examination_id=examination_id)
        .order_by(Result.percentage.desc(), Result.obtained_marks.desc())
        .all()
    )
    previous_key = None
    rank = 0
    for index, result in enumerate(results, start=1):
        key = (to_float(result.percentage), to_float(result.obtained_marks))
        if key != previous_key:
            rank = index
            previous_key = key
        result.rank = rank


def recalculate_exam_results(examination_id: int) -> int:
    """Recalculate every result for an examination and refresh ranks."""
    student_ids = [
        row[0]
        for row in db.session.query(Mark.student_id)
        .filter(Mark.examination_id == examination_id)
        .distinct()
        .all()
    ]
    for student_id in student_ids:
        recalculate_result(student_id, examination_id)
    db.session.flush()
    update_ranks(examination_id)
    return len(student_ids)


# ---------------------------------------------------------------------------
# Notifications and misc
# ---------------------------------------------------------------------------
def visible_notifications(user):
    """Notifications targeted at a user plus global/role-wide notices."""
    audience = "students" if user.role == "student" else "admins"
    return Notification.query.filter(
        Notification.is_active.is_(True),
        or_(
            Notification.audience == "all",
            Notification.audience == audience,
            Notification.user_id == user.id,
        ),
    ).order_by(Notification.created_at.desc())


def unread_notification_count(user) -> int:
    return visible_notifications(user).filter(
        ~Notification.reads.any(NotificationRead.user_id == user.id)
    ).count()


def paginate(query, per_page: int | None = None):
    page = request.args.get("page", 1, type=int)
    size = per_page or current_app.config.get("PAGE_SIZE", 10)
    return query.paginate(page=page, per_page=size, error_out=False)


def safe_next_url(target: str | None) -> str | None:
    """Only allow local relative redirect targets."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def csrf_token() -> str:
    """Return (creating if needed) the per-session CSRF token."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def page_url(page: int) -> str:
    """Build a pagination link that keeps current filters."""
    args = request.args.to_dict()
    args["page"] = page
    return url_for(request.endpoint, **(request.view_args or {}), **args)
