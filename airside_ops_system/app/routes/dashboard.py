"""
Dashboard routes and API endpoints for widgets/charts.
"""
from datetime import date
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.models.form import FormSubmission, IssueWorkflow
from app.models.apron import Shift
from app.services.analytics_service import AnalyticsService
from app.services.workflow_service import WorkflowService
from app.services.aodb_sync import AodbSyncService


dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    kpis = AnalyticsService.get_dashboard_kpis()
    recent_submissions = FormSubmission.query.order_by(FormSubmission.created_at.desc()).limit(10).all()
    current_shift = Shift.query.filter_by(status='active').order_by(Shift.created_at.desc()).first()
    workflow_data = WorkflowService.dashboard_data_for_user(current_user)
    today_flights = AodbSyncService.flights_for_date(date.today())
    last_sync = AodbSyncService.last_sync_time()
    return render_template(
        'dashboard.html',
        kpis=kpis,
        recent_submissions=recent_submissions,
        current_shift=current_shift,
        pending_directed=workflow_data['pending_directed'],
        closed_recent=workflow_data['closed_recent'],
        workflow_stats=workflow_data['workflow_stats'],
        role_breakdown=workflow_data['role_breakdown'],
        department_overview=workflow_data['department_overview'],
        today_flights=today_flights,
        last_sync=last_sync,
    )


@dashboard_bp.route('/workflow/<int:issue_id>/advance', methods=['POST'])
@login_required
def advance_issue(issue_id):
    issue = db.session.get(IssueWorkflow, issue_id)
    if not issue:
        flash('Issue workflow item was not found.', 'danger')
        return redirect(url_for('dashboard.index'))

    note = (request.form.get('note') or '').strip()
    ok, message = issue.advance(current_user, note)
    if ok:
        db.session.commit()
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/workflow/<int:issue_id>/close', methods=['POST'])
@login_required
def close_issue(issue_id):
    issue = db.session.get(IssueWorkflow, issue_id)
    if not issue:
        flash('Issue workflow item was not found.', 'danger')
        return redirect(url_for('dashboard.index'))

    note = (request.form.get('closure_notes') or '').strip()
    ok, message = issue.close(current_user, note)
    if ok:
        if issue.submission and issue.submission.status != 'closed':
            issue.submission.status = 'closed'
        db.session.commit()
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/api/kpis')
@login_required
def api_kpis():
    return jsonify(AnalyticsService.get_dashboard_kpis())


@dashboard_bp.route('/api/incident-trend')
@login_required
def api_incident_trend():
    return jsonify(AnalyticsService.incident_trend(7))
