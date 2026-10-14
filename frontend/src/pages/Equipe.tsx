import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { TeamMember } from "@/lib/types";
import { usePlan } from "@/lib/plans";
import { Trash2, UserPlus, Users } from "lucide-react";

export default function Equipe() {
  const client = useQueryClient();
  const { plan } = usePlan();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const team = useQuery({ queryKey: ["team"], queryFn: () => apiGet<TeamMember[]>("/auth/team") });
  const add = useMutation({ mutationFn: () => apiPost<TeamMember>("/auth/team", form), onSuccess: () => { setForm({ name: "", email: "", password: "" }); client.invalidateQueries({ queryKey: ["team"] }); toast.success("Atendente adicionado!"); }, onError: (e) => toast.error(e.message) });
  const remove = useMutation({ mutationFn: (id: string) => apiDelete<{ ok: boolean }>(`/auth/team/${id}`), onSuccess: () => client.invalidateQueries({ queryKey: ["team"] }), onError: (e) => toast.error(e.message) });
  const limit = plan?.limits.users;
  return <div className="max-w-3xl space-y-6" data-testid="team-page">
    <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Acessos da loja</p><h1 className="flex items-center gap-2 font-heading text-3xl font-semibold tracking-tight"><Users size={26} className="text-[#C5533B]" /> Equipe</h1><p className="mt-2 text-sm text-stone-500" data-testid="team-limit">{team.data?.length ?? 0} de {limit ?? "∞"} usuário(s) no plano {plan?.plan_name}. Atendentes veem todo o painel.</p></div>
    <Card className="border-stone-200 shadow-sm"><CardContent className="grid gap-3 p-5 sm:grid-cols-[1fr_1fr_160px_auto]"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Nome" data-testid="team-name-input" /><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="E-mail" data-testid="team-email-input" /><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Senha (6+)" data-testid="team-password-input" /><Button onClick={() => add.mutate()} disabled={!form.name || !form.email || form.password.length < 6 || add.isPending} className="gap-1.5 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="team-add-button"><UserPlus size={15} /> Adicionar</Button></CardContent></Card>
    <Card className="divide-y divide-stone-100 border-stone-200 shadow-sm">{(team.data ?? []).map((m) => <div key={m.id} className="flex items-center justify-between p-4" data-testid={`team-member-${m.id}`}><div><strong className="block text-sm">{m.name}</strong><small className="text-xs text-stone-500">{m.email}</small></div><div className="flex items-center gap-2"><Badge className="border-stone-200 bg-stone-50 text-stone-700">{m.role === "admin" ? "Administrador" : "Atendente"}</Badge>{m.role !== "admin" && <Button variant="ghost" size="icon-sm" onClick={() => remove.mutate(m.id)} aria-label="Remover" data-testid={`team-remove-${m.id}`}><Trash2 size={14} className="text-red-500" /></Button>}</div></div>)}</Card>
  </div>;
}
