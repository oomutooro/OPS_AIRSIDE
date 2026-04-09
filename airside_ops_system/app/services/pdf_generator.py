"""
PDF generation service for forms and reports.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from app.utils.form_schemas import FORM_SCHEMAS


class PDFGeneratorService:
    """Generate PDFs for form submissions matching manual structure."""

    def __init__(self):
        self.styles = getSampleStyleSheet()

    def _build_header(self, form_number: int, template_title: str):
        rows = [
            ['Entebbe International Airport', 'Airside Operations Digital Form'],
            [f'Form {form_number}', template_title],
            ['Generated', datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')],
        ]
        table = Table(rows, colWidths=[40 * mm, 135 * mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1a56db')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f1f5f9')),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.HexColor('#64748b')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        return table

    def _value(self, data: dict, key: str):
        val = data.get(key, '-')
        if isinstance(val, list):
            return ', '.join(str(v) for v in val)
        return str(val)

    def _build_schema_sections(self, form_number: int, data: dict):
        schema = FORM_SCHEMAS.get(form_number, {'sections': []})
        blocks = []
        for section in schema.get('sections', []):
            blocks.append(Paragraph(f"<b>{section.get('name', 'Section')}</b>", self.styles['Heading4']))

            if section.get('fields'):
                rows = [['Field', 'Value']]
                for field in section['fields']:
                    rows.append([field.replace('_', ' ').title(), self._value(data, field)])
                tbl = Table(rows, colWidths=[65 * mm, 110 * mm], repeatRows=1)
                tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f59e0b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                ]))
                blocks.append(tbl)
                blocks.append(Spacer(1, 3 * mm))

            if section.get('checklist'):
                rows = [['Checklist Item', 'Status', 'Remark']]
                sec_name = section.get('name', '').replace(' ', '_')
                for idx, item in enumerate(section['checklist']):
                    status_key = f'check_{idx}_{sec_name}'
                    remark_key = f'remark_{idx}_{sec_name}'
                    rows.append([
                        item,
                        self._value(data, status_key),
                        self._value(data, remark_key),
                    ])
                tbl = Table(rows, colWidths=[90 * mm, 30 * mm, 55 * mm], repeatRows=1)
                tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                ]))
                blocks.append(tbl)
                blocks.append(Spacer(1, 3 * mm))

        return blocks

    def generate_form_pdf(self, form_submission, template_title='Airside Form'):
        """Generate a manual-style, sectioned PDF based on form schema."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )

        elements = []
        form_number = form_submission.template.form_number if form_submission.template else 0
        full_title = template_title
        schema = FORM_SCHEMAS.get(form_number)
        if schema and schema.get('title'):
            full_title = schema['title']

        elements.append(self._build_header(form_number, full_title))
        elements.append(Spacer(1, 4 * mm))

        meta_rows = [
            ['Reference', form_submission.reference_number or '-'],
            ['Status', form_submission.status],
            ['Location', form_submission.location_ref or '-'],
            ['Inspector', form_submission.submitted_by.full_name if form_submission.submitted_by else '-'],
            ['Submission Date', form_submission.submission_date.strftime('%Y-%m-%d') if form_submission.submission_date else '-'],
            ['Generated At', datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')],
        ]
        meta_table = Table(meta_rows, colWidths=[45 * mm, 130 * mm])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 6 * mm))

        data = form_submission.data or {}
        elements.extend(self._build_schema_sections(form_number, data))

        elements.append(Spacer(1, 4 * mm))
        signature_rows = [
            ['Signature Captured', 'Yes' if form_submission.outgoing_signature else 'No'],
            ['Recorded IP', data.get('ip_address', '-')],
        ]
        sig_table = Table(signature_rows, colWidths=[60 * mm, 115 * mm])
        sig_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))
        elements.append(sig_table)

        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data

    def generate_dashboard_report_pdf(self, title, kpis: dict, charts_summary: list):
        """Generate management report PDF from dashboard stats."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
        elements = [Paragraph(f"<b>{title}</b>", self.styles['Title']), Spacer(1, 10)]

        kpi_rows = [['KPI', 'Value']] + [[k, str(v)] for k, v in kpis.items()]
        kpi_table = Table(kpi_rows, colWidths=[120, 120])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f59e0b')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 15))

        elements.append(Paragraph('<b>Charts Summary</b>', self.styles['Heading3']))
        for item in charts_summary:
            elements.append(Paragraph(f"- {item}", self.styles['BodyText']))

        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
