"""
Inspection routes for forms 1,4,5,6,7,8,9,13,14,18,19,20,21,22,24,25.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.models.form import FormSubmission, FormTemplate
from app.models.inspection import ESSTATMotorisedInspection, ESSTATNonMotorisedInspection
from app.services.workflow_service import WorkflowService
from app.utils.decorators import role_required
from app.utils.form_schemas import FORM_SCHEMAS

inspection_bp = Blueprint('inspection', __name__)


def _save_generic_form(form_number: int, location='Airside'):
    template = FormTemplate.query.filter_by(form_number=form_number).first()
    if not template:
        return False, f'Form template {form_number} not found.'

    data = request.form.to_dict(flat=True)
    data['checkboxes'] = request.form.getlist('checklist_items')

    submission = FormSubmission(
        form_template_id=template.id,
        status=request.form.get('status', 'submitted'),
        submitted_by_user_id=current_user.id,
        location_ref=request.form.get('location_ref', location),
        gps_latitude=request.form.get('gps_latitude') or None,
        gps_longitude=request.form.get('gps_longitude') or None,
        outgoing_signature=request.form.get('signature_data'),
        data=data,
    )
    db.session.add(submission)
    WorkflowService.ensure_issue_for_submission(submission, current_user)
    db.session.commit()
    return True, 'Submitted successfully.'


@inspection_bp.route('/form/<int:form_number>', methods=['GET', 'POST'])
@login_required
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

    recent = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == form_number
    ).order_by(FormSubmission.created_at.desc()).limit(10).all()

    schema = FORM_SCHEMAS.get(form_number, {'title': f'Form {form_number}', 'sections': []})
    return render_template(
        template_name_map[form_number],
        recent=recent,
        form_number=form_number,
        schema=schema,
    )


@inspection_bp.route('/forms')
@login_required
def form_list():
    templates = FormTemplate.query.filter(
        FormTemplate.form_number.in_([1, 4, 5, 6, 7, 8, 9, 13, 14, 18, 19, 20, 21, 22, 24, 25])
    ).order_by(FormTemplate.form_number).all()
    return render_template('inspections/forms_index.html', templates=templates)
