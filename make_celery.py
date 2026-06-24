# make_celery.py
from app import create_app

flask_app = create_app()
celery_app = flask_app.extensions.get("celery")
if celery_app is None:
	raise RuntimeError("Celery was not initialized on the Flask app.")

celery = celery_app