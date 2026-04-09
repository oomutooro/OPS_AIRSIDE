"""
Helper functions used across modules.
"""
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app


def allowed_file(filename, allowed_extensions=None):
    """Check if uploaded file extension is allowed."""
    if not filename or '.' not in filename:
        return False

    ext = filename.rsplit('.', 1)[1].lower()
    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return ext in allowed_extensions


def generate_unique_filename(filename):
    """Generate a secure unique filename preserving extension."""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    unique_id = uuid.uuid4().hex
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    return f"{timestamp}_{unique_id}.{ext}" if ext else f"{timestamp}_{unique_id}"


def save_uploaded_file(file_storage, subfolder='documents'):
    """Save an uploaded file and return path details."""
    if not file_storage or not file_storage.filename:
        return None

    original_filename = secure_filename(file_storage.filename)
    unique_filename = generate_unique_filename(original_filename)

    upload_base = current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads')
    save_dir = os.path.join(upload_base, subfolder)
    os.makedirs(save_dir, exist_ok=True)

    full_path = os.path.join(save_dir, unique_filename)
    file_storage.save(full_path)

    return {
        'original_filename': original_filename,
        'stored_filename': unique_filename,
        'file_path': full_path,
        'file_type': original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else '',
        'file_size_bytes': os.path.getsize(full_path),
    }


def format_reference(prefix: str, entity_id: int, dt: datetime = None) -> str:
    """Create reference format PREFIX-YYYYMMDD-00001."""
    dt = dt or datetime.utcnow()
    return f"{prefix}-{dt.strftime('%Y%m%d')}-{entity_id:05d}"


def parse_bool(value):
    """Normalize common true/false input values."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
