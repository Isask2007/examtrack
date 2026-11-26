"""ExamTrack application factory."""

from __future__ import annotations

import secrets
from datetime import datetime

from flask import Flask, abort, render_template, request, session
from flask_login import current_user

from .config import Config
from .extensions import db, login_manager
from .models import User
from .utils import csrf_token, page_url, to_float, unread_notification_count


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # ---- CSRF protection for all state-changing requests -----------------
    @app.before_request
    def enforce_csrf():
        if "csrf_token" not in session:
            csrf_token()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            submitted = request.form.get("csrf_token") or request.headers.get(
                "X-CSRF-Token"
            )
            expected = session.get("csrf_token", "")
            if not submitted or not secrets.compare_digest(str(submitted), str(expected)):
                abort(
                    400,
                    description="Your security token expired. Refresh the page and try again.",
                )

    # ---- Template helpers -------------------------------------------------
    @app.context_processor
    def inject_globals():
        return {
            "app_name": "ExamTrack",
            "csrf_token": csrf_token,
            "page_url": page_url,
            "current_year": datetime.utcnow().year,
            "unread_count": (
                unread_notification_count(current_user)
                if current_user.is_authenticated
                else 0
            ),
        }

    @app.template_filter("datefmt")
    def date_filter(value, fmt: str = "%d %b %Y"):
        return value.strftime(fmt) if value else "—"

    @app.template_filter("datetimefmt")
    def datetime_filter(value, fmt: str = "%d %b %Y, %I:%M %p"):
        return value.strftime(fmt) if value else "—"

    @app.template_filter("num")
    def number_filter(value):
        return f"{to_float(value):.2f}"

    @app.template_filter("intcomma")
    def int_filter(value):
        return f"{int(to_float(value)):,}"

    # ---- Error pages ------------------------------------------------------
    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/error.html", code=400, title="Bad Request", message=getattr(error, "description", "Invalid request.")), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/error.html", code=403, title="Access Denied", message="You do not have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/error.html", code=404, title="Page Not Found", message="The page you requested does not exist."), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/error.html", code=500, title="Server Error", message="Something went wrong. Please try again or contact the administrator."), 500

    # ---- Blueprints -------------------------------------------------------
    from .blueprints.auth import auth_bp
    from .blueprints.admin import admin_bp
    from .blueprints.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(student_bp)

    # ---- CLI --------------------------------------------------------------
    from .cli import register_commands

    register_commands(app)

    return app
