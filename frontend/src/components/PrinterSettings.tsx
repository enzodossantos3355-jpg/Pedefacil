import { useState } from "react";
import { Bluetooth, Printer, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { testReceipt } from "@/lib/print";
import { bluetoothSupported, pairBluetoothPrinter, printerConfig, printThermal, savePrinterConfig, type PrinterMode } from "@/lib/thermal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const MODES: [PrinterMode, string, string, typeof Printer][] = [
  ["bluetooth", "Bluetooth direto", "Chrome no Android ou PC · impressoras BLE", Bluetooth],
  ["rawbt", "App RawBT (Android)", "Qualquer impressora Bluetooth, inclusive as comuns", Smartphone],
  ["browser", "Janela de impressão", "iPhone ou impressora do computador", Printer],
];

/** Thermal printer (58mm) of THIS device: saved in the browser, since each phone/PC has its own printer. */
export default function PrinterSettings({ storeName }: { storeName: string }) {
  const [cfg, setCfg] = useState(printerConfig);
  const [busy, setBusy] = useState(false);
  const update = (patch: Partial<ReturnType<typeof printerConfig>>) => { savePrinterConfig({ storeName, ...patch }); setCfg(printerConfig()); };
  const connect = async () => {
    setBusy(true);
    try { const name = await pairBluetoothPrinter(); update({ mode: "bluetooth", deviceName: name }); toast.success(`Conectado a ${name}`); }
    catch (e) { if ((e as Error).name !== "NotFoundError") toast.error((e as Error).message); }
    finally { setBusy(false); }
  };
  const test = async () => {
    savePrinterConfig({ storeName });
    if (cfg.mode === "browser") return toast.info("No modo janela, use o botão Imprimir dos pedidos.");
    setBusy(true);
    try { await printThermal(testReceipt()); if (cfg.mode === "bluetooth") toast.success("Teste enviado para a impressora!"); }
    catch (e) { toast.error((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <Card className="border-stone-200 shadow-sm" data-testid="printer-settings"><CardContent className="space-y-4 p-6">
      <div><h3 className="flex items-center gap-2 font-heading text-lg font-semibold"><Printer size={20} className="text-[#C5533B]" /> Impressora térmica 58mm</h3><p className="text-sm text-stone-500">Imprime comanda e ficha de entrega direto na impressora. A escolha vale para este aparelho.</p></div>
      <div className="grid gap-3 sm:grid-cols-3">
        {MODES.map(([id, title, desc, Icon]) => (
          <button key={id} type="button" onClick={() => update({ mode: id })} className={`rounded-xl border p-3 text-left transition-colors ${cfg.mode === id ? "border-[#C5533B] bg-[#fff7f4] ring-1 ring-[#C5533B]" : "border-stone-200 bg-white hover:bg-stone-50"}`} data-testid={`printer-mode-${id}`}>
            <strong className="flex items-center gap-1.5 text-sm"><Icon size={14} /> {title}</strong><span className="text-xs text-stone-500">{desc}</span>
          </button>
        ))}
      </div>
      {cfg.mode === "bluetooth" && (
        <div className="space-y-2 rounded-xl bg-stone-50 p-3 text-sm" data-testid="printer-bluetooth">
          {!bluetoothSupported() && <p className="text-xs text-amber-800" data-testid="printer-bluetooth-unsupported">Este navegador não tem Bluetooth. Use o Chrome no Android/PC ou o modo RawBT.</p>}
          <p data-testid="printer-device-name">{cfg.deviceName ? `🖨️ ${cfg.deviceName}` : "Nenhuma impressora conectada ainda."}</p>
          <Button type="button" size="sm" variant="outline" disabled={busy || !bluetoothSupported()} onClick={connect} data-testid="printer-connect-button"><Bluetooth size={14} className="mr-1" /> {cfg.deviceName ? "Trocar impressora" : "Conectar impressora"}</Button>
          <p className="text-[11px] text-stone-500">Ligue a impressora e toque em Conectar. Se ela não aparecer na lista, ela é Bluetooth clássico: use o modo RawBT.</p>
        </div>
      )}
      {cfg.mode === "rawbt" && <p className="rounded-xl bg-stone-50 p-3 text-xs text-stone-600" data-testid="printer-rawbt-help">Instale o app <strong>RawBT</strong> (Play Store), pareie a impressora nele e escolha-a como padrão. Ao imprimir, o PedeFácil envia a comanda para o RawBT.</p>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={cfg.autoPrint} disabled={cfg.mode === "browser"} onChange={(e) => update({ autoPrint: e.target.checked })} className="h-4 w-4 accent-[#C5533B]" data-testid="printer-autoprint-checkbox" /> Imprimir a comanda automaticamente quando um pedido for confirmado (status Novo)</label>
      <Button type="button" variant="outline" disabled={busy} onClick={test} data-testid="printer-test-button"><Printer size={14} className="mr-1" /> Imprimir teste</Button>
    </CardContent></Card>
  );
}
