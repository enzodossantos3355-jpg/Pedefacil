import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FEATURE_LABELS, PLAN_NAMES, REQUIRED_PLAN, usePlan } from "@/lib/plans";
import { Lock, Sparkles } from "lucide-react";

/** Renders children when the plan includes the feature; otherwise a lock with "Disponível no plano X" + upgrade. */
export default function FeatureGate({ feature, children, compact = false }: { feature: string; children: ReactNode; compact?: boolean }) {
  const { has, isLoading } = usePlan();
  if (isLoading) return null; // never mount a locked page's queries before the plan is known
  if (has(feature)) return <>{children}</>;
  return <LockedFeature feature={feature} compact={compact} />;
}

export function LockedFeature({ feature, compact = false }: { feature: string; compact?: boolean }) {
  const navigate = useNavigate();
  const plan = PLAN_NAMES[REQUIRED_PLAN[feature] ?? "pro"];
  if (compact) {
    return <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed border-amber-300 bg-amber-50/60 p-4" data-testid={`locked-${feature}`}>
      <span className="flex items-center gap-2 text-sm text-amber-900"><Lock size={15} /> <strong>{FEATURE_LABELS[feature] ?? feature}</strong> · Disponível no plano {plan}</span>
      <Button size="sm" onClick={() => navigate("/planos")} className="gap-1.5 bg-[#C5533B] hover:bg-[#A6432E]" data-testid={`upgrade-${feature}-button`}><Sparkles size={14} /> Fazer upgrade</Button>
    </div>;
  }
  return <div className="mx-auto max-w-xl py-10" data-testid={`locked-${feature}`}>
    <Card className="border-stone-200 shadow-sm"><CardContent className="space-y-5 p-8">
      <span className="grid h-14 w-14 place-items-center rounded-2xl bg-amber-50 text-amber-700"><Lock size={26} /></span>
      <div><h1 className="font-heading text-2xl font-semibold tracking-tight">{FEATURE_LABELS[feature] ?? feature}</h1><p className="mt-2 text-sm text-stone-600">Disponível no plano <strong>{plan}</strong>. Faça upgrade para liberar esta função na sua loja.</p></div>
      <Button onClick={() => navigate("/planos")} className="gap-2 bg-[#C5533B] hover:bg-[#A6432E]" data-testid={`upgrade-${feature}-button`}><Sparkles size={16} /> Fazer upgrade</Button>
    </CardContent></Card>
  </div>;
}
