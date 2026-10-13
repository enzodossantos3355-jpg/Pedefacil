export interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "atendente";
}

export interface Additional {
  name: string;
  price: number;
}

export interface ProductSize {
  name: string;
  price: number;
}

export interface OrderItem {
  product_id: string;
  name: string;
  price: number;
  quantity: number;
  size: string;
  additionals: Additional[];
}

export interface Order {
  order_id: string;
  customer_name: string;
  customer_phone: string;
  delivery_type: string;
  address: string;
  payment_method: string;
  notes: string;
  items: OrderItem[];
  subtotal: number;
  delivery_fee: number;
  total: number;
  status: string;
  zone_name: string;
  courier_id: string;
  latitude: number | null;
  longitude: number | null;
  source: string;
  created_at: string;
}

export interface Product {
  product_id: string;
  name: string;
  category: string;
  price: number;
  description: string;
  active: boolean;
  image_url: string;
  sizes: ProductSize[];
  additionals: Additional[];
  stock: number | null;
}

export interface Customer {
  customer_id: string;
  name: string;
  phone: string;
  address: string;
  notes: string;
  orders_count: number;
  total_spent: number;
  addresses: string[];
  preferences: string[];
}

export interface StoreSettings {
  accepting_orders: boolean;
  store_name: string;
  store_address: string;
  store_maps_url: string;
  store_lat: number | null;
  store_lng: number | null;
  business_hours: string;
  closed_message: string;
  pix_key_type: string;
  pix_key: string;
  pix_beneficiary: string;
  high_demand_message: string;
  ai_custom_instructions: string;
  notify_status_changes: boolean;
  default_delivery_fee: number;
}

export interface LatLng {
  lat: number;
  lng: number;
}

export interface DeliveryZone {
  zone_id: string;
  name: string;
  fee: number;
  kind: "polygon" | "radius" | "keyword";
  polygon: LatLng[];
  radius_km: number;
  keywords: string[];
}

export interface Courier {
  courier_id: string;
  name: string;
  phone: string;
  active: boolean;
  deliveries_today: number;
  fees_today: number;
}

export interface WhatsAppStatus {
  status: string;
  is_connected: boolean;
  qr_code: string | null;
  pairing_code: string | null;
  phone: string | null;
  last_error?: string | null;
  detail?: string;
}

export interface DayStatus {
  is_open: boolean;
  day_state: string;
  revenue: number;
  open_orders: number;
  total_orders: number;
  initial_cash_balance: number;
  opened_at: string | null;
}

export interface DashboardSummary {
  today: string;
  revenue: number;
  month_revenue: number;
  total_orders: number;
  active_orders: number;
  average_ticket: number;
  average_fee: number;
  open_orders: number;
  accepting_orders: boolean;
  recent_orders: Order[];
}

export interface ReportSummary {
  revenue: number;
  month_revenue: number;
  total_orders: number;
  avg_ticket: number;
  avg_fee: number;
  completed_orders: number;
  by_payment: Record<string, number>;
  top_products: { name: string; quantity: number }[];
}

export interface ChatMessage {
  id: string;
  sender: "customer" | "bot" | "attendant";
  text: string;
  timestamp: string;
}

export interface Chat {
  chat_id: string;
  customer_name: string;
  phone: string;
  jid: string;
  status: string;
  is_human_controlled: boolean;
  last_message: string;
  last_timestamp: string;
  messages: ChatMessage[];
  latest_order: Order | null;
}

export const ORDER_STATUSES = ["Em Análise", "Novo", "Em Preparo", "Pronto", "Saiu para Entrega", "Entregue", "Cancelado"];
export const formatCurrency = (value: number) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
export const formatTime = (value: string) => new Date(value).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

export function statusClass(status: string): string {
  const styles: Record<string, string> = {
    "Em Análise": "bg-amber-50 text-amber-800 border-amber-200",
    Novo: "bg-blue-50 text-blue-800 border-blue-200",
    "Em Preparo": "bg-orange-50 text-orange-800 border-orange-200",
    Pronto: "bg-emerald-50 text-emerald-800 border-emerald-200",
    "Saiu para Entrega": "bg-[#fceee6] text-[#a6432e] border-[#e8b5a0]",
    Entregue: "bg-stone-100 text-stone-700 border-stone-300",
    Cancelado: "bg-red-50 text-red-800 border-red-200",
  };
  return styles[status] ?? "bg-stone-100 text-stone-700 border-stone-200";
}