from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime

class Organization(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    plan: str = "free"
    stripe_customer_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    full_name: Optional[str] = None
    is_admin: bool = False
    org_id: Optional[int] = Field(default=None, foreign_key="organization.id")
    organization: Optional["Organization"] = Relationship()

class Template(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: Optional[int] = Field(default=None, foreign_key="organization.id")
    name: str
    html: str
    css: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Invoice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str
    org_id: Optional[int] = Field(default=None, foreign_key="organization.id")
    template_id: Optional[int] = Field(default=None, foreign_key="template.id")
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "queued"
    pdf_path: Optional[str] = None
    data_json: str
    error_message: Optional[str] = None

class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: Optional[int] = Field(default=None, foreign_key="organization.id")
    stripe_payment_id: Optional[str] = None
    amount: int = 0
    currency: str = "usd"
    type: str = "one_off"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Download(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: Optional[int] = Field(default=None, foreign_key="invoice.id")
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    paid: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
  
