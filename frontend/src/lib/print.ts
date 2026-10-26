import { toast } from "sonner";
import type { Courier, Order } from "@/lib/types";
import { formatCurrency } from "@/lib/types";
import { printerConfig, printThermal, Receipt } from "@/lib/thermal";

const esc = (v: string) => v.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] ?? c);

function openPrint(title: string, body: string) {
  const w = window.open("", "_blank", "width=380,height=640");
  if (!w) return;
  w.document.write(`<html><head><title>${esc(title)}</title><style>body{font-family:monospace;font-size:12px;width:58mm;margin:0 auto;padding:8px}h1{font-size:15px;text-align:center;margin:4px 0}hr{border:0;border-top:1px dashed #000}.r{display:flex;justify-content:space-between}.b{font-weight:bold}</style></head><body>${body}<script>window.onload=()=>{window.print()}</script></body></html>`);
  w.document.close();
}

const itemsHtml = (o: Order) =>
  o.items.map((i) => `<div class="r"><span>${i.quantity}x ${esc(i.name)}${i.size ? ` (${esc(i.size)})` : ""}</span><span>${formatCurrency(i.price * i.quantity)}</span></div>${i.additionals.map((a) => `<div>&nbsp;&nbsp;+ ${(a.quantity ?? 1) > 1 ? `${a.quantity}x ` : ""}${esc(a.name)}</div>`).join("")}`).join("");

const useThermal = () => printerConfig().mode !== "browser";
const send = (r: Receipt) => printThermal(r).catch((e: Error) => toast.error(`Impressora: ${e.message}`));
const payLine = (o: Order) => (o.payments?.length ? o.payments.map((p) => `${p.method} ${formatCurrency(p.amount)}`).join(" + ") : o.payment_method || "Pendente");

function header(r: Receipt) {
  const { storeName } = printerConfig();
  if (storeName) r.center().bold().line(storeName).bold(false).center(false);
}

export function kitchenReceipt(o: Order): Receipt {
  const r = new Receipt();
  header(r);
  r.center().big().line(`#${o.order_id.slice(-6).toUpperCase()}`).big(false).line(new Date(o.created_at).toLocaleString("pt-BR")).center(false).rule();
  r.bold().wrapped(`${o.customer_name} - ${o.delivery_type}`).bold(false);
  if (o.customer_phone) r.line(`Tel: ${o.customer_phone}`);
  if (o.delivery_type === "Entrega" && o.address) r.wrapped(`End: ${o.address}`);
  r.rule();
  for (const i of o.items) {
    r.bold().row(`${i.quantity}x ${i.name}${i.size ? ` (${i.size})` : ""}`, formatCurrency(i.price * i.quantity)).bold(false);
    for (const a of i.additionals) r.line(`  + ${(a.quantity ?? 1) > 1 ? `${a.quantity}x ` : ""}${a.name}`);
  }
  r.rule();
  if (o.notes) r.bold().wrapped(`OBS: ${o.notes}`).bold(false).rule();
  if (o.delivery_fee) r.row("Taxa de entrega", formatCurrency(o.delivery_fee));
  if (o.surcharge) r.row("Acrescimo", formatCurrency(o.surcharge));
  if (o.discount) r.row("Desconto", `-${formatCurrency(o.discount)}`);
  r.bold().row("TOTAL", formatCurrency(o.total)).bold(false);
  r.wrapped(`Pagamento: ${payLine(o)}${o.payment_status === "pago" ? " (PAGO)" : ""}`);
  return r.feedAndCut();
}

export function printKitchenTicket(o: Order) {
  if (useThermal()) return void send(kitchenReceipt(o));
  openPrint(`Comanda ${o.order_id}`, `<h1>COMANDA #${o.order_id.slice(-6).toUpperCase()}</h1><div>${new Date(o.created_at).toLocaleString("pt-BR")}</div><div class="b">${esc(o.customer_name)} • ${esc(o.delivery_type)}</div><hr/>${itemsHtml(o)}<hr/>${o.notes ? `<div class="b">OBS: ${esc(o.notes)}</div>` : ""}<div class="r b"><span>TOTAL</span><span>${formatCurrency(o.total)}</span></div>`);
}

export function deliveryCardText(o: Order, courier?: Courier) {
  const maps = o.latitude != null && o.longitude != null ? `https://www.google.com/maps/dir/?api=1&destination=${o.latitude},${o.longitude}` : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(o.address)}`;
  return `🛵 ENTREGA #${o.order_id.slice(-6).toUpperCase()}${courier ? ` • ${courier.name}` : ""}\n👤 ${o.customer_name} • ${o.customer_phone || "sem telefone"}\n📍 ${o.address || "Retirada"}\n${o.items.map((i) => `• ${i.quantity}x ${i.name}${i.size ? ` (${i.size})` : ""}`).join("\n")}\n🚚 Taxa: ${formatCurrency(o.delivery_fee)}\n💰 Cobrar: ${o.payment_method === "Pix" ? "Já pago via Pix (conferir)" : `${formatCurrency(o.total)} (${o.payment_method})`}\n🗺️ ${maps}`;
}

export function printDeliveryCard(o: Order, courier?: Courier) {
  if (useThermal()) {
    const r = new Receipt();
    header(r);
    r.center().big().line("ENTREGA").big(false).line(`#${o.order_id.slice(-6).toUpperCase()}`).center(false).rule();
    if (courier) r.line(`Entregador: ${courier.name}`);
    r.bold().wrapped(o.customer_name).bold(false).line(`Tel: ${o.customer_phone || "sem telefone"}`).wrapped(`End: ${o.address || "Retirada"}`).rule();
    for (const i of o.items) r.row(`${i.quantity}x ${i.name}${i.size ? ` (${i.size})` : ""}`, "");
    r.rule().row("Taxa", formatCurrency(o.delivery_fee)).bold();
    r.wrapped(o.payment_status === "pago" ? `JA PAGO (${payLine(o)}) - NAO COBRAR` : `COBRAR ${formatCurrency(o.total)} - ${o.payment_intent || payLine(o)}`).bold(false);
    return void send(r.feedAndCut());
  }
  openPrint(`Entrega ${o.order_id}`, `<h1>FICHA DE ENTREGA</h1><pre style="white-space:pre-wrap;font-family:monospace">${esc(deliveryCardText(o, courier))}</pre>`);
}

export function testReceipt(): Receipt {
  const r = new Receipt();
  header(r);
  return r.center().big().line("PedeFacil").big(false).line("Teste de impressao").center(false).rule().row("1x Marmita de Feijoada", "R$ 20,00").row("  + 2x Ovo", "R$ 4,00").rule().bold().row("TOTAL", "R$ 24,00").bold(false).center().line("Impressora 58mm OK!").center(false).feedAndCut();
}
