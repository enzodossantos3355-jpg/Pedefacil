export interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "atendente" | "master";
  store_id: string;
  store_name: string;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface PlanInfo {
  plan: string;
  plan_name: string;
  status: string;
  features: string[];
  limits: Record<string, number>;
  expired: boolean;
  trial_days_left: number | null;
  trial_ends_at: string | null;
  current_period_end: string | null;
  tables_enabled: boolean;
}

export interface PlanOption {
  key: "basico" | "padrao" | "pro";
  name: string;
  price: number;
  features: string[];
  limits: Record<string, number>;
}

export interface StoreAdmin {
  store_id: string;
  name: string;
  owner_email: string;
  plan: string;
  status: string;
  effective_plan: string;
  trial_ends_at: string | null;
  current_period_end: string | null;
  created_at: string | null;
  orders_count: number;
}

export interface PlatformSettings {
  site_url: string;
  footer_text: string;
}

export interface SupportMessage {
  id: string;
  sender: "loja" | "suporte";
  author: string;
  text: string;
  timestamp: string;
}

export interface SupportTicket {
  ticket_id: string;
  store_id: string;
  store_name: string;
  user_email: string;
  subject: string;
  category: string;
  status: "aberto" | "respondido" | "resolvido";
  created_at: string;
  updated_at: string;
  messages: SupportMessage[];
}

export interface DiningTable {
  table_id: string;
  number: number;
  seats: number;
  status: "livre" | "ocupada";
  opened_at: string | null;
  orders: Order[];
  total: number;
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
  pix_copia_e_cola: string;
  latitude: number | null;
  longitude: number | null;
  source: string;
  table_number: number | null;
  created_at: string;
}

export interface PixCharge {
  copia_e_cola: string;
  qr_code_base64: string;
  valor: string;
  txid: string;
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
  favorites: string[];
  usual_additionals: string[];
  usual_delivery: string;
  usual_payment: string;
  last_order: string;
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
  pix_mode: "chave" | "brcode";
  pix_city: string;
  tables_enabled: boolean;
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
  kind: "polygon" | "radius" | "keyword" | "cep";
  polygon: LatLng[];
  radius_km: number;
  keywords: string[];
  ceps: string[];
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

export const ORDER_STATUSES = ["Em Análise", "Novo", "Em Preparo", "Pronto", "Em Entrega", "Concluído", "Cancelado"];
export const PAYMENT_METHODS = ["Pendente", "Dinheiro", "Cartão Crédito", "Cartão Débito", "Pix", "Outro"];
export const formatCurrency = (value: number) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
export const formatTime = (value: string) => new Date(value).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

export function statusClass(status: string): string {
  const styles: Record<string, string> = {
    "Em Análise": "bg-amber-50 text-amber-800 border-amber-200",
    Novo: "bg-blue-50 text-blue-800 border-blue-200",
    "Em Preparo": "bg-orange-50 text-orange-800 border-orange-200",
    Pronto: "bg-emerald-50 text-emerald-800 border-emerald-200",
    "Em Entrega": "bg-[#fceee6] text-[#a6432e] border-[#e8b5a0]",
    "Concluído": "bg-stone-100 text-stone-700 border-stone-300",
    Cancelado: "bg-red-50 text-red-800 border-red-200",
  };
  return styles[status] ?? "bg-stone-100 text-stone-700 border-stone-200";
}