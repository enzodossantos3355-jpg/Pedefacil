import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, ShieldCheck, Zap } from "lucide-react";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPut } from "@/lib/api";
import { CreditCard } from "lucide-react";
import type { MercadoPagoStatus, PointDevice, StoreSettings } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Choice between the old static Pix (receipt) and "Pix Automático" via the store's own Mercado Pago account. */
export default function MercadoPagoPanel({ form, set }: { form: StoreSettings; set: (p: Partial<StoreSettings>) => void }) {
  const client = useQueryClient();
  const [token, setToken] = useState("");
  const mp = useQuery({ queryKey: ["mercadopago"], queryFn: () => apiGet<MercadoPagoStatus>("/payments/mercadopago") });
  const save = useMutation({
    mutationFn: () => apiPut<MercadoPagoStatus>("/payments/mercadopago", { access_token: token }),
    onSuccess: (d) => { client.setQueryData(["mercadopago"], d); setToken(""); set({ pix_provider: "mercadopago" }); toast.success("Mercado Pago conectado! Clique em Salvar configurações para ativar."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: () => apiDelete<MercadoPagoStatus>("/payments/mercadopago"),
    onSuccess: (d) => { client.setQueryData(["mercadopago"], d); set({ pix_provider: "manual" }); toast.success("Mercado Pago desconectado."); },
  });
  const [findDevices, setFindDevices] = useState(false);
  const devices = useQuery({ queryKey: ["point-devices"], queryFn: () => apiGet<PointDevice[]>("/payments/point/devices"), enabled: findDevices && !!mp.data?.configured, retry: false });
  const choose = useMutation({ mutationFn: (id: string) => apiPut<MercadoPagoStatus>("/payments/point/device", { device_id: id }), onSuccess: (d) => { client.setQueryData(["mercadopago"], d); toast.success("Point Smart 2 configurada no modo integrado!"); }, onError: (e: Error) => toast.error(e.message) });
  const webhook = `${window.location.origin}/api/webhooks/mercadopago?store=${mp.data?.store_id ?? ""}`;
  const options = [
    ["manual", "Pix Manual (atual)", "Grátis. Envia o código Pix e a IA confere o comprovante (favorecido, valor e se não é agendado).", ShieldCheck],
    ["mercadopago", "Pix Automático (Mercado Pago)", "Com taxa do Mercado Pago. O pagamento é detectado sozinho, sem comprovante.", Zap],
  ] as const;

  return (
    <div className="space-y-3" data-testid="pix-provider-section">
      <div className="grid gap-3 sm:grid-cols-2">
        {options.map(([id, title, desc, Icon]) => (
          <button key={id} type="button" onClick={() => (id === "mercadopago" && !mp.data?.configured ? toast.info("Cole e salve seu Access Token do Mercado Pago abaixo primeiro.") : set({ pix_provider: id }))}
            className={`rounded-xl border p-4 text-left transition-colors ${form.pix_provider === id ? "border-[#C5533B] bg-[#fff7f4] ring-1 ring-[#C5533B]" : "border-stone-200 bg-white hover:bg-stone-50"}`} data-testid={`pix-provider-${id}`}>
            <strong className="flex items-center gap-1.5 text-sm"><Icon size={14} /> {title}</strong><span className="text-xs text-stone-500">{desc}</span>
          </button>
        ))}
      </div>
      <div className="space-y-2 rounded-xl border border-stone-200 bg-white p-4" data-testid="mercadopago-panel">
        {mp.data?.configured ? (
          <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm" data-testid="mercadopago-status">✅ Conta Mercado Pago conectada{mp.data.account ? `: ${mp.data.account}` : ""}</span><Button type="button" variant="outline" size="sm" onClick={() => remove.mutate()} data-testid="mercadopago-remove-button">Desconectar</Button></div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
            <div><Label htmlFor="mp-token">Access Token do Mercado Pago</Label><Input id="mp-token" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="APP_USR-..." className="mt-1" data-testid="mercadopago-token-input" /></div>
            <Button type="button" disabled={token.trim().length < 20 || save.isPending} onClick={() => save.mutate()} data-testid="mercadopago-save-button">{save.isPending ? "Verificando..." : "Salvar token"}</Button>
          </div>
        )}
        <p className="text-[11px] text-stone-500">Onde achar: Mercado Pago → Suas integrações → sua aplicação → Credenciais de produção → Access Token. O token fica guardado só no servidor.</p>
        {mp.data?.configured && <div className="text-[11px] text-stone-600">Para confirmação instantânea, cadastre este Webhook (evento "Order") no painel do Mercado Pago:
          <button type="button" onClick={() => { navigator.clipboard.writeText(webhook); toast.success("URL copiada!"); }} className="mt-1 flex w-full items-center gap-1.5 truncate rounded-md bg-stone-100 px-2 py-1 font-mono text-[11px] hover:bg-stone-200" data-testid="mercadopago-webhook-copy"><Copy size={11} />{webhook}</button>
          Sem o webhook, o painel confere os pagamentos a cada 20 segundos.</div>}
        {mp.data?.configured && <div className="space-y-2 border-t border-stone-100 pt-3" data-testid="point-section">
          <strong className="flex items-center gap-1.5 text-sm"><CreditCard size={14} /> Maquininha Point Smart 2</strong>
          {mp.data.point_device_id ? <p className="text-xs text-stone-600" data-testid="point-device-current">✅ Em uso: <span className="font-mono">{mp.data.point_device_id}</span></p> : <p className="text-xs text-stone-500">Ligue a maquininha logada na mesma conta do Mercado Pago e escolha ela aqui.</p>}
          <Button type="button" size="sm" variant="outline" onClick={() => { setFindDevices(true); devices.refetch(); }} disabled={devices.isFetching} data-testid="point-find-devices">{devices.isFetching ? "Buscando..." : "Buscar maquininhas"}</Button>
          {devices.error && <p className="text-xs text-red-600" data-testid="point-devices-error">{(devices.error as Error).message}</p>}
          {devices.data?.length === 0 && <p className="text-xs text-stone-500" data-testid="point-devices-empty">Nenhuma maquininha encontrada nessa conta.</p>}
          {devices.data?.map((d) => <div key={d.id} className="flex items-center justify-between rounded-lg bg-stone-50 px-3 py-2 text-xs"><span className="font-mono">{d.id} <small className="text-stone-400">({d.operating_mode || "?"})</small></span><Button type="button" size="sm" disabled={choose.isPending || mp.data?.point_device_id === d.id} onClick={() => choose.mutate(d.id)} data-testid={`point-use-${d.id}`}>{mp.data?.point_device_id === d.id ? "Em uso" : "Usar esta"}</Button></div>)}
          <p className="text-[11px] text-stone-500">No painel do Mercado Pago, ative também o Webhook de "Integrações Point" com a mesma URL acima para o "Pago" aparecer na hora.</p>
        </div>}
      </div>
    </div>
  );
}
