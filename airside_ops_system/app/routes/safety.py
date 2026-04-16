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
    return render_template('safety/incident_report.html', incidents=incidents)


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
    return render_template('safety/incident_investigation.html', incidents=incidents)


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
    return render_template('safety/violation_form.html', violations=violations, violation_types=violation_types)


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
    return render_template('safety/spot_check.html', records=records)


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
