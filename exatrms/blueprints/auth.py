"""Authentication, session and account settings routes."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import User
from ..utils import audit, safe_next_url, valid_password

auth_bp = Blueprint("auth", __name__)


def _dashboard_url(user: User) -> str:
    return url_for("admin.dashboard") if user.role == "admin" else url_for("student.dashboard")


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(_dashboard_url(current_user))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_dashboard_url(current_user))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter(
            or_(User.username == identifier, User.email == identifier)
        ).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid username/email or password.", "danger")
        elif not user.is_active:
            flash("This account has been deactivated. Contact the administrator.", "warning")
        else:
            user.last_login_at = datetime.utcnow()
            login_user(user, remember=remember)
            audit("LOGIN", "user", user.id, f"Signed in as {user.role}")
            db.session.commit()
            flash(f"Welcome back, {user.display_name}!", "success")
            target = safe_next_url(request.args.get("next"))
            return redirect(target or _dashboard_url(user))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("LOGOUT", "user", current_user.id, "Signed out")
    db.session.commit()
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(current_user.password_hash, current_password):
            flash("Your current password is incorrect.", "danger")
        elif not valid_password(new_password):
            flash("New password must be at least 8 characters and contain letters and numbers.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        else:
            current_user.password_hash = generate_password_hash(new_password)
            audit("PASSWORD_CHANGE", "user", current_user.id, "Changed account password")
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for("auth.settings"))

    return render_template("auth/settings.html")
