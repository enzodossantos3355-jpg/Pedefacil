import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CreditCard, Loader2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import { formatCurrency, type MercadoPagoStatus, type Order } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/** Never leave the modal spinning: the request is abandoned after `ms` with a clear message. */
function withTimeout<T>(p: Promise<T>, ms = 15000): Promise<T> {
  return Promise.race([p, new Promise<T>((_, reject) => setTimeout(() => reject(new Error("O servidor não respondeu em 15 segundos. Confira a internet e tente de novo.")), ms))]);
}
const NOT_ARRIVED_MS = 45000;

const WAITING = ["OPEN", "ON_TERMINAL", "PROCESSING", "CONFIRMATION_REQUIRED"];
const STATE_TEXT: Record<string, string> = { OPEN: "Cobrança enviada. Aguardando na maquininha...", ON_TERMINAL: "Cliente pagando na maquininha...", PROCESSING: "Processando pagamento...", CONFIRMATION_REQUIRED: "Confirmando pagamento...", CANCELED: "Cobrança cancelada.", ERROR: "Erro na maquininha. Tente de novo.", ABANDONED: "Cobrança abandonada na maquininha." };

/** "Cobrar na Point Smart 2": sends the order total to the terminal, waits (polling + webhook) and shows Pago. */
export default function PointCharge({ order }: { order: Order }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const mp = useQuery({ queryKey: ["mercadopago"], queryFn: () => apiGet<MercadoPagoStatus>("/payments/mercadopago") });
  const waiting = !!order.point_intent_id && WAITING.includes(order.point_state) && order.payment_status !== "pago";
  const [sentAt, setSentAt] = useState<number>(() => Date.now());
  const [now, setNow] = useState<number>(() => Date.now());
  const status = useQuery({ queryKey: ["point", order.order_id], queryFn: () => withTimeout(apiGet<Order>(`/pedidos/${order.order_id}/point-status`)), enabled: open && waiting, retry: false, refetchInterval: (q) => (q.state.error ? false : 3000) });
  useEffect(() => { if (status.error) toast.error((status.error as Error).message); }, [status.error]);
  useEffect(() => { if (!open) return; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, [open]);
  const live = status.data ?? order;
  const paid = live.payment_status === "pago";
  useEffect(() => { if (status.data && (status.data.payment_status !== order.payment_status || status.data.point_state !== order.point_state)) client.invalidateQueries({ queryKey: ["orders"] }); }, [status.data, order.payment_status, order.point_state, client]);
  const charge = useMutation({
    mutationFn: (type: string) => withTimeout(apiPost<Order>(`/pedidos/${order.order_id}/pagar-point`, { type })),
    onSuccess: (o) => { setSentAt(Date.now()); client.setQueryData(["point", order.order_id], o); client.invalidateQueries({ queryKey: ["orders"] }); },
    onError: (e: Error) => toast.error(e.message, { duration: 10000 }),
  });
  const [canForce, setCanForce] = useState(false);
  const cancel = useMutation({
    mutationFn: (force: boolean) => withTimeout(apiPost<Order>(`/pedidos/${order.order_id}/cancelar-point${force ? "?force=true" : ""}`)),
    onSuccess: (o, force) => { setCanForce(false); client.setQueryData(["point", order.order_id], o); client.removeQueries({ queryKey: ["point", order.order_id] }); client.invalidateQueries({ queryKey: ["orders"] }); toast.success(force ? "Pedido liberado no painel. Cancele também na tela da maquininha." : "Cobrança cancelada na maquininha."); },
    onError: (e: Error) => { if (e instanceof ApiError && (e.body as { detail?: { can_force?: boolean } })?.detail?.can_force) setCanForce(true); toast.error(e.message, { duration: 10000 }); },
  });
  const ForceRelease = () => (canForce ? <Button variant="outline" className="w-full" disabled={cancel.isPending} onClick={() => cancel.mutate(true)} data-testid="point-charge-force-release">Liberar no painel (já cancelei na maquininha)</Button> : null);
  if (!mp.data?.point_device_id || (order.payment_status === "pago" && !open)) return null;
  const isWaiting = !paid && !!live.point_intent_id && WAITING.includes(live.point_state) && !status.error;
  const notArrived = isWaiting && live.point_state === "OPEN" && now - sentAt > NOT_ARRIVED_MS;

  return (
    <>
      <button onClick={() => setOpen(true)} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors ${waiting ? "border-sky-300 bg-sky-50 text-sky-800" : "border-stone-300 text-stone-700 hover:bg-stone-50"}`} data-testid={`point-charge-open-${order.order_id}`}>
        <CreditCard size={11} /> {waiting ? "Aguardando na maquininha" : "Cobrar na Point Smart 2"}
      </button>
      <Dialog open={open} onOpenChange={setOpen}><DialogContent className="sm:max-w-sm" data-testid="point-charge-dialog">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><CreditCard size={18} className="text-[#C5533B]" /> Point Smart 2</DialogTitle></DialogHeader>
        <div className="rounded-2xl bg-stone-50 p-4 text-center"><small className="text-xs text-stone-500">Pedido #{order.order_id.slice(-6).toUpperCase()}</small><strong className="block font-heading text-3xl">{formatCurrency(order.total)}</strong></div>
        {paid ? (
          <div className="flex flex-col items-center gap-2 py-3 text-emerald-700" data-testid="point-charge-paid"><CheckCircle2 size={40} /><strong>Pago!</strong><span className="text-xs text-stone-500">Comprovante impresso na maquininha.</span></div>
        ) : status.error ? (
          <div className="space-y-2" data-testid="point-charge-error">
            <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700" data-testid="point-charge-error-message">{(status.error as Error).message}</p>
            <div className="grid grid-cols-2 gap-2"><Button variant="outline" onClick={() => status.refetch()} data-testid="point-charge-retry-status">Consultar de novo</Button><Button variant="outline" className="text-red-600" disabled={cancel.isPending} onClick={() => cancel.mutate(false)} data-testid="point-charge-cancel">Cancelar cobrança</Button></div>
            <ForceRelease />
          </div>
        ) : isWaiting ? (
          <div className="space-y-3" data-testid="point-charge-waiting">
            <p className="flex items-center justify-center gap-2 py-2 text-sm text-sky-800"><Loader2 size={16} className="animate-spin" /> {STATE_TEXT[live.point_state] ?? "Aguardando pagamento na maquininha..."}</p>
            {notArrived && <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-900" data-testid="point-charge-not-arrived">A cobrança ainda não apareceu na maquininha. Confira se a Point Smart 2 está ligada, com internet, logada na mesma conta e no modo integrado. Se precisar, cancele e cobre de novo.</p>}
            <Button variant="outline" className="w-full text-red-600 hover:bg-red-50" disabled={cancel.isPending} onClick={() => cancel.mutate(false)} data-testid="point-charge-cancel"><XCircle size={15} className="mr-1.5" /> Cancelar cobrança</Button>
            <ForceRelease />
          </div>
        ) : (
          <div className="space-y-2" data-testid="point-charge-start">
            {live.point_state && STATE_TEXT[live.point_state] && <p className="text-center text-xs text-stone-500" data-testid="point-charge-last-state">{STATE_TEXT[live.point_state]}</p>}
            <div className="grid grid-cols-2 gap-2">
              <Button disabled={charge.isPending} onClick={() => charge.mutate("credit_card")} data-testid="point-charge-credit">{charge.isPending ? <Loader2 size={15} className="animate-spin" /> : "Crédito"}</Button>
              <Button disabled={charge.isPending} onClick={() => charge.mutate("debit_card")} data-testid="point-charge-debit">Débito</Button>
            </div>
            <Button variant="outline" className="w-full" disabled={charge.isPending} onClick={() => charge.mutate("")} data-testid="point-charge-any">Cliente escolhe na maquininha</Button>
          </div>
        )}
      </DialogContent></Dialog>
    </>
  );
}
