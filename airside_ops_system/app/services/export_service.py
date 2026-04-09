"""
Export service for CSV/Excel output.
"""
import io
import pandas as pd


class ExportService:
    """Convert query results and form data to CSV/Excel outputs."""

    @staticmethod
    def submissions_to_dataframe(submissions):
        rows = []
        for s in submissions:
            rows.append({
                'id': s.id,
                'reference_number': s.reference_number,
                'form_template_id': s.form_template_id,
                'status': s.status,
                'location_ref': s.location_ref,
                'submission_date': s.submission_date,
                'created_at': s.created_at,
                'submitted_by_user_id': s.submitted_by_user_id,
            })
        return pd.DataFrame(rows)

    @staticmethod
    def to_csv_bytes(df: pd.DataFrame) -> bytes:
        return df.to_csv(index=False).encode('utf-8')

    @staticmethod
    def to_excel_bytes(df: pd.DataFrame, sheet_name='Report') -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        output.seek(0)
        return output.read()
