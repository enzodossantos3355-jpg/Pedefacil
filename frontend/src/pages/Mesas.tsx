import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { DiningTable, OrderItem, Product } from "@/lib/types";
import { formatCurrency, PAYMENT_METHODS } from "@/lib/types";
import { Armchair, Plus, Receipt, Trash2, X } from "lucide-react";

export default function Mesas() {
  const client = useQueryClient();
  const [number, setNumber] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [items, setItems] = useState<OrderItem[]>([]);
  const [pay, setPay] = useState("Dinheiro");
  const tables = useQuery({ queryKey: ["tables"], queryFn: () => apiGet<DiningTable[]>("/tables"), refetchInterval: 8000 });
  const products = useQuery({ queryKey: ["products"], queryFn: () => apiGet<Product[]>("/products") });
  const table = tables.data?.find((t) => t.table_id === openId);
  const refresh = () => { client.invalidateQueries({ queryKey: ["tables"] }); client.invalidateQueries({ queryKey: ["orders"] }); };
  const add = useMutation({ mutationFn: () => apiPost<DiningTable>("/tables", { number: Number(number), seats: 4 }), onSuccess: () => { setNumber(""); refresh(); toast.success("Mesa cadastrada."); }, onError: (e) => toast.error(e.message) });
  const remove = useMutation({ mutationFn: (id: string) => apiDelete<{ ok: boolean }>(`/tables/${id}`), onSuccess: refresh, onError: (e) => toast.error(e.message) });
  const launch = useMutation({ mutationFn: () => apiPost<DiningTable>(`/tables/${openId}/orders`, { items }), onSuccess: () => { setItems([]); refresh(); toast.success("Pedido enviado para a cozinha!"); }, onError: (e) => toast.error(e.message) });
  const close = useMutation({ mutationFn: () => apiPost<DiningTable>(`/tables/${openId}/close`, { payment_method: pay }), onSuccess: () => { setOpenId(null); refresh(); toast.success("Conta fechada e mesa liberada."); }, onError: (e) => toast.error(e.message) });
  const addItem = (p: Product) => { const size = p.sizes[0]; setItems((l) => [...l, { product_id: p.product_id, name: p.name, price: size ? size.price : p.price, quantity: 1, size: size?.name ?? "", additionals: [] }]); };

  return <div className="space-y-6" data-testid="tables-page">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Salão</p><h1 className="font-heading text-3xl font-semibold tracking-tight">Mesas</h1></div>
      <div className="flex gap-2"><Input type="number" min={1} value={number} onChange={(e) => setNumber(e.target.value)} placeholder="Nº da mesa" className="w-32 bg-white" data-testid="table-number-input" /><Button onClick={() => add.mutate()} disabled={!number} className="gap-1.5 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="add-table-button"><Plus size={15} /> Adicionar mesa</Button></div></div>
    <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">{(tables.data ?? []).map((t) => <button key={t.table_id} onClick={() => setOpenId(t.table_id)} className={`group relative rounded-2xl border p-5 text-left shadow-sm transition-transform hover:-translate-y-0.5 ${t.status === "ocupada" ? "border-[#C5533B] bg-[#fff7f4]" : "border-stone-200 bg-white"}`} data-testid={`table-card-${t.number}`}>
      <Armchair size={22} className={t.status === "ocupada" ? "text-[#C5533B]" : "text-stone-400"} /><strong className="mt-2 block font-heading text-2xl">Mesa {t.number}</strong>
      <Badge className={t.status === "ocupada" ? "border-[#e8b5a0] bg-white text-[#a6432e]" : "border-emerald-200 bg-emerald-50 text-emerald-800"}>{t.status === "ocupada" ? `Ocupada · ${formatCurrency(t.total)}` : "Livre"}</Badge>
    </button>)}{!tables.data?.length && <p className="col-span-full text-sm text-stone-500" data-testid="tables-empty">Cadastre as mesas do salão para lançar pedidos por mesa.</p>}</div>

    <Dialog open={!!table} onOpenChange={(v) => { if (!v) { setOpenId(null); setItems([]); } }}><DialogContent className="max-h-[90vh] overflow-y-auto border-stone-200 bg-[#F9F8F6] sm:max-w-2xl">{table && <>
      <DialogHeader><DialogTitle data-testid="table-dialog-title">Mesa {table.number} · {table.status === "ocupada" ? "Ocupada" : "Livre"}</DialogTitle></DialogHeader>
      {table.orders.length > 0 && <Card className="border-stone-200"><CardContent className="space-y-1 p-4 text-sm" data-testid="table-orders">{table.orders.map((o) => <div key={o.order_id} className="flex justify-between"><span>{o.items.map((i) => `${i.quantity}× ${i.name}${i.size ? ` ${i.size}` : ""}`).join(", ")} <span className="text-xs text-stone-400">· {o.status}</span></span><strong>{formatCurrency(o.total)}</strong></div>)}<div className="flex justify-between border-t border-stone-100 pt-2 font-semibold"><span>Total da conta</span><span data-testid="table-total">{formatCurrency(table.total)}</span></div></CardContent></Card>}
      <div><p className="mb-1.5 text-sm font-medium">Lançar itens</p><div className="flex flex-wrap gap-2 rounded-xl border border-stone-200 bg-white p-3">{(products.data ?? []).filter((p) => p.active).map((p) => <button key={p.product_id} type="button" onClick={() => addItem(p)} className="rounded-lg border border-stone-200 px-2.5 py-2 text-xs hover:border-[#C5533B]" data-testid={`table-add-product-${p.product_id}`}>+ {p.name}</button>)}</div>
        {items.length > 0 && <div className="mt-2 space-y-1 rounded-xl border border-stone-200 bg-white p-3 text-sm">{items.map((i, idx) => <div key={idx} className="flex items-center justify-between"><span>{i.name}{i.size ? ` ${i.size}` : ""}</span><span className="flex items-center gap-2">{formatCurrency(i.price)}<button onClick={() => setItems(items.filter((_, n) => n !== idx))} aria-label="Remover" data-testid={`table-remove-item-${idx}`}><X size={14} className="text-red-500" /></button></span></div>)}<Button size="sm" onClick={() => launch.mutate()} disabled={launch.isPending} className="mt-2 w-full" data-testid="table-launch-button">Enviar para a cozinha</Button></div>}</div>
      <DialogFooter className="flex-wrap gap-2 sm:justify-between">
        {table.status === "livre" ? <Button variant="ghost" onClick={() => { remove.mutate(table.table_id); setOpenId(null); }} className="gap-1.5 text-red-600" data-testid="table-delete-button"><Trash2 size={14} /> Remover mesa</Button> : <span />}
        {table.status === "ocupada" && <div className="flex gap-2"><select value={pay} onChange={(e) => setPay(e.target.value)} className="h-9 rounded-md border border-stone-200 bg-white px-2 text-sm" data-testid="table-payment-select">{PAYMENT_METHODS.filter((p) => p !== "Pendente").map((p) => <option key={p}>{p}</option>)}</select><Button onClick={() => close.mutate()} className="gap-1.5 bg-emerald-600 hover:bg-emerald-700" data-testid="table-close-button"><Receipt size={15} /> Fechar conta</Button></div>}
      </DialogFooter>
    </>}</DialogContent></Dialog>
  </div>;
}
