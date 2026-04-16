"""
Reporting routes: daily ops report, analytics dashboard, custom report builder, exports.
"""
from collections import Counter
from io import BytesIO
from datetime import date, datetime
from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from app.models.form import FormSubmission, FormTemplate
from app.models.reference import Company
from app.services.export_service import ExportService
from app.services.analytics_service import AnalyticsService
from app.services.pdf_generator import PDFGeneratorService
from app.services.workflow_service import WorkflowService
from flask_login import current_user

report_bp = Blueprint('report', __name__)


LEGEND_CODE_TO_INTERACTION = {
    'A': 'EQUIPMENT TO EQUIPMENT',
    'B': 'EQUIPMENT TO AIRCRAFT',
    'C': 'EQUIPMENT TO PERSONNEL',
    'D': 'EQUIPMENT TO PROPERTY',
    'E': 'EQUIPMENT TO PASSENGER',
    'F': 'AIRCRAFT TO EQUIPMENT',
    'G': 'AIRCRAFT TO AIRCRAFT',
    'H': 'AIRCRAFT TO PERSONNEL',
    'I': 'AIRCRAFT TO PROPERTY',
    'J': 'AIRCRAFT TO PASSENGER',
    'K': 'PERSONNEL TO EQUIPMENT',
    'L': 'PERSONNEL TO AIRCRAFT',
    'M': 'PERSONNEL TO PERSONNEL',
    'N': 'PERSONNEL TO PROPERTY',
    'O': 'PERSONNEL TO PASSENGER',
    'P': 'PROPERTY TO EQUIPMENT',
    'Q': 'PROPERTY TO AIRCRAFT',
    'R': 'PROPERTY TO PERSONNEL',
    'S': 'PROPERTY TO PROPERTY',
    'T': 'PROPERTY TO PASSENGER',
}


def _quarter_label(dt: date) -> str:
    q = (dt.month - 1) // 3 + 1
    return f'{dt.year}-Q{q}'


def _safe_date_from_submission(submission, field_name='occurrence_date'):
    data = submission.data or {}
    raw = (data.get(field_name) or '').strip()
    if raw:
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass
    if submission.submission_date:
        return submission.submission_date
    return submission.created_at.date()


def _is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or '').strip().lower()
    return raw in ('1', 'true', 'yes', 'y', 'on', 'checked')


def _normalize_incident_cause(value):
    raw = (value or '').strip().lower()
    mapping = {
        'bird strike': 'BIRD STRIKE',
        'bird_strike': 'BIRD STRIKE',
        'human error': 'HUMAN ERROR',
        'human_error': 'HUMAN ERROR',
        'bad weather': 'BAD WEATHER',
        'weather': 'BAD WEATHER',
        'medical': 'MEDICAL',
        'passenger misconduct': 'PASSENGER MISCONDUCT',
        'passenger_misconduct': 'PASSENGER MISCONDUCT',
        'tyre burst': 'TYRE BURST',
        'tyre_burst': 'TYRE BURST',
        'passenger cause': 'PASSENGER CAUSE',
        'passenger_cause': 'PASSENGER CAUSE',
        'airport environment': 'AIRPORT ENVIRONMENT',
        'airport_environment': 'AIRPORT ENVIRONMENT',
        'fod': 'FOD',
        'wildlife': 'WILDLIFE',
    }
    if raw in mapping:
        return mapping[raw]
    return (value or 'OTHER').strip().upper() or 'OTHER'


def _normalize_incident_legend(value):
    raw = (value or '').strip().lower()
    mapping = {
        'accident': 'ACCIDENT',
        'incident': 'INCIDENT',
        'near_miss': 'NEAR MISS',
        'near miss': 'NEAR MISS',
        'runway_incursion': 'RUNWAY INCURSION',
        'runway incursion': 'RUNWAY INCURSION',
        'bird_strike': 'BIRD STRIKE',
        'bird strike': 'BIRD STRIKE',
        'wildlife': 'WILDLIFE',
    }
    return mapping.get(raw, (value or 'OTHER').strip().upper() or 'OTHER')


def _normalize_interaction(data):
    explicit = (data.get('interaction_category') or '').strip().upper()
    if explicit:
        return explicit
    legend_code = (data.get('legend_code') or '').strip().upper()
    if legend_code in LEGEND_CODE_TO_INTERACTION:
        return LEGEND_CODE_TO_INTERACTION[legend_code]
    source = (data.get('interaction_source') or '').strip().upper()
    target = (data.get('interaction_target') or '').strip().upper()
    if source and target:
        return f'{source} TO {target}'
    return 'UNSPECIFIED'


def _incident_analytics_payload(quarter_filter=''):
    template = FormTemplate.query.filter_by(form_number=10).first()
    if not template:
        return {
            'has_template': False,
            'rows': [],
            'available_quarters': [],
            'quarter_filter': quarter_filter,
            'quarter_totals': {},
            'legend_counts': {},
            'interaction_counts': {},
            'cause_counts': {},
            'impact_counts': {},
            'total_occurrences': 0,
            'kpis': {},
            'top_interactions': [],
            'top_causes': [],
        }

    submissions = FormSubmission.query.filter_by(form_template_id=template.id).order_by(FormSubmission.created_at.desc()).all()

    rows = []
    for s in submissions:
        data = s.data or {}
        occurrence_dt = _safe_date_from_submission(s)
        quarter = _quarter_label(occurrence_dt)
        impact_equipment = _is_checked(data.get('damage_equipment')) or _is_checked(data.get('damage_to_equipment'))
        impact_aircraft = _is_checked(data.get('damage_aircraft')) or _is_checked(data.get('damage_to_aircraft'))
        impact_property = _is_checked(data.get('damage_property')) or _is_checked(data.get('damage_to_property'))
        impact_personnel = _is_checked(data.get('harm_personnel')) or _is_checked(data.get('harm_to_personnel'))
        impact_passenger = _is_checked(data.get('harm_passenger')) or _is_checked(data.get('harm_to_passenger'))

        rows.append({
            'submission': s,
            'reference_number': s.reference_number or f'SUB-{s.id}',
            'occurrence_date': occurrence_dt,
            'quarter': quarter,
            'location': (data.get('location') or s.location_ref or '').strip(),
            'legend': _normalize_incident_legend(data.get('incident_legend') or data.get('incident_type')),
            'legend_code': (data.get('legend_code') or '').strip().upper(),
            'interaction': _normalize_interaction(data),
            'cause': _normalize_incident_cause(data.get('cause_category') or data.get('cause_or_factor')),
            'impact_equipment': impact_equipment,
            'impact_aircraft': impact_aircraft,
            'impact_property': impact_property,
            'impact_personnel': impact_personnel,
            'impact_passenger': impact_passenger,
            'description': (data.get('description') or '').strip(),
            'notes': (data.get('incident_notes') or data.get('observations') or '').strip(),
        })

    available_quarters = sorted({row['quarter'] for row in rows}, reverse=True)
    if not quarter_filter:
        quarter_filter = available_quarters[0] if available_quarters else _quarter_label(date.today())

    filtered = [row for row in rows if row['quarter'] == quarter_filter] if quarter_filter else list(rows)

    quarter_totals = Counter(row['quarter'] for row in rows)
    legend_counts = Counter(row['legend'] for row in filtered)
    interaction_counts = Counter(row['interaction'] for row in filtered)
    cause_counts = Counter(row['cause'] for row in filtered)

    impact_counts = {
        'Damage to Equipment': sum(1 for row in filtered if row['impact_equipment']),
        'Damage to Aircraft': sum(1 for row in filtered if row['impact_aircraft']),
        'Damage to Property': sum(1 for row in filtered if row['impact_property']),
        'Harm to Personnel': sum(1 for row in filtered if row['impact_personnel']),
        'Harm to Passenger': sum(1 for row in filtered if row['impact_passenger']),
    }

    total_occurrences = len(filtered)
    aircraft_damage_rate = round((impact_counts['Damage to Aircraft'] / total_occurrences) * 100, 1) if total_occurrences else 0
    personnel_harm_rate = round((impact_counts['Harm to Personnel'] / total_occurrences) * 100, 1) if total_occurrences else 0

    return {
        'has_template': True,
        'rows': filtered,
        'available_quarters': available_quarters,
        'quarter_filter': quarter_filter,
        'quarter_totals': dict(sorted(quarter_totals.items())),
        'legend_counts': dict(legend_counts.most_common()),
        'interaction_counts': dict(interaction_counts.most_common()),
        'cause_counts': dict(cause_counts.most_common()),
        'impact_counts': impact_counts,
        'total_occurrences': total_occurrences,
        'kpis': {
            'Total Incidents (Quarter)': total_occurrences,
            'Aircraft Damage Rate %': aircraft_damage_rate,
            'Personnel Harm Rate %': personnel_harm_rate,
            'Top Cause': cause_counts.most_common(1)[0][0] if cause_counts else 'N/A',
        },
        'top_interactions': interaction_counts.most_common(12),
        'top_causes': cause_counts.most_common(12),
    }


def _normalize_sticker_status(value):
    raw = (value or '').strip().upper()
    if raw in ('GREEN', 'SERVICEABLE', 'COMPLIANT'):
        return 'GREEN'
    if raw in ('YELLOW', 'ORANGE', 'CONDITIONAL', 'GRACE'):
        return 'YELLOW'
    if raw in ('RED', 'GROUNDED', 'NON-COMPLIANT'):
        return 'RED'
    return ''


def _safe_submission_datetime(submission):
    data = submission.data or {}
    inspection_date = data.get('inspection_date')
    inspection_time = data.get('inspection_time')
    if inspection_date and inspection_time:
        try:
            return datetime.fromisoformat(f'{inspection_date}T{inspection_time}')
        except ValueError:
            pass
    if submission.submission_date and submission.submission_time:
        return datetime.combine(submission.submission_date, submission.submission_time)
    return submission.created_at


def _build_essat_sticker_rows(submissions):
    rows = []
    for submission in submissions:
        data = submission.data or {}
        sticker_status = _normalize_sticker_status(data.get('sticker_status'))
        rows.append({
            'submission': submission,
            'reference_number': submission.reference_number or f'SUB-{submission.id}',
            'company': (data.get('organization_company') or 'Unspecified').strip() or 'Unspecified',
            'vehicle_no': (data.get('airside_vehicle_no') or '').strip(),
            'equipment_description': (data.get('vehicle_equipment_description') or '').strip(),
            'sticker_no': (data.get('sticker_no') or '').strip(),
            'sticker_status': sticker_status,
            'serviceability_label': 'Serviceable' if sticker_status == 'GREEN' else 'Conditional (Grace)' if sticker_status == 'YELLOW' else 'Grounded' if sticker_status == 'RED' else 'Unknown',
            'inspection_date': data.get('inspection_date') or '',
            'inspection_time': data.get('inspection_time') or '',
            'submitted_at': _safe_submission_datetime(submission),
        })
    return rows


@report_bp.route('/daily-ops-report', methods=['GET', 'POST'])
@login_required
def daily_ops_report():
    if request.method == 'POST':
        # Uses Form 12 template submission storage
        from app import db
        template = FormTemplate.query.filter_by(form_number=12).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Airside Ops',
                data=request.form.to_dict(flat=False),
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)
            db.session.commit()
            flash('Daily operational report submitted.', 'success')
        return redirect(url_for('report.daily_ops_report'))

    reports = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 12
    ).order_by(FormSubmission.created_at.desc()).limit(30).all()
    return render_template('reports/daily_ops_report.html', reports=reports)


@report_bp.route('/analytics-dashboard')
@login_required
def analytics_dashboard():
    kpis = AnalyticsService.get_dashboard_kpis()
    trend = AnalyticsService.incident_trend(30)
    return render_template('reports/analytics_dashboard.html', kpis=kpis, trend=trend)


@report_bp.route('/custom-report-builder')
@login_required
def custom_report_builder():
    templates = FormTemplate.query.order_by(FormTemplate.form_number).all()
    return render_template('reports/custom_report_builder.html', templates=templates)


@report_bp.route('/essat-sticker-report')
@login_required
def essat_sticker_report():
    template = FormTemplate.query.filter_by(form_number=18).first()
    if not template:
        flash('ESSAT Motorised form template is not configured.', 'warning')
        return redirect(url_for('report.custom_report_builder'))

    registered_companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    company_filter = (request.args.get('company') or '').strip()
    sticker_filter = _normalize_sticker_status(request.args.get('sticker_status') or 'GREEN') or 'GREEN'
    from_date = (request.args.get('from_date') or '').strip()
    to_date = (request.args.get('to_date') or '').strip()

    submissions = FormSubmission.query.filter_by(form_template_id=template.id).order_by(FormSubmission.created_at.desc()).all()
    rows = _build_essat_sticker_rows(submissions)

    if company_filter:
        rows = [row for row in rows if row['company'].lower() == company_filter.lower()]
    if sticker_filter:
        rows = [row for row in rows if row['sticker_status'] == sticker_filter]
    if from_date:
        rows = [row for row in rows if row['inspection_date'] and row['inspection_date'] >= from_date]
    if to_date:
        rows = [row for row in rows if row['inspection_date'] and row['inspection_date'] <= to_date]

    rows.sort(key=lambda row: (
        row['company'].lower(),
        row['inspection_date'] or '9999-12-31',
        row['inspection_time'] or '99:99',
        row['vehicle_no'].lower(),
    ))

    return render_template(
        'reports/essat_sticker_report.html',
        rows=rows,
        companies=registered_companies,
        company_filter=company_filter,
        sticker_filter=sticker_filter,
        from_date=from_date,
        to_date=to_date,
    )


@report_bp.route('/incident-analytics')
@login_required
def incident_analytics_report():
    quarter_filter = (request.args.get('quarter') or '').strip()
    payload = _incident_analytics_payload(quarter_filter=quarter_filter)
    if not payload['has_template']:
        flash('Incident report template (Form 10) is not configured.', 'warning')
        return redirect(url_for('report.custom_report_builder'))
    return render_template('reports/incident_analytics.html', **payload)


@report_bp.route('/incident-analytics/export.xlsx')
@login_required
def incident_analytics_export_excel():
    import pandas as pd

    quarter_filter = (request.args.get('quarter') or '').strip()
    payload = _incident_analytics_payload(quarter_filter=quarter_filter)

    summary_rows = [
        {'Metric': k, 'Value': v} for k, v in payload['kpis'].items()
    ]
    by_quarter_rows = [
        {'Quarter': q, 'Total Occurrences': total}
        for q, total in payload['quarter_totals'].items()
    ]
    by_cause_rows = [
        {'Cause': cause, 'Occurrences': count}
        for cause, count in payload['cause_counts'].items()
    ]
    by_interaction_rows = [
        {'Interaction Category': cat, 'Occurrences': count}
        for cat, count in payload['interaction_counts'].items()
    ]
    detailed_rows = [
        {
            'Reference': row['reference_number'],
            'Occurrence Date': row['occurrence_date'],
            'Quarter': row['quarter'],
            'Legend': row['legend'],
            'Legend Code': row.get('legend_code', ''),
            'Interaction': row['interaction'],
            'Cause': row['cause'],
            'Location': row['location'],
            'Damage Equipment': row['impact_equipment'],
            'Damage Aircraft': row['impact_aircraft'],
            'Damage Property': row['impact_property'],
            'Harm Personnel': row['impact_personnel'],
            'Harm Passenger': row['impact_passenger'],
            'Description': row['description'],
            'Notes': row['notes'],
        }
        for row in payload['rows']
    ]

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name='Summary')
        pd.DataFrame(by_quarter_rows).to_excel(writer, index=False, sheet_name='By Quarter')
        pd.DataFrame(by_cause_rows).to_excel(writer, index=False, sheet_name='By Cause')
        pd.DataFrame(by_interaction_rows).to_excel(writer, index=False, sheet_name='By Interaction')
        pd.DataFrame(detailed_rows).to_excel(writer, index=False, sheet_name='Detailed Records')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f'incident_analytics_{payload["quarter_filter"]}_{date.today().isoformat()}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@report_bp.route('/incident-analytics/export.pdf')
@login_required
def incident_analytics_export_pdf():
    quarter_filter = (request.args.get('quarter') or '').strip()
    payload = _incident_analytics_payload(quarter_filter=quarter_filter)
    service = PDFGeneratorService()

    summary_lines = []
    for cause, count in payload['top_causes'][:5]:
        summary_lines.append(f'Top Cause: {cause} ({count})')
    for category, count in payload['top_interactions'][:5]:
        summary_lines.append(f'Interaction: {category} ({count})')
    for impact, count in payload['impact_counts'].items():
        summary_lines.append(f'{impact}: {count}')

    pdf_bytes = service.generate_dashboard_report_pdf(
        title=f'Incident Analytics Report - {payload["quarter_filter"]}',
        kpis=payload['kpis'],
        charts_summary=summary_lines,
    )
    return send_file(
        BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=f'incident_analytics_{payload["quarter_filter"]}_{date.today().isoformat()}.pdf',
        mimetype='application/pdf',
    )


@report_bp.route('/export/submissions.csv')
@login_required
def export_submissions_csv():
    submissions = FormSubmission.query.order_by(FormSubmission.created_at.desc()).all()
    df = ExportService.submissions_to_dataframe(submissions)
    csv_bytes = ExportService.to_csv_bytes(df)
    return Response(
        csv_bytes,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=submissions_{date.today().isoformat()}.csv'}
    )


@report_bp.route('/export/submissions.xlsx')
@login_required
def export_submissions_excel():
    submissions = FormSubmission.query.order_by(FormSubmission.created_at.desc()).all()
    df = ExportService.submissions_to_dataframe(submissions)
    excel_bytes = ExportService.to_excel_bytes(df, sheet_name='Submissions')
    return send_file(
        BytesIO(excel_bytes),
        as_attachment=True,
        download_name=f'submissions_{date.today().isoformat()}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@report_bp.route('/submission/<int:submission_id>/pdf')
@login_required
def submission_pdf(submission_id):
    submission = FormSubmission.query.get_or_404(submission_id)
    service = PDFGeneratorService()
    title = submission.template.title if submission.template else 'Airside Form'
    pdf_bytes = service.generate_form_pdf(submission, template_title=title)
    filename = f"{submission.reference_number or f'SUB-{submission.id}'}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf',
    )
