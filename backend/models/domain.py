from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


STATUS_FLOW = ["Em Análise", "Novo", "Em Preparo", "Pronto", "Saiu para Entrega", "Entregue", "Cancelado"]


class UserCreate(BaseModel):
    name: str = Field(min_length=2)
    email: str
    password: str = Field(min_length=6)
    role: Literal["admin", "atendente"] = "admin"


class LoginRequest(BaseModel):
    email: str
    password: str


class User(BaseModel):
    id: str
    name: str
    email: str
    role: Literal["admin", "atendente"]


class Additional(BaseModel):
    name: str
    price: float = 0


class ProductSize(BaseModel):
    name: str
    price: float = Field(ge=0)


class OrderItem(BaseModel):
    product_id: str
    name: str
    price: float  # unit price including size and additionals
    quantity: int = Field(ge=1)
    size: str = ""
    additionals: list[Additional] = []


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2)
    customer_phone: str = ""
    delivery_type: str = "Entrega"
    address: str = ""
    payment_method: str = "Pix"
    notes: str = ""
    items: list[OrderItem] = Field(min_length=1)
    delivery_fee: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    status: str = "Novo"
    source: str = "balcao"


class OrderUpdate(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None
    delivery_type: str | None = None
    address: str | None = None
    payment_method: str | None = None
    notes: str | None = None
    status: str | None = None
    items: list[OrderItem] | None = None
    delivery_fee: float | None = None
    courier_id: str | None = None


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: new_id("ord"))
    customer_name: str
    customer_phone: str = ""
    delivery_type: str
    address: str = ""
    payment_method: str
    notes: str = ""
    items: list[OrderItem]
    subtotal: float = 0
    delivery_fee: float = 0
    total: float = 0
    status: str = "Novo"
    zone_name: str = ""
    courier_id: str = ""
    latitude: float | None = None
    longitude: float | None = None
    source: str = "balcao"
    created_at: datetime = Field(default_factory=now_utc)


class ProductCreate(BaseModel):
    name: str = Field(min_length=2)
    category: str = "Marmita"
    price: float = Field(ge=0)
    description: str = ""
    active: bool = True
    image_url: str = ""
    sizes: list[ProductSize] = []
    additionals: list[Additional] = []
    stock: int | None = None  # None = sem controle de estoque


class Product(ProductCreate):
    product_id: str = Field(default_factory=lambda: new_id("prod"))


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2)
    phone: str = ""
    address: str = ""
    notes: str = ""


class Customer(CustomerCreate):
    customer_id: str = Field(default_factory=lambda: new_id("cust"))
    orders_count: int = 0
    total_spent: float = 0
    addresses: list[str] = []
    preferences: list[str] = []


class StoreSettings(BaseModel):
    accepting_orders: bool = True
    store_name: str = "Marmita Hub"
    store_address: str = "Rua do Sabor, 150 - Centro, São Paulo - SP"
    store_maps_url: str = ""
    store_lat: float | None = -23.5505
    store_lng: float | None = -46.6333
    business_hours: str = "Segunda a sábado, das 10h30 às 15h"
    closed_message: str = "Nosso expediente está encerrado no momento. Voltamos no próximo horário de atendimento!"
    pix_key_type: str = "Celular"
    pix_key: str = ""
    pix_beneficiary: str = ""
    high_demand_message: str = "Estamos com alta demanda agora. Em instantes voltamos a aceitar pedidos!"
    ai_custom_instructions: str = ""
    notify_status_changes: bool = True
    default_delivery_fee: float = 5


class LatLng(BaseModel):
    lat: float
    lng: float


class DeliveryZoneCreate(BaseModel):
    name: str = Field(min_length=2)
    fee: float = Field(ge=0)
    kind: Literal["polygon", "radius", "keyword"] = "keyword"
    polygon: list[LatLng] = []
    radius_km: float = 0
    keywords: list[str] = []


class DeliveryZone(DeliveryZoneCreate):
    zone_id: str = Field(default_factory=lambda: new_id("zone"))


class FeeQuote(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    text: str = ""


class FeeQuoteResult(BaseModel):
    found: bool
    fee: float
    zone_name: str = ""
    distance_km: float | None = None


class CourierCreate(BaseModel):
    name: str = Field(min_length=2)
    phone: str = ""
    active: bool = True


class Courier(CourierCreate):
    courier_id: str = Field(default_factory=lambda: new_id("moto"))
    deliveries_today: int = 0
    fees_today: float = 0


class DayOpenRequest(BaseModel):
    initial_cash: float = Field(default=0, ge=0)


class DayStatus(BaseModel):
    is_open: bool = True
    day_state: str = "open"
    revenue: float = 0
    open_orders: int = 0
    total_orders: int = 0
    initial_cash_balance: float = 0
    opened_at: datetime | None = None


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    sender: Literal["customer", "bot", "attendant"]
    text: str
    timestamp: datetime = Field(default_factory=now_utc)


class Chat(BaseModel):
    chat_id: str
    customer_name: str
    phone: str
    jid: str = ""
    status: str = "bot_active"
    is_human_controlled: bool = False
    last_message: str = ""
    last_timestamp: datetime = Field(default_factory=now_utc)
    messages: list[ChatMessage] = []
    latest_order: Order | None = None


class MessageCreate(BaseModel):
    text: str = Field(min_length=1)


class HumanToggle(BaseModel):
    enable_human: bool


class StatusUpdate(BaseModel):
    status: str


class IncomingMessage(BaseModel):
    jid: str = ""
    phone: str
    name: str = ""
    text: str
    latitude: float | None = None
    longitude: float | None = None


class SimulateMessage(BaseModel):
    phone: str = "5511988887777"
    name: str = "Cliente Teste"
    text: str = Field(min_length=1)
    latitude: float | None = None
    longitude: float | None = None


class WhatsAppStart(BaseModel):
    pairing_phone: str = ""


class TextRequest(BaseModel):
    text: str = Field(min_length=2)


class DescriptionRequest(BaseModel):
    name: str = Field(min_length=2)
    category: str = "Marmita"


class DashboardSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    today: str
    revenue: float
    month_revenue: float
    total_orders: int
    active_orders: int
    average_ticket: float
    average_fee: float
    open_orders: int
    accepting_orders: bool
    recent_orders: list[Order]


class ReportSummary(BaseModel):
    revenue: float
    month_revenue: float
    total_orders: int
    avg_ticket: float
    avg_fee: float
    completed_orders: int
    by_payment: dict[str, float]
    top_products: list[dict[str, Any]]
