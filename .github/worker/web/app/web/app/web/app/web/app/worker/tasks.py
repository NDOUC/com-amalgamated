import os
import json
import asyncio
import traceback
from celery import Celery
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine, select
from web.app.models import Invoice
from jinja2 import Environment, FileSystemLoader, select_autoescape
import httpx
from pyppeteer import connect

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
PDF_OUTPUT_DIR = os.getenv("PDF_OUTPUT_DIR", "/data/pdfs")
CHROME_HOST = os.getenv("CHROME_HOST", "chrome")
CHROME_DEBUG_PORT = int(os.getenv("CHROME_DEBUG_PORT", "9222"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/invoices")

celery_app = Celery("pdf_worker", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

TEMPLATES_DIR = "/app/templates"
env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"])
)

def get_chrome_ws_endpoint():
    try:
        url = f"http://{CHROME_HOST}:{CHROME_DEBUG_PORT}/json/version"
        r = httpx.get(url, timeout=5.0)
        r.raise_for_status()
        j = r.json()
        return j.get("webSocketDebuggerUrl")
    except Exception as e:
        print("Error fetching chrome ws endpoint:", e)
        return None

async def render_html_to_pdf_via_ws(html_content: str, output_path: str):
    ws_endpoint = get_chrome_ws_endpoint()
    if not ws_endpoint:
        raise RuntimeError("Could not get Chrome WebSocket endpoint")
    browser = await connect(browserWSEndpoint=ws_endpoint)
    page = await browser.newPage()
    await page.setContent(html_content, waitUntil="networkidle0")
    await page.emulateMediaType("screen")
    await page.pdf({
        "path": output_path,
        "format": "A4",
        "printBackground": True,
        "margin": {"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
    })
    await page.close()
    await browser.disconnect()

def notify_failure(invoice_id: int, error: str):
    print(f"[ALERT] Invoice {invoice_id} failed: {error}")

@celery_app.task(bind=True, name="generate_pdf", max_retries=3)
def generate_pdf(self, invoice_id: int):
    async def _run():
        print(f"Starting PDF generation for invoice {invoice_id}")
        with SessionLocal() as session:
            inv = session.get(Invoice, invoice_id)
            if not inv:
                raise RuntimeError("Invoice not found")
            try:
                inv.status = "processing"
                session.add(inv)
                session.commit()
            except Exception:
                pass
            data = json.loads(inv.data_json)
            context = {
                "customer": data.get("customer", {}),
                "items": data.get("items", []),
                "metadata": data.get("metadata", {}),
                "uuid": inv.uuid,
                "created_at": inv.created_at.strftime("%Y-%m-%d"),
            }
            template_name = "invoice.html"
            template = env.get_template(template_name)
            html = template.render(**context)
            os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)
            filename = f"{inv.uuid}.pdf"
            output_path = os.path.join(PDF_OUTPUT_DIR, filename)
            try:
                await render_html_to_pdf_via_ws(html, output_path)
            except Exception as e:
                tb = traceback.format_exc()
                print("PDF render failed:", e, tb)
                with SessionLocal() as session2:
                    inv2 = session2.get(Invoice, invoice_id)
                    inv2.status = "failed"
                    inv2.error_message = str(e)
                    session2.add(inv2)
                    session2.commit()
                notify_failure(invoice_id, str(e))
                try:
                    raise self.retry(exc=e, countdown=2 ** self.request.retries)
                except Exception:
                    raise
            with SessionLocal() as session3:
                inv3 = session3.get(Invoice, invoice_id)
                inv3.pdf_path = output_path
                inv3.status = "done"
                session3.add(inv3)
                session3.commit()
                print(f"PDF written to {output_path}")

    return asyncio.run(_run())
