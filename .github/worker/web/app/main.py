from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.responses import FileResponse
from sqlmodel import SQLModel, Session, create_engine, select
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import os, uuid, json
from .models import User, Organization, Template, Invoice
from .auth import get_password_hash, create_access_token, authenticate_user, get_current_user
from .tasks import enqueue_pdf_task
from .utils import create_signed_download_token, resolve_signed_download_token

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/invoices")
PDF_OUTPUT_DIR = os.getenv("PDF_OUTPUT_DIR", "/data/pdfs")
os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL, echo=False)
app = FastAPI(title="Invoice PDF Generator")

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

class SignUpPayload(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    org_name: Optional[str] = None

@app.post("/auth/signup")
def signup(payload: SignUpPayload):
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == payload.email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        org = Organization(name=payload.org_name or payload.email)
        session.add(org)
        session.commit()
        session.refresh(org)
        user = User(email=payload.email, hashed_password=get_password_hash(payload.password), full_name=payload.full_name, org_id=org.id, is_admin=True)
        session.add(user)
        session.commit()
        session.refresh(user)
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

class TokenRequest(BaseModel):
    username: str
    password: str

@app.post("/auth/token")
def login_for_access_token(form_data: TokenRequest = Body(...)):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

# Template management
class TemplateCreate(BaseModel):
    name: str
    html: str
    css: Optional[str] = None

@app.post("/templates", status_code=201)
def create_template(payload: TemplateCreate, current_user: User = Depends(get_current_user)):
    tpl = Template(org_id=current_user.org_id, name=payload.name, html=payload.html, css=payload.css)
    with Session(engine) as session:
        session.add(tpl)
        session.commit()
        session.refresh(tpl)
    return {"id": tpl.id, "name": tpl.name}

@app.get("/templates")
def list_templates(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        stmt = select(Template).where(Template.org_id == current_user.org_id)
        tpls = session.exec(stmt).all()
        return tpls

@app.get("/templates/{template_id}")
def get_template(template_id: int, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        tpl = session.get(Template, template_id)
        if not tpl or tpl.org_id != current_user.org_id:
            raise HTTPException(status_code=404, detail="Template not found")
        return tpl

# Invoice create/generate
class Item(BaseModel):
    description: str
    qty: int
    unit_price: float

class Customer(BaseModel):
    name: str
    address: Optional[str] = ""

class InvoiceCreate(BaseModel):
    template_id: Optional[int] = None
    customer: Customer
    items: List[Item]
    metadata: Optional[dict] = {}

@app.post("/invoices", status_code=201)
def create_invoice(payload: InvoiceCreate, current_user: User = Depends(get_current_user)):
    invoice_uuid = str(uuid.uuid4())
    now = datetime.utcnow()
    data_json = json.dumps(payload.dict())
    db_invoice = Invoice(uuid=invoice_uuid, created_at=now, status="queued", data_json=data_json, org_id=current_user.org_id, created_by=current_user.id, template_id=payload.template_id)
    with Session(engine) as session:
        session.add(db_invoice)
        session.commit()
        session.refresh(db_invoice)
    enqueue_pdf_task.delay("generate_pdf", db_invoice.id)
    return {"id": db_invoice.id, "uuid": invoice_uuid, "status": db_invoice.status}

@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        inv = session.get(Invoice, invoice_id)
        if not inv or inv.org_id != current_user.org_id:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return inv

@app.get("/invoices/{invoice_id}/download")
def download_invoice(invoice_id: int, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        inv = session.get(Invoice, invoice_id)
        if not inv or inv.org_id != current_user.org_id:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv.pdf_path:
            raise HTTPException(status_code=404, detail="PDF not yet generated")
        token = create_signed_download_token(inv.pdf_path, expires_seconds=600)
        download_url = f"/download/{token}"
        return {"download_url": download_url, "expires_in": 600}

@app.get("/download/{token}")
def serve_download(token: str):
    file_path = resolve_signed_download_token(token)
    if not file_path:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
    return FileResponse(file_path, media_type="application/pdf", filename=os.path.basename(file_path))

# Stripe scaffold endpoints
import stripe
stripe_api_key = os.getenv("STRIPE_API_KEY", "")
stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
if stripe_api_key:
    stripe.api_key = stripe_api_key

@app.post("/billing/checkout-session")
def create_checkout_session(invoice_id: int, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        inv = session.get(Invoice, invoice_id)
        if not inv or inv.org_id != current_user.org_id:
            raise HTTPException(status_code=404, detail="Invoice not found")
    if not stripe_api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd", "product_data": {"name": f"Invoice {invoice_id} download"}, "unit_amount": 299}, "quantity": 1}],
            mode="payment",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            metadata={"invoice_id": str(invoice_id), "org_id": str(current_user.org_id)}
        )
        return {"checkout_url": checkout.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhooks/stripe")
async def stripe_webhook(request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = None
    if stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, stripe_webhook_secret)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {e}")
    else:
        event = json.loads(payload)
    if event["type"] == "checkout.session.completed" or event.get("type") == "checkout.session.completed":
        session_data = event["data"]["object"]
        metadata = session_data.get("metadata", {}) or {}
        invoice_id = metadata.get("invoice_id")
        if invoice_id:
            with Session(engine) as db:
                inv = db.get(Invoice, int(invoice_id))
                if inv:
                    inv.status = "paid"
                    db.add(inv)
                    db.commit()
    return {"received": True}
