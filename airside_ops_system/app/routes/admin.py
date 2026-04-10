"""
Administration routes: user management, reference data, form builder, system settings.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required
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


@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'supervisor', 'auditor', 'inspector')
def user_management():
    if request.method == 'POST':
        selected_role = request.form.get('role', 'viewer')
        if not _validate_user_role(selected_role):
            flash('You are not allowed to assign that role.', 'danger')
            return redirect(url_for('admin.user_management'))

        if User.query.filter_by(username=request.form.get('username')).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('admin.user_management'))

        if User.query.filter_by(email=request.form.get('email')).first():
            flash('Email already exists.', 'danger')
            return redirect(url_for('admin.user_management'))

        user = User(
            username=request.form.get('username'),
            email=request.form.get('email'),
            full_name=request.form.get('full_name'),
            role=selected_role,
            badge_number=request.form.get('badge_number'),
            department=request.form.get('department'),
            is_active=bool(request.form.get('is_active', True)),
        )
        user.set_password(request.form.get('password', 'ChangeMe123!'))
        db.session.add(user)
        db.session.commit()
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
@login_required
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
        selected_role = request.form.get('role', user.role)
        if not _validate_user_role(selected_role):
            flash('You are not allowed to assign that role.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        existing_username = User.query.filter(User.username == request.form.get('username'), User.id != user.id).first()
        if existing_username:
            flash('Username already exists.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        existing_email = User.query.filter(User.email == request.form.get('email'), User.id != user.id).first()
        if existing_email:
            flash('Email already exists.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        user.username = request.form.get('username')
        user.full_name = request.form.get('full_name')
        user.email = request.form.get('email')
        user.badge_number = request.form.get('badge_number')
        user.department = request.form.get('department')
        user.role = selected_role
        user.is_active = request.form.get('is_active') == 'on'

        new_password = request.form.get('password')
        if new_password:
            user.set_password(new_password)

        db.session.commit()
        flash('User access updated.', 'success')
        return redirect(url_for('admin.user_management'))

    return render_template(
        'admin/edit_user.html',
        user=user,
        role_labels=ROLE_LABELS,
        assignable_roles=_assignable_roles(current_user),
    )


@admin_bp.route('/reference-data')
@login_required
@role_required('admin', 'supervisor')
def reference_data():
    companies = Company.query.order_by(Company.name).all()
    locations = AirsideLocation.query.order_by(AirsideLocation.code).all()
    stands = ParkingStand.query.order_by(ParkingStand.stand_code).all()
    return render_template('admin/reference_data.html', companies=companies, locations=locations, stands=stands)


@admin_bp.route('/form-builder', methods=['GET', 'POST'])
@login_required
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
@login_required
@role_required('admin')
def system_settings():
    return render_template('admin/system_settings.html')


# ──────────────────────────────────────────────────────────────────
# AODB Write-back Queue Monitoring
# ──────────────────────────────────────────────────────────────────

@admin_bp.route('/aodb-writeback-queue', methods=['GET', 'POST'])
@login_required
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
@login_required
@role_required('admin', 'supervisor')
def api_aodb_writeback_detail(item_id):
    """API endpoint to get write-back item details."""
    item = db.session.get(AodbWriteback, item_id)
    if not item:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(item.to_dict())
