import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { DayStatus } from "@/lib/types";
import { LockKeyhole, LockKeyholeOpen } from "lucide-react";

/** Orders, PDV, WhatsApp AI and attendance only operate while the caixa do dia is open. */
export default function DayGate({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [cash, setCash] = useState("0");
  const day = useQuery({ queryKey: ["day", "status"], queryFn: () => apiGet<DayStatus>("/day/status"), refetchInterval: 15000 });
  const open = useMutation({
    mutationFn: () => apiPost<DayStatus>("/day/open", { initial_cash: Number(cash) || 0 }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["day", "status"] }); toast.success("Caixa do dia aberto com sucesso!"); },
    onError: () => toast.error("Não foi possível abrir o caixa."),
  });
  if (day.data?.is_open !== false) return <>{children}</>;
  return (
    <div className="mx-auto max-w-xl py-10" data-testid="day-closed-gate">
      <Card className="border-stone-200 shadow-sm">
        <CardContent className="space-y-5 p-8">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-[#fceee6] text-[#C5533B]"><LockKeyhole size={26} /></span>
          <div>
            <h1 className="font-heading text-2xl font-semibold tracking-tight" data-testid="day-closed-title">Caixa fechado</h1>
            <p className="mt-2 text-sm text-stone-600">Pedidos, PDV, IA do WhatsApp e atendimento ficam pausados até o caixa do dia ser aberto. Cardápio, clientes e configurações continuam disponíveis.</p>
          </div>
          <div className="flex items-end gap-3">
            <div className="flex-1"><Label htmlFor="gate-initial-cash">Troco inicial (R$)</Label><Input id="gate-initial-cash" type="number" min={0} step="0.5" value={cash} onChange={(e) => setCash(e.target.value)} className="mt-1.5" data-testid="day-gate-initial-cash-input" /></div>
            <Button onClick={() => open.mutate()} disabled={open.isPending} className="gap-2 bg-[#C5533B] hover:bg-[#A6432E]" data-testid="day-gate-open-button"><LockKeyholeOpen size={16} /> {open.isPending ? "Abrindo..." : "Abrir Caixa"}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
