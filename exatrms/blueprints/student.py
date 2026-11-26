"""Student-facing routes: results, marksheets, analytics and notifications."""

from __future__ import annotations

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

from ..extensions import db, login_manager
from ..models import Examination, Mark, Notification, NotificationRead, Result, Subject
from ..pdf import generate_marksheet_pdf
from ..utils import paginate, student_required, to_float, visible_notifications

student_bp = Blueprint("student", __name__, url_prefix="/student")


@student_bp.before_request
def require_student():
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if current_user.role != "student":
        abort(403)


def _profile():
    student = current_user.student
    if not student:
        abort(403, description="No student profile is linked to this account.")
    return student


def _published_results_query(student_id: int):
    return Result.query.join(Result.examination).filter(
        Result.student_id == student_id,
        Examination.is_published.is_(True),
        Result.published_at.isnot(None),
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@student_bp.route("/dashboard")
def dashboard():
    student = _profile()
    results = (
        _published_results_query(student.id)
        .order_by(Examination.created_at.desc())
        .all()
    )
    latest = results[0] if results else None
    percentages = [to_float(r.percentage) for r in results]
    stats = {
        "exams": len(results),
        "average": round(sum(percentages) / len(percentages), 2) if percentages else 0,
        "best": round(max(percentages), 2) if percentages else 0,
        "gpa": to_float(latest.gpa) if latest else 0,
        "passed": sum(1 for r in results if r.status == "pass"),
    }
    notifications = visible_notifications(current_user).limit(5).all()
    return render_template(
        "student/dashboard.html",
        student=student,
        stats=stats,
        results=results[:5],
        latest=latest,
        notifications=notifications,
    )


@student_bp.route("/profile")
def profile():
    return render_template("student/profile.html", student=_profile())


# ---------------------------------------------------------------------------
# Results and marksheets
# ---------------------------------------------------------------------------
@student_bp.route("/results")
def results():
    student = _profile()
    query = _published_results_query(student.id).order_by(Examination.created_at.desc())
    exam_id = request.args.get("exam_id", type=int)
    if exam_id:
        query = query.filter(Result.examination_id == exam_id)
    exams = Examination.query.filter_by(is_published=True).order_by(Examination.created_at.desc()).all()
    return render_template(
        "student/results.html",
        student=student,
        results_page=paginate(query),
        exams=exams,
        exam_id=exam_id,
    )


@student_bp.route("/results/<int:id>")
def result_detail(id: int):
    student = _profile()
    result = _published_results_query(student.id).filter(Result.id == id).first_or_404()
    marks = (
        Mark.query.filter_by(student_id=student.id, examination_id=result.examination_id)
        .join(Mark.subject)
        .order_by(Subject.code)
        .all()
    )
    return render_template("student/result_detail.html", student=student, result=result, marks=marks)


@student_bp.route("/results/<int:id>/marksheet.pdf")
def marksheet_pdf(id: int):
    student = _profile()
    result = _published_results_query(student.id).filter(Result.id == id).first_or_404()
    marks = (
        Mark.query.filter_by(student_id=student.id, examination_id=result.examination_id)
        .join(Mark.subject)
        .order_by(Subject.code)
        .all()
    )
    pdf = generate_marksheet_pdf(student, result.examination, result, marks)
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"marksheet-{student.student_code}-{result.examination_id}.pdf",
    )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@student_bp.route("/analytics")
def analytics():
    student = _profile()
    results = _published_results_query(student.id).all()
    percentages = [to_float(r.percentage) for r in results]
    stats = {
        "count": len(results),
        "passed": sum(1 for r in results if r.status == "pass"),
        "average": round(sum(percentages) / len(percentages), 2) if percentages else 0,
        "best": round(max(percentages), 2) if percentages else 0,
    }
    return render_template(
        "student/analytics.html", student=student, results=results, stats=stats
    )


@student_bp.route("/api/performance")
def api_performance():
    student = _profile()
    results = (
        _published_results_query(student.id)
        .order_by(Examination.created_at)
        .all()
    )
    return jsonify(
        {
            "labels": [r.examination.name for r in results],
            "datasets": [
                {
                    "label": "Percentage",
                    "data": [round(to_float(r.percentage), 2) for r in results],
                    "backgroundColor": "#4f46e5",
                    "borderColor": "#4f46e5",
                    "borderWidth": 2,
                    "fill": True,
                    "tension": 0.35,
                },
                {
                    "label": "Pass Mark",
                    "data": [35] * len(results),
                    "borderColor": "#f43f5e",
                    "borderDash": [6, 4],
                    "borderWidth": 2,
                    "pointRadius": 0,
                    "fill": False,
                },
            ],
        }
    )


@student_bp.route("/api/subjects")
def api_subjects():
    student = _profile()
    result_id = request.args.get("result_id", type=int)
    query = _published_results_query(student.id)
    result = query.filter(Result.id == result_id).first() if result_id else query.order_by(Result.calculated_at.desc()).first()
    labels, data = [], []
    if result:
        marks = (
            Mark.query.filter_by(student_id=student.id, examination_id=result.examination_id)
            .join(Mark.subject)
            .order_by(Subject.code)
            .all()
        )
        labels = [m.subject.code for m in marks]
        data = [round(to_float(m.percentage), 2) for m in marks]
    return jsonify(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "Marks %",
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
@student_bp.route("/notifications")
def notifications():
    query = visible_notifications(current_user)
    return render_template(
        "student/notifications.html",
        notifications=query.all(),
        read_ids={
            row.notification_id
            for row in NotificationRead.query.filter_by(user_id=current_user.id).all()
        },
    )


@student_bp.route("/notifications/<int:id>/read", methods=["POST"])
def notification_read(id: int):
    notification = visible_notifications(current_user).filter_by(id=id).first_or_404()
    existing = NotificationRead.query.filter_by(
        user_id=current_user.id, notification_id=notification.id
    ).first()
    if not existing:
        db.session.add(
            NotificationRead(user_id=current_user.id, notification_id=notification.id)
        )
        db.session.commit()
    return redirect(request.referrer or url_for("student.notifications"))


@student_bp.route("/notifications/read-all", methods=["POST"])
def notification_read_all():
    unread = visible_notifications(current_user).filter(
        ~Notification.reads.any(NotificationRead.user_id == current_user.id)
    ).all()
    for notification in unread:
        db.session.add(
            NotificationRead(user_id=current_user.id, notification_id=notification.id)
        )
    db.session.commit()
    flash(f"Marked {len(unread)} notification(s) as read.", "success")
    return redirect(url_for("student.notifications"))
