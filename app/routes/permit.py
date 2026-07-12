"""
Permit routes: ADP applications, renewals, vehicle registration, company management.
"""
from datetime import date, timedelta
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from app import db
from app.models.incident import Violation
from app.models.permit import ADPApplication, ADPPermit, ADPProfile, UGANDA_ADP_DRIVER_CLASSES
from app.models.reference import AirsideVehicle, Company
from app.models.form import FormSubmission, FormTemplate
from app.services.workflow_service import WorkflowService

permit_bp = Blueprint('permit', __name__)


def _page_overview(title, subtitle, summary_cards, related_reports, add_href='#new-report-form', add_label='Insert New Report'):
    return {
        'title': title,
        'subtitle': subtitle,
        'summary_cards': summary_cards,
        'related_reports': related_reports,
        'add_href': add_href,
        'add_label': add_label,
        'list_caption': 'Latest permit-related reports and their current status',
    }


def _status_tone(status):
    return {
        'submitted': 'primary',
        'approved': 'success',
        'issued': 'success',
        'draft': 'secondary',
        'expired': 'danger',
        'rejected': 'danger',
    }.get((status or '').lower(), 'secondary')


def _parse_optional_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _essat_linked_vehicles_query():
    """Vehicles that are tied to ESSAT inspections and a registered company."""
    return AirsideVehicle.query.filter(
        AirsideVehicle.company_id.isnot(None),
        AirsideVehicle.last_essat_date.isnot(None),
    )


def _operational_vehicles_query():
    """Operational vehicles allowed for airside use by ESSAT state."""
    return _essat_linked_vehicles_query().filter(
        AirsideVehicle.is_active.is_(True),
        AirsideVehicle.is_grounded.is_(False),
    )


def _adp_profile_summary(profile: ADPProfile) -> dict:
    return {
        'reference': profile.adp_number,
        'title': profile.full_name,
        'meta': profile.company_details,
        'status_label': profile.training_status_label,
        'status_tone': 'success' if profile.adp_training_completed else 'warning',
        'workflow_label': f"{profile.offender_level} | {profile.incident_count} incident{'s' if profile.incident_count != 1 else ''}",
        'workflow_tone': 'danger' if profile.violation_count >= 3 else ('warning' if profile.has_violations else 'success'),
        'updated_at': profile.updated_at.strftime('%d %b %Y %H:%M') if profile.updated_at else '-',
    }


@permit_bp.route('/overview')
@login_required
def overview():
    today = date.today()
    expiring_soon = ADPPermit.query.filter(ADPPermit.expiry_date.isnot(None), ADPPermit.expiry_date <= today + timedelta(days=30)).count()
    adp_profile_count = ADPProfile.query.count()
    essat_linked_vehicle_count = _essat_linked_vehicles_query().count()
    operational_vehicle_count = _operational_vehicles_query().count()
    grounded_vehicle_count = _essat_linked_vehicles_query().filter(AirsideVehicle.is_grounded.is_(True)).count()
    essat_unlinked_violations = Violation.query.filter(
        Violation.vehicle_registration.isnot(None),
        ~func.upper(Violation.vehicle_registration).in_(
            db.session.query(func.upper(AirsideVehicle.registration)).filter(
                AirsideVehicle.last_essat_date.isnot(None)
            )
        ),
    ).count()

    summary_cards = [
        {'label': 'ADP Profiles', 'value': adp_profile_count, 'help_text': 'Registered ADP drivers'},
        {'label': 'Training Complete', 'value': ADPProfile.query.filter_by(adp_training_completed=True).count(), 'help_text': 'Profiles with ADP training recorded'},
        {'label': 'UCAA Touch Keys', 'value': ADPProfile.query.filter_by(is_ucaa_staff=True, has_touch_key=True).count(), 'help_text': 'UCAA staff with touch key recorded'},
        {'label': 'Linked Violations', 'value': Violation.query.filter(Violation.offender_adp_number.isnot(None)).count(), 'help_text': 'Violation records carrying an ADP number'},
        {'label': 'Expiring Soon', 'value': expiring_soon, 'help_text': 'Permits expiring within 30 days'},
        {'label': 'Companies', 'value': Company.query.count(), 'help_text': 'Managed companies and operators'},
    ]

    if essat_linked_vehicle_count > 0:
        summary_cards.extend([
            {'label': 'Operational Vehicles', 'value': operational_vehicle_count, 'help_text': 'ESSAT-compliant vehicles allowed to operate airside'},
            {'label': 'Grounded Vehicles', 'value': grounded_vehicle_count, 'help_text': 'Vehicles blocked from use per ESSAT state'},
        ])

    if essat_unlinked_violations > 0:
        summary_cards.append({
            'label': 'Unlinked Vehicle Violations',
            'value': essat_unlinked_violations,
            'help_text': 'Violations raised for vehicles not yet linked to ESSAT records',
            'tone': 'warning',
        })

    sections = [
        {
            'title': 'ADP Registry',
            'description': 'Driver profiles, company details, training status, licence classes, and violation history.',
            'badge': f'{adp_profile_count} profiles',
            'links': [
                {'label': 'ADP Registry', 'url': url_for('permit.adp_registry'), 'meta': 'Driver profile workspace'},
                {'label': 'ADP Applications', 'url': url_for('permit.adp_application'), 'meta': 'Form 17 workspace'},
                {'label': 'ADP Renewals', 'url': url_for('permit.adp_renewal'), 'meta': 'Permit renewal workspace'},
            ],
            'action': {'label': 'Register ADP Driver', 'url': url_for('permit.adp_registry')},
        },
        {
            'title': 'Permit Registry',
            'description': 'Vehicles and operators synchronized with ESSAT inspection outcomes.',
            'badge': f'{operational_vehicle_count} vehicles' if operational_vehicle_count > 0 else None,
            'links': [
                {'label': 'Vehicle Registration', 'url': url_for('permit.vehicle_registration'), 'meta': 'ESSAT-linked airside vehicle registry'},
                {'label': 'Company Management', 'url': url_for('permit.company_management'), 'meta': 'Operator registry'},
                {'label': 'ESSAT Analytics', 'url': url_for('essat.analytics'), 'meta': 'Inspection and compliance dashboard'},
            ],
            'action': {'label': 'Register Vehicle', 'url': url_for('permit.vehicle_registration')},
        },
    ]

    return render_template(
        'shared/section_overview.html',
        overview_title='Permit Dashboard',
        overview_subtitle='Each permit area acts like a heading with its own report list, dashboard cues, and entry point for new forms.',
        summary_cards=summary_cards,
        sections=sections,
        primary_action={'label': 'Register ADP Driver', 'url': url_for('permit.adp_registry')},
    )


@permit_bp.route('/adp-registry', methods=['GET', 'POST'])
@login_required
def adp_registry():
    if request.method == 'POST':
        adp_number = (request.form.get('adp_number') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()
        company_id = request.form.get('company_id') or None

        if not adp_number or not full_name or not company_id:
            flash('ADP number, driver name, and company are required.', 'danger')
            return redirect(url_for('permit.adp_registry'))

        profile = ADPProfile.query.filter_by(adp_number=adp_number).first() or ADPProfile(adp_number=adp_number)
        profile.full_name = full_name
        profile.company_id = int(company_id)
        profile.badge_number = (request.form.get('badge_number') or '').strip() or None
        profile.job_title = (request.form.get('job_title') or '').strip() or None
        profile.date_of_birth = _parse_optional_date(request.form.get('date_of_birth'))
        profile.gender = (request.form.get('gender') or '').strip() or None
        profile.phone = (request.form.get('phone') or '').strip() or None
        profile.email = (request.form.get('email') or '').strip() or None
        profile.adp_training_completed = request.form.get('adp_training_completed') == '1'
        profile.adp_training_date = _parse_optional_date(request.form.get('adp_training_date'))
        profile.is_ucaa_staff = request.form.get('is_ucaa_staff') == '1'
        profile.has_touch_key = request.form.get('has_touch_key') == '1'
        profile.touch_key_number = (request.form.get('touch_key_number') or '').strip() or None
        profile.national_driving_license_no = (request.form.get('national_driving_license_no') or '').strip() or None
        profile.ndl_expiry = _parse_optional_date(request.form.get('ndl_expiry'))
        profile.driver_license_classes = request.form.getlist('driver_license_classes')
        profile.notes = (request.form.get('notes') or '').strip() or None
        profile.created_by_user_id = current_user.id

        db.session.add(profile)
        db.session.commit()
        flash('ADP registry profile saved.', 'success')
        return redirect(url_for('permit.adp_registry'))

    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    profiles = ADPProfile.query.order_by(ADPProfile.created_at.desc()).limit(50).all()
    return render_template(
        'permits/adp_registry.html',
        companies=companies,
        profiles=profiles,
        driver_license_classes=UGANDA_ADP_DRIVER_CLASSES.items(),
        page_overview=_page_overview(
            'ADP Registry Workspace',
            'Register ADP holders with company data, training status, UCAA touch key details, licence classes, and violation history.',
            [
                {'label': 'Profiles', 'value': ADPProfile.query.count(), 'help_text': 'Registered ADP holders'},
                {'label': 'Training Complete', 'value': ADPProfile.query.filter_by(adp_training_completed=True).count(), 'help_text': 'Profiles with training recorded'},
                {'label': 'UCAA Touch Keys', 'value': ADPProfile.query.filter_by(is_ucaa_staff=True, has_touch_key=True).count(), 'help_text': 'UCAA staff with touch key'},
                {'label': 'Linked Violations', 'value': Violation.query.filter(Violation.offender_adp_number.isnot(None)).count(), 'help_text': 'Violations captured against an ADP number'},
            ],
            [_adp_profile_summary(profile) for profile in profiles[:6]],
            add_label='Register ADP Driver',
        ),
    )


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
            ndl_expiry=_parse_optional_date(request.form.get('ndl_expiry')),
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
        page_overview=_page_overview(
            'ADP Applications Workspace',
            'Review recent applications and their status before entering a new ADP application below.',
            [
                {'label': 'Applications', 'value': ADPApplication.query.count(), 'help_text': 'Total ADP applications captured'},
                {'label': 'Submitted', 'value': ADPApplication.query.filter_by(status='submitted').count(), 'help_text': 'Applications awaiting approval'},
                {'label': 'Approved', 'value': ADPApplication.query.filter_by(status='approved').count(), 'help_text': 'Applications already approved'},
                {'label': 'Latest Applicant', 'value': apps[0].applicant_name if apps else 'None', 'help_text': apps[0].created_at.strftime('%d %b %Y %H:%M') if apps else 'No applications yet'},
            ],
            [
                {
                    'reference': application.application_no or f'ADP-{application.id}',
                    'title': application.applicant_name or 'ADP application',
                    'meta': application.status.replace('_', ' ').title() if application.status else 'Submitted',
                    'status_label': (application.status or 'submitted').replace('_', ' ').title(),
                    'status_tone': _status_tone(application.status),
                    'workflow_label': 'Permit Intake',
                    'workflow_tone': 'info',
                    'updated_at': application.created_at.strftime('%d %b %Y %H:%M') if application.created_at else '-',
                }
                for application in apps[:6]
            ],
        ),
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
    return render_template(
        'permits/adp_renewal.html',
        permits=permits,
        page_overview=_page_overview(
            'ADP Renewals Workspace',
            'Check the renewal queue and permit expiry status before processing the next renewal.',
            [
                {'label': 'Total Permits', 'value': ADPPermit.query.count(), 'help_text': 'Issued ADP permits in the registry'},
                {'label': 'Active', 'value': ADPPermit.query.filter_by(is_active=True).count(), 'help_text': 'Permits currently active'},
                {'label': 'Suspended', 'value': ADPPermit.query.filter_by(is_suspended=True).count(), 'help_text': 'Permits temporarily suspended'},
                {'label': 'Next Expiry', 'value': permits[0].expiry_date.strftime('%d %b %Y') if permits and permits[0].expiry_date else 'None', 'help_text': permits[0].holder_name if permits else 'No permits yet'},
            ],
            [
                {
                    'reference': permit.adp_number or f'PERMIT-{permit.id}',
                    'title': permit.holder_name or 'ADP permit',
                    'meta': permit.expiry_date.strftime('%d %b %Y') if permit.expiry_date else 'No expiry',
                    'status_label': 'Active' if permit.is_active else 'Inactive',
                    'status_tone': 'success' if permit.is_active else 'secondary',
                    'workflow_label': 'Renewal Queue',
                    'workflow_tone': 'warning',
                    'updated_at': permit.updated_at.strftime('%d %b %Y %H:%M') if permit.updated_at else '-',
                }
                for permit in permits[:6]
            ],
            add_label='Process Renewal',
        ),
    )


@permit_bp.route('/vehicle-registration', methods=['GET', 'POST'])
@login_required
def vehicle_registration():
    if request.method == 'POST':
        company_id = request.form.get('company_id', type=int)
        if not company_id:
            flash('Company is required. Vehicles must be linked to the responsible operator.', 'danger')
            return redirect(url_for('permit.vehicle_registration'))

        vehicle = AirsideVehicle(
            registration=request.form.get('registration'),
            call_sign=request.form.get('call_sign'),
            company_id=company_id,
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

    vehicles = _essat_linked_vehicles_query().order_by(AirsideVehicle.updated_at.desc()).limit(100).all()
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    return render_template(
        'permits/vehicle_registration.html',
        vehicles=vehicles,
        companies=companies,
        operational_count=_operational_vehicles_query().count(),
        grounded_count=_essat_linked_vehicles_query().filter(AirsideVehicle.is_grounded.is_(True)).count(),
    )


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
