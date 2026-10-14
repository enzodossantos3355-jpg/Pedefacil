import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bike, Phone, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import { formatCurrency, type Courier } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** (77) 98888-7777 display mask over raw DDD+number digits. */
function maskPhone(d: string) {
  const v = d.replace(/\D/g, "");
  if (v.length <= 2) return v ? `(${v}` : "";
  if (v.length <= 6) return `(${v.slice(0, 2)}) ${v.slice(2)}`;
  return `(${v.slice(0, 2)}) ${v.slice(2, v.length - 4)}-${v.slice(-4)}`;
}

/** Courier (motoboy) management: register, pause and see today's deliveries/fees. */
export default function Entregadores() {
  const client = useQueryClient();
  const [form, setForm] = useState({ name: "", phone: "" });
  const couriers = useQuery({ queryKey: ["couriers"], queryFn: () => apiGet<Courier[]>("/couriers") });
  const refresh = () => client.invalidateQueries({ queryKey: ["couriers"] });
  const add = useMutation({
    mutationFn: () => { if (form.phone.length < 10) throw new Error("Digite o DDD + número do WhatsApp do entregador."); return apiPost<Courier>("/couriers", { ...form, phone: `55${form.phone}`, active: true }); },
    onSuccess: () => { refresh(); setForm({ name: "", phone: "" }); toast.success("Entregador cadastrado!"); },
    onError: (e: Error) => toast.error(e.message),
  });
  const toggle = useMutation({ mutationFn: (c: Courier) => apiPut<Courier>(`/couriers/${c.courier_id}`, { name: c.name, phone: c.phone, active: !c.active }), onSuccess: refresh, onError: (e: Error) => toast.error(e.message) });
  const working = useMutation({ mutationFn: (id: string) => apiPost<Courier>(`/couriers/${id}/working`), onSuccess: refresh, onError: (e: Error) => toast.error(e.message) });
  const remove = useMutation({ mutationFn: (id: string) => apiDelete(`/couriers/${id}`), onSuccess: () => { refresh(); toast.success("Entregador removido."); }, onError: (e: Error) => toast.error(e.message) });
  const list = couriers.data ?? [];

  return (
    <div className="space-y-6" data-testid="couriers-page">
      <div><h1 className="font-heading text-3xl font-bold text-stone-900">Entregadores</h1><p className="text-sm text-stone-500">Marque quem trabalha hoje. Só eles aparecem nos pedidos. Cada entrega soma a taxa da área ao saldo do entregador, e ao sair para entrega ele recebe no WhatsApp a ficha com nome, telefone, localização, pedido e pagamento.</p></div>
      <Card className="border-stone-200 bg-white"><CardContent className="p-5">
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate(); }} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end" data-testid="courier-form">
          <div><Label htmlFor="courier-name">Nome</Label><Input id="courier-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ex: Carlos" className="mt-1" data-testid="courier-name-input" /></div>
          <div><Label htmlFor="courier-phone">WhatsApp (DDD + número)</Label><div className="mt-1 flex items-center overflow-hidden rounded-md border border-input bg-white focus-within:ring-2 focus-within:ring-[#C5533B]/30"><span className="border-r border-stone-200 bg-stone-50 px-3 py-2 text-sm font-semibold text-stone-600" data-testid="courier-phone-prefix">🇧🇷 +55</span><input id="courier-phone" required inputMode="numeric" value={maskPhone(form.phone)} onChange={(e) => setForm({ ...form, phone: e.target.value.replace(/\D/g, "").replace(/^55(?=\d{10,11}$)/, "").slice(0, 11) })} placeholder="(77) 98888-7777" className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm outline-none" data-testid="courier-phone-input" /></div><small className="text-[11px] text-stone-500">{form.phone.length >= 10 ? `Será enviado para +55 ${maskPhone(form.phone)}` : "Digite o DDD e o número do celular"}</small></div>
          <Button type="submit" disabled={add.isPending} data-testid="courier-add-button">Adicionar</Button>
        </form>
      </CardContent></Card>
      {list.length === 0 && !couriers.isLoading && <p className="rounded-2xl border border-dashed border-stone-300 py-10 text-center text-sm text-stone-400" data-testid="couriers-empty">Nenhum entregador cadastrado ainda.</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {list.map((c) => (
          <Card key={c.courier_id} className={`border-stone-200 bg-white transition-opacity ${c.active ? "" : "opacity-60"}`} data-testid={`courier-card-${c.courier_id}`}><CardContent className="space-y-3 p-5">
            <div className="flex items-start justify-between gap-2"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-full bg-[#fff7f4] text-[#C5533B]"><Bike size={18} /></span><div><strong className="block" data-testid={`courier-name-${c.courier_id}`}>{c.name}</strong><small className="flex items-center gap-1 text-stone-500" data-testid={`courier-phone-${c.courier_id}`}><Phone size={11} />+{c.phone.slice(0, 2)} {maskPhone(c.phone.slice(2))}</small></div></div>
              <button onClick={() => remove.mutate(c.courier_id)} className="text-stone-400 transition-colors hover:text-red-600" aria-label="Remover" data-testid={`courier-delete-${c.courier_id}`}><Trash2 size={16} /></button></div>
            <button onClick={() => working.mutate(c.courier_id)} className={`flex w-full items-center justify-between rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${c.working_today ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-stone-200 bg-stone-50 text-stone-500 hover:bg-stone-100"}`} data-testid={`courier-working-toggle-${c.courier_id}`}><span>{c.working_today ? "✓ Trabalhando hoje" : "Folga hoje"}</span><small className="font-normal">{c.working_today ? "toque para tirar" : "toque para escalar"}</small></button>
            <div className="flex gap-4 text-xs text-stone-600"><span data-testid={`courier-deliveries-${c.courier_id}`}><strong className="text-stone-900">{c.deliveries_today}</strong> entregas hoje</span><span data-testid={`courier-fees-${c.courier_id}`}><strong className="text-stone-900">{formatCurrency(c.fees_today)}</strong> de saldo hoje</span></div>
            <Button variant="outline" size="sm" className="w-full" onClick={() => toggle.mutate(c)} data-testid={`courier-toggle-${c.courier_id}`}>{c.active ? "Pausar entregador" : "Reativar entregador"}</Button>
          </CardContent></Card>
        ))}
      </div>
    </div>
  );
}
