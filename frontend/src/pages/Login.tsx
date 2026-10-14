import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPost } from "@/lib/api";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PlanOption, User } from "@/lib/types";
import { formatCurrency } from "@/lib/types";
import { FEATURE_LABELS } from "@/lib/plans";
import { Armchair, Bike, Bot, Check, ChefHat, ClipboardList, Crown, Headphones, Lock, MapPin, Mic, QrCode, Sparkles, Users, Wallet } from "lucide-react";

const HERO = "https://images.unsplash.com/photo-1618417376251-a9b0894035b4?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400";
const FEATURES: { icon: typeof Bot; title: string; text: string }[] = [
  { icon: Bot, title: "Atendente IA no WhatsApp", text: "Responde, mostra o cardápio, fecha o pedido na hora e até ouve áudios dos clientes." },
  { icon: ClipboardList, title: "Pedidos e cozinha", text: "Fila de produção em tempo real, filtros por status e pagamento, cupom impresso." },
  { icon: QrCode, title: "Pix QR Code com valor", text: "QR Code e Copia e Cola travados no total de cada pedido. Grátis, sem taxas." },
  { icon: MapPin, title: "Taxas por área, raio ou CEP", text: "Desenhe zonas no mapa: a IA lê a localização do WhatsApp e calcula o frete." },
  { icon: Bike, title: "Motoboys", text: "Atribua entregas e envie a ficha do pedido para o entregador." },
  { icon: Armchair, title: "Mesas (opcional)", text: "Abra mesas, lance pedidos para a cozinha e feche a conta do salão." },
  { icon: Users, title: "Clientes (CRM)", text: "Cadastro automático pelo WhatsApp com preferências e histórico." },
  { icon: Wallet, title: "Caixa do dia", text: "Abertura e fechamento de caixa com histórico arquivado." },
  { icon: Sparkles, title: "Relatórios com IA", text: "Faturamento, ticket médio e dicas práticas para vender mais." },
  { icon: Mic, title: "Pedido por voz", text: "Dite o pedido no balcão e a IA monta tudo com o seu cardápio." },
];
const TAGLINE: Record<string, string> = { basico: "Para organizar o balcão", padrao: "WhatsApp com IA vendendo por você", pro: "Tudo liberado para crescer" };

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(location.pathname === "/login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const plans = useQuery({ queryKey: ["billing", "plans"], queryFn: () => apiGet<PlanOption[]>("/billing/plans") });
  const login = useMutation({
    mutationFn: () => apiPost<User>("/auth/login", { email, password }),
    onSuccess: async (u) => { queryClient.clear(); toast.success("Bem-vindo de volta ao PedeFácil!"); navigate(u.role === "master" ? "/master" : "/dashboard"); },
    onError: () => toast.error("E-mail ou senha inválidos."),
  });
  const submit = (event: FormEvent) => { event.preventDefault(); login.mutate(); };

  return <div className="min-h-screen bg-[#F9F8F6] text-stone-900" data-testid="login-page">
    <header className="sticky top-0 z-30 border-b border-stone-200/70 bg-[#F9F8F6]/85 backdrop-blur" data-testid="landing-header">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <a href="#topo" className="flex items-center gap-2.5" data-testid="landing-brand"><img src="/logo.svg" alt="PedeFácil" className="h-9 w-9" /><span><strong className="block font-heading text-lg leading-tight">PedeFácil</strong><small className="block text-[10px] text-stone-500">Gestão & Delivery Inteligente</small></span></a>
        <nav className="hidden items-center gap-6 text-sm text-stone-600 md:flex"><a href="#funcoes" className="hover:text-stone-900" data-testid="landing-nav-features">Funções</a><a href="#planos" className="hover:text-stone-900" data-testid="landing-nav-plans">Planos</a></nav>
        <div className="flex items-center gap-2"><Button variant="ghost" onClick={() => setOpen(true)} className="text-stone-700" data-testid="landing-login-button">Entrar</Button><Link to="/register" className={buttonVariants({ className: "bg-[#C5533B] hover:bg-[#A6432E]" })} data-testid="landing-register-button">Cadastrar</Link></div>
      </div>
    </header>

    <section id="topo" className="mx-auto grid max-w-6xl items-center gap-10 px-5 py-14 lg:grid-cols-[1.1fr_0.9fr] lg:py-20">
      <div className="space-y-6">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800"><Sparkles size={13} /> 7 dias grátis, sem cartão</span>
        <h1 className="font-heading text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl" data-testid="landing-title">Seu restaurante vendendo no WhatsApp <span className="text-[#C5533B]">no piloto automático.</span></h1>
        <p className="max-w-xl text-lg text-stone-600">Pedidos, cozinha, Pix, entregas e um atendente com IA que fecha pedidos sozinho. Tudo em um só painel, feito para marmitarias e restaurantes.</p>
        <div className="flex flex-wrap gap-3"><Link to="/register" className={buttonVariants({ size: "lg", className: "bg-[#C5533B] px-6 hover:bg-[#A6432E]" })} data-testid="hero-register-button">Começar teste grátis</Link><a href="#planos" className={buttonVariants({ size: "lg", variant: "outline", className: "px-6" })} data-testid="hero-plans-button">Ver planos</a></div>
      </div>
      <div className="relative">
        <img src={HERO} alt="Marmita brasileira" className="aspect-[4/3] w-full rounded-3xl object-cover shadow-xl" />
        <div className="absolute -bottom-5 -left-4 max-w-[260px] rounded-2xl border border-stone-200 bg-white/95 p-4 shadow-lg backdrop-blur" data-testid="hero-chat-card"><small className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700"><Headphones size={13} /> Atendente IA</small><p className="mt-1 text-sm">Fechado! 3 marmitas M por R$ 68,70 😋 Retirada na loja. Pedido #A1B2C3 🧾</p></div>
      </div>
    </section>

    <section id="funcoes" className="border-y border-stone-200 bg-white py-16" data-testid="landing-features">
      <div className="mx-auto max-w-6xl px-5"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Funções</p><h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">Tudo que a operação precisa</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">{FEATURES.map((f) => <Feature key={f.title} icon={<f.icon size={20} />} title={f.title} text={f.text} />)}</div>
      </div>
    </section>

    <section id="planos" className="mx-auto max-w-6xl px-5 py-16" data-testid="landing-plans">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Planos</p><h2 className="mt-2 font-heading text-3xl font-semibold tracking-tight">Escolha o tamanho certo para sua loja</h2><p className="mt-2 text-sm text-stone-500">Comece com 7 dias grátis (funções do Básico, com limites) e assine quando quiser.</p>
      <div className="mt-8 grid gap-5 lg:grid-cols-3">{(plans.data ?? []).map((p) => { const featured = p.key === "padrao"; return <div key={p.key} className={`overflow-hidden rounded-2xl border bg-white shadow-sm ${featured ? "border-[#C5533B] ring-1 ring-[#C5533B]" : "border-stone-200"}`} data-testid={`landing-plan-${p.key}`}>
        {featured && <div className="bg-[#C5533B] py-1.5 text-center text-[11px] font-bold uppercase tracking-[0.16em] text-white">Mais escolhido</div>}
        <div className="space-y-5 p-6"><div><h3 className="flex items-center gap-2 font-heading text-xl font-semibold">{p.key === "pro" && <Crown size={18} className="text-amber-500" />}{p.name}</h3><p className="text-sm text-stone-500">{TAGLINE[p.key]}</p></div>
          <div><strong className="font-heading text-4xl">{formatCurrency(p.price)}</strong><span className="text-sm text-stone-500">/mês</span></div>
          <ul className="space-y-2 text-sm">{Object.keys(FEATURE_LABELS).map((f) => { const on = p.features.includes(f); return <li key={f} className={`flex items-center gap-2 ${on ? "text-stone-800" : "text-stone-400"}`}>{on ? <Check size={15} className="text-emerald-600" /> : <Lock size={13} />}{FEATURE_LABELS[f]}</li>; })}</ul>
          <Link to="/register" className={buttonVariants({ variant: featured ? "default" : "outline", className: `w-full ${featured ? "bg-[#C5533B] hover:bg-[#A6432E]" : ""}` })} data-testid={`landing-plan-${p.key}-button`}>Começar grátis</Link></div>
      </div>; })}</div>
    </section>

    <footer className="border-t border-stone-200 py-8 text-center text-xs text-stone-500"><ChefHat size={16} className="mx-auto mb-2 text-[#C5533B]" />PedeFácil · Gestão & Delivery Inteligente</footer>

    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="border-stone-200 bg-[#F9F8F6] sm:max-w-md" data-testid="login-form-container">
      <DialogHeader><DialogTitle className="flex items-center gap-2"><img src="/logo.svg" alt="" className="h-7 w-7" /> Entrar no PedeFácil</DialogTitle></DialogHeader>
      <form onSubmit={submit} className="space-y-4" data-testid="login-form">
        <div><Label htmlFor="login-email">E-mail</Label><Input id="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="voce@restaurante.com" className="mt-1.5 bg-white" data-testid="login-email-input" /></div>
        <div><Label htmlFor="login-password">Senha</Label><Input id="login-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1.5 bg-white" data-testid="login-password-input" /></div>
        <Button type="submit" disabled={login.isPending} className="w-full bg-[#C5533B] hover:bg-[#A6432E]" data-testid="login-submit-button">{login.isPending ? "Entrando..." : "Entrar"}</Button>
      </form>
      <p className="text-center text-sm text-stone-500">Ainda não tem conta? <Link to="/register" className="font-semibold text-[#C5533B] hover:underline" data-testid="register-link">Cadastre-se grátis</Link></p>
    </DialogContent></Dialog>
  </div>;
}

function Feature({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return <div className="rounded-2xl border border-stone-200 bg-[#FAF9F6] p-5 transition-transform hover:-translate-y-0.5" data-testid="landing-feature-card"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#fceee6] text-[#C5533B]">{icon}</span><strong className="mt-3 block text-sm">{title}</strong><p className="mt-1 text-xs leading-relaxed text-stone-600">{text}</p></div>;
}
