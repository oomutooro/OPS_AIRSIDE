"""
Safety routes: incidents, violations, investigations, FOD walks.
"""
from datetime import date, datetime
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.models.form import FormSubmission, FormTemplate
from app.models.incident import Incident, Violation, ViolationType
from app.models.inspection import FODWalk
from app.services.workflow_service import WorkflowService

safety_bp = Blueprint('safety', __name__)


def _page_overview(title, subtitle, summary_cards, related_reports, add_href='#new-report-form', add_label='Insert New Report'):
    return {
        'title': title,
        'subtitle': subtitle,
        'summary_cards': summary_cards,
        'related_reports': related_reports,
        'add_href': add_href,
        'add_label': add_label,
        'list_caption': 'Latest related reports and their current status',
    }


def _status_tone(status):
    return {
        'open': 'warning',
        'draft': 'secondary',
        'submitted': 'primary',
        'under_review': 'info',
        'under_investigation': 'info',
        'closed': 'success',
        'complete': 'success',
    }.get((status or '').lower(), 'secondary')


@safety_bp.route('/overview')
@login_required
def overview():
    incident_total = Incident.query.count()
    open_incidents = Incident.query.filter(Incident.status.in_(['open', 'under_investigation', 'under_review'])).count()
    violation_total = Violation.query.filter_by(form_type='form_15').count()
    spot_check_total = Violation.query.filter_by(form_type='form_16').count()

    sections = [
        {
            'title': 'Incidents',
            'description': 'Capture, review, and monitor incident reports from initial submission through close-out.',
            'badge': f'{incident_total} total',
            'links': [
                {'label': 'Incident Reports', 'url': url_for('safety.incident_report'), 'meta': 'Form 10 workspace'},
                {'label': 'Investigations', 'url': url_for('safety.incident_investigation'), 'meta': 'Form 11 workspace'},
            ],
            'action': {'label': 'Add Incident Report', 'url': url_for('safety.incident_report')},
        },
        {
            'title': 'Violations and Spot Checks',
            'description': 'Track enforcement reports, penalties, and on-spot observations from the same dashboard area.',
            'badge': f'{violation_total + spot_check_total} total',
            'links': [
                {'label': 'Violations', 'url': url_for('safety.violation_form'), 'meta': 'Form 15 workspace'},
                {'label': 'Spot Checks', 'url': url_for('safety.spot_check'), 'meta': 'Form 16 workspace'},
                {'label': 'FOD Walk Schedule', 'url': url_for('safety.fod_walk_schedule'), 'meta': 'Campaign planning'},
            ],
            'action': {'label': 'Add Violation Report', 'url': url_for('safety.violation_form')},
        },
    ]

    return render_template(
        'shared/section_overview.html',
        overview_title='Safety Dashboard',
        overview_subtitle='Use each report family as an overview heading, then go deeper into incidents, investigations, violations, and spot checks.',
        summary_cards=[
            {'label': 'Open Incidents', 'value': open_incidents, 'help_text': 'Incidents still being processed or investigated'},
            {'label': 'All Incidents', 'value': incident_total, 'help_text': 'Captured incident records'},
            {'label': 'Violations', 'value': violation_total, 'help_text': 'Recorded Form 15 enforcement reports'},
            {'label': 'Spot Checks', 'value': spot_check_total, 'help_text': 'Recorded Form 16 observations'},
        ],
        sections=sections,
        primary_action={'label': 'Add Incident Report', 'url': url_for('safety.incident_report')},
    )


@safety_bp.route('/incident-report', methods=['GET', 'POST'])
@login_required
def incident_report():
    if request.method == 'POST':
        occurrence_time_raw = (request.form.get('occurrence_time') or '').strip()
        occurrence_time = None
        if occurrence_time_raw:
            try:
                occurrence_time = datetime.strptime(occurrence_time_raw, '%H:%M').time()
            except ValueError:
                occurrence_time = None

        company_airline = (request.form.get('company_airline') or '').strip()
        operator = (request.form.get('operator') or '').strip()
        aircraft_equipment_reg_no = (request.form.get('aircraft_equipment_reg_no') or '').strip()
        aircraft_equipment_type = (request.form.get('aircraft_equipment_type') or '').strip()
        weather = (request.form.get('weather') or '').strip()
        phase_of_operation = (request.form.get('phase_of_operation') or '').strip()

        incident = Incident(
            report_date=date.today(),
            occurrence_date=request.form.get('occurrence_date') or date.today(),
            occurrence_time=occurrence_time,
            location=request.form.get('location'),
            incident_type=request.form.get('incident_type', 'incident'),
            severity=request.form.get('severity', 'minor'),
            description=request.form.get('description'),
            sequence_of_events=request.form.get('sequence_of_events'),
            immediate_actions_taken=request.form.get('immediate_actions'),
            airline_operator=operator or company_airline or None,
            flight_number=(request.form.get('flight_no') or '').strip() or None,
            aircraft_registration=aircraft_equipment_reg_no or None,
            aircraft_type=aircraft_equipment_type or None,
            weather_conditions={
                'weather': weather,
                'phase_of_operation': phase_of_operation,
            },
            reported_by_user_id=current_user.id,
            reported_at=datetime.utcnow(),
            operator_report_submitted=True,
            status='open',
        )
        incident.set_reporting_deadlines()
        db.session.add(incident)

        template = FormTemplate.query.filter_by(form_number=10).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref=incident.location,
                data=request.form.to_dict(flat=True),
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)

        db.session.commit()
        flash('Incident report submitted.', 'success')
        return redirect(url_for('safety.incident_report'))

    incidents = Incident.query.order_by(Incident.created_at.desc()).limit(20).all()
    critical_incidents = Incident.query.filter_by(severity='critical').count()
    page_overview = _page_overview(
        'Incident Reports Workspace',
        'See the current incident workload before entering a new incident report below.',
        [
            {'label': 'Total Incidents', 'value': Incident.query.count(), 'help_text': 'All incident reports on record'},
            {'label': 'Open Cases', 'value': Incident.query.filter(Incident.status.in_(['open', 'under_investigation', 'under_review'])).count(), 'help_text': 'Cases still awaiting closure'},
            {'label': 'Critical', 'value': critical_incidents, 'help_text': 'Critical severity incidents logged'},
            {'label': 'Latest Status', 'value': incidents[0].status.replace('_', ' ').title() if incidents else 'None', 'help_text': incidents[0].created_at.strftime('%d %b %Y %H:%M') if incidents else 'No incidents yet'},
        ],
        [
            {
                'reference': incident.incident_number or f'INC-{incident.id}',
                'title': incident.location or 'Incident report',
                'meta': (incident.incident_type or 'incident').replace('_', ' ').title(),
                'status_label': (incident.status or 'open').replace('_', ' ').title(),
                'status_tone': _status_tone(incident.status),
                'workflow_label': (incident.severity or 'normal').title(),
                'workflow_tone': 'danger' if incident.severity == 'critical' else 'secondary',
                'updated_at': incident.created_at.strftime('%d %b %Y %H:%M') if incident.created_at else '-',
            }
            for incident in incidents[:6]
        ],
    )
    return render_template('safety/incident_report.html', incidents=incidents, page_overview=page_overview)


@safety_bp.route('/incident-investigation', methods=['GET', 'POST'])
@login_required
def incident_investigation():
    if request.method == 'POST':
        incident_id = request.form.get('incident_id')
        incident = db.session.get(Incident, int(incident_id)) if incident_id else None
        if incident:
            incident.investigation_findings = request.form.get('investigation_findings')
            incident.probable_cause = request.form.get('probable_cause')
            incident.status = 'under_review'
            incident.investigator_user_id = current_user.id
            db.session.commit()
            flash('Investigation details saved.', 'success')
        else:
            flash('Incident not found.', 'danger')
        return redirect(url_for('safety.incident_investigation'))

    incidents = Incident.query.filter(Incident.status.in_(['open', 'under_investigation', 'under_review'])).all()
    page_overview = _page_overview(
        'Investigation Workspace',
        'Review all active cases first, then capture findings for the selected incident.',
        [
            {'label': 'Active Cases', 'value': len(incidents), 'help_text': 'Incidents still under investigation or review'},
            {'label': 'Open', 'value': sum(1 for incident in incidents if incident.status == 'open'), 'help_text': 'Not yet picked up for investigation'},
            {'label': 'Under Review', 'value': sum(1 for incident in incidents if incident.status == 'under_review'), 'help_text': 'Investigation findings already submitted'},
            {'label': 'Investigator Load', 'value': len({incident.investigator_user_id for incident in incidents if incident.investigator_user_id}), 'help_text': 'Investigators currently assigned'},
        ],
        [
            {
                'reference': incident.incident_number or f'INC-{incident.id}',
                'title': incident.location or 'Investigation case',
                'meta': (incident.incident_type or 'incident').replace('_', ' ').title(),
                'status_label': (incident.status or 'open').replace('_', ' ').title(),
                'status_tone': _status_tone(incident.status),
                'workflow_label': 'Investigation',
                'workflow_tone': 'info',
                'updated_at': incident.updated_at.strftime('%d %b %Y %H:%M') if incident.updated_at else '-',
            }
            for incident in incidents[:6]
        ],
        add_label='Insert Investigation Record',
    )
    return render_template('safety/incident_investigation.html', incidents=incidents, page_overview=page_overview)


@safety_bp.route('/violation', methods=['GET', 'POST'])
@login_required
def violation_form():
    if request.method == 'POST':
        vt = request.form.get('violation_type_id')
        violation = Violation(
            form_type='form_15',
            offender_name=request.form.get('offender_name'),
            offender_badge=request.form.get('offender_badge'),
            vehicle_registration=request.form.get('vehicle_registration'),
            violation_type_id=int(vt) if vt else None,
            violation_description=request.form.get('violation_description'),
            violation_location=request.form.get('violation_location'),
            violation_date=date.today(),
            issuing_officer_user_id=current_user.id,
            issuing_officer_name=current_user.full_name,
            penalty_amount=float(request.form.get('penalty_amount') or 0),
            penalty_currency=request.form.get('penalty_currency', 'UGX'),
            status='open',
        )
        db.session.add(violation)

        template = FormTemplate.query.filter_by(form_number=15).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref=violation.violation_location,
                data=request.form.to_dict(flat=True),
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)

        db.session.commit()
        flash('Violation recorded.', 'success')
        return redirect(url_for('safety.violation_form'))

    violations = Violation.query.order_by(Violation.created_at.desc()).limit(20).all()
    violation_types = ViolationType.query.filter_by(is_active=True).order_by(ViolationType.description).all()
    page_overview = _page_overview(
        'Violations Workspace',
        'Track issued violations, their status, and then add a new violation below.',
        [
            {'label': 'Total Violations', 'value': Violation.query.filter_by(form_type='form_15').count(), 'help_text': 'All Form 15 records'},
            {'label': 'Open Cases', 'value': Violation.query.filter_by(form_type='form_15', status='open').count(), 'help_text': 'Violations still unresolved'},
            {'label': 'Violation Types', 'value': len(violation_types), 'help_text': 'Configured active violation categories'},
            {'label': 'Latest Record', 'value': violations[0].created_at.strftime('%d %b') if violations else 'None', 'help_text': violations[0].offender_name if violations else 'No violations yet'},
        ],
        [
            {
                'reference': f'VIO-{violation.id}',
                'title': violation.offender_name or 'Violation report',
                'meta': violation.violation_location or 'Airside',
                'status_label': (violation.status or 'open').replace('_', ' ').title(),
                'status_tone': _status_tone(violation.status),
                'workflow_label': 'Enforcement',
                'workflow_tone': 'danger',
                'updated_at': violation.created_at.strftime('%d %b %Y %H:%M') if violation.created_at else '-',
            }
            for violation in violations[:6]
        ],
    )
    return render_template('safety/violation_form.html', violations=violations, violation_types=violation_types, page_overview=page_overview)


@safety_bp.route('/spot-check', methods=['GET', 'POST'])
@login_required
def spot_check():
    if request.method == 'POST':
        violation = Violation(
            form_type='form_16',
            offender_name=request.form.get('offender_name'),
            offender_badge=request.form.get('offender_badge'),
            vehicle_registration=request.form.get('vehicle_registration'),
            violation_description=request.form.get('observation'),
            violation_location=request.form.get('location'),
            violation_date=date.today(),
            issuing_officer_user_id=current_user.id,
            issuing_officer_name=current_user.full_name,
            status='open',
        )
        db.session.add(violation)

        template = FormTemplate.query.filter_by(form_number=16).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref=violation.violation_location,
                data=request.form.to_dict(flat=True),
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)

        db.session.commit()
        flash('Spot check report captured.', 'success')
        return redirect(url_for('safety.spot_check'))

    records = Violation.query.filter_by(form_type='form_16').order_by(Violation.created_at.desc()).limit(20).all()
    page_overview = _page_overview(
        'Spot Check Workspace',
        'See all spot check reports already inserted, then add the next report from the form below.',
        [
            {'label': 'Total Spot Checks', 'value': Violation.query.filter_by(form_type='form_16').count(), 'help_text': 'All Form 16 observations'},
            {'label': 'Open Follow-up', 'value': Violation.query.filter_by(form_type='form_16', status='open').count(), 'help_text': 'Spot checks still awaiting action'},
            {'label': 'Closed', 'value': Violation.query.filter_by(form_type='form_16', status='closed').count(), 'help_text': 'Spot checks already cleared'},
            {'label': 'Latest Record', 'value': records[0].created_at.strftime('%d %b') if records else 'None', 'help_text': records[0].offender_name if records else 'No records yet'},
        ],
        [
            {
                'reference': f'SPOT-{record.id}',
                'title': record.offender_name or 'Spot check',
                'meta': record.violation_location or 'Airside',
                'status_label': (record.status or 'open').replace('_', ' ').title(),
                'status_tone': _status_tone(record.status),
                'workflow_label': 'Observation',
                'workflow_tone': 'warning',
                'updated_at': record.created_at.strftime('%d %b %Y %H:%M') if record.created_at else '-',
            }
            for record in records[:6]
        ],
    )
    return render_template('safety/spot_check.html', records=records, page_overview=page_overview)


@safety_bp.route('/fod-walk-schedule', methods=['GET', 'POST'])
@login_required
def fod_walk_schedule():
    if request.method == 'POST':
        walk = FODWalk(
            walk_date=request.form.get('walk_date') or date.today(),
            quarter=request.form.get('quarter'),
            year=int(request.form.get('year') or date.today().year),
            participants=[],
            areas_covered=request.form.getlist('areas_covered'),
            organized_by=current_user.full_name,
            organized_by_user_id=current_user.id,
            status='draft',
        )
        db.session.add(walk)
        db.session.commit()
        flash('FOD walk scheduled.', 'success')
        return redirect(url_for('safety.fod_walk_schedule'))

    walks = FODWalk.query.order_by(FODWalk.walk_date.desc()).limit(20).all()
    return render_template('safety/fod_walk_schedule.html', walks=walks)
