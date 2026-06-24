# app/tasks.py
from celery import shared_task
import time

@shared_task
def long_running_task(x, y):
    """An example of a long-running task."""
    time.sleep(10)
    return x + y