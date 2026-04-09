"""
Dashboard routes and API endpoints for widgets/charts.
"""
from flask import Blueprint, jsonify, render_template
from flask_login import login_required
from app.models.form import FormSubmission
from app.models.apron import Shift
from app.services.analytics_service import AnalyticsService


dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    kpis = AnalyticsService.get_dashboard_kpis()
    recent_submissions = FormSubmission.query.order_by(FormSubmission.created_at.desc()).limit(10).all()
    current_shift = Shift.query.filter_by(status='active').order_by(Shift.created_at.desc()).first()
    return render_template(
        'dashboard.html',
        kpis=kpis,
        recent_submissions=recent_submissions,
        current_shift=current_shift,
    )


@dashboard_bp.route('/api/kpis')
@login_required
def api_kpis():
    return jsonify(AnalyticsService.get_dashboard_kpis())


@dashboard_bp.route('/api/incident-trend')
@login_required
def api_incident_trend():
    return jsonify(AnalyticsService.incident_trend(7))
