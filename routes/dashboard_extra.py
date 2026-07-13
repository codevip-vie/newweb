from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

extra_bp = Blueprint("dashboard_extra", __name__, url_prefix="/dashboard")


@extra_bp.route("/feature-overview")
@login_required
def feature_overview():
    return render_template("dashboard/feature_overview.html")
