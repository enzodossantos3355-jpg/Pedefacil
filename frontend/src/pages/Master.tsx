import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPatch, apiPut } from "@/lib/api";
import { endSession } from "@/lib/session";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Navigate } from "react-router-dom";
import type { User, PlatformSettings, StoreAdmin, SupportTicket } from "@/lib/types";
import { PLAN_NAMES } from "@/lib/plans";
import { TicketDesk } from "@/pages/Suporte";
import { Globe, LogOut, Save, Store } from "lucide-react";

const d = (v: string | null) => (v ? new Date(v).toLocaleDateString("pt-BR") : "—");

export default function Master() {
  const client = useQueryClient();
  const me = useQuery({ queryKey: ["auth", "me"], queryFn: () => apiGet<User>("/auth/me"), retry: false });
  const [tab, setTab] = useState<"lojas" | "suporte" | "config">("lojas");
  const stores = useQuery({ queryKey: ["master", "stores"], queryFn: () => apiGet<StoreAdmin[]>("/master/stores") });
  const tickets = useQuery({ queryKey: ["support", "all"], queryFn: () => apiGet<SupportTicket[]>("/master/tickets"), refetchInterval: 15000 });
  const settings = useQuery({ queryKey: ["master", "settings"], queryFn: () => apiGet<PlatformSettings>("/master/settings") });
  const [form, setForm] = useState<PlatformSettings>({ site_url: "", footer_text: "" });
  useEffect(() => { if (settings.data) setForm(settings.data); }, [settings.data]);
  const update = useMutation({ mutationFn: ({ id, body }: { id: string; body: object }) => apiPut<StoreAdmin>(`/master/stores/${id}`, body), onSuccess: () => { client.invalidateQueries({ queryKey: ["master", "stores"] }); toast.success("Loja atualizada."); }, onError: (e) => toast.error(e.message) });
  const saveSettings = useMutation({ mutationFn: () => apiPut<PlatformSettings>("/master/settings", form), onSuccess: () => toast.success("Configurações da plataforma salvas.") });
  const ticketStatus = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => apiPatch<SupportTicket>(`/master/tickets/${id}`, { status }), onSuccess: () => client.invalidateQueries({ queryKey: ["support"] }) });
  if (me.isError) return <Navigate to="/login" replace />;
  if (me.data && me.data.role !== "master") return <Navigate to="/dashboard" replace />;
  const openTickets = (tickets.data ?? []).filter((t) => t.status === "aberto").length;

  return <div className="min-h-screen bg-[#F9F8F6] text-stone-900" data-testid="master-page">
    <header className="flex h-16 items-center justify-between border-b border-stone-200 bg-white px-6"><div className="flex items-center gap-3"><img src="/logo.svg" alt="PedeFácil" className="h-9 w-9" /><strong className="font-heading text-lg">PedeFácil · Painel Master</strong></div><Button variant="ghost" onClick={() => endSession()} className="gap-1.5 text-stone-600" data-testid="master-logout-button"><LogOut size={16} /> Sair</Button></header>
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex gap-1 border-b border-stone-200">{([["lojas", `Restaurantes (${stores.data?.length ?? 0})`], ["suporte", `Suporte (${openTickets} abertos)`], ["config", "Plataforma"]] as const).map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-4 py-3 text-sm font-medium ${tab === k ? "border-[#C5533B] text-[#C5533B]" : "border-transparent text-stone-500"}`} data-testid={`master-tab-${k}`}>{l}</button>)}</div>
      {tab === "lojas" && <div className="space-y-3">{(stores.data ?? []).map((s) => <Card key={s.store_id} className="border-stone-200 shadow-sm" data-testid={`master-store-${s.store_id}`}><CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0"><strong className="flex items-center gap-2"><Store size={16} className="text-[#C5533B]" />{s.name}</strong><small className="block text-xs text-stone-500">{s.owner_email} · desde {d(s.created_at)} · {s.orders_count} pedidos</small><div className="mt-2 flex flex-wrap gap-1.5"><Badge className="border-stone-200 bg-stone-50 text-stone-700" data-testid={`master-store-plan-${s.store_id}`}>Em vigor: {PLAN_NAMES[s.effective_plan] ?? s.effective_plan}</Badge><Badge className="border-stone-200 bg-white text-stone-600">Status: {s.status}</Badge><Badge className="border-stone-200 bg-white text-stone-600">{s.status === "trialing" ? `Teste até ${d(s.trial_ends_at)}` : `Período até ${d(s.current_period_end)}`}</Badge></div></div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={s.plan} onChange={(e) => update.mutate({ id: s.store_id, body: { plan: e.target.value, status: "active" } })} className="h-8 rounded-md border border-stone-200 bg-white px-2 text-sm" data-testid={`master-plan-select-${s.store_id}`}>{["basico", "padrao", "pro"].map((p) => <option key={p} value={p}>{PLAN_NAMES[p]}</option>)}</select>
          <Button size="sm" variant="outline" onClick={() => update.mutate({ id: s.store_id, body: { extend_days: 30 } })} data-testid={`master-extend-${s.store_id}`}>+30 dias</Button>
          <Button size="sm" variant="outline" onClick={() => update.mutate({ id: s.store_id, body: { extend_days: 7, status: "trialing" } })} data-testid={`master-trial-${s.store_id}`}>+7 dias de teste</Button>
          {s.status !== "canceled" ? <Button size="sm" variant="outline" onClick={() => update.mutate({ id: s.store_id, body: { status: "canceled" } })} className="border-red-200 text-red-600 hover:bg-red-50" data-testid={`master-block-${s.store_id}`}>Bloquear</Button>
            : <Button size="sm" onClick={() => update.mutate({ id: s.store_id, body: { status: "active" } })} className="bg-emerald-600 hover:bg-emerald-700" data-testid={`master-activate-${s.store_id}`}>Ativar</Button>}
        </div>
      </CardContent></Card>)}</div>}
      {tab === "suporte" && <TicketDesk tickets={tickets.data ?? []} replyPath={(id) => `/master/tickets/${id}/messages`} side="suporte" header={(t) => <Button size="sm" variant="outline" onClick={() => ticketStatus.mutate({ id: t.ticket_id, status: t.status === "resolvido" ? "aberto" : "resolvido" })} data-testid="ticket-resolve-button">{t.status === "resolvido" ? "Reabrir" : "Marcar resolvido"}</Button>} />}
      {tab === "config" && <Card className="max-w-2xl border-stone-200 shadow-sm"><CardContent className="space-y-4 p-6"><h2 className="flex items-center gap-2 font-heading text-lg font-semibold"><Globe size={18} /> Assinatura nas mensagens</h2><p className="text-sm text-stone-600">Quando um pedido é concluído, o cliente recebe no WhatsApp este texto e o link do site.</p>
        <div><Label htmlFor="footer-text">Texto</Label><Input id="footer-text" value={form.footer_text} onChange={(e) => setForm({ ...form, footer_text: e.target.value })} className="mt-1.5" data-testid="platform-footer-input" /></div>
        <div><Label htmlFor="site-url">Link do site</Label><Input id="site-url" value={form.site_url} onChange={(e) => setForm({ ...form, site_url: e.target.value })} placeholder="https://pedefacil.com.br" className="mt-1.5" data-testid="platform-site-url-input" /></div>
        <div className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-xs text-stone-600" data-testid="platform-footer-preview">🙏 Pedido #A1B2C3 concluído. Obrigado pela preferência, bom apetite!<br /><br />✨ {form.footer_text}<br />{form.site_url}</div>
        <Button onClick={() => saveSettings.mutate()} className="gap-2 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="platform-save-button"><Save size={15} /> Salvar</Button></CardContent></Card>}
    </main>
  </div>;
}
