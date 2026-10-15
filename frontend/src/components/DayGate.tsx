import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { DayStatus } from "@/lib/types";
import { LockKeyhole, LockKeyholeOpen } from "lucide-react";

/** Orders, PDV, WhatsApp AI and attendance only operate while the caixa do dia is open. */
export default function DayGate({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const day = useQuery({ queryKey: ["day", "status"], queryFn: () => apiGet<DayStatus>("/day/status"), refetchInterval: 15000 });
  const open = useMutation({
    mutationFn: () => apiPost<DayStatus>("/day/open", { initial_cash: 0 }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["day", "status"] }); toast.success("Novo dia iniciado!"); },
    onError: () => toast.error("Não foi possível abrir o caixa."),
  });
  if (day.data?.is_open !== false) return <>{children}</>;
  return (
    <div className="mx-auto max-w-xl py-10" data-testid="day-closed-gate">
      <Card className="border-stone-200 shadow-sm">
        <CardContent className="space-y-5 p-8">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-[#fceee6] text-[#C5533B]"><LockKeyhole size={26} /></span>
          <div>
            <h1 className="font-heading text-2xl font-semibold tracking-tight" data-testid="day-closed-title">Dia fechado</h1>
            <p className="mt-2 text-sm text-stone-600">Com o dia fechado não é possível criar pedidos, e a IA e o atendimento do WhatsApp ficam desativados até você começar um novo dia. Cardápio, clientes e configurações continuam disponíveis.</p>
          </div>
          <div className="flex items-end gap-3">
            
            <Button onClick={() => open.mutate()} disabled={open.isPending} className="gap-2 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="day-gate-open-button"><LockKeyholeOpen size={16} /> {open.isPending ? "Iniciando..." : "Começar novo dia"}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
