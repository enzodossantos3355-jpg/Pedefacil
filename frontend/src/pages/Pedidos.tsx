import { useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { usePlan } from "@/lib/plans";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { Courier, Order, OrderItem, PixCharge, Product } from "@/lib/types";
import { formatCurrency, ORDER_STATUSES, PAYMENT_METHODS, statusClass } from "@/lib/types";
import { deliveryCardText, printDeliveryCard, printKitchenTicket } from "@/lib/print";
import { Banknote, Bike, ChefHat, ChevronDown, ChevronUp, CircleDollarSign, ClipboardList, Clock, Copy, CreditCard, House, MapPin, Mic, MoreVertical, Pencil, Phone, Plus, Printer, QrCode, Search, Sparkles, Trash2, X, type LucideIcon } from "lucide-react";

type Draft = { customer_name: string; customer_phone: string; delivery_type: string; address: string; payment_method: string; notes: string; items: OrderItem[]; courier_id: string };
const emptyForm: Draft = { customer_name: "", customer_phone: "", delivery_type: "Retirada", address: "", payment_method: "Pendente", notes: "", items: [], courier_id: "" };
const STRIP: Record<string, string> = { "Em Análise": "bg-amber-400", Novo: "bg-blue-300", "Em Preparo": "bg-orange-400", Pronto: "bg-emerald-500", "Em Entrega": "bg-[#C5533B]", "Concluído": "bg-stone-400", Cancelado: "bg-red-400" };
const PAY_ICON: Record<string, LucideIcon> = { Pendente: Clock, Dinheiro: Banknote, "Cartão Crédito": CreditCard, "Cartão Débito": CreditCard, Pix: QrCode, Outro: CircleDollarSign };
const PAY_COLOR: Record<string, string> = { Pendente: "text-amber-600", Dinheiro: "text-emerald-700", "Cartão Crédito": "text-blue-700", "Cartão Débito": "text-sky-700", Pix: "text-teal-700", Outro: "text-stone-600" };
const slug = (s: string) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replaceAll(" ", "-");
const formatDate = (v: string) => new Date(v).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

type SpeechResult = { results: ArrayLike<ArrayLike<{ transcript: string }>> };
type Recognizer = { lang: string; interimResults: boolean; onresult: (e: SpeechResult) => void; onend: () => void; onerror: () => void; start: () => void; stop: () => void };
const SpeechCtor = (window as unknown as { SpeechRecognition?: new () => Recognizer; webkitSpeechRecognition?: new () => Recognizer }).SpeechRecognition
  ?? (window as unknown as { webkitSpeechRecognition?: new () => Recognizer }).webkitSpeechRecognition;

export default function Pedidos() {
  const client = useQueryClient();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { has } = usePlan();
  const [typeFilter, setTypeFilter] = useState("Todos");
  const [payFilter, setPayFilter] = useState("Todos");
  const [statusFilter, setStatusFilter] = useState(params.get("status") ?? "Todos");
  const [search, setSearch] = useState("");
  const [kitchenOpen, setKitchenOpen] = useState(true);
  const [formOpen, setFormOpen] = useState(params.get("novo") === "1");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiText, setAiText] = useState("");
  const [listening, setListening] = useState(false);
  const recognizer = useRef<Recognizer | null>(null);
  const [form, setForm] = useState<Draft>(emptyForm);
  const [pixFor, setPixFor] = useState<Order | null>(null);
  const orders = useQuery({ queryKey: ["orders"], queryFn: () => apiGet<Order[]>("/orders"), refetchInterval: 8000 });
  const products = useQuery({ queryKey: ["products"], queryFn: () => apiGet<Product[]>("/products") });
  const couriers = useQuery({ queryKey: ["couriers"], queryFn: () => apiGet<Courier[]>("/couriers") });
  const refresh = () => { for (const key of ["orders", "products", "dashboard", "couriers"]) client.invalidateQueries({ queryKey: [key] }); client.invalidateQueries({ queryKey: ["day", "status"] }); };
  const closeForm = () => { setFormOpen(false); setEditingId(null); setForm(emptyForm); };
  const save = useMutation({
    mutationFn: () => editingId
      ? apiPut<Order>(`/orders/${editingId}`, { ...form, ...(form.delivery_type === "Retirada" ? { delivery_fee: 0, courier_id: "" } : {}) })
      : apiPost<Order>("/orders", form),
    onSuccess: () => { refresh(); toast.success(editingId ? "Pedido atualizado!" : "Pedido criado com sucesso!"); closeForm(); },
    onError: () => toast.error("Preencha o cliente e pelo menos um item."),
  });
  const status = useMutation({ mutationFn: ({ id, s }: { id: string; s: string }) => apiPatch<Order>(`/orders/${id}/status`, { status: s }), onSuccess: (o) => { refresh(); toast.success(`Pedido atualizado para "${o.status}".`); } });
  const payment = useMutation({ mutationFn: ({ id, p }: { id: string; p: string }) => apiPut<Order>(`/orders/${id}`, { payment_method: p }), onSuccess: (o) => { refresh(); toast.success(`Pagamento: ${o.payment_method}.`); } });
  const remove = useMutation({ mutationFn: (id: string) => apiDelete<{ ok: boolean }>(`/orders/${id}`), onSuccess: () => { refresh(); toast.success("Pedido excluído permanentemente."); } });
  const parse = useMutation({
    mutationFn: () => apiPost<Draft>("/ai/parse-order", { text: aiText }),
    onSuccess: (d) => { setEditingId(null); setForm({ ...emptyForm, ...d, delivery_type: d.delivery_type || "Retirada", payment_method: d.payment_method || "Pendente", courier_id: "" }); setAiOpen(false); setFormOpen(true); toast.success(`IA estruturou ${d.items.length} item(ns). Revise e salve.`); },
    onError: () => toast.error("Não foi possível interpretar o texto."),
  });

  const all = useMemo(() => {
    const q = search.toLowerCase();
    return (orders.data ?? []).filter((o) => !q || o.customer_name.toLowerCase().includes(q) || o.order_id.toLowerCase().includes(q) || o.customer_phone.includes(q));
  }, [orders.data, search]);
  const byType = all.filter((o) => typeFilter === "Todos" || o.delivery_type === typeFilter);
  const byPay = byType.filter((o) => payFilter === "Todos" || (o.payment_method || "Pendente") === payFilter);
  const visible = byPay.filter((o) => statusFilter === "Todos" || o.status === statusFilter);
  const kitchen = useMemo(() => {
    const map = new Map<string, { name: string; novo: number; preparo: number }>();
    for (const o of orders.data ?? []) {
      if (o.status !== "Novo" && o.status !== "Em Preparo") continue;
      for (const i of o.items) {
        const name = `${i.name}${i.size ? ` ${i.size}` : ""}`;
        const cur = map.get(name) ?? { name, novo: 0, preparo: 0 };
        if (o.status === "Novo") cur.novo += i.quantity; else cur.preparo += i.quantity;
        map.set(name, cur);
      }
    }
    return [...map.values()].sort((a, b) => b.novo + b.preparo - (a.novo + a.preparo));
  }, [orders.data]);
  const kitchenTotal = kitchen.reduce((s, k) => s + k.novo + k.preparo, 0);

  const openEdit = (o: Order) => { setEditingId(o.order_id); setForm({ customer_name: o.customer_name, customer_phone: o.customer_phone, delivery_type: o.delivery_type, address: o.address, payment_method: o.payment_method || "Pendente", notes: o.notes, items: o.items, courier_id: o.courier_id }); setFormOpen(true); };
  const addProduct = (p: Product) => {
    const size = p.sizes[0];
    setForm((f) => ({ ...f, items: [...f.items, { product_id: p.product_id, name: p.name, price: size ? size.price : p.price, quantity: 1, size: size?.name ?? "", additionals: [] }] }));
  };
  const updateItem = (idx: number, patch: (item: OrderItem, p?: Product) => OrderItem) => setForm((f) => ({ ...f, items: f.items.map((it, i) => (i === idx ? patch(it, products.data?.find((p) => p.product_id === it.product_id)) : it)) }));
  const unitPrice = (p: Product | undefined, size: string, adds: OrderItem["additionals"]) => (p?.sizes.find((s) => s.name === size)?.price ?? p?.price ?? 0) + adds.reduce((s, a) => s + a.price, 0);
  const subtotal = form.items.reduce((s, i) => s + i.price * i.quantity, 0);
  const courierMap = new Map((couriers.data ?? []).map((c) => [c.courier_id, c]));

  const toggleVoice = () => {
    if (!has("voz")) { toast.info("Pedido por voz: disponível no plano Pro.", { action: { label: "Ver planos", onClick: () => navigate("/planos") } }); return; }
    if (!SpeechCtor) { toast.error("Seu navegador não suporta ditado por voz. Use o Chrome."); return; }
    if (listening) { recognizer.current?.stop(); return; }
    const r = new SpeechCtor();
    r.lang = "pt-BR";
    r.interimResults = false;
    r.onresult = (e) => { const said = Array.from(e.results).map((res) => res[0].transcript).join(" "); setAiText(said); setAiOpen(true); };
    r.onend = () => setListening(false);
    r.onerror = () => { setListening(false); toast.error("Não consegui ouvir. Tente de novo."); };
    recognizer.current = r;
    setListening(true);
    r.start();
    toast.info("Pode falar o pedido...");
  };

  return <div className="space-y-6 pb-20" data-testid="orders-page">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">PDV, cozinha e expedição</p><h1 className="font-heading text-3xl font-semibold tracking-tight">Gestão de Pedidos</h1></div>
      <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => setAiOpen(true)} className="gap-2 border-amber-300 text-amber-800 hover:bg-amber-50" data-testid="ai-order-button"><Sparkles size={16} /> Pedido por texto (IA)</Button><Button onClick={() => { setEditingId(null); setForm(emptyForm); setFormOpen(true); }} className="gap-2 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="new-order-button"><Plus size={17} /> Novo Pedido</Button></div>
    </div>

    <Card className="overflow-hidden border-amber-100 bg-gradient-to-r from-white to-[#fff8ef] shadow-sm" data-testid="kitchen-panel">
      <button onClick={() => setKitchenOpen(!kitchenOpen)} className="flex w-full items-center justify-between p-4 text-left" data-testid="kitchen-toggle-button">
        <span className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-amber-500 text-white"><ChefHat size={20} /></span><span><small className="block text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">Cozinha</small><strong className="text-sm text-stone-900" data-testid="kitchen-summary">{kitchenTotal} {kitchenTotal === 1 ? "item" : "itens"} pra fazer · {kitchen.length} {kitchen.length === 1 ? "produto" : "produtos"}</strong></span></span>
        {kitchenOpen ? <ChevronUp size={18} className="text-stone-500" /> : <ChevronDown size={18} className="text-stone-500" />}
      </button>
      {kitchenOpen && <div className="flex gap-3 overflow-x-auto border-t border-amber-100 p-4" data-testid="kitchen-items">
        {kitchen.map((k) => <div key={k.name} className="flex min-w-56 items-center gap-3 rounded-xl border border-stone-200 bg-white p-3" data-testid={`kitchen-item-${slug(k.name)}`}><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#C5533B] font-heading text-lg font-semibold text-white">{k.novo + k.preparo}</span><span className="min-w-0"><strong className="block truncate text-sm">{k.name}</strong><span className="mt-1 flex gap-1">{k.novo > 0 && <Badge className="border-blue-200 bg-blue-50 text-[10px] text-blue-800">Novo {k.novo}</Badge>}{k.preparo > 0 && <Badge className="border-orange-200 bg-orange-50 text-[10px] text-orange-800">Em Preparo {k.preparo}</Badge>}</span></span></div>)}
        {!kitchen.length && <p className="text-sm text-stone-500">Nada na fila da cozinha agora.</p>}
      </div>}
    </Card>

    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex gap-2 overflow-x-auto">
        {([["Todos", ClipboardList], ["Entrega", MapPin], ["Retirada", House]] as const).map(([t, Icon]) => { const n = all.filter((o) => t === "Todos" || o.delivery_type === t).length; const on = typeFilter === t; return <button key={t} onClick={() => setTypeFilter(t)} className={`flex items-center gap-2 whitespace-nowrap rounded-xl border px-4 py-2.5 text-sm font-semibold transition-colors ${on ? "border-[#C5533B] bg-[#C5533B] text-white shadow-sm" : "border-stone-200 bg-white text-stone-700 hover:bg-stone-50"}`} data-testid={`type-filter-${slug(t)}`}><Icon size={16} /> {t} <span className={`text-xs ${on ? "text-white/80" : "text-stone-400"}`}>{n}</span></button>; })}
      </div>
      <div className="relative lg:w-72"><Search size={16} className="absolute left-3 top-2.5 text-stone-400" /><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar cliente, telefone ou #" className="bg-white pl-9" data-testid="orders-search-input" /></div>
    </div>

    <div className="flex items-center gap-2 overflow-x-auto pb-1" data-testid="payment-filters">
      <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">Pagamento</span>
      <button onClick={() => setPayFilter("Todos")} className={`whitespace-nowrap rounded-full border px-3.5 py-1.5 text-sm font-semibold ${payFilter === "Todos" ? "border-stone-900 bg-stone-900 text-white" : "border-stone-200 bg-white text-stone-700"}`} data-testid="payment-filter-todos">Todos <span className="ml-1 text-xs opacity-70">{byType.length}</span></button>
      {PAYMENT_METHODS.map((p) => { const Icon = PAY_ICON[p]; const n = byType.filter((o) => (o.payment_method || "Pendente") === p).length; const on = payFilter === p; return <button key={p} onClick={() => setPayFilter(p)} className={`flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 py-1.5 text-sm font-semibold transition-colors ${on ? "border-stone-900 bg-stone-900 text-white" : `border-stone-200 bg-white ${PAY_COLOR[p]} hover:bg-stone-50`}`} data-testid={`payment-filter-${slug(p)}`}><Icon size={14} /> {p} <span className="text-xs opacity-60">{n}</span></button>; })}
    </div>

    <div className="flex gap-1 overflow-x-auto border-b border-stone-200" data-testid="status-tabs">
      {["Todos", ...ORDER_STATUSES].map((s) => { const n = byPay.filter((o) => s === "Todos" || o.status === s).length; const on = statusFilter === s; return <button key={s} onClick={() => setStatusFilter(s)} className={`-mb-px whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-colors ${on ? "border-[#C5533B] text-[#C5533B]" : "border-transparent text-stone-500 hover:text-stone-800"}`} data-testid={`status-tab-${slug(s)}`}>{s} <span className="text-stone-400">({n})</span></button>; })}
    </div>

    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="orders-grid">
      {visible.map((o) => <OrderCard key={o.order_id} order={o} courier={courierMap.get(o.courier_id)} onStatus={(s) => status.mutate({ id: o.order_id, s })} onPayment={(p) => payment.mutate({ id: o.order_id, p })} onEdit={() => openEdit(o)} onPix={() => setPixFor(o)} onDelete={() => { if (window.confirm("Excluir este pedido permanentemente?")) remove.mutate(o.order_id); }} />)}
      {!visible.length && <Card className="border-dashed border-stone-300 md:col-span-2 xl:col-span-3"><CardContent className="py-14 text-center"><ClipboardList size={42} className="mx-auto mb-3 text-stone-300" /><strong className="block text-stone-700" data-testid="orders-empty">Nenhum pedido encontrado</strong></CardContent></Card>}
    </div>

    <button onClick={toggleVoice} className={`fixed bottom-6 right-6 z-30 grid h-16 w-16 place-items-center rounded-full text-white shadow-lg transition-transform hover:scale-105 ${listening ? "animate-pulse bg-red-600" : "bg-[#C5533B]"}`} data-testid="voice-order-button" aria-label="Pedido por voz" title="Ditar pedido por voz"><Mic size={26} /></button>

    <PixDialog order={pixFor} onClose={() => setPixFor(null)} />

    <Dialog open={aiOpen} onOpenChange={setAiOpen}><DialogContent className="border-stone-200 bg-[#F9F8F6]"><DialogHeader><DialogTitle className="flex items-center gap-2"><Sparkles size={18} className="text-amber-500" /> Criar pedido a partir de texto</DialogTitle></DialogHeader><p className="text-sm text-stone-600">Cole ou dite a mensagem do cliente. A IA identifica itens, tamanhos, adicionais, endereço e pagamento usando o seu cardápio.</p><Textarea rows={5} value={aiText} onChange={(e) => setAiText(e.target.value)} placeholder="Ex: quero 3 marmitas G com ovo" className="bg-white" data-testid="ai-order-text-input" /><DialogFooter><Button variant="outline" onClick={() => setAiOpen(false)} data-testid="ai-order-cancel-button">Cancelar</Button><Button onClick={() => parse.mutate()} disabled={aiText.trim().length < 3 || parse.isPending} data-testid="ai-order-parse-button">{parse.isPending ? "Interpretando..." : "Estruturar com IA"}</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={formOpen} onOpenChange={(v) => (v ? setFormOpen(true) : closeForm())}><DialogContent className="max-h-[90vh] overflow-y-auto border-stone-200 bg-[#F9F8F6] sm:max-w-2xl"><DialogHeader><DialogTitle data-testid="order-form-title">{editingId ? `Editar Pedido #${editingId.slice(-6).toUpperCase()}` : "Novo Pedido no Balcão"}</DialogTitle></DialogHeader><form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4" data-testid="new-order-form">
      <div className="grid gap-3 sm:grid-cols-2"><Field label="Nome do Cliente" id="order-customer"><Input id="order-customer" required value={form.customer_name} onChange={(e) => setForm({ ...form, customer_name: e.target.value })} data-testid="new-order-customer-input" /></Field><Field label="WhatsApp / Telefone" id="order-phone"><Input id="order-phone" value={form.customer_phone} onChange={(e) => setForm({ ...form, customer_phone: e.target.value })} data-testid="new-order-phone-input" /></Field></div>
      <div className="grid gap-3 sm:grid-cols-2"><Field label="Tipo de Atendimento" id="delivery-type"><Select value={form.delivery_type} onValueChange={(v) => setForm({ ...form, delivery_type: v })}><SelectTrigger id="delivery-type" className="w-full bg-white" data-testid="new-order-delivery-select"><SelectValue>{(v) => (v === "Retirada" ? "Retirada no Balcão" : "Entrega (Delivery)")}</SelectValue></SelectTrigger><SelectContent><SelectItem value="Retirada">Retirada no Balcão</SelectItem><SelectItem value="Entrega">Entrega (Delivery)</SelectItem></SelectContent></Select></Field><Field label="Forma de Pagamento" id="payment-type"><Select value={form.payment_method} onValueChange={(v) => setForm({ ...form, payment_method: v })}><SelectTrigger id="payment-type" className="w-full bg-white" data-testid="new-order-payment-select"><SelectValue>{(v) => v as string}</SelectValue></SelectTrigger><SelectContent>{PAYMENT_METHODS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select></Field></div>
      {form.delivery_type === "Entrega" && <div className="grid gap-3 sm:grid-cols-[1fr_220px]"><Field label="Endereço de Entrega (a taxa é calculada pela zona)" id="order-address"><Input id="order-address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="Rua, número, bairro" data-testid="new-order-address-input" /></Field>{editingId && <Field label="Entregador" id="order-courier"><Select value={form.courier_id || "none"} onValueChange={(v) => setForm({ ...form, courier_id: v === "none" ? "" : v })}><SelectTrigger id="order-courier" className="w-full bg-white" data-testid="order-courier-select"><SelectValue>{(v) => couriers.data?.find((c) => c.courier_id === v)?.name ?? "Sem entregador"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="none">Sem entregador</SelectItem>{(couriers.data ?? []).filter((c) => c.active).map((c) => <SelectItem key={c.courier_id} value={c.courier_id}>{c.name}</SelectItem>)}</SelectContent></Select></Field>}</div>}
      <div><Label>Cardápio — clique para adicionar</Label><div className="mt-1 flex flex-wrap gap-2 rounded-xl border border-stone-200 bg-white p-3">{(products.data ?? []).filter((p) => p.active).map((p) => <button type="button" key={p.product_id} onClick={() => addProduct(p)} className="rounded-lg border border-stone-200 px-2.5 py-2 text-xs font-medium hover:border-[#C5533B] hover:bg-[#fff7f4]" data-testid={`add-product-${p.product_id}`}>+ {p.name} ({formatCurrency(p.sizes[0]?.price ?? p.price)}){p.stock != null && <span className="ml-1 text-stone-400">· {p.stock} un.</span>}</button>)}</div></div>
      {form.items.length > 0 && <div className="space-y-2 rounded-xl border border-stone-200 bg-white p-3" data-testid="new-order-items">{form.items.map((it, idx) => { const p = products.data?.find((x) => x.product_id === it.product_id); return <div key={idx} className="rounded-lg bg-stone-50 p-2.5 text-sm"><div className="flex items-center justify-between gap-2"><span className="font-medium">{it.name}</span><div className="flex items-center gap-2"><Input type="number" min={1} value={it.quantity} onChange={(e) => updateItem(idx, (i) => ({ ...i, quantity: Math.max(1, Number(e.target.value)) }))} className="h-7 w-16 bg-white" data-testid={`order-item-qty-${idx}`} /><strong className="w-20 text-right">{formatCurrency(it.price * it.quantity)}</strong><button type="button" onClick={() => setForm({ ...form, items: form.items.filter((_, i) => i !== idx) })} className="text-red-500 hover:text-red-700" data-testid={`remove-order-item-${idx}`} aria-label="Remover item"><X size={15} /></button></div></div>{p && (p.sizes.length > 0 || p.additionals.length > 0) && <div className="mt-2 flex flex-wrap gap-1.5">{p.sizes.map((s) => <button type="button" key={s.name} onClick={() => updateItem(idx, (i, pp) => ({ ...i, size: s.name, price: unitPrice(pp, s.name, i.additionals) }))} className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${it.size === s.name ? "border-[#C5533B] bg-[#C5533B] text-white" : "border-stone-300 bg-white"}`} data-testid={`order-item-${idx}-size-${s.name}`}>{s.name}</button>)}{p.additionals.map((a) => { const on = it.additionals.some((x) => x.name === a.name); return <button type="button" key={a.name} onClick={() => updateItem(idx, (i, pp) => { const adds = on ? i.additionals.filter((x) => x.name !== a.name) : [...i.additionals, a]; return { ...i, additionals: adds, price: unitPrice(pp, i.size, adds) }; })} className={`rounded-md border px-2 py-0.5 text-[11px] ${on ? "border-emerald-500 bg-emerald-50 text-emerald-800" : "border-stone-300 bg-white"}`} data-testid={`order-item-${idx}-add-${slug(a.name)}`}>+ {a.name} {formatCurrency(a.price)}</button>; })}</div>}</div>; })}<div className="border-t border-stone-100 pt-2 text-right text-sm font-semibold" data-testid="new-order-subtotal">Subtotal: {formatCurrency(subtotal)} {form.delivery_type === "Entrega" && <span className="font-normal text-stone-500">+ taxa da zona</span>}</div></div>}
      <Field label="Observações" id="order-notes"><Input id="order-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Ex: sem cebola, tocar interfone 12" data-testid="new-order-notes-input" /></Field>
      <DialogFooter><Button type="button" variant="outline" onClick={closeForm} data-testid="new-order-cancel-button">Cancelar</Button><Button type="submit" disabled={save.isPending} data-testid="new-order-save-button">{editingId ? "Salvar Alterações" : "Salvar Pedido"}</Button></DialogFooter></form></DialogContent></Dialog>
  </div>;
}

function PixDialog({ order, onClose }: { order: Order | null; onClose: () => void }) {
  const pix = useQuery({ queryKey: ["order-pix", order?.order_id, order?.total], queryFn: () => apiGet<PixCharge>(`/orders/${order?.order_id}/pix`), enabled: !!order, retry: false });
  const copy = () => { if (pix.data) { navigator.clipboard.writeText(pix.data.copia_e_cola); toast.success("Pix Copia e Cola copiado!"); } };
  return <Dialog open={!!order} onOpenChange={(v) => !v && onClose()}><DialogContent className="border-stone-200 bg-[#F9F8F6] sm:max-w-md"><DialogHeader><DialogTitle className="flex items-center gap-2"><QrCode size={18} className="text-teal-700" /> Pix do pedido #{order?.order_id.slice(-6).toUpperCase()}</DialogTitle></DialogHeader>
    {pix.isLoading && <p className="py-10 text-center text-sm text-stone-500">Gerando QR Code...</p>}
    {pix.error && <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" data-testid="order-pix-error">{pix.error.message}</p>}
    {pix.data && <div className="space-y-4 text-center" data-testid="order-pix-content"><img src={pix.data.qr_code_base64} alt="QR Code Pix" className="mx-auto h-60 w-60 rounded-xl border border-stone-200 bg-white p-2" data-testid="order-pix-qr" /><strong className="block font-heading text-2xl" data-testid="order-pix-value">R$ {pix.data.valor.replace(".", ",")}</strong><Textarea readOnly rows={3} value={pix.data.copia_e_cola} className="bg-white font-mono text-[11px]" data-testid="order-pix-code" /><Button onClick={copy} className="w-full gap-2 bg-teal-700 hover:bg-teal-800" data-testid="order-pix-copy-button"><Copy size={15} /> Copiar Pix Copia e Cola</Button></div>}
  </DialogContent></Dialog>;
}

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) { return <div><Label htmlFor={id}>{label}</Label><div className="mt-1.5">{children}</div></div>; }

function OrderCard({ order: o, courier, onStatus, onPayment, onEdit, onPix, onDelete }: { order: Order; courier?: Courier; onStatus: (s: string) => void; onPayment: (p: string) => void; onEdit: () => void; onPix: () => void; onDelete: () => void }) {
  const pay = o.payment_method || "Pendente";
  const PayIcon = PAY_ICON[pay] ?? CircleDollarSign;
  const id = o.order_id;
  const copyCard = () => { navigator.clipboard.writeText(deliveryCardText(o, courier)); toast.success("Ficha de entrega copiada!"); };
  return <Card className="overflow-hidden border-stone-200 bg-white shadow-sm transition-shadow hover:shadow-md" data-testid={`order-card-${id}`}>
    <div className={`h-1.5 ${STRIP[o.status] ?? "bg-stone-300"}`} />
    <CardContent className="flex h-full flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-2"><Badge className={`${statusClass(o.status)} text-[10px] font-bold uppercase tracking-wide`} data-testid={`order-status-${id}`}>{o.status}</Badge><span className="text-xs text-stone-400">{formatDate(o.created_at)}</span><span className="font-mono text-[11px] text-stone-400">#{id.slice(-6).toUpperCase()}</span>{o.source === "whatsapp" && <Badge className="border-emerald-200 bg-emerald-50 text-[10px] text-emerald-800">WhatsApp</Badge>}</div>
      <div><strong className="block font-heading text-lg text-stone-900" data-testid={`order-customer-${id}`}>{o.customer_name}</strong><div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500"><span className="flex items-center gap-1">{o.delivery_type === "Retirada" ? <House size={13} /> : <MapPin size={13} />}{o.delivery_type}</span>{o.customer_phone && <span className="flex items-center gap-1"><Phone size={12} />{o.customer_phone}</span>}{courier && <span className="flex items-center gap-1"><Bike size={13} />{courier.name}</span>}</div>{o.address && o.delivery_type !== "Retirada" && <p className="mt-1 truncate text-xs text-stone-600">📍 {o.address}{o.zone_name ? ` · ${o.zone_name}` : ""}</p>}</div>
      <div className="space-y-1 border-t border-stone-100 pt-3 text-sm text-stone-700" data-testid={`order-items-${id}`}>{o.items.map((i, idx) => <p key={idx}>{i.quantity}× {i.name}{i.size ? ` ${i.size}` : ""}{i.additionals.length ? <span className="text-stone-500"> + {i.additionals.map((a) => a.name).join(", ")}</span> : null}</p>)}{o.notes && <p className="text-xs italic text-amber-800">Obs: {o.notes}</p>}</div>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-stone-100 pt-3">
        <div className="min-w-0"><strong className="block font-heading text-lg" data-testid={`order-total-${id}`}>{formatCurrency(o.total)}</strong><span className={`flex items-center gap-1 text-xs font-medium ${PAY_COLOR[pay] ?? "text-stone-500"}`} data-testid={`order-payment-${id}`}><PayIcon size={12} />{pay}</span></div>
        <div className="flex items-center gap-1">
          {o.status === "Em Análise" && <Button size="sm" onClick={() => onStatus("Novo")} className="h-8 bg-emerald-600 text-xs hover:bg-emerald-700" data-testid={`approve-order-${id}`}>Aprovar</Button>}
          <Button variant="ghost" size="sm" onClick={onEdit} className="h-8 gap-1.5 text-xs text-stone-700" data-testid={`edit-order-${id}`}><Pencil size={14} /> Editar</Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="sm" className="h-8 gap-1 text-xs text-stone-700" data-testid={`more-order-${id}`} />}><MoreVertical size={14} /> Mais</DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuGroup><DropdownMenuLabel>Status</DropdownMenuLabel>{ORDER_STATUSES.map((s) => <DropdownMenuItem key={s} disabled={s === o.status} onClick={() => onStatus(s)} data-testid={`order-${id}-status-${slug(s)}`}>{s}</DropdownMenuItem>)}</DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup><DropdownMenuLabel>Pagamento</DropdownMenuLabel>{PAYMENT_METHODS.map((p) => <DropdownMenuItem key={p} disabled={p === pay} onClick={() => onPayment(p)} data-testid={`order-${id}-payment-${slug(p)}`}>{p}</DropdownMenuItem>)}</DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onEdit} data-testid={`order-${id}-menu-edit`}><Pencil size={14} /> Editar pedido</DropdownMenuItem>
              <DropdownMenuItem onClick={onPix} data-testid={`order-${id}-pix`}><QrCode size={14} /> Pix (QR Code)</DropdownMenuItem>
              <DropdownMenuItem onClick={() => printKitchenTicket(o)} data-testid={`print-ticket-${id}`}><Printer size={14} /> Imprimir cupom</DropdownMenuItem>
              {o.delivery_type !== "Retirada" && <><DropdownMenuItem onClick={() => printDeliveryCard(o, courier)} data-testid={`print-delivery-${id}`}><Bike size={14} /> Ficha do motoboy</DropdownMenuItem><DropdownMenuItem onClick={copyCard} data-testid={`copy-delivery-${id}`}><Copy size={14} /> Copiar ficha de entrega</DropdownMenuItem></>}
              <DropdownMenuItem variant="destructive" onClick={onDelete} data-testid={`delete-order-${id}`}><Trash2 size={14} /> Excluir</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </CardContent>
  </Card>;
}
