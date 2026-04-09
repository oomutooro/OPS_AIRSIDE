"""
Apron management routes: stand allocation, shift handover, staff deployment, TPBB ops.
"""
from datetime import date, datetime, timedelta
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.models.apron import StandAllocation, Shift, ShiftRoster, HandoverReport
from app.models.reference import ParkingStand
from app.models.user import User
from app.models.form import FormSubmission, FormTemplate
from app.utils.decorators import role_required

apron_bp = Blueprint('apron', __name__)


def _parse_iso_date(value: str, default_value: date = None) -> date:
    if not value:
        return default_value or date.today()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return default_value or date.today()


def _user_is_on_shift(user_id: int, duty_date: date, shift_type: str) -> bool:
    entry = ShiftRoster.query.filter_by(user_id=user_id, duty_date=duty_date).first()
    if not entry:
        return False
    return entry.duty_type == shift_type


def _on_duty_users(duty_date: date, shift_type: str):
    return db.session.query(User).join(ShiftRoster, ShiftRoster.user_id == User.id).filter(
        ShiftRoster.duty_date == duty_date,
        ShiftRoster.duty_type == shift_type,
        User.is_active.is_(True)
    ).order_by(User.full_name).all()


@apron_bp.route('/stand-allocation', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'supervisor', 'inspector', 'operator')
def stand_allocation():
    if request.method == 'POST':
        allocation = StandAllocation(
            allocation_date=date.today(),
            flight_number=request.form.get('flight_number'),
            aircraft_registration=request.form.get('aircraft_registration'),
            aircraft_type=request.form.get('aircraft_type'),
            allocated_stand_code=request.form.get('allocated_stand'),
            requested_stand_code=request.form.get('requested_stand'),
            requires_follow_me=bool(request.form.get('requires_follow_me')),
            flight_type=request.form.get('flight_type'),
            status='allocated',
            allocated_by_user_id=current_user.id,
        )
        db.session.add(allocation)
        db.session.commit()
        flash('Stand allocation saved.', 'success')
        return redirect(url_for('apron.stand_allocation'))

    stands = ParkingStand.query.filter_by(is_active=True).order_by(ParkingStand.stand_code).all()
    allocations = StandAllocation.query.order_by(StandAllocation.created_at.desc()).limit(20).all()
    return render_template('apron/stand_allocation.html', stands=stands, allocations=allocations)


@apron_bp.route('/shift-handover', methods=['GET', 'POST'])
@login_required
def shift_handover():
    handover_date = _parse_iso_date(request.form.get('handover_date') if request.method == 'POST' else request.args.get('handover_date'))

    if request.method == 'POST':
        outgoing_user_id = int(request.form.get('outgoing_user_id') or 0)
        incoming_user_id = int(request.form.get('incoming_user_id') or 0)
        outgoing_shift_type = (request.form.get('outgoing_shift_type') or 'day').lower()
        incoming_shift_type = (request.form.get('incoming_shift_type') or 'night').lower()

        outgoing_user = db.session.get(User, outgoing_user_id)
        incoming_user = db.session.get(User, incoming_user_id)

        if not outgoing_user or not incoming_user:
            flash('Please select valid outgoing and incoming shift personnel.', 'danger')
            return redirect(url_for('apron.shift_handover', handover_date=handover_date.isoformat()))

        if not _user_is_on_shift(outgoing_user.id, handover_date, outgoing_shift_type):
            flash(f'{outgoing_user.full_name} is not rostered for {outgoing_shift_type} shift on {handover_date}.', 'danger')
            return redirect(url_for('apron.shift_handover', handover_date=handover_date.isoformat()))

        if not _user_is_on_shift(incoming_user.id, handover_date, incoming_shift_type):
            flash(f'{incoming_user.full_name} is not rostered for {incoming_shift_type} shift on {handover_date}.', 'danger')
            return redirect(url_for('apron.shift_handover', handover_date=handover_date.isoformat()))

        report = HandoverReport(
            handover_date=handover_date,
            outgoing_name=outgoing_user.full_name,
            outgoing_badge=outgoing_user.badge_number,
            incoming_name=incoming_user.full_name,
            incoming_badge=incoming_user.badge_number,
            major_events=request.form.get('major_events'),
            pending_issues=request.form.get('pending_issues'),
            outgoing_sign=request.form.get('outgoing_signature'),
            incoming_sign=request.form.get('incoming_signature'),
            status='complete' if request.form.get('outgoing_signature') and request.form.get('incoming_signature') else 'pending',
        )
        db.session.add(report)

        template = FormTemplate.query.filter_by(form_number=2).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Apron Tower',
                data={
                    'handover_date': handover_date.isoformat(),
                    'outgoing_shift_type': outgoing_shift_type,
                    'incoming_shift_type': incoming_shift_type,
                    'outgoing_user_id': outgoing_user.id,
                    'incoming_user_id': incoming_user.id,
                    'outgoing_name': report.outgoing_name,
                    'incoming_name': report.incoming_name,
                    'major_events': report.major_events,
                    'pending_issues': report.pending_issues,
                },
            )
            db.session.add(submission)

        db.session.commit()
        flash('Shift handover report submitted.', 'success')
        return redirect(url_for('apron.shift_handover'))

    reports = HandoverReport.query.order_by(HandoverReport.created_at.desc()).limit(20).all()
    day_users = _on_duty_users(handover_date, 'day')
    night_users = _on_duty_users(handover_date, 'night')
    return render_template(
        'apron/shift_handover.html',
        reports=reports,
        handover_date=handover_date,
        day_users=day_users,
        night_users=night_users,
    )


@apron_bp.route('/shift-roster', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'supervisor')
def shift_roster():
    if request.method == 'POST':
        start_date = _parse_iso_date(request.form.get('start_date'))
        end_date = _parse_iso_date(request.form.get('end_date'), start_date)
        user_ids = [int(uid) for uid in request.form.getlist('user_ids') if uid.isdigit()]
        start_cycle = (request.form.get('start_cycle') or 'day').lower()
        overwrite_existing = request.form.get('overwrite_existing') == 'on'

        if end_date < start_date:
            flash('End date must be on or after start date.', 'danger')
            return redirect(url_for('apron.shift_roster'))

        if not user_ids:
            flash('Please select at least one user for roster generation.', 'danger')
            return redirect(url_for('apron.shift_roster'))

        start_idx = ShiftRoster.index_for_duty(start_cycle)
        days = (end_date - start_date).days + 1
        created_count = 0
        updated_count = 0

        for user_id in user_ids:
            for offset in range(days):
                duty_date = start_date + timedelta(days=offset)
                cycle_idx = (start_idx + offset) % 4
                duty_type = ShiftRoster.duty_for_index(cycle_idx)
                entry = ShiftRoster.query.filter_by(user_id=user_id, duty_date=duty_date).first()
                if entry:
                    if overwrite_existing:
                        entry.duty_type = duty_type
                        entry.cycle_day_index = cycle_idx
                        entry.created_by_user_id = current_user.id
                        updated_count += 1
                else:
                    db.session.add(ShiftRoster(
                        duty_date=duty_date,
                        user_id=user_id,
                        duty_type=duty_type,
                        cycle_day_index=cycle_idx,
                        created_by_user_id=current_user.id,
                    ))
                    created_count += 1

        db.session.commit()
        flash(f'Roster saved: {created_count} created, {updated_count} updated.', 'success')
        return redirect(url_for('apron.shift_roster'))

    target_date = _parse_iso_date(request.args.get('date'))
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    roster_entries = ShiftRoster.query.filter_by(duty_date=target_date).order_by(ShiftRoster.duty_type, ShiftRoster.user_id).all()
    return render_template(
        'apron/shift_roster.html',
        users=users,
        target_date=target_date,
        roster_entries=roster_entries,
    )


@apron_bp.route('/staff-deployment', methods=['GET', 'POST'])
@login_required
def staff_deployment():
    if request.method == 'POST':
        template = FormTemplate.query.filter_by(form_number=23).first()
        if template:
            data = {
                'shift_date': request.form.get('shift_date'),
                'shift_type': request.form.get('shift_type'),
                'scheduled_movements': request.form.get('scheduled_movements'),
                'non_scheduled_movements': request.form.get('non_scheduled_movements'),
                'deployed_officers': request.form.getlist('deployed_officers'),
                'other_deployments': request.form.get('other_deployments'),
            }
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Airside',
                data=data,
            )
            db.session.add(submission)
            db.session.commit()
            flash('Staff deployment plan submitted.', 'success')
        return redirect(url_for('apron.staff_deployment'))

    submissions = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 23
    ).order_by(FormSubmission.created_at.desc()).limit(20).all()
    return render_template('apron/staff_deployment.html', submissions=submissions)


@apron_bp.route('/tpbb-operations', methods=['GET', 'POST'])
@login_required
def tpbb_operations():
    if request.method == 'POST':
        template = FormTemplate.query.filter_by(form_number=5).first()
        if template:
            data = {
                'bridge_no': request.form.get('bridge_no'),
                'flight_number': request.form.get('flight_number'),
                'pre_arrival_test': request.form.get('pre_arrival_test'),
                'docking_time': request.form.get('docking_time'),
                'backoff_time': request.form.get('backoff_time'),
                'remarks': request.form.get('remarks'),
            }
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Terminal Apron',
                data=data,
            )
            db.session.add(submission)
            db.session.commit()
            flash('TPBB operation recorded.', 'success')
        return redirect(url_for('apron.tpbb_operations'))

    logs = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 5
    ).order_by(FormSubmission.created_at.desc()).limit(20).all()
    return render_template('apron/tpbb_operations.html', logs=logs)
