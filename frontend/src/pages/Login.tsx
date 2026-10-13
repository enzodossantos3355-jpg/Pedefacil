import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UtensilsCrossed } from "lucide-react";
import type { User } from "@/lib/types";

export default function Login() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("admin@marmitahub.com");
  const [password, setPassword] = useState("marmita123");
  const login = useMutation({
    mutationFn: () => apiPost<User>("/auth/login", { email, password }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["auth", "me"] }); toast.success("Bem-vindo de volta ao Marmita Hub!"); navigate("/dashboard"); },
    onError: () => toast.error("E-mail ou senha inválidos."),
  });
  const submit = (event: FormEvent) => { event.preventDefault(); login.mutate(); };
  return <div className="grid min-h-screen bg-[#F9F8F6] lg:grid-cols-[1.05fr_0.95fr]" data-testid="login-page">
    <div className="relative hidden overflow-hidden bg-stone-900 lg:block" data-testid="login-image-panel">
      <img src="https://static.prod-images.emergentagent.com/jobs/3902cf64-244c-4c85-b121-742028aab87f/images/cac5a669c2b1c379a713fded35cbcba22131ce47bdb6e0457b5e90a0ddec9160.png" alt="Refeição brasileira em uma marmita" className="h-full w-full object-cover opacity-80" />
      <div className="absolute inset-0 bg-gradient-to-t from-stone-950/90 via-stone-900/20 to-transparent" />
      <div className="absolute bottom-14 left-12 right-12 text-white"><div className="mb-4 flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#C5533B]"><UtensilsCrossed size={22} /></span><strong className="font-heading text-2xl">Marmita Hub</strong></div><p className="max-w-lg text-sm leading-relaxed text-stone-300">Gestão operacional ágil, controle da cozinha, expedição rápida e atendimento organizado para o seu restaurante.</p></div>
    </div>
    <div className="flex items-center justify-center p-6 sm:p-10"><div className="w-full max-w-md" data-testid="login-form-container">
      <div className="mb-8 text-center sm:text-left"><div className="mb-6 flex items-center justify-center gap-2 sm:justify-start"><span className="grid h-9 w-9 place-items-center rounded-lg bg-[#C5533B] text-white"><UtensilsCrossed size={18} /></span><strong className="font-heading text-xl">Marmita Hub</strong></div><h1 className="font-heading text-3xl font-semibold tracking-tight text-stone-900">Acesse sua conta</h1><p className="mt-2 text-sm text-stone-500">Entre para acompanhar a operação da sua loja.</p></div>
      <form onSubmit={submit} className="space-y-5" data-testid="login-form"><div><Label htmlFor="login-email">E-mail</Label><Input id="login-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="exemplo@restaurante.com" className="mt-1.5 h-11 bg-white" data-testid="login-email-input" /></div><div><Label htmlFor="login-password">Senha</Label><Input id="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" className="mt-1.5 h-11 bg-white" data-testid="login-password-input" /></div><Button type="submit" disabled={login.isPending} className="h-11 w-full bg-[#C5533B] font-semibold hover:bg-[#A6432E]" data-testid="login-submit-button">{login.isPending ? "Entrando..." : "Entrar no Sistema"}</Button></form>
      <div className="mt-6 rounded-xl border border-stone-200 bg-white p-4 text-xs text-stone-600" data-testid="demo-login-hint"><strong className="block text-stone-900">Acesso de demonstração</strong><span>admin@marmitahub.com · marmita123</span><br /><span>atendente@marmitahub.com · marmita123</span></div>
      <p className="mt-6 text-center text-sm text-stone-500">Ainda não tem conta? <Link to="/register" className="font-semibold text-[#C5533B] hover:underline" data-testid="register-link">Cadastre-se grátis</Link></p>
    </div></div>
  </div>;
}