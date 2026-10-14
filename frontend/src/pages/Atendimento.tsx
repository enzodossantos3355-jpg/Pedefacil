import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { Chat, WhatsAppStatus } from "@/lib/types";
import { formatCurrency, formatTime, statusClass } from "@/lib/types";
import { Bot, Headphones, MessageCircle, Send, Trash2, UserRound, Wifi, WifiOff } from "lucide-react";

export default function Atendimento() {
  const client = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const chats = useQuery({ queryKey: ["chats"], queryFn: () => apiGet<Chat[]>("/whatsapp/chats"), refetchInterval: 5000 });
  const wa = useQuery({ queryKey: ["whatsapp", "status"], queryFn: () => apiGet<WhatsAppStatus>("/whatsapp/status"), refetchInterval: 10000 });
  const list = (chats.data ?? []).filter((c) => { const q = search.toLowerCase(); return !q || c.customer_name.toLowerCase().includes(q) || c.phone.includes(q); });
  const current = chats.data?.find((chat) => chat.chat_id === selected);
  useEffect(() => { if ((!selected || !current) && chats.data?.[0]) setSelected(chats.data[0].chat_id); }, [chats.data, selected, current]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [current?.messages.length, selected]);
  const refresh = () => client.invalidateQueries({ queryKey: ["chats"] });
  const send = useMutation({ mutationFn: () => apiPost<Chat>(`/whatsapp/chats/${selected}/message`, { text }), onSuccess: () => { setText(""); refresh(); }, onError: () => toast.error("Não foi possível enviar a mensagem.") });
  const toggle = useMutation({ mutationFn: (enable: boolean) => apiPost<Chat>(`/whatsapp/chats/${selected}/toggle-human`, { enable_human: enable }), onSuccess: (_, enable) => { refresh(); toast.success(enable ? "Atendimento assumido. A IA está pausada para este cliente." : "IA reativada para este cliente."); } });
  const removeChat = useMutation({ mutationFn: (id: string) => apiDelete<{ ok: boolean }>(`/whatsapp/chats/${id}`), onSuccess: () => { setSelected(null); refresh(); toast.success("Conversa apagada do painel."); } });
  const removeMessage = useMutation({ mutationFn: (id: string) => apiDelete<Chat>(`/whatsapp/chats/${selected}/messages/${id}`), onSuccess: () => { refresh(); toast.success("Mensagem apagada."); } });
  const connected = wa.data?.is_connected;

  return <div className="space-y-6" data-testid="support-page">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">WhatsApp & atendente virtual</p><h1 className="font-heading text-3xl font-semibold tracking-tight">Atendimento</h1><p className="mt-2 text-sm text-stone-500">Acompanhe a IA, assuma conversas e apague o que não precisa mais.</p></div>
      <Badge className={`w-fit ${connected ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`} data-testid="whatsapp-connection-badge">{connected ? <><Wifi size={14} className="mr-1" /> Conectado · +{wa.data?.phone}</> : <><WifiOff size={14} className="mr-1" /> WhatsApp desconectado</>}</Badge>
    </div>
    <div className="grid min-h-[560px] gap-4 lg:grid-cols-[330px_1fr]">
      <Card className="flex flex-col overflow-hidden border-stone-200 shadow-sm" data-testid="chat-list-card">
        <div className="border-b border-stone-200 bg-stone-50 p-4"><div className="flex items-center gap-2"><Headphones size={17} className="text-[#C5533B]" /><strong className="text-sm">Conversas recentes</strong><span className="ml-auto text-xs text-stone-400">{list.length}</span></div><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar cliente ou telefone..." className="mt-3 bg-white text-sm" data-testid="chat-search-input" /></div>
        <div className="max-h-[620px] flex-1 divide-y divide-stone-100 overflow-y-auto">
          {list.map((chat) => <button key={chat.chat_id} onClick={() => setSelected(chat.chat_id)} className={`w-full p-4 text-left transition-colors hover:bg-stone-50 ${selected === chat.chat_id ? "border-l-4 border-[#C5533B] bg-stone-100" : ""}`} data-testid={`chat-list-item-${chat.chat_id}`}><div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-50 text-emerald-700"><MessageCircle size={17} /></span><span className="min-w-0 flex-1"><strong className="block truncate text-sm">{chat.customer_name}</strong><small className="block text-[11px] text-stone-500">{chat.phone}</small><span className="mt-1 block truncate text-xs text-stone-600">{chat.last_message}</span></span><small className="text-[10px] text-stone-400">{chat.last_timestamp ? formatTime(chat.last_timestamp) : ""}</small></div><span className={`mt-2 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${chat.is_human_controlled ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"}`}>{chat.is_human_controlled ? "Humano" : "IA ativa"}</span></button>)}
          {!list.length && <p className="p-6 text-center text-sm text-stone-400" data-testid="chat-list-empty">Nenhuma conversa.</p>}
        </div>
      </Card>
      <Card className="flex min-h-[560px] flex-col overflow-hidden border-stone-200 bg-[#FAF9F6] shadow-sm" data-testid="chat-window-card">
        {current ? <>
          <div className="flex flex-col justify-between gap-3 border-b border-stone-200 bg-white p-4 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-full bg-stone-100"><UserRound size={18} /></span><div><strong className="block text-sm" data-testid="chat-customer-name">{current.customer_name}</strong><small className="text-xs text-stone-500">WhatsApp: +{current.phone}</small></div>{current.latest_order && <Badge className={`${statusClass(current.latest_order.status)} ml-2`} data-testid="chat-latest-order">#{current.latest_order.order_id.slice(-6).toUpperCase()} · {current.latest_order.status} · {formatCurrency(current.latest_order.total)}</Badge>}</div>
            <div className="flex gap-2"><Button variant={current.is_human_controlled ? "default" : "outline"} size="sm" onClick={() => toggle.mutate(!current.is_human_controlled)} className="gap-1.5" data-testid="toggle-human-support-button">{current.is_human_controlled ? <><Bot size={15} /> Reativar IA</> : <><UserRound size={15} /> Assumir Atendimento</>}</Button><Button variant="outline" size="sm" onClick={() => { if (window.confirm("Apagar esta conversa inteira do painel?")) removeChat.mutate(current.chat_id); }} className="gap-1.5 border-red-200 text-red-600 hover:bg-red-50" data-testid="delete-chat-button"><Trash2 size={15} /> Apagar conversa</Button></div>
          </div>
          <div className="max-h-[560px] flex-1 space-y-4 overflow-y-auto p-5" data-testid="chat-message-list">
            {current.messages.map((message) => <div key={message.id} className={`group flex flex-col ${message.sender === "customer" ? "items-start" : "items-end"}`} data-testid={`chat-message-${message.id}`}>
              <small className="mb-1 flex items-center gap-2 text-[10px] text-stone-400">{message.sender === "customer" ? current.customer_name : message.sender === "bot" ? "Atendente virtual" : "Atendente humano"} · {formatTime(message.timestamp)}<button onClick={() => removeMessage.mutate(message.id)} className="text-stone-300 opacity-0 transition-opacity hover:text-red-600 group-hover:opacity-100" data-testid={`delete-message-${message.id}`} aria-label="Apagar mensagem" title="Apagar mensagem"><Trash2 size={12} /></button></small>
              <div className={`max-w-[85%] whitespace-pre-line break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${message.sender === "customer" ? "rounded-tl-sm border border-stone-200 bg-white" : message.sender === "bot" ? "rounded-tr-sm bg-[#005c4b] text-white" : "rounded-tr-sm bg-blue-600 text-white"}`}>{message.text}</div>
            </div>)}
            {!current.messages.length && <p className="py-10 text-center text-sm text-stone-400">Sem mensagens.</p>}
            <div ref={bottom} />
          </div>
          <form onSubmit={(event: FormEvent) => { event.preventDefault(); if (text.trim()) send.mutate(); }} className="flex gap-2 border-t border-stone-200 bg-white p-3" data-testid="chat-message-form"><Input value={text} onChange={(event) => setText(event.target.value)} placeholder="Digite uma mensagem para o cliente (pausa a IA)..." className="bg-stone-50" data-testid="chat-message-input" /><Button type="submit" disabled={!text.trim() || send.isPending} className="gap-1.5 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="chat-send-button"><Send size={15} /> Enviar</Button></form>
        </> : <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-stone-500"><MessageCircle size={48} className="mb-3 text-stone-300" /><strong>Selecione uma conversa</strong><span className="mt-1 text-sm">As mensagens aparecerão nesta janela.</span></div>}
      </Card>
    </div>
  </div>;
}
