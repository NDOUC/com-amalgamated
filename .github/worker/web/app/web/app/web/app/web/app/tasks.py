from celery import Celery
import os

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery = Celery("web_tasks", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

def enqueue_pdf_task(task_name: str = "generate_pdf", *args, **kwargs):
    return celery.send_task(task_name, args=args, kwargs=kwargs)
  
