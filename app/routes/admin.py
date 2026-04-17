"""
Administration routes: user management, reference data, form builder, system settings.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from app import db
from app.models.user import User, Role
from app.models.reference import Company, AirsideLocation, ParkingStand
from app.models.form import FormTemplate
from app.models.flight import AodbWriteback
from app.utils.decorators import role_required

admin_bp = Blueprint('admin', __name__)

ROLE_LABELS = {
    'viewer': 'Viewer',
    'operator': 'Operator (AOO / OO)',
    'inspector': 'Inspector (SOO)',
    'auditor': 'Auditor / Principal',
    'supervisor': 'Supervisor / Manager',
    'admin': 'System Admin',
}


def _assignable_roles(user):
    if user.role == 'admin':
        return list(ROLE_LABELS.keys())
    return ['viewer', 'operator', 'inspector', 'auditor', 'supervisor']


def _can_manage_user(actor, target_user):
    if actor.role == 'admin':
        return True
    return target_user.role != 'admin'


def _validate_user_role(selected_role):
    if selected_role not in ROLE_LABELS:
        return False
    if selected_role not in _assignable_roles(current_user):
        return False
    return True


def _normalize_optional_text(value):
    value = (value or '').strip()
    return value or None


@admin_bp.route('/users', methods=['GET', 'POST'])
@role_required('admin', 'supervisor', 'auditor', 'inspector')
def user_management():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()
        badge_number = _normalize_optional_text(request.form.get('badge_number'))
        department = _normalize_optional_text(request.form.get('department'))
        selected_role = request.form.get('role', 'viewer')
        if not _validate_user_role(selected_role):
            flash('You are not allowed to assign that role.', 'danger')
            return redirect(url_for('admin.user_management'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('admin.user_management'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return redirect(url_for('admin.user_management'))

        if badge_number and User.query.filter_by(badge_number=badge_number).first():
            flash('Badge number already exists.', 'danger')
            return redirect(url_for('admin.user_management'))

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role=selected_role,
            badge_number=badge_number,
            department=department,
            is_active=bool(request.form.get('is_active', True)),
        )
        user.set_password(request.form.get('password', 'ChangeMe123!'))
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('User could not be created due to duplicate unique fields (username, email, or badge number).', 'danger')
            return redirect(url_for('admin.user_management'))
        flash('User created.', 'success')
        return redirect(url_for('admin.user_management'))

    users = User.query.order_by(User.created_at.desc()).all()
    return render_template(
        'admin/user_management.html',
        users=users,
        role_labels=ROLE_LABELS,
        assignable_roles=_assignable_roles(current_user),
    )


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'supervisor', 'auditor', 'inspector')
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.user_management'))

    if not _can_manage_user(current_user, user):
        flash('You are not allowed to edit this user.', 'danger')
        return redirect(url_for('admin.user_management'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()
        email = (request.form.get('email') or '').strip()
        badge_number = _normalize_optional_text(request.form.get('badge_number'))
        department = _normalize_optional_text(request.form.get('department'))
        selected_role = request.form.get('role', user.role)
        if not _validate_user_role(selected_role):
            flash('You are not allowed to assign that role.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        existing_username = User.query.filter(User.username == username, User.id != user.id).first()
        if existing_username:
            flash('Username already exists.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        existing_email = User.query.filter(User.email == email, User.id != user.id).first()
        if existing_email:
            flash('Email already exists.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        existing_badge = None
        if badge_number:
            existing_badge = User.query.filter(User.badge_number == badge_number, User.id != user.id).first()
        if existing_badge:
            flash('Badge number already exists.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        user.username = username
        user.full_name = full_name
        user.email = email
        user.badge_number = badge_number
        user.department = department
        user.role = selected_role
        user.is_active = request.form.get('is_active') == 'on'

        new_password = request.form.get('password')
        if new_password:
            user.set_password(new_password)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('User could not be updated due to duplicate unique fields (username, email, or badge number).', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))
        flash('User access updated.', 'success')
        return redirect(url_for('admin.user_management'))

    return render_template(
        'admin/edit_user.html',
        user=user,
        role_labels=ROLE_LABELS,
        assignable_roles=_assignable_roles(current_user),
    )


@admin_bp.route('/reference-data')
@role_required('admin', 'supervisor')
def reference_data():
    companies = Company.query.order_by(Company.name).all()
    locations = AirsideLocation.query.order_by(AirsideLocation.code).all()
    stands = ParkingStand.query.order_by(ParkingStand.stand_code).all()
    bridges = ParkingStand.query.filter_by(has_pbb=True).order_by(ParkingStand.pbb_number, ParkingStand.stand_code).all()
    return render_template(
        'admin/reference_data.html',
        companies=companies,
        locations=locations,
        stands=stands,
        bridges=bridges,
    )


@admin_bp.route('/reference-data/company/new', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def create_company():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        code = (request.form.get('code') or '').strip() or None
        if not name:
            flash('Company name is required.', 'danger')
            return redirect(url_for('admin.create_company'))

        if code and Company.query.filter(Company.code == code).first():
            flash('Company code already exists.', 'danger')
            return redirect(url_for('admin.create_company'))

        company = Company(
            name=name,
            code=code,
            company_type=(request.form.get('company_type') or 'other').strip(),
            contact_person=(request.form.get('contact_person') or '').strip() or None,
            phone=(request.form.get('phone') or '').strip() or None,
            email=(request.form.get('email') or '').strip() or None,
            address=(request.form.get('address') or '').strip() or None,
            is_active=request.form.get('is_active') == 'on',
        )
        db.session.add(company)
        db.session.commit()
        flash('Company created.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_company.html', company=None)


@admin_bp.route('/reference-data/company/<int:company_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def edit_company(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip() or None
        if code:
            exists = Company.query.filter(Company.code == code, Company.id != company.id).first()
            if exists:
                flash('Company code already exists.', 'danger')
                return redirect(url_for('admin.edit_company', company_id=company.id))

        company.name = (request.form.get('name') or '').strip()
        company.code = code
        company.company_type = (request.form.get('company_type') or 'other').strip()
        company.contact_person = (request.form.get('contact_person') or '').strip() or None
        company.phone = (request.form.get('phone') or '').strip() or None
        company.email = (request.form.get('email') or '').strip() or None
        company.address = (request.form.get('address') or '').strip() or None
        company.is_active = request.form.get('is_active') == 'on'

        if not company.name:
            flash('Company name is required.', 'danger')
            return redirect(url_for('admin.edit_company', company_id=company.id))

        db.session.commit()
        flash('Company updated.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_company.html', company=company)


@admin_bp.route('/reference-data/company/<int:company_id>/delete', methods=['POST'])
@role_required('admin', 'supervisor')
def delete_company(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    try:
        db.session.delete(company)
        db.session.commit()
        flash('Company deleted.', 'success')
    except Exception:
        db.session.rollback()
        flash('Company cannot be deleted because it is referenced. Set it inactive instead.', 'warning')
    return redirect(url_for('admin.reference_data'))


@admin_bp.route('/reference-data/location/new', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def create_location():
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().upper()
        name = (request.form.get('name') or '').strip()
        zone = (request.form.get('zone') or '').strip().lower()

        if not code or not name or not zone:
            flash('Code, name, and zone are required.', 'danger')
            return redirect(url_for('admin.create_location'))

        if AirsideLocation.query.filter(AirsideLocation.code == code).first():
            flash('Location code already exists.', 'danger')
            return redirect(url_for('admin.create_location'))

        location = AirsideLocation(
            code=code,
            name=name,
            zone=zone,
            description=(request.form.get('description') or '').strip() or None,
            is_active=request.form.get('is_active') == 'on',
        )
        db.session.add(location)
        db.session.commit()
        flash('Location created.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_location.html', location=None)


@admin_bp.route('/reference-data/location/<int:location_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def edit_location(location_id):
    location = db.session.get(AirsideLocation, location_id)
    if not location:
        flash('Location not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().upper()
        if not code:
            flash('Location code is required.', 'danger')
            return redirect(url_for('admin.edit_location', location_id=location.id))

        exists = AirsideLocation.query.filter(AirsideLocation.code == code, AirsideLocation.id != location.id).first()
        if exists:
            flash('Location code already exists.', 'danger')
            return redirect(url_for('admin.edit_location', location_id=location.id))

        location.code = code
        location.name = (request.form.get('name') or '').strip()
        location.zone = (request.form.get('zone') or '').strip().lower()
        location.description = (request.form.get('description') or '').strip() or None
        location.is_active = request.form.get('is_active') == 'on'

        if not location.name or not location.zone:
            flash('Location name and zone are required.', 'danger')
            return redirect(url_for('admin.edit_location', location_id=location.id))

        db.session.commit()
        flash('Location updated.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_location.html', location=location)


@admin_bp.route('/reference-data/location/<int:location_id>/delete', methods=['POST'])
@role_required('admin', 'supervisor')
def delete_location(location_id):
    location = db.session.get(AirsideLocation, location_id)
    if not location:
        flash('Location not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    try:
        db.session.delete(location)
        db.session.commit()
        flash('Location deleted.', 'success')
    except Exception:
        db.session.rollback()
        flash('Location cannot be deleted because it is referenced. Set it inactive instead.', 'warning')
    return redirect(url_for('admin.reference_data'))


@admin_bp.route('/reference-data/stand/new', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def create_stand():
    if request.method == 'POST':
        stand_code = (request.form.get('stand_code') or '').strip().upper()
        if not stand_code:
            flash('Stand code is required.', 'danger')
            return redirect(url_for('admin.create_stand'))

        if ParkingStand.query.filter(ParkingStand.stand_code == stand_code).first():
            flash('Stand code already exists.', 'danger')
            return redirect(url_for('admin.create_stand'))

        stand = ParkingStand(
            stand_code=stand_code,
            stand_number=(request.form.get('stand_number') or '').strip(),
            apron=(request.form.get('apron') or '').strip(),
            category=(request.form.get('category') or '').strip() or None,
            has_pbb=request.form.get('has_pbb') == 'on',
            pbb_number=(request.form.get('pbb_number') or '').strip() or None,
            notes=(request.form.get('notes') or '').strip() or None,
            is_active=request.form.get('is_active') == 'on',
        )
        if not stand.stand_number or not stand.apron:
            flash('Stand number and apron are required.', 'danger')
            return redirect(url_for('admin.create_stand'))
        db.session.add(stand)
        db.session.commit()
        flash('Parking stand created.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_stand.html', stand=None)


@admin_bp.route('/reference-data/stand/<int:stand_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def edit_stand(stand_id):
    stand = db.session.get(ParkingStand, stand_id)
    if not stand:
        flash('Stand not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    if request.method == 'POST':
        stand_code = (request.form.get('stand_code') or '').strip().upper()
        if not stand_code:
            flash('Stand code is required.', 'danger')
            return redirect(url_for('admin.edit_stand', stand_id=stand.id))

        exists = ParkingStand.query.filter(ParkingStand.stand_code == stand_code, ParkingStand.id != stand.id).first()
        if exists:
            flash('Stand code already exists.', 'danger')
            return redirect(url_for('admin.edit_stand', stand_id=stand.id))

        stand.stand_code = stand_code
        stand.stand_number = (request.form.get('stand_number') or '').strip()
        stand.apron = (request.form.get('apron') or '').strip()
        stand.category = (request.form.get('category') or '').strip() or None
        stand.has_pbb = request.form.get('has_pbb') == 'on'
        stand.pbb_number = (request.form.get('pbb_number') or '').strip() or None
        stand.notes = (request.form.get('notes') or '').strip() or None
        stand.is_active = request.form.get('is_active') == 'on'

        if not stand.stand_number or not stand.apron:
            flash('Stand number and apron are required.', 'danger')
            return redirect(url_for('admin.edit_stand', stand_id=stand.id))

        db.session.commit()
        flash('Parking stand updated.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_stand.html', stand=stand)


@admin_bp.route('/reference-data/stand/<int:stand_id>/delete', methods=['POST'])
@role_required('admin', 'supervisor')
def delete_stand(stand_id):
    stand = db.session.get(ParkingStand, stand_id)
    if not stand:
        flash('Stand not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    try:
        db.session.delete(stand)
        db.session.commit()
        flash('Parking stand deleted.', 'success')
    except Exception:
        db.session.rollback()
        flash('Parking stand cannot be deleted because it is referenced. Set it inactive instead.', 'warning')
    return redirect(url_for('admin.reference_data'))


@admin_bp.route('/reference-data/bridge/new', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def create_bridge():
    available_stands = ParkingStand.query.filter_by(has_pbb=False).order_by(ParkingStand.stand_code).all()
    if request.method == 'POST':
        stand_id_raw = request.form.get('stand_id')
        pbb_number = (request.form.get('pbb_number') or '').strip().upper()
        stand = db.session.get(ParkingStand, int(stand_id_raw)) if stand_id_raw and stand_id_raw.isdigit() else None

        if not stand:
            flash('Please select a valid stand for the bridge.', 'danger')
            return redirect(url_for('admin.create_bridge'))
        if not pbb_number:
            flash('Bridge number is required.', 'danger')
            return redirect(url_for('admin.create_bridge'))

        stand.has_pbb = True
        stand.pbb_number = pbb_number
        db.session.commit()
        flash('Bridge mapping created.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_bridge.html', stand=None, stands=available_stands)


@admin_bp.route('/reference-data/bridge/<int:stand_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def edit_bridge(stand_id):
    stand = db.session.get(ParkingStand, stand_id)
    if not stand:
        flash('Bridge stand not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    if request.method == 'POST':
        pbb_number = (request.form.get('pbb_number') or '').strip().upper()
        if not pbb_number:
            flash('Bridge number is required.', 'danger')
            return redirect(url_for('admin.edit_bridge', stand_id=stand.id))

        stand.has_pbb = True
        stand.pbb_number = pbb_number
        stand.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Bridge details updated.', 'success')
        return redirect(url_for('admin.reference_data'))

    return render_template('admin/edit_bridge.html', stand=stand, stands=[])


@admin_bp.route('/reference-data/bridge/<int:stand_id>/delete', methods=['POST'])
@role_required('admin', 'supervisor')
def delete_bridge(stand_id):
    stand = db.session.get(ParkingStand, stand_id)
    if not stand:
        flash('Bridge not found.', 'danger')
        return redirect(url_for('admin.reference_data'))

    stand.has_pbb = False
    stand.pbb_number = None
    db.session.commit()
    flash('Bridge mapping removed from stand.', 'success')
    return redirect(url_for('admin.reference_data'))


@admin_bp.route('/form-builder', methods=['GET', 'POST'])
@role_required('admin')
def form_builder():
    if request.method == 'POST':
        template_id = request.form.get('template_id')
        template = db.session.get(FormTemplate, int(template_id)) if template_id else None
        if template:
            template.version = request.form.get('version', template.version)
            template.schema_definition = template.schema_definition or {}
            template.ui_layout = template.ui_layout or {}
            db.session.commit()
            flash('Form template updated.', 'success')
        return redirect(url_for('admin.form_builder'))

    templates = FormTemplate.query.order_by(FormTemplate.form_number).all()
    return render_template('admin/form_builder.html', templates=templates)


@admin_bp.route('/system-settings')
@role_required('admin')
def system_settings():
    return render_template('admin/system_settings.html')


# ──────────────────────────────────────────────────────────────────
# AODB Write-back Queue Monitoring
# ──────────────────────────────────────────────────────────────────

@admin_bp.route('/aodb-writeback-queue', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def aodb_writeback_queue():
    """Monitor and manage AODB write-back queue."""
    from app.services.aodb_writeback import AodbWritebackService
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'retry_failed':
            result = AodbWritebackService.retry_failed_items()
            flash(result.get('message', 'Failed items queued for retry.'), 'success')
        elif action == 'process_now':
            result = AodbWritebackService.process_queue(batch_size=20)
            msg = (
                f"Processed {result['processed']} items: "
                f"{result['succeeded']} succeeded, {result['failed']} failed"
            )
            flash(msg, 'success' if result['failed'] == 0 else 'warning')
        return redirect(url_for('admin.aodb_writeback_queue'))
    
    status = AodbWritebackService.get_queue_status()
    recent_items = AodbWritebackService.get_recent_items(50)
    return render_template(
        'admin/aodb_writeback_queue.html',
        status=status,
        recent_items=recent_items,
    )


@admin_bp.route('/api/aodb-writeback/<int:item_id>', methods=['GET'])
@role_required('admin', 'supervisor')
def api_aodb_writeback_detail(item_id):
    """API endpoint to get write-back item details."""
    item = db.session.get(AodbWriteback, item_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(item.to_dict())
