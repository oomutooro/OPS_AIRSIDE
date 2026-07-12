"""
Inspection routes for forms 1,4,5,6,7,8,9,13,14,18,19,20,21,22,24,25.
"""
from datetime import date
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from app import db
from app.models.form import FormSubmission, FormTemplate
from app.models.inspection import ESSTATMotorisedInspection, ESSTATNonMotorisedInspection
from app.models.reference import AirsideVehicle, Company, EquipmentInventory
from app.services.workflow_service import WorkflowService
from app.utils.decorators import role_required
from app.utils.form_schemas import FORM_SCHEMAS

inspection_bp = Blueprint('inspection', __name__)

WORKFLOW_LEVEL_LABELS = {
    'operator': ('Operator Level', 'primary'),
    'inspector': ('Senior Level', 'info'),
    'auditor': ('Manager Review', 'warning'),
    'supervisor': ('Senior Manager Review', 'danger'),
}


def _normalize_sticker_status(value: str | None) -> str:
    raw = (value or '').strip().upper()
    if raw in ('GREEN', 'SERVICEABLE', 'COMPLIANT'):
        return 'GREEN'
    if raw in ('YELLOW', 'ORANGE', 'CONDITIONAL', 'GRACE'):
        return 'YELLOW'
    if raw in ('RED', 'GROUNDED', 'NON-COMPLIANT'):
        return 'RED'
    return ''


def _quarter_cycle_from_date(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f'{d.year}-Q{q}'


def _sync_vehicle_from_essat_submission(submission: FormSubmission):
    """Persist Form 18 outcome into AirsideVehicle and link matching inventory rows."""
    data = submission.data or {}
    registration = (
        (data.get('airside_vehicle_no') or '').strip()
        or (data.get('vehicle_equipment_id_no') or '').strip()
    )
    if not registration:
        return

    company_name = (data.get('organization_company') or '').strip()
    company = Company.query.filter(func.lower(Company.name) == company_name.lower()).first() if company_name else None
    sticker_status = _normalize_sticker_status(data.get('sticker_status'))

    inspection_date_raw = (data.get('inspection_date') or '').strip()
    try:
        inspection_date = date.fromisoformat(inspection_date_raw) if inspection_date_raw else date.today()
    except ValueError:
        inspection_date = date.today()

    vehicle = AirsideVehicle.query.filter(
        func.upper(AirsideVehicle.registration) == registration.upper()
    ).first() or AirsideVehicle(registration=registration.upper())

    vehicle.company_id = company.id if company else vehicle.company_id
    vehicle.vehicle_type = (data.get('type') or '').strip() or vehicle.vehicle_type
    vehicle.make_model = (data.get('vehicle_equipment_description') or '').strip() or vehicle.make_model
    vehicle.colour = (data.get('colour') or '').strip() or vehicle.colour
    vehicle.essat_sticker_no = (data.get('sticker_no') or '').strip() or vehicle.essat_sticker_no
    vehicle.last_essat_date = inspection_date

    if sticker_status == 'RED':
        vehicle.is_grounded = True
        vehicle.is_active = False
        vehicle.grounded_reason = 'Grounded by ESSAT inspection outcome (RED status).'
    else:
        vehicle.is_grounded = False
        vehicle.is_active = True
        if vehicle.grounded_reason and 'ESSAT inspection outcome' in (vehicle.grounded_reason or ''):
            vehicle.grounded_reason = None

    db.session.add(vehicle)
    db.session.flush()

    cycle = _quarter_cycle_from_date(inspection_date)
    if vehicle.company_id:
        matching_inventory = EquipmentInventory.query.filter(
            EquipmentInventory.company_id == vehicle.company_id,
            EquipmentInventory.equipment_type == 'motorised',
            EquipmentInventory.inspection_cycle == cycle,
            EquipmentInventory.registration.isnot(None),
            func.upper(EquipmentInventory.registration) == vehicle.registration,
        ).all()

        for row in matching_inventory:
            row.inspection_submission_id = submission.id
            db.session.add(row)


def _status_tone(status):
    return {
        'draft': 'secondary',
        'submitted': 'primary',
        'approved': 'success',
        'rejected': 'danger',
        'closed': 'success',
    }.get((status or '').lower(), 'secondary')


def _workflow_summary(submission):
    workflow_item = submission.workflow_item
    if not workflow_item:
        return 'Not Routed', 'secondary'
    if workflow_item.status == 'closed' or submission.status in ('approved', 'closed'):
        return 'Cleared Completely', 'success'
    return WORKFLOW_LEVEL_LABELS.get(
        workflow_item.current_owner_role,
        ((workflow_item.current_owner_role or 'Pending').replace('_', ' ').title(), 'secondary'),
    )


def _build_form_page_overview(template, recent):
    total_reports = FormSubmission.query.filter_by(form_template_id=template.id).count()
    pending_reports = FormSubmission.query.filter(
        FormSubmission.form_template_id == template.id,
        FormSubmission.status.in_(['draft', 'submitted'])
    ).count()
    cleared_reports = FormSubmission.query.filter(
        FormSubmission.form_template_id == template.id,
        FormSubmission.status.in_(['approved', 'closed'])
    ).count()
    latest_report = recent[0] if recent else None

    related_reports = []
    for submission in recent[:6]:
        workflow_label, workflow_tone = _workflow_summary(submission)
        related_reports.append({
            'reference': submission.reference_number or f'SUB-{submission.id}',
            'title': template.title,
            'meta': submission.location_ref or 'Airside Ops',
            'status_label': (submission.status or 'draft').replace('_', ' ').title(),
            'status_tone': _status_tone(submission.status),
            'workflow_label': workflow_label,
            'workflow_tone': workflow_tone,
            'updated_at': submission.created_at.strftime('%d %b %Y %H:%M') if submission.created_at else '-',
        })

    return {
        'title': f'Form {template.form_number} - {template.title}',
        'subtitle': 'Review the summary first, then add a new report using the form below.',
        'add_label': 'Insert New Report',
        'add_href': '#new-report-form',
        'list_caption': 'Latest reports already inserted for this form',
        'summary_cards': [
            {'label': 'Total Reports', 'value': total_reports, 'help_text': 'All submissions captured for this form'},
            {'label': 'Pending Action', 'value': pending_reports, 'help_text': 'Draft or submitted reports awaiting action'},
            {'label': 'Cleared', 'value': cleared_reports, 'help_text': 'Reports fully approved or closed'},
            {
                'label': 'Latest Report',
                'value': latest_report.reference_number if latest_report and latest_report.reference_number else (f'SUB-{latest_report.id}' if latest_report else 'None'),
                'help_text': latest_report.created_at.strftime('%d %b %Y %H:%M') if latest_report and latest_report.created_at else 'No submissions yet',
            },
        ],
        'related_reports': related_reports,
    }


def _save_generic_form(form_number: int, location='Airside'):
    template = FormTemplate.query.filter_by(form_number=form_number).first()
    if not template:
        return False, f'Form template {form_number} not found.'

    data = request.form.to_dict(flat=True)
    data['recorded_by'] = current_user.full_name
    data['checkboxes'] = request.form.getlist('checklist_items')

    submission = FormSubmission(
        form_template_id=template.id,
        status=request.form.get('status', 'submitted'),
        submitted_by_user_id=current_user.id,
        location_ref=request.form.get('location_ref', location),
        gps_latitude=request.form.get('gps_latitude') or None,
        gps_longitude=request.form.get('gps_longitude') or None,
        outgoing_signature=request.form.get('signature_data') if current_app.config.get('SIGNATURE_CAPTURE_ENABLED', False) else None,
        data=data,
    )
    db.session.add(submission)
    db.session.flush()

    if form_number == 18:
        _sync_vehicle_from_essat_submission(submission)

    WorkflowService.ensure_issue_for_submission(submission, current_user)
    from app.models.form import AuditLog
    AuditLog.log(
        'SUBMIT_FORM',
        user_id=current_user.id,
        entity_type='FormSubmission',
        form_template_id=template.id,
        description=f'{current_user.full_name} submitted Form {form_number} ({template.title})',
    )
    db.session.commit()
    return True, 'Submitted successfully.'


@inspection_bp.route('/form/<int:form_number>', methods=['GET', 'POST'])
@role_required('admin', 'supervisor', 'inspector', 'operator')
def generic_form(form_number):
    template_name_map = {
        1: 'inspections/form_01_proficiency.html',
        4: 'inspections/form_04_stand_inspection.html',
        6: 'inspections/form_06_manoeuvring_area.html',
        7: 'inspections/form_07_apron_inspection.html',
        8: 'inspections/form_08_runway_condition.html',
        9: 'inspections/form_09_spillage.html',
        13: 'inspections/form_13_turnaround_audit.html',
        14: 'inspections/form_14_equipment_survey.html',
        18: 'inspections/form_18_essat_motorised.html',
        19: 'inspections/form_19_essat_non_motorised.html',
        20: 'inspections/form_20_fod.html',
        21: 'inspections/form_21_fod_walk.html',
        22: 'inspections/form_22_fueling_safety.html',
        24: 'inspections/form_24_tank_farm.html',
        25: 'inspections/form_25_low_visibility.html',
    }

    if form_number not in template_name_map:
        flash('Unsupported inspection form.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        ok, message = _save_generic_form(form_number)
        flash(message, 'success' if ok else 'danger')
        return redirect(url_for('inspection.generic_form', form_number=form_number))

    recent = FormSubmission.query.options(
        joinedload(FormSubmission.workflow_item)
    ).join(FormTemplate).filter(
        FormTemplate.form_number == form_number
    ).order_by(FormSubmission.created_at.desc()).limit(10).all()

    template = FormTemplate.query.filter_by(form_number=form_number).first()
    schema = FORM_SCHEMAS.get(form_number, {'title': f'Form {form_number}', 'sections': []})
    page_overview = _build_form_page_overview(template, recent) if template else None
    if page_overview and form_number in (18, 19):
        page_overview['quick_links'] = [
            {'label': 'ESSAT Sticker Report', 'url': url_for('report.essat_sticker_report'), 'icon': 'fa-tag'},
            {'label': 'ESSAT Analytics', 'url': url_for('essat.analytics'), 'icon': 'fa-chart-line'},
            {'label': 'ESSAT Equipment Inventory', 'url': url_for('essat.inventory_list'), 'icon': 'fa-boxes'},
        ]
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all() if form_number == 18 else []
    return render_template(
        template_name_map[form_number],
        recent=recent,
        form_number=form_number,
        schema=schema,
        page_overview=page_overview,
        companies=companies,
    )


@inspection_bp.route('/forms')
@login_required
def form_list():
    templates = FormTemplate.query.filter(
        FormTemplate.form_number.in_([1, 4, 5, 6, 7, 8, 9, 13, 14, 18, 19, 20, 21, 22, 24, 25])
    ).order_by(FormTemplate.form_number).all()

    template_ids = [template.id for template in templates]
    submitted_count = FormSubmission.query.filter(FormSubmission.form_template_id.in_(template_ids)).count() if template_ids else 0
    pending_count = FormSubmission.query.filter(
        FormSubmission.form_template_id.in_(template_ids),
        FormSubmission.status.in_(['draft', 'submitted'])
    ).count() if template_ids else 0
    cleared_count = FormSubmission.query.filter(
        FormSubmission.form_template_id.in_(template_ids),
        FormSubmission.status.in_(['approved', 'closed'])
    ).count() if template_ids else 0

    def grouped_links(form_numbers):
        group_templates = [template for template in templates if template.form_number in form_numbers]
        return [
            {
                'label': f'Form {template.form_number} - {template.title}',
                'url': url_for('inspection.generic_form', form_number=template.form_number),
                'meta': 'Open report workspace',
            }
            for template in group_templates
        ]

    sections = [
        {
            'title': 'Airfield Checks',
            'description': 'Daily apron, stand, runway, manoeuvring area, and spill inspection reports.',
            'badge': 'Core inspections',
            'links': grouped_links([1, 4, 6, 7, 8, 9]),
            'action': {'label': 'Add New Inspection', 'url': url_for('inspection.generic_form', form_number=1)},
        },
        {
            'title': 'Audit and Equipment Reports',
            'description': 'Turnaround audits, equipment surveys, and operational assurance forms.',
            'badge': 'Audit',
            'links': grouped_links([13, 14]),
            'action': {'label': 'Start Audit Report', 'url': url_for('inspection.generic_form', form_number=13)},
        },
        {
            'title': 'ESSAT and Safety Checks',
            'description': 'ESSAT, FOD, fueling safety, tank farm, and low visibility reports.',
            'badge': 'Specialized',
            'links': grouped_links([18, 19, 20, 21, 22, 24, 25]),
            'action': {'label': 'Add ESSAT Report', 'url': url_for('inspection.generic_form', form_number=18)},
        },
    ]

    return render_template(
        'shared/section_overview.html',
        overview_title='Inspection Dashboard',
        overview_subtitle='Open a report family, review its current workload, and start a new form from the relevant section.',
        summary_cards=[
            {'label': 'Active Forms', 'value': len(templates), 'help_text': 'Inspection forms available to this workspace'},
            {'label': 'Submitted Reports', 'value': submitted_count, 'help_text': 'All inspection reports captured so far'},
            {'label': 'Pending Review', 'value': pending_count, 'help_text': 'Draft or submitted inspections still in progress'},
            {'label': 'Cleared Reports', 'value': cleared_count, 'help_text': 'Inspection reports fully approved or closed'},
        ],
        sections=sections,
        primary_action={'label': 'Start New Inspection', 'url': url_for('inspection.generic_form', form_number=1)},
    )
