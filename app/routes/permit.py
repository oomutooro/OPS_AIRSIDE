"""
Permit routes: ADP applications, renewals, vehicle registration, company management.
"""
from datetime import date, timedelta
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.models.permit import ADPApplication, ADPPermit
from app.models.reference import AirsideVehicle, Company
from app.models.form import FormSubmission, FormTemplate
from app.services.workflow_service import WorkflowService

permit_bp = Blueprint('permit', __name__)


@permit_bp.route('/adp-application', methods=['GET', 'POST'])
@login_required
def adp_application():
    if request.method == 'POST':
        signature_enabled = current_app.config.get('SIGNATURE_CAPTURE_ENABLED', False)
        appn = ADPApplication(
            application_date=date.today(),
            applicant_name=request.form.get('applicant_name'),
            applicant_badge=request.form.get('applicant_badge'),
            company_id=request.form.get('company_id') or None,
            national_driving_license_no=request.form.get('national_driving_license_no'),
            ndl_expiry=request.form.get('ndl_expiry') or None,
            vehicle_categories_requested=request.form.getlist('vehicle_categories'),
            theory_test_score=float(request.form.get('theory_test_score') or 0),
            practical_test_passed=bool(request.form.get('practical_test_passed')),
            sponsor_name=request.form.get('sponsor_name'),
            sponsor_title=request.form.get('sponsor_title'),
            applicant_signature=request.form.get('applicant_signature') if signature_enabled else None,
            created_by_user_id=current_user.id,
            status='submitted',
        )
        db.session.add(appn)

        template = FormTemplate.query.filter_by(form_number=17).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Permit Office',
                data={**request.form.to_dict(flat=False), 'recorded_by': current_user.full_name},
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)

        db.session.commit()
        flash('ADP application submitted.', 'success')
        return redirect(url_for('permit.adp_application'))

    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    apps = ADPApplication.query.order_by(ADPApplication.created_at.desc()).limit(20).all()
    return render_template(
        'permits/adp_application.html',
        companies=companies,
        applications=apps,
        signature_capture_enabled=bool(current_app.config.get('SIGNATURE_CAPTURE_ENABLED', False)),
    )


@permit_bp.route('/adp-renewal', methods=['GET', 'POST'])
@login_required
def adp_renewal():
    if request.method == 'POST':
        permit_id = request.form.get('permit_id')
        permit = db.session.get(ADPPermit, int(permit_id)) if permit_id else None
        if permit:
            permit.issue_date = date.today()
            permit.expiry_date = date.today() + timedelta(days=730)
            permit.refresher_completed_date = date.today()
            permit.is_suspended = False
            permit.is_active = True
            db.session.commit()
            flash('ADP renewed successfully.', 'success')
        else:
            flash('Permit not found.', 'danger')
        return redirect(url_for('permit.adp_renewal'))

    permits = ADPPermit.query.order_by(ADPPermit.expiry_date.asc()).limit(50).all()
    return render_template('permits/adp_renewal.html', permits=permits)


@permit_bp.route('/vehicle-registration', methods=['GET', 'POST'])
@login_required
def vehicle_registration():
    if request.method == 'POST':
        vehicle = AirsideVehicle(
            registration=request.form.get('registration'),
            call_sign=request.form.get('call_sign'),
            company_id=request.form.get('company_id') or None,
            vehicle_type=request.form.get('vehicle_type'),
            make_model=request.form.get('make_model'),
            colour=request.form.get('colour'),
            beacon_colour=request.form.get('beacon_colour'),
            adp_code=request.form.get('adp_code'),
            essat_sticker_no=request.form.get('essat_sticker_no'),
            is_active=True,
        )
        db.session.add(vehicle)
        db.session.commit()
        flash('Vehicle registered.', 'success')
        return redirect(url_for('permit.vehicle_registration'))

    vehicles = AirsideVehicle.query.order_by(AirsideVehicle.created_at.desc()).limit(50).all()
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    return render_template('permits/vehicle_registration.html', vehicles=vehicles, companies=companies)


@permit_bp.route('/company-management', methods=['GET', 'POST'])
@login_required
def company_management():
    if request.method == 'POST':
        company = Company(
            name=request.form.get('name'),
            code=request.form.get('code'),
            company_type=request.form.get('company_type'),
            contact_person=request.form.get('contact_person'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            is_active=True,
        )
        db.session.add(company)
        db.session.commit()
        flash('Company created.', 'success')
        return redirect(url_for('permit.company_management'))

    companies = Company.query.order_by(Company.name).all()
    return render_template('permits/company_management.html', companies=companies)
