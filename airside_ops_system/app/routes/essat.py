"""
ESSAT Equipment Inventory and Analytics routes.

Handles:
- Company equipment inventory submission (pre-inspection lists)
- Inventory management (view, edit, link to inspection)
- ESSAT analytics dashboard (compliance trends, issue analysis, quarterly comparisons)
"""
from datetime import date, datetime, timedelta
from collections import defaultdict
from flask import Blueprint, flash, redirect, render_template, request, url_for, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.reference import Company, EquipmentInventory
from app.models.form import FormSubmission, FormTemplate
from app.utils.decorators import role_required

essat_bp = Blueprint('essat', __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STICKER_LABELS = {
    'GREEN': 'Serviceable (Compliant)',
    'YELLOW': 'Conditional (Grace Period)',
    'RED': 'Grounded (Non-Compliant)',
}

STICKER_COLOURS = {
    'GREEN': 'success',
    'YELLOW': 'warning',
    'RED': 'danger',
}


def _normalize_sticker(value):
    raw = (value or '').strip().upper()
    if raw in ('GREEN', 'SERVICEABLE', 'COMPLIANT'):
        return 'GREEN'
    if raw in ('YELLOW', 'ORANGE', 'CONDITIONAL', 'GRACE'):
        return 'YELLOW'
    if raw in ('RED', 'GROUNDED', 'NON-COMPLIANT'):
        return 'RED'
    return ''


def _current_quarter() -> str:
    """Return e.g. '2026-Q1' for the current date."""
    today = date.today()
    q = (today.month - 1) // 3 + 1
    return f'{today.year}-Q{q}'


def _quarter_date_range(cycle: str):
    """
    Given '2026-Q1' returns (date(2026,1,1), date(2026,3,31)).
    Also accepts plain year '2026' → full year.
    """
    try:
        if '-Q' in cycle:
            year_str, q_str = cycle.split('-Q')
            year = int(year_str)
            q = int(q_str)
            starts = [(1, 1), (4, 1), (7, 1), (10, 1)]
            ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
            start = date(year, starts[q - 1][0], starts[q - 1][1])
            end = date(year, ends[q - 1][0], ends[q - 1][1])
            return start, end
        else:
            year = int(cycle)
            return date(year, 1, 1), date(year, 12, 31)
    except (ValueError, IndexError):
        return None, None


def _essat_submissions_for_cycle(template_id, cycle: str):
    """Return Form 18/19 submissions that fall within the quarter date range."""
    start, end = _quarter_date_range(cycle)
    if start is None:
        return []
    q = FormSubmission.query.filter_by(form_template_id=template_id)
    q = q.filter(FormSubmission.submission_date >= start, FormSubmission.submission_date <= end)
    return q.all()


def _available_cycles():
    """Return the last 5 quarters as cycle strings, newest first."""
    today = date.today()
    current_q = (today.month - 1) // 3 + 1
    current_year = today.year
    cycles = []
    q, y = current_q, current_year
    for _ in range(5):
        cycles.append(f'{y}-Q{q}')
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    return cycles


def _extract_checklist_issues(submission):
    """
    Extract checklist items marked as FAIL/NO from a FormSubmission ESSAT form.
    Returns list of strings (item names that failed).
    """
    data = submission.data or {}
    issues = []
    for key, value in data.items():
        if key.startswith('checklist_') and isinstance(value, str):
            if value.strip().upper() in ('FAIL', 'NO', 'N', '0', 'FALSE'):
                # Convert key like 'checklist_Starting_Condition' → 'Starting Condition'
                label = key.replace('checklist_', '').replace('_', ' ').title()
                issues.append(label)
    return issues


# ---------------------------------------------------------------------------
# Equipment Inventory — Submit and Manage
# ---------------------------------------------------------------------------

@essat_bp.route('/inventory')
@login_required
def inventory_list():
    """View all submitted equipment inventory entries."""
    cycle_filter = (request.args.get('cycle') or _current_quarter()).strip()
    company_filter = request.args.get('company', '').strip()
    type_filter = request.args.get('equipment_type', '').strip()

    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    cycles = _available_cycles()

    q = EquipmentInventory.query.filter_by(inspection_cycle=cycle_filter)
    if company_filter:
        co = Company.query.filter_by(name=company_filter).first()
        if co:
            q = q.filter_by(company_id=co.id)
    if type_filter in ('motorised', 'non-motorised'):
        q = q.filter_by(equipment_type=type_filter)

    items = q.order_by(EquipmentInventory.company_id, EquipmentInventory.registration).all()

    # Counts by company for summary
    totals_by_company = defaultdict(lambda: {'total': 0, 'inspected': 0})
    for item in items:
        cname = item.company.name if item.company else 'Unknown'
        totals_by_company[cname]['total'] += 1
        if item.is_inspected:
            totals_by_company[cname]['inspected'] += 1

    return render_template(
        'essat/inventory_list.html',
        items=items,
        companies=companies,
        cycles=cycles,
        cycle_filter=cycle_filter,
        company_filter=company_filter,
        type_filter=type_filter,
        totals_by_company=dict(totals_by_company),
    )


@essat_bp.route('/inventory/submit', methods=['GET', 'POST'])
@login_required
def inventory_submit():
    """Submit equipment inventory for a cycle."""
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    cycles = _available_cycles()

    if request.method == 'POST':
        company_id = request.form.get('company_id', type=int)
        cycle = (request.form.get('inspection_cycle') or '').strip()
        equipment_type = request.form.get('equipment_type', 'motorised')
        registration = (request.form.get('registration') or '').strip()
        description = (request.form.get('description') or '').strip()
        make_model = (request.form.get('make_model') or '').strip()
        year_str = (request.form.get('year_of_manufacture') or '').strip()
        notes = (request.form.get('notes') or '').strip()

        if not company_id or not cycle:
            flash('Company and Inspection Cycle are required.', 'danger')
            return render_template('essat/inventory_submit.html', companies=companies, cycles=cycles)

        year = int(year_str) if year_str.isdigit() else None

        item = EquipmentInventory(
            company_id=company_id,
            inspection_cycle=cycle,
            equipment_type=equipment_type,
            registration=registration or None,
            description=description or None,
            make_model=make_model or None,
            year_of_manufacture=year,
            submitted_date=date.today(),
            submitted_by=current_user.full_name,
            notes=notes or None,
        )
        db.session.add(item)
        db.session.commit()
        flash(f'Equipment entry added to {cycle} inventory.', 'success')
        return redirect(url_for('essat.inventory_list', cycle=cycle))

    return render_template('essat/inventory_submit.html', companies=companies, cycles=cycles,
                           current_cycle=_current_quarter())


@essat_bp.route('/inventory/<int:item_id>/delete', methods=['POST'])
@role_required(['admin', 'supervisor'])
def inventory_delete(item_id):
    item = EquipmentInventory.query.get_or_404(item_id)
    cycle = item.inspection_cycle
    db.session.delete(item)
    db.session.commit()
    flash('Equipment entry removed.', 'success')
    return redirect(url_for('essat.inventory_list', cycle=cycle))


@essat_bp.route('/inventory/<int:item_id>/link-inspection', methods=['POST'])
@login_required
def inventory_link_inspection(item_id):
    """Link an inventory entry to an existing FormSubmission (inspection record)."""
    item = EquipmentInventory.query.get_or_404(item_id)
    submission_id = request.form.get('submission_id', type=int)
    if submission_id:
        item.inspection_submission_id = submission_id
        db.session.commit()
        flash('Linked to inspection record.', 'success')
    return redirect(url_for('essat.inventory_list', cycle=item.inspection_cycle))


# ---------------------------------------------------------------------------
# ESSAT Analytics Dashboard
# ---------------------------------------------------------------------------

@essat_bp.route('/analytics')
@login_required
def analytics():
    """
    ESSAT Analytics Dashboard.
    Covers compliance rates, issue frequencies, quarterly trends, observations.
    """
    cycle_filter = (request.args.get('cycle') or _current_quarter()).strip()
    cycles = _available_cycles()
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()

    # Load Form 18 (Motorised) and Form 19 (Non-Motorised) templates
    t18 = FormTemplate.query.filter_by(form_number=18).first()
    t19 = FormTemplate.query.filter_by(form_number=19).first()

    t18_id = t18.id if t18 else None
    t19_id = t19.id if t19 else None

    # ---- Inventory for cycle ----
    inv_items = EquipmentInventory.query.filter_by(inspection_cycle=cycle_filter).all()
    total_submitted = len(inv_items)
    total_submitted_motorised = sum(1 for i in inv_items if i.equipment_type == 'motorised')
    total_submitted_non_motorised = sum(1 for i in inv_items if i.equipment_type == 'non-motorised')

    # ---- Inspections for cycle ----
    start, end = _quarter_date_range(cycle_filter)

    def _get_submissions(template_id):
        if not template_id or not start:
            return []
        return FormSubmission.query.filter_by(form_template_id=template_id).filter(
            FormSubmission.submission_date >= start,
            FormSubmission.submission_date <= end,
        ).all()

    subs18 = _get_submissions(t18_id)
    subs19 = _get_submissions(t19_id)
    all_subs = subs18 + subs19

    total_inspected = len(all_subs)

    # ---- Sticker status breakdown (motorised Form 18) ----
    sticker_counts = {'GREEN': 0, 'YELLOW': 0, 'RED': 0, 'UNKNOWN': 0}
    for sub in subs18:
        data = sub.data or {}
        s = _normalize_sticker(data.get('sticker_status'))
        if s in sticker_counts:
            sticker_counts[s] += 1
        else:
            sticker_counts['UNKNOWN'] += 1

    # ---- Per-company compliance breakdown ----
    company_stats = {}
    for sub in subs18:
        data = sub.data or {}
        cname = (data.get('organization_company') or 'Unspecified').strip() or 'Unspecified'
        if cname not in company_stats:
            company_stats[cname] = {'GREEN': 0, 'YELLOW': 0, 'RED': 0, 'total': 0}
        s = _normalize_sticker(data.get('sticker_status'))
        company_stats[cname]['total'] += 1
        if s in ('GREEN', 'YELLOW', 'RED'):
            company_stats[cname][s] += 1

    # Add % compliant per company (GREEN / total)
    for cname, stats in company_stats.items():
        total = stats['total']
        stats['pct_compliant'] = round(stats['GREEN'] / total * 100) if total else 0
        stats['pct_conditional'] = round(stats['YELLOW'] / total * 100) if total else 0
        stats['pct_non_compliant'] = round(stats['RED'] / total * 100) if total else 0

    company_stats_sorted = sorted(company_stats.items(), key=lambda x: x[1]['RED'], reverse=True)

    # ---- Issue frequency (checklist failures) ----
    issue_counter = defaultdict(int)
    company_issues = defaultdict(lambda: defaultdict(int))
    for sub in subs18:
        data = sub.data or {}
        cname = (data.get('organization_company') or 'Unspecified').strip() or 'Unspecified'
        for key, value in data.items():
            if not key.startswith('checklist_'):
                continue
            if isinstance(value, str) and value.strip().upper() in ('FAIL', 'NO', 'N', '0', 'FALSE'):
                label = key.replace('checklist_', '').replace('_', ' ').title()
                issue_counter[label] += 1
                company_issues[cname][label] += 1

    top_issues = sorted(issue_counter.items(), key=lambda x: x[1], reverse=True)[:15]

    # Company with most issues
    company_total_issues = {
        cname: sum(counts.values()) for cname, counts in company_issues.items()
    }
    company_issues_sorted = sorted(company_total_issues.items(), key=lambda x: x[1], reverse=True)

    # ---- Quarterly trend (last 3 quarters including current) ----
    trend_cycles = cycles[:3][::-1]  # oldest first
    trend_data = []
    for cyc in trend_cycles:
        inv_count = EquipmentInventory.query.filter_by(inspection_cycle=cyc).count()
        s, e = _quarter_date_range(cyc)
        if s and t18_id:
            insp_count = FormSubmission.query.filter_by(form_template_id=t18_id).filter(
                FormSubmission.submission_date >= s,
                FormSubmission.submission_date <= e,
            ).count()
            if t19_id:
                insp_count += FormSubmission.query.filter_by(form_template_id=t19_id).filter(
                    FormSubmission.submission_date >= s,
                    FormSubmission.submission_date <= e,
                ).count()
        else:
            insp_count = 0
        trend_data.append({
            'cycle': cyc,
            'submitted': inv_count,
            'inspected': insp_count,
        })

    # ---- Observations & Recommendations from Form 18 Remarks sections ----
    observations = []
    for sub in subs18:
        data = sub.data or {}
        general_remarks = (data.get('general_remarks') or '').strip()
        recommendations = (data.get('recommendations') or '').strip()
        if general_remarks or recommendations:
            observations.append({
                'submission': sub,
                'company': (data.get('organization_company') or 'Unspecified').strip(),
                'vehicle_no': (data.get('airside_vehicle_no') or '').strip(),
                'inspection_date': data.get('inspection_date') or '',
                'general_remarks': general_remarks,
                'recommendations': recommendations,
            })

    # Inventory vs inspected coverage (submitted_inventory that links to inspection)
    linked_count = sum(1 for i in inv_items if i.is_inspected)
    unlinked_count = total_submitted - linked_count

    return render_template(
        'essat/analytics.html',
        cycle_filter=cycle_filter,
        cycles=cycles,
        companies=companies,
        # Summary numbers
        total_submitted=total_submitted,
        total_submitted_motorised=total_submitted_motorised,
        total_submitted_non_motorised=total_submitted_non_motorised,
        total_inspected=total_inspected,
        linked_count=linked_count,
        unlinked_count=unlinked_count,
        # Sticker breakdown
        sticker_counts=sticker_counts,
        # Per-company compliance
        company_stats=company_stats_sorted,
        # Issue analysis
        top_issues=top_issues,
        company_issues=dict(company_issues),
        company_issues_sorted=company_issues_sorted,
        # Quarterly trend
        trend_data=trend_data,
        # Observations
        observations=observations,
    )
