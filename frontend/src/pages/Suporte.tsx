import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { SupportTicket } from "@/lib/types";
import { LifeBuoy, Plus, Send } from "lucide-react";

const STATUS_STYLE: Record<string, string> = { aberto: "border-amber-200 bg-amber-50 text-amber-800", respondido: "border-blue-200 bg-blue-50 text-blue-800", resolvido: "border-emerald-200 bg-emerald-50 text-emerald-800" };
const fmt = (v: string) => new Date(v).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Ticket list + thread, shared by the restaurant's Central de Suporte and the master panel. */
export function TicketDesk({ tickets, replyPath, side, header }: { tickets: SupportTicket[]; replyPath: (id: string) => string; side: "loja" | "suporte"; header?: (t: SupportTicket) => React.ReactNode }) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState("");
  const current = tickets.find((t) => t.ticket_id === selected) ?? tickets[0];
  const reply = useMutation({ mutationFn: () => apiPost<SupportTicket>(replyPath(current!.ticket_id), { text }), onSuccess: () => { setText(""); client.invalidateQueries({ queryKey: ["support"] }); toast.success("Mensagem enviada."); } });
  if (!tickets.length) return <Card className="border-dashed border-stone-300"><CardContent className="py-12 text-center text-sm text-stone-500" data-testid="tickets-empty">Nenhum chamado ainda.</CardContent></Card>;
  return <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
    <Card className="overflow-hidden border-stone-200 shadow-sm"><div className="max-h-[560px] divide-y divide-stone-100 overflow-y-auto">{tickets.map((t) => <button key={t.ticket_id} onClick={() => setSelected(t.ticket_id)} className={`w-full p-4 text-left hover:bg-stone-50 ${current?.ticket_id === t.ticket_id ? "border-l-4 border-[#C5533B] bg-stone-100" : ""}`} data-testid={`ticket-item-${t.ticket_id}`}><div className="flex items-center justify-between gap-2"><strong className="truncate text-sm">{t.subject}</strong><Badge className={`${STATUS_STYLE[t.status]} text-[10px]`}>{t.status}</Badge></div><small className="block text-[11px] text-stone-500">{side === "suporte" ? `${t.store_name} · ` : ""}{t.category} · {fmt(t.updated_at)}</small></button>)}</div></Card>
    {current && <Card className="flex min-h-[420px] flex-col overflow-hidden border-stone-200 bg-[#FAF9F6] shadow-sm" data-testid="ticket-thread">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-200 bg-white p-4"><div><strong className="block text-sm" data-testid="ticket-subject">{current.subject}</strong><small className="text-xs text-stone-500">{current.store_name} · {current.user_email}</small></div>{header?.(current)}</div>
      <div className="flex-1 space-y-3 overflow-y-auto p-5">{current.messages.map((m) => <div key={m.id} className={`flex flex-col ${m.sender === side ? "items-end" : "items-start"}`}><small className="mb-1 text-[10px] text-stone-400">{m.author} · {fmt(m.timestamp)}</small><div className={`max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2.5 text-sm shadow-sm ${m.sender === side ? "bg-[#C5533B] text-white" : "border border-stone-200 bg-white"}`}>{m.text}</div></div>)}</div>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (text.trim()) reply.mutate(); }} className="flex gap-2 border-t border-stone-200 bg-white p-3"><Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Escreva sua mensagem..." data-testid="ticket-reply-input" /><Button type="submit" disabled={!text.trim() || reply.isPending} className="gap-1.5 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="ticket-reply-button"><Send size={15} /> Enviar</Button></form>
    </Card>}
  </div>;
}

export default function Suporte() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ subject: "", category: "Dúvida", message: "" });
  const tickets = useQuery({ queryKey: ["support", "mine"], queryFn: () => apiGet<SupportTicket[]>("/support/tickets"), refetchInterval: 15000 });
  const create = useMutation({ mutationFn: () => apiPost<SupportTicket>("/support/tickets", form), onSuccess: () => { setOpen(false); setForm({ subject: "", category: "Dúvida", message: "" }); client.invalidateQueries({ queryKey: ["support"] }); toast.success("Chamado aberto! Responderemos em breve."); }, onError: (e) => toast.error(e.message) });
  return <div className="space-y-6" data-testid="support-center-page">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Fale com a equipe PedeFácil</p><h1 className="flex items-center gap-2 font-heading text-3xl font-semibold tracking-tight"><LifeBuoy size={26} className="text-[#C5533B]" /> Central de Suporte</h1></div><Button onClick={() => setOpen(!open)} className="gap-2 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="new-ticket-button"><Plus size={16} /> Novo chamado</Button></div>
    {open && <Card className="border-stone-200 shadow-sm"><CardContent className="space-y-4 p-6"><div className="grid gap-4 sm:grid-cols-[1fr_200px]"><div><Label htmlFor="ticket-subject">Assunto</Label><Input id="ticket-subject" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} className="mt-1.5" data-testid="ticket-subject-input" /></div><div><Label htmlFor="ticket-category">Categoria</Label><select id="ticket-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="mt-1.5 h-9 w-full rounded-md border border-stone-200 bg-white px-2 text-sm" data-testid="ticket-category-select">{["Dúvida", "Problema técnico", "WhatsApp", "Pagamento / plano", "Sugestão"].map((c) => <option key={c}>{c}</option>)}</select></div></div><div><Label htmlFor="ticket-message">Mensagem</Label><Textarea id="ticket-message" rows={4} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} className="mt-1.5" data-testid="ticket-message-input" /></div><Button onClick={() => create.mutate()} disabled={form.subject.length < 3 || form.message.length < 3 || create.isPending} data-testid="ticket-submit-button">Enviar chamado</Button></CardContent></Card>}
    <TicketDesk tickets={tickets.data ?? []} replyPath={(id) => `/support/tickets/${id}/messages`} side="loja" />
  </div>;
}
