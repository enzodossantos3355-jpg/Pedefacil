import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { PlanInfo } from "@/lib/types";

// Mirrors backend/lib/plans.py
export const FEATURE_LABELS: Record<string, string> = {
  pedidos: "Pedidos e cozinha", pdv: "PDV / balcão", cardapio: "Cardápio", clientes: "Clientes (CRM)", caixa: "Caixa do dia",
  whatsapp_ia: "WhatsApp com IA", pix_qr: "Pix QR Code com valor", zonas: "Zonas e taxas de entrega", motoboys: "Motoboys", mesas: "Mesas (opcional)",
  relatorios_ia: "Relatórios com IA", voz: "Pedido por voz", audio_whatsapp: "IA ouve áudios do WhatsApp", backup: "Backup e restauração", multi_atendentes: "Vários atendentes",
};
export const REQUIRED_PLAN: Record<string, "basico" | "padrao" | "pro"> = {
  pedidos: "basico", pdv: "basico", cardapio: "basico", clientes: "basico", caixa: "basico",
  whatsapp_ia: "padrao", pix_qr: "padrao", zonas: "padrao", motoboys: "padrao", mesas: "padrao",
  relatorios_ia: "pro", voz: "pro", audio_whatsapp: "pro", backup: "pro", multi_atendentes: "pro",
};
export const PLAN_NAMES: Record<string, string> = { basico: "Básico", padrao: "Padrão", pro: "Pro", trial: "Teste grátis", expired: "Expirado" };

export function usePlan() {
  const q = useQuery({ queryKey: ["billing", "me"], queryFn: () => apiGet<PlanInfo>("/billing/me"), retry: false, staleTime: 30_000 });
  const has = (feature: string) => !!q.data?.features.includes(feature);
  return { plan: q.data, isLoading: q.isLoading, has };
}
