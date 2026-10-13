import { useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { DayStatus, User } from "@/lib/types";
import { formatCurrency } from "@/lib/types";
import { Archive, BarChart3, Bell, Boxes, ChevronLeft, ChevronRight, CircleUserRound, ClipboardList, CookingPot, Headphones, LayoutDashboard, LogOut, Menu, Settings2, Users, UtensilsCrossed, Wifi, X } from "lucide-react";

const navItems = [
  { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
  { label: "Pedidos", path: "/pedidos", icon: ClipboardList },
  { label: "Atendimento WhatsApp", path: "/atendimento", icon: Headphones },
  { label: "Clientes Salvos", path: "/clientes", icon: Users },
  { label: "Cardápio", path: "/produtos", icon: UtensilsCrossed },
  { label: "Relatórios", path: "/relatorios", icon: BarChart3 },
  { label: "Armazenamento & Caixa", path: "/armazenamento", icon: Archive },
  { label: "Configurações", path: "/configuracoes", icon: Settings2 },
];

export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [cashOpen, setCashOpen] = useState(false);
  const [initialCash, setInitialCash] = useState("0");
  const user = useQuery({ queryKey: ["auth", "me"], queryFn: () => apiGet<User>("/auth/me"), retry: false });
  const day = useQuery({ queryKey: ["day", "status"], queryFn: () => apiGet<DayStatus>("/day/status"), refetchInterval: 15000 });
  const dayMutation = useMutation({
    mutationFn: async () => {
      if (day.data?.is_open) return apiPost<DayStatus>("/day/close");
      return apiPost<DayStatus>("/day/open", { initial_cash: Number(initialCash) || 0 });
    },
    onSuccess: (next) => {
      day.refetch();
      setCashOpen(false);
      toast.success(next.is_open ? "Caixa do dia aberto com sucesso!" : "Caixa do dia fechado e arquivado.");
    },
    onError: () => toast.error("Não foi possível atualizar o caixa."),
  });
  const logout = useMutation({
    mutationFn: () => apiPost<{ ok: boolean }>("/auth/logout"),
    onSuccess: () => { queryClient.clear(); navigate("/login"); toast.success("Sessão encerrada."); },
  });

  if (user.error instanceof ApiError && user.error.status === 401) return <Navigate to="/login" replace />;
  const isOpen = day.data?.is_open ?? true;
  const displayUser = user.data ?? { name: "Operador", email: "operador@marmitahub.com", role: "admin" as const };

  return (
    <div className="min-h-screen bg-[#F9F8F6] text-stone-900">
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-[#E7E5E4] bg-[#F4F2EF] transition-transform duration-200 lg:translate-x-0 ${collapsed ? "lg:w-[84px]" : "lg:w-72"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`} data-testid="app-sidebar">
        <div className="flex h-20 items-center justify-between border-b border-[#E7E5E4] px-5">
          <Link to="/dashboard" className="flex min-w-0 items-center gap-3" data-testid="brand-dashboard-link">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#C5533B] text-2xl shadow-sm">🍱</span>
            {!collapsed && <span className="min-w-0"><strong className="block truncate font-heading text-lg leading-tight">Marmita Hub</strong><small className="block truncate text-[11px] font-medium text-stone-500">Gestão & Delivery Inteligente</small></span>}
          </Link>
          <button className="hidden rounded-lg p-2 text-stone-400 hover:bg-stone-200 hover:text-stone-800 lg:block" onClick={() => setCollapsed(!collapsed)} data-testid="sidebar-collapse-button" aria-label="Recolher menu">{collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}</button>
          <button className="rounded-lg p-2 text-stone-400 hover:bg-stone-200 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-close-button" aria-label="Fechar menu"><X size={19} /></button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto p-3" data-testid="main-navigation">
          {navItems.map((item) => {
            const active = location.pathname === item.path;
            const Icon = item.icon;
            return <Link key={item.path} to={item.path} onClick={() => setMobileOpen(false)} className={`group flex items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors ${active ? "bg-[#C5533B] text-white shadow-sm" : "text-stone-600 hover:bg-stone-200/70 hover:text-stone-900"}`} data-testid={`nav-${item.label.toLowerCase().replaceAll(" ", "-").replaceAll("&", "e").replaceAll("ã", "a")}`}><Icon size={19} className="shrink-0" /><span className={collapsed ? "lg:hidden" : ""}>{item.label}</span></Link>;
          })}
        </nav>
        <div className={`border-t border-[#E7E5E4] p-3 ${collapsed ? "lg:px-2" : ""}`}>
          <Link to="/configuracoes" className="mb-3 flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3 hover:bg-amber-100" data-testid="whatsapp-prepared-card">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#C5533B] text-white"><Wifi size={16} /></span>
            {!collapsed && <span className="min-w-0"><strong className="block text-xs text-amber-950">Canal WhatsApp</strong><small className="block truncate text-[11px] text-stone-500">Preparado para conectar</small></span>}
          </Link>
          <div className="flex items-center justify-between gap-2 rounded-xl bg-white/60 p-2.5">
            <div className={`flex min-w-0 items-center gap-2 ${collapsed ? "lg:hidden" : ""}`}><span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-stone-200 text-stone-600"><CircleUserRound size={17} /></span><span className="min-w-0"><strong className="block truncate text-xs">{displayUser.name}</strong><small className="block truncate text-[10px] text-stone-500">{displayUser.role === "admin" ? "Administrador" : "Atendente"}</small></span></div>
            <button onClick={() => logout.mutate()} className="rounded-lg p-2 text-stone-400 hover:bg-red-50 hover:text-red-600" data-testid="logout-button" aria-label="Sair"><LogOut size={17} /></button>
          </div>
        </div>
      </aside>

      <div className={`min-h-screen transition-[padding] duration-200 ${collapsed ? "lg:pl-[84px]" : "lg:pl-72"}`}>
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#E7E5E4] bg-white/90 px-4 backdrop-blur sm:px-8" data-testid="app-header">
          <div className="flex items-center gap-3"><button className="rounded-lg p-2 text-stone-500 hover:bg-stone-100 lg:hidden" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-button" aria-label="Abrir menu"><Menu size={20} /></button><button onClick={() => setCashOpen(true)} className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${isOpen ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-700"}`} data-testid="cash-status-button"><span className={`h-2 w-2 rounded-full ${isOpen ? "bg-emerald-500" : "bg-red-500"}`} />Caixa {isOpen ? "Aberto" : "Fechado"}<span className="hidden font-normal text-stone-500 sm:inline">• {day.data?.total_orders ?? 0} pedidos</span></button><Badge className="hidden border-emerald-200 bg-emerald-50 text-emerald-800 sm:inline-flex" data-testid="assistant-status-badge"><CookingPot size={13} className="mr-1" /> Operação ativa</Badge></div>
          <div className="flex items-center gap-3"><button className="relative rounded-lg p-2 text-stone-500 hover:bg-stone-100" data-testid="notifications-button" aria-label="Notificações"><Bell size={19} /><span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[#C5533B]" /></button><div className="hidden items-center gap-2 border-l border-stone-200 pl-3 sm:flex"><span className="text-right"><strong className="block text-xs">{displayUser.name}</strong><small className="block text-[10px] text-stone-500">{displayUser.role === "admin" ? "Administrador" : "Atendente"}</small></span><CircleUserRound size={21} className="text-stone-400" /></div></div>
        </header>
        <main className="mx-auto w-full max-w-[1440px] p-4 sm:p-6 lg:p-8" data-testid="main-content"><Outlet /></main>
      </div>

      <Dialog open={cashOpen} onOpenChange={setCashOpen}><DialogContent className="border-stone-200 bg-[#F9F8F6]" data-testid="cash-dialog"><DialogHeader><DialogTitle>{isOpen ? "Controle do Caixa do Dia" : "Abertura do Caixa do Dia"}</DialogTitle></DialogHeader>{isOpen ? <div className="space-y-4"><div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4"><strong className="block text-emerald-950">🟢 Caixa Aberto</strong><span className="text-sm text-emerald-800">{day.data?.total_orders ?? 0} pedidos registrados • {formatCurrency(day.data?.revenue ?? 0)}</span></div><p className="text-sm text-stone-600">Ao fechar, o período atual será arquivado e novas comandas ficam pausadas até a abertura.</p><DialogFooter><Button variant="outline" onClick={() => setCashOpen(false)} data-testid="cash-dialog-cancel-button">Voltar</Button><Button variant="destructive" onClick={() => dayMutation.mutate()} data-testid="cash-close-button">Fechar Caixa & Finalizar Dia</Button></DialogFooter></div> : <div className="space-y-4"><div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">Abra o caixa para liberar pedidos no balcão e acompanhar a operação.</div><div><Label htmlFor="initial-cash">Fundo de troco (R$)</Label><Input id="initial-cash" type="number" min="0" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} className="mt-1 bg-white" data-testid="initial-cash-input" /></div><DialogFooter><Button variant="outline" onClick={() => setCashOpen(false)} data-testid="cash-open-cancel-button">Cancelar</Button><Button onClick={() => dayMutation.mutate()} data-testid="cash-open-button">Abrir Caixa Agora</Button></DialogFooter></div>}</DialogContent></Dialog>
    </div>
  );
}