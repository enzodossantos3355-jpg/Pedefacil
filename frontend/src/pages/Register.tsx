import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { User } from "@/lib/types";

export default function Register() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "admin" });
  const register = useMutation({ mutationFn: () => apiPost<User>("/auth/register", form), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["auth", "me"] }); toast.success("Conta criada! Bem-vindo ao Marmita Hub."); navigate("/dashboard"); }, onError: () => toast.error("Não foi possível criar a conta. Verifique os dados.") });
  const submit = (event: FormEvent) => { event.preventDefault(); register.mutate(); };
  return <div className="flex min-h-screen items-center justify-center bg-[#F9F8F6] p-6" data-testid="register-page"><div className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-7 shadow-sm sm:p-9"><div className="mb-8"><div className="mb-5 flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-lg bg-[#C5533B] text-white">🍱</span><strong className="font-heading text-xl">Marmita Hub</strong></div><h1 className="font-heading text-3xl font-semibold">Crie sua conta</h1><p className="mt-2 text-sm text-stone-500">Comece a organizar pedidos, cardápio e atendimento.</p></div><form onSubmit={submit} className="space-y-4" data-testid="register-form"><div><Label htmlFor="register-name">Nome</Label><Input id="register-name" required minLength={2} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className="mt-1.5 bg-white" data-testid="register-name-input" /></div><div><Label htmlFor="register-email">E-mail</Label><Input id="register-email" required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} className="mt-1.5 bg-white" data-testid="register-email-input" /></div><div><Label htmlFor="register-password">Senha</Label><Input id="register-password" required minLength={6} type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} className="mt-1.5 bg-white" data-testid="register-password-input" /></div><Button type="submit" disabled={register.isPending} className="mt-2 h-11 w-full bg-[#C5533B] hover:bg-[#A6432E]" data-testid="register-submit-button">{register.isPending ? "Criando..." : "Criar Conta"}</Button></form><p className="mt-6 text-center text-sm text-stone-500">Já possui uma conta? <Link to="/login" className="font-semibold text-[#C5533B] hover:underline" data-testid="back-login-link">Entrar</Link></p></div></div>;
}