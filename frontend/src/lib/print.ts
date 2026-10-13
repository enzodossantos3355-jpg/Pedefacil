import type { Courier, Order } from "@/lib/types";
import { formatCurrency } from "@/lib/types";

const esc = (v: string) => v.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] ?? c);

function openPrint(title: string, body: string) {
  const w = window.open("", "_blank", "width=380,height=640");
  if (!w) return;
  w.document.write(`<html><head><title>${esc(title)}</title><style>body{font-family:monospace;font-size:12px;width:58mm;margin:0 auto;padding:8px}h1{font-size:15px;text-align:center;margin:4px 0}hr{border:0;border-top:1px dashed #000}.r{display:flex;justify-content:space-between}.b{font-weight:bold}</style></head><body>${body}<script>window.onload=()=>{window.print()}</script></body></html>`);
  w.document.close();
}

const itemsHtml = (o: Order) =>
  o.items.map((i) => `<div class="r"><span>${i.quantity}x ${esc(i.name)}${i.size ? ` (${esc(i.size)})` : ""}</span><span>${formatCurrency(i.price * i.quantity)}</span></div>${i.additionals.map((a) => `<div>&nbsp;&nbsp;+ ${esc(a.name)}</div>`).join("")}`).join("");

export function printKitchenTicket(o: Order) {
  openPrint(`Comanda ${o.order_id}`, `<h1>COMANDA #${o.order_id.slice(-6).toUpperCase()}</h1><div>${new Date(o.created_at).toLocaleString("pt-BR")}</div><div class="b">${esc(o.customer_name)} • ${esc(o.delivery_type)}</div><hr/>${itemsHtml(o)}<hr/>${o.notes ? `<div class="b">OBS: ${esc(o.notes)}</div>` : ""}<div class="r b"><span>TOTAL</span><span>${formatCurrency(o.total)}</span></div>`);
}

export function deliveryCardText(o: Order, courier?: Courier) {
  const maps = o.latitude != null && o.longitude != null ? `https://www.google.com/maps/dir/?api=1&destination=${o.latitude},${o.longitude}` : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(o.address)}`;
  return `🛵 ENTREGA #${o.order_id.slice(-6).toUpperCase()}${courier ? ` • ${courier.name}` : ""}\n👤 ${o.customer_name} • ${o.customer_phone || "sem telefone"}\n📍 ${o.address || "Retirada"}\n${o.items.map((i) => `• ${i.quantity}x ${i.name}${i.size ? ` (${i.size})` : ""}`).join("\n")}\n🚚 Taxa: ${formatCurrency(o.delivery_fee)}\n💰 Cobrar: ${o.payment_method === "Pix" ? "Já pago via Pix (conferir)" : `${formatCurrency(o.total)} (${o.payment_method})`}\n🗺️ ${maps}`;
}

export function printDeliveryCard(o: Order, courier?: Courier) {
  openPrint(`Entrega ${o.order_id}`, `<h1>FICHA DE ENTREGA</h1><pre style="white-space:pre-wrap;font-family:monospace">${esc(deliveryCardText(o, courier))}</pre>`);
}
