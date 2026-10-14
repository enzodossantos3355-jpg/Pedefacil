import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { PlanOption } from "@/lib/types";
import { formatCurrency } from "@/lib/types";
import { FEATURE_LABELS, usePlan } from "@/lib/plans";
import { Check, CheckCircle2, Clock, Crown, Lock, XCircle } from "lucide-react";

const ALL = Object.keys(FEATURE_LABELS);
const TAGLINE: Record<string, string> = { basico: "Para começar a organizar o balcão", padrao: "WhatsApp com IA vendendo por você", pro: "Tudo liberado para crescer" };

export default function Planos() {
  const { plan } = usePlan();
  const plans = useQuery({ queryKey: ["billing", "plans"], queryFn: () => apiGet<PlanOption[]>("/billing/plans") });
  const checkout = useMutation({
    mutationFn: (key: string) => apiPost<{ checkout_url: string }>("/billing/checkout", { plan: key, origin_url: window.location.origin }),
    onSuccess: (d) => { window.location.href = d.checkout_url; },
    onError: (e) => toast.error(e.message),
  });
  return <div className="space-y-7" data-testid="plans-page">
    <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Assinatura mensal</p><h1 className="font-heading text-3xl font-semibold tracking-tight">Planos PedeFácil</h1>
      {plan && <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-stone-600" data-testid="current-plan-info">Plano atual: <Badge className={plan.expired ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-800"}>{plan.plan_name}</Badge>{plan.trial_days_left != null && <span className="flex items-center gap-1 text-amber-700"><Clock size={14} /> {plan.trial_days_left} dia(s) restantes de teste</span>}{plan.expired && <span className="text-red-700">Escolha um plano para voltar a usar o sistema.</span>}</p>}
    </div>
    <div className="grid gap-5 lg:grid-cols-3">
      {(plans.data ?? []).map((p) => { const current = plan?.plan === p.key; const featured = p.key === "padrao"; return <Card key={p.key} className={`relative overflow-hidden shadow-sm ${featured ? "border-[#C5533B] ring-1 ring-[#C5533B]" : "border-stone-200"}`} data-testid={`plan-card-${p.key}`}>
        {featured && <div className="bg-[#C5533B] py-1.5 text-center text-[11px] font-bold uppercase tracking-[0.16em] text-white">Mais escolhido</div>}
        <CardContent className="space-y-5 p-6">
          <div><h2 className="flex items-center gap-2 font-heading text-xl font-semibold">{p.key === "pro" && <Crown size={18} className="text-amber-500" />}{p.name}</h2><p className="text-sm text-stone-500">{TAGLINE[p.key]}</p></div>
          <div><strong className="font-heading text-4xl" data-testid={`plan-price-${p.key}`}>{formatCurrency(p.price)}</strong><span className="text-sm text-stone-500">/mês</span></div>
          <ul className="space-y-2 text-sm">{ALL.map((f) => { const on = p.features.includes(f); return <li key={f} className={`flex items-center gap-2 ${on ? "text-stone-800" : "text-stone-400"}`}>{on ? <Check size={15} className="text-emerald-600" /> : <Lock size={13} />}{FEATURE_LABELS[f]}</li>; })}<li className="flex items-center gap-2 text-stone-800"><Check size={15} className="text-emerald-600" />Até {p.limits.users} usuário(s)</li></ul>
          <Button onClick={() => checkout.mutate(p.key)} disabled={current || checkout.isPending} className={`w-full ${featured ? "bg-[#C5533B] hover:bg-[#A6432E]" : ""}`} variant={featured ? "default" : "outline"} data-testid={`subscribe-${p.key}-button`}>{current ? "Plano atual" : checkout.isPending && checkout.variables === p.key ? "Abrindo pagamento..." : `Assinar ${p.name}`}</Button>
        </CardContent>
      </Card>; })}
    </div>
    <p className="text-xs text-stone-500">Pagamento mensal com cartão via Stripe. O teste grátis de 7 dias inclui só as funções do Básico, com limite de 20 pedidos, 8 produtos e 20 clientes.</p>
  </div>;
}

export function PaymentResult() {
  const client = useQueryClient();
  const location = useLocation();
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const cancelled = location.pathname.endsWith("/cancel");
  const [tries, setTries] = useState(0);
  const status = useQuery({ queryKey: ["payment", sessionId, tries], queryFn: () => apiGet<{ payment_status: string; status: string }>(`/payments/status/${sessionId}`), enabled: !!sessionId && !cancelled });
  const paid = status.data?.payment_status === "paid";
  useEffect(() => {
    if (paid) { client.invalidateQueries({ queryKey: ["billing"] }); return; }
    if (!cancelled && sessionId && status.data && tries < 15) { const t = setTimeout(() => setTries((n) => n + 1), 2000); return () => clearTimeout(t); }
  }, [paid, status.data, tries, cancelled, sessionId, client]);
  return <div className="mx-auto max-w-lg py-12" data-testid="payment-result-page"><Card className="border-stone-200 shadow-sm"><CardContent className="space-y-4 p-8 text-center">
    {cancelled ? <><XCircle size={48} className="mx-auto text-stone-400" /><h1 className="font-heading text-2xl font-semibold" data-testid="payment-result-title">Pagamento cancelado</h1><p className="text-sm text-stone-600">Nenhuma cobrança foi feita. Você pode escolher um plano quando quiser.</p></>
      : paid ? <><CheckCircle2 size={48} className="mx-auto text-emerald-600" /><h1 className="font-heading text-2xl font-semibold" data-testid="payment-result-title">Plano ativado!</h1><p className="text-sm text-stone-600">Pagamento confirmado. As novas funções já estão liberadas.</p></>
      : <><Clock size={48} className="mx-auto animate-pulse text-amber-500" /><h1 className="font-heading text-2xl font-semibold" data-testid="payment-result-title">Confirmando pagamento...</h1><p className="text-sm text-stone-600">Isso leva alguns segundos.</p></>}
    <Link to={paid ? "/dashboard" : "/planos"} className={buttonVariants({ className: "bg-[#C5533B] hover:bg-[#A6432E]" })} data-testid="payment-result-continue">{paid ? "Ir para o painel" : "Ver planos"}</Link>
  </CardContent></Card></div>;
}
