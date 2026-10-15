import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Banknote, CircleDollarSign, Clock, CreditCard, House, MapPin, QrCode, ReceiptText, Trash2, type LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { apiDelete, apiGet } from "@/lib/api";
import { formatCurrency, statusClass, type DayClose, type DayCloseDetail } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const PAY: Record<string, [LucideIcon, string]> = {
  Pix: [QrCode, "bg-teal-50 text-teal-800"], Pendente: [Clock, "bg-amber-50 text-amber-700"], Dinheiro: [Banknote, "bg-emerald-50 text-emerald-800"],
  "Cartão Crédito": [CreditCard, "bg-blue-50 text-blue-800"], "Cartão Débito": [CreditCard, "bg-sky-50 text-sky-800"],
};
const fmt = (d: string | null) => (d ? new Date(d).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "?");

function PayChip({ method }: { method: string }) {
  const [Icon, cls] = PAY[method] ?? [CircleDollarSign, "bg-stone-100 text-stone-700"];
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${cls}`}><Icon size={13} />{method}</span>;
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="space-y-2"><h4 className="text-[11px] font-bold uppercase tracking-[0.14em] text-stone-500">{title}</h4><div className="divide-y divide-stone-100 rounded-2xl border border-stone-200 bg-white">{children}</div></div>
);

/** Armazenamento: closed days (what's stored = orders, totals, couriers' earnings) with report and delete. */
export default function ClosedDays() {
  const client = useQueryClient();
  const [openId, setOpenId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const closes = useQuery({ queryKey: ["day", "closes"], queryFn: () => apiGet<DayClose[]>("/day/closes") });
  const report = useQuery({ queryKey: ["day", "close", openId], queryFn: () => apiGet<DayCloseDetail>(`/day/closes/${openId}`), enabled: !!openId });
  const remove = useMutation({
    mutationFn: (id: string) => apiDelete<{ ok: boolean; orders_removed: number }>(`/day/closes/${id}`),
    onSuccess: (r) => { client.invalidateQueries({ queryKey: ["day", "closes"] }); setDeleteId(null); setOpenId(null); toast.success(`Dia apagado (${r.orders_removed} pedidos removidos).`); },
    onError: (e: Error) => toast.error(e.message),
  });
  const r = report.data;
  const list = closes.data ?? [];

  return (
    <Card className="border-stone-200 shadow-sm"><CardContent className="p-5" data-testid="closed-days">
      <div className="mb-1 flex items-center gap-2"><Archive size={18} className="text-[#C5533B]" /><h2 className="font-heading font-semibold">Dias fechados</h2></div>
      <p className="mb-3 text-xs text-stone-500">Ao fechar o dia ficam guardados aqui: todos os pedidos (itens, cliente, pagamento, entrega/retirada), o faturamento, os totais por forma de pagamento e por produto, e o saldo de cada entregador. As conversas do WhatsApp são apagadas.</p>
      {list.length === 0 && <p className="rounded-xl border border-dashed border-stone-200 py-6 text-center text-sm text-stone-400" data-testid="closed-days-empty">Nenhum dia fechado ainda.</p>}
      {list.map((c) => (
        <div key={c.close_id} className="flex flex-wrap items-center justify-between gap-2 border-t border-stone-100 py-3 text-sm transition-colors hover:bg-stone-50/60" data-testid={`close-record-${c.close_id}`}>
          <button onClick={() => setOpenId(c.close_id)} className="min-w-0 text-left" data-testid={`close-open-${c.close_id}`}>
            <strong className="block">{new Date(c.created_at).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" })}</strong>
            <span className="text-xs text-stone-500">{c.total_orders} pedidos · ticket {formatCurrency(c.avg_ticket)}{c.couriers.length ? ` · ${c.couriers.length} entregador(es)` : ""}</span>
          </button>
          <div className="flex items-center gap-2"><strong className="text-[#C5533B]">{formatCurrency(c.revenue)}</strong>
            <Button size="sm" variant="outline" onClick={() => setOpenId(c.close_id)} data-testid={`close-view-orders-${c.close_id}`}>Ver relatório</Button>
            <button onClick={() => setDeleteId(c.close_id)} className="rounded-md p-1.5 text-stone-400 transition-colors hover:bg-red-50 hover:text-red-600" aria-label="Apagar dia" data-testid={`close-delete-${c.close_id}`}><Trash2 size={16} /></button></div>
        </div>
      ))}

      <Dialog open={!!openId} onOpenChange={(v) => !v && setOpenId(null)}><DialogContent className="max-h-[90vh] overflow-y-auto bg-[#F9F8F6] sm:max-w-xl" data-testid="close-detail-dialog">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><ReceiptText size={18} className="text-[#C5533B]" /> Relatório do dia</DialogTitle></DialogHeader>
        {report.isLoading && <p className="text-sm text-stone-500">Carregando...</p>}
        {r && <div className="space-y-4">
          <p className="text-xs text-stone-500" data-testid="report-period">{fmt(r.opened_at)} → {fmt(r.created_at)}</p>
          <div className="rounded-2xl border border-[#C5533B]/20 bg-gradient-to-b from-[#fde8df] to-[#fff7f4] p-5 text-center" data-testid="report-revenue">
            <small className="text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">Faturamento</small>
            <strong className="block font-heading text-4xl text-[#C5533B]">{formatCurrency(r.revenue)}</strong>
            <span className="text-xs text-stone-500">{r.total_orders} pedidos · ticket médio {formatCurrency(r.avg_ticket)}</span>
          </div>
          <div className="grid grid-cols-2 gap-3">{["Entrega", "Retirada"].map((t) => { const l = r.by_type.find((x) => x.label === t); return <div key={t} className="rounded-2xl border border-stone-200 bg-white p-4" data-testid={`report-type-${t.toLowerCase()}`}><small className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-[0.12em] text-stone-500">{t === "Entrega" ? <MapPin size={12} /> : <House size={12} />}{t}</small><strong className="block text-xl">{formatCurrency(l?.total ?? 0)}</strong><span className="text-xs text-stone-500">{l?.count ?? 0} pedidos</span></div>; })}</div>
          <Section title="Por forma de pagamento">{r.by_payment.map((p) => <div key={p.label} className="flex items-center justify-between px-3 py-2" data-testid={`report-pay-${p.label}`}><PayChip method={p.label} /><span className="text-sm"><small className="mr-3 text-stone-400">{p.count}×</small><strong>{formatCurrency(p.total)}</strong></span></div>)}</Section>
          {r.couriers.length > 0 && <Section title="Entregadores">{r.couriers.map((c) => <div key={c.courier_id} className="flex items-center justify-between px-3 py-2 text-sm" data-testid={`report-courier-${c.courier_id}`}><span>🛵 {c.name}</span><span><small className="mr-3 text-stone-400">{c.deliveries} entregas</small><strong>{formatCurrency(c.fees)}</strong></span></div>)}</Section>}
          <Section title="Top produtos">{r.top_products.map((p, i) => <div key={p.label} className="flex items-center justify-between px-3 py-2 text-sm" data-testid={`report-product-${i}`}><span><span className="mr-3 text-stone-400">{i + 1}</span><strong className="font-semibold">{p.label}</strong></span><span><small className="mr-3 text-stone-400">{p.count} un.</small><strong>{formatCurrency(p.total)}</strong></span></div>)}</Section>
          <div className="space-y-2"><h4 className="text-[11px] font-bold uppercase tracking-[0.14em] text-stone-500">Pedidos do dia</h4>
            {r.orders.map((o) => <div key={o.order_id} className="rounded-2xl border border-stone-200 bg-white p-3" data-testid={`close-order-${o.order_id}`}>
              <div className="flex items-start justify-between gap-2"><div className="flex items-center gap-2"><Badge className={`${statusClass(o.status)} text-[10px]`}>{o.status}</Badge><strong>{o.customer_name}</strong></div><strong>{formatCurrency(o.total)}</strong></div>
              <div className="mt-1 text-xs text-stone-600">{o.items.map((i, k) => <p key={k}>{i.quantity}× {i.name}{i.size ? ` ${i.size}` : ""}</p>)}</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">{(o.payments?.length ? o.payments.map((p) => p.method) : [o.payment_method || "Pendente"]).map((m) => <PayChip key={m} method={m} />)}<span className="flex items-center gap-1 text-[11px] text-stone-500">{o.delivery_type === "Entrega" ? <MapPin size={11} /> : <House size={11} />}{o.delivery_type}</span></div>
            </div>)}
            {r.orders.length === 0 && <p className="text-sm text-stone-400">Nenhum pedido neste dia.</p>}
          </div>
          <Button variant="outline" className="w-full text-red-600 hover:bg-red-50" onClick={() => setDeleteId(r.close_id)} data-testid="report-delete-button"><Trash2 size={15} className="mr-1.5" /> Apagar este dia</Button>
        </div>}
      </DialogContent></Dialog>

      <Dialog open={!!deleteId} onOpenChange={(v) => !v && setDeleteId(null)}><DialogContent className="sm:max-w-sm" data-testid="close-delete-dialog">
        <DialogHeader><DialogTitle>Apagar este dia fechado?</DialogTitle></DialogHeader>
        <p className="text-sm text-stone-600">O relatório e os pedidos desse dia serão apagados de vez. Seus clientes salvos continuam.</p>
        <DialogFooter><Button variant="outline" onClick={() => setDeleteId(null)} data-testid="close-delete-cancel">Cancelar</Button><Button variant="destructive" disabled={remove.isPending} onClick={() => deleteId && remove.mutate(deleteId)} data-testid="close-delete-confirm">Apagar</Button></DialogFooter>
      </DialogContent></Dialog>
    </CardContent></Card>
  );
}
