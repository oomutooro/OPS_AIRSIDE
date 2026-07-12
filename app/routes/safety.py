"""
Safety routes: incidents, violations, investigations, FOD walks.
"""
from datetime import date, datetime
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from app import db
from app.models.form import FormSubmission, FormTemplate
from app.models.incident import Incident, Violation, ViolationType
from app.models.permit import ADPProfile
from app.models.inspection import FODWalk
from app.models.reference import AirsideVehicle, Company
from app.services.workflow_service import WorkflowService

safety_bp = Blueprint('safety', __name__)


def _normalize_adp_number(value: str | None) -> str:
    return (value or '').strip().upper()


def _offender_level_from_violation_count(violation_count: int) -> str:
    if violation_count >= 3:
        return 'third_offender'
    if violation_count == 2:
        return 'second_offender'
    if violation_count == 1:
        return 'first_offender'
    return 'no_prior_offence'


def _offender_penalty_multiplier(violation_count: int) -> float:
    """Escalate penalties for repeat offenders."""
    if violation_count >= 3:
        return 1.5
    if violation_count == 2:
        return 1.25
    return 1.0


def _parse_optional_time(value: str | None):
    raw = (value or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%H:%M').time()
    except ValueError:
        return None


def _parse_optional_date(value: str | None):
    raw = (value or '').strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _manual_follow_up_action(offence_number: int) -> str:
    if offence_number >= 3:
        return 'Third punch reached: forward ADP/ASP to MO for suspension and further action.'
    if offence_number == 2:
        return 'Second punch: maintain violation records and monitor for escalation.'
    if offence_number == 1:
        return 'First punch: issue violation form and applicable penalty.'
    return 'No action required.'


def _penalty_for_violation_type(vt: ViolationType | None, unit_quantity: float | None = None) -> tuple[float, str]:
    if not vt:
        return 0.0, 'UGX'

    currency = (vt.penalty_currency or 'UGX').upper()
    if currency == 'USD':
        base = float(vt.standard_penalty_usd or 0)
    else:
        currency = 'UGX'
        base = float(vt.standard_penalty_ugx or 0)

    if vt.is_per_unit:
        qty = unit_quantity if unit_quantity and unit_quantity > 0 else 1.0
        return round(base * qty, 2), currency
    return round(base, 2), currency


def _incident_records_for_adp(adp_number: str, person_name: str | None = None) -> list[Incident]:
    adp = _normalize_adp_number(adp_number)
    records = {}

    if person_name:
        name_matches = Incident.query.filter_by(vehicle_operator_name=person_name).all()
        for incident in name_matches:
            records[incident.id] = incident

    if adp:
        tagged_incidents = Incident.query.filter(Incident.weather_conditions.isnot(None)).all()
        for incident in tagged_incidents:
            payload = incident.weather_conditions if isinstance(incident.weather_conditions, dict) else {}
            tagged_adp = _normalize_adp_number(payload.get('involved_adp_number'))
            if tagged_adp and tagged_adp == adp:
                records[incident.id] = incident

    return sorted(records.values(), key=lambda item: item.occurrence_date or date.min, reverse=True)


def _violation_records_for_adp(adp_number: str) -> list[Violation]:
    adp = _normalize_adp_number(adp_number)
    if not adp:
        return []
    return Violation.query.filter(
        func.upper(Violation.offender_adp_number) == adp
    ).order_by(Violation.violation_date.desc(), Violation.id.desc()).all()


def _vehicle_non_compliance(vehicle: AirsideVehicle | None) -> tuple[str | None, str | None]:
    """Return violation code and message when vehicle should not be operating."""
    if not vehicle:
        return None, None

    if vehicle.is_grounded or not vehicle.is_active:
        return 'dangerous_mechanical_condition', 'Vehicle is grounded/inactive per ESSAT and must not be operated.'

    if not vehicle.last_essat_date:
        return 'no_essat_sticker', 'Vehicle has no ESSAT inspection record and must not be operated.'

    return None, None


def _create_vehicle_use_violation(
    vehicle_registration: str,
    offender_name: str | None,
    offender_adp_number: str | None,
    location: str | None,
    message: str,
    code: str,
):
    vt = ViolationType.query.filter_by(code=code, is_active=True).first()
    penalty_amount, penalty_currency = _penalty_for_violation_type(vt, None)

    violation = Violation(
        form_type='form_16',
        offender_name=offender_name,
        offender_adp_number=offender_adp_number,
        vehicle_registration=vehicle_registration,
        violation_type_id=vt.id if vt else None,
        violation_description=message,
        violation_location=location,
        violation_date=date.today(),
        issuing_officer_user_id=current_user.id,
        issuing_officer_name=current_user.full_name,
        issuing_officer_badge=current_user.badge_number,
        penalty_amount=penalty_amount,
        penalty_currency=penalty_currency,
        status='open',
        notes='Auto-generated from vehicle-use validation against ESSAT status.',
    )
    db.session.add(violation)
    return violation


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
        'adp_punched': 'danger',
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
        involved_adp_number = _normalize_adp_number(request.form.get('involved_adp_number'))
        matched_profile = ADPProfile.query.filter(
            func.upper(ADPProfile.adp_number) == involved_adp_number
        ).first() if involved_adp_number else None
        involved_person_name = (request.form.get('involved_person_name') or '').strip()
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
            vehicle_operator_name=involved_person_name or (matched_profile.full_name if matched_profile else None),
            weather_conditions={
                'weather': weather,
                'phase_of_operation': phase_of_operation,
                'involved_adp_number': involved_adp_number or None,
            },
            reported_by_user_id=current_user.id,
            reported_at=datetime.utcnow(),
            operator_report_submitted=True,
            status='open',
        )
        incident.set_reporting_deadlines()
        db.session.add(incident)

        possible_vehicle = AirsideVehicle.query.filter(
            func.upper(AirsideVehicle.registration) == aircraft_equipment_reg_no.upper()
        ).first() if aircraft_equipment_reg_no else None
        non_compliance_code, non_compliance_message = _vehicle_non_compliance(possible_vehicle)
        if non_compliance_code and non_compliance_message:
            _create_vehicle_use_violation(
                vehicle_registration=aircraft_equipment_reg_no,
                offender_name=involved_person_name or operator,
                offender_adp_number=involved_adp_number or None,
                location=(request.form.get('location') or '').strip() or None,
                message=non_compliance_message,
                code=non_compliance_code,
            )
            flash('ESSAT rule applied: vehicle is not fit for operation, and a violation has been logged.', 'warning')

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
        vt_id = int(vt) if vt and vt.isdigit() else None
        violation_type = db.session.get(ViolationType, vt_id) if vt_id else None

        offender_adp_number = _normalize_adp_number(request.form.get('offender_adp_number')) or None
        offender_company_id_raw = request.form.get('offender_company_id')
        offender_company_id = int(offender_company_id_raw) if offender_company_id_raw and offender_company_id_raw.isdigit() else None
        matched_profile = ADPProfile.query.filter(
            func.upper(ADPProfile.adp_number) == offender_adp_number
        ).first() if offender_adp_number else None

        unit_quantity_raw = (request.form.get('unit_quantity') or '').strip()
        try:
            unit_quantity = float(unit_quantity_raw) if unit_quantity_raw else None
        except ValueError:
            unit_quantity = None

        prior_violation_count = len(_violation_records_for_adp(offender_adp_number)) if offender_adp_number else 0
        current_offence_number = prior_violation_count + 1
        offender_level = _offender_level_from_violation_count(current_offence_number)
        offence_action = _manual_follow_up_action(current_offence_number)
        penalty_amount, penalty_currency = _penalty_for_violation_type(violation_type, unit_quantity)
        violation_date = _parse_optional_date(request.form.get('violation_date')) or date.today()
        violation_time = _parse_optional_time(request.form.get('violation_time'))

        offender_name = (request.form.get('offender_name') or '').strip() or (matched_profile.full_name if matched_profile else None)
        nature_of_violation = (request.form.get('nature_of_violation') or '').strip()
        cause_of_violation = (request.form.get('cause_of_violation') or '').strip()
        violation_description = (request.form.get('violation_description') or '').strip() or nature_of_violation or (violation_type.description if violation_type else '')

        awareness = (request.form.get('aware_of_violation') or '').strip().lower() or 'unspecified'
        last_training = _parse_optional_date(request.form.get('last_training_date'))
        trained_by = (request.form.get('trained_by') or '').strip()
        offender_statement = (
            f"Awareness: {awareness}. "
            f"Last training: {last_training.isoformat() if last_training else 'not provided'}. "
            f"Trainer: {trained_by or 'not provided'}."
        )

        enforcer_remark = (request.form.get('enforcer_remark') or '').strip()
        soo_remark = (request.form.get('soo_remark') or '').strip()
        weather = (request.form.get('weather') or '').strip()
        other_names = (request.form.get('other_names') or '').strip()
        designation = (request.form.get('designation') or '').strip()
        organization_name = (request.form.get('organization_name') or '').strip()
        enforcer_surname = (request.form.get('enforcer_surname') or '').strip()
        enforcer_other_names = (request.form.get('enforcer_other_names') or '').strip()
        soo_surname = (request.form.get('soo_surname') or '').strip()
        soo_other_names = (request.form.get('soo_other_names') or '').strip()
        notes_lines = [
            f"Offence tier: {offender_level.replace('_', ' ')} (occurrence #{current_offence_number}).",
            f"Enforcement action: {offence_action}",
            f"Weather: {weather or 'not recorded'}.",
            f"Offender other names: {other_names or 'not provided'}.",
            f"Organization: {organization_name or 'not provided'}.",
            f"Designation: {designation or 'not provided'}.",
            f"Cause of violation: {cause_of_violation or 'not provided'}.",
            f"Enforcer remarks: {enforcer_remark or 'none'} (Surname: {enforcer_surname or '-'}, Other names: {enforcer_other_names or '-'})",
            f"SOO remarks: {soo_remark or 'none'} (Surname: {soo_surname or '-'}, Other names: {soo_other_names or '-'})",
        ]

        company_id_to_use = offender_company_id or (matched_profile.company_id if matched_profile else None)

        violation = Violation(
            form_type='form_15',
            offender_name=offender_name,
            offender_badge=(request.form.get('offender_badge') or '').strip() or None,
            offender_adp_number=offender_adp_number,
            offender_company_id=company_id_to_use,
            vehicle_registration=(request.form.get('vehicle_registration') or '').strip() or None,
            violation_type_id=vt_id,
            violation_description=violation_description,
            violation_location=(request.form.get('violation_location') or '').strip() or None,
            violation_date=violation_date,
            violation_time=violation_time,
            issuing_officer_user_id=current_user.id,
            issuing_officer_name=(request.form.get('enforcer_display_name') or '').strip() or current_user.full_name,
            issuing_officer_badge=current_user.badge_number,
            penalty_amount=penalty_amount,
            penalty_currency=penalty_currency,
            unit_quantity=unit_quantity,
            status='adp_punched' if offender_adp_number and current_offence_number >= 3 else 'open',
            adp_punched=bool(offender_adp_number),
            offender_acknowledgement=offender_statement,
            offender_signature=(request.form.get('offender_signature_name') or '').strip() or None,
            offender_acknowledgement_date=datetime.utcnow(),
            employer_name=f"{soo_surname} {soo_other_names}".strip() or None,
            employer_title='UCAA SOO/AS/SC Remarks',
            employer_signature=(request.form.get('soo_signature_name') or '').strip() or None,
            notes='\n'.join(notes_lines),
        )
        db.session.add(violation)

        template = FormTemplate.query.filter_by(form_number=15).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref=violation.violation_location,
                data=request.form.to_dict(flat=False),
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)

        db.session.commit()
        if offender_adp_number:
            if current_offence_number >= 3:
                flash('Violation recorded. Third offender reached three punches; forward ADP/ASP for suspension action as per manual.', 'warning')
            elif current_offence_number == 2:
                flash('Violation recorded. Second offender logged; second punch action captured.', 'warning')
            else:
                flash('Violation recorded. First offender logged with first punch and manual penalty.', 'success')
        else:
            flash('Violation recorded with manual penalty schedule.', 'success')
        return redirect(url_for('safety.violation_form'))

    violations = Violation.query.order_by(Violation.created_at.desc()).limit(20).all()
    violation_types = ViolationType.query.filter_by(is_active=True).order_by(ViolationType.description).all()
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
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
    return render_template(
        'safety/violation_form.html',
        violations=violations,
        violation_types=violation_types,
        companies=companies,
        today=date.today().isoformat(),
        page_overview=page_overview,
    )


@safety_bp.route('/spot-check', methods=['GET', 'POST'])
@login_required
def spot_check():
    if request.method == 'POST':
        offender_adp_number = _normalize_adp_number(request.form.get('offender_adp_number')) or None
        matched_profile = ADPProfile.query.filter(
            func.upper(ADPProfile.adp_number) == offender_adp_number
        ).first() if offender_adp_number else None
        violation = Violation(
            form_type='form_16',
            offender_name=request.form.get('offender_name'),
            offender_badge=request.form.get('offender_badge'),
            offender_adp_number=offender_adp_number,
            offender_company_id=matched_profile.company_id if matched_profile else None,
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


@safety_bp.route('/api/adp-history')
@login_required
def adp_history_lookup():
    adp_number = _normalize_adp_number(request.args.get('adp_number'))
    if not adp_number:
        return jsonify({'found': False, 'message': 'ADP number is required.'}), 400

    profile = ADPProfile.query.filter(func.upper(ADPProfile.adp_number) == adp_number).first()
    profile_name = profile.full_name if profile else None
    violations = _violation_records_for_adp(adp_number)
    incidents = _incident_records_for_adp(adp_number, profile_name)

    violation_count = len(violations)
    next_offence_number = violation_count + 1
    offender_level = _offender_level_from_violation_count(next_offence_number)

    return jsonify({
        'found': bool(profile),
        'adp_number': adp_number,
        'person_name': profile_name,
        'company': profile.company.name if profile and profile.company else None,
        'violation_count': violation_count,
        'incident_count': len(incidents),
        'offender_level': offender_level,
        'recommended_action': _manual_follow_up_action(next_offence_number),
        'recent_violations': [
            {
                'reference': item.violation_number or f'VIO-{item.id}',
                'date': item.violation_date.isoformat() if item.violation_date else None,
                'status': item.status,
                'description': item.violation_description,
                'penalty_amount': item.penalty_amount,
                'penalty_currency': item.penalty_currency,
            }
            for item in violations[:5]
        ],
        'recent_incidents': [
            {
                'reference': item.incident_number or f'INC-{item.id}',
                'date': item.occurrence_date.isoformat() if item.occurrence_date else None,
                'status': item.status,
                'severity': item.severity,
                'location': item.location,
            }
            for item in incidents[:5]
        ],
    })
