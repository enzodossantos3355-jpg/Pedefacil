/**
 * Direct printing to 58mm thermal printers (ESC/POS).
 * - "bluetooth": Web Bluetooth (Chrome on Android / PC) — BLE printers.
 * - "rawbt": RawBT app on Android — works with classic Bluetooth printers too.
 * - "browser": the old print window (iPhone, or no thermal printer).
 * The printer belongs to the device (phone/PC), so the choice is saved in this browser.
 */

export type PrinterMode = "browser" | "bluetooth" | "rawbt";
export const COLS = 32; // 58mm, font A

const KEY = "pf_printer";
type Saved = { mode: PrinterMode; storeName: string; autoPrint: boolean; deviceName: string };
export function printerConfig(): Saved {
  try {
    return { mode: "browser", storeName: "", autoPrint: false, deviceName: "", ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { mode: "browser", storeName: "", autoPrint: false, deviceName: "" };
  }
}
export function savePrinterConfig(patch: Partial<Saved>) {
  localStorage.setItem(KEY, JSON.stringify({ ...printerConfig(), ...patch }));
}
export const bluetoothSupported = () => typeof navigator !== "undefined" && "bluetooth" in navigator;

// ---------- ESC/POS builder ----------
const ESC = 0x1b, GS = 0x1d;
/** Cheap printers rarely have the right code page: print plain ASCII (ã→a, ç→c), drop emojis. */
export const ascii = (s: string) => s.replace(/[\u00a0\u202f]/g, " ").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^\x20-\x7e\n]/g, "");

export class Receipt {
  private bytes: number[] = [ESC, 0x40]; // init
  private push(...b: number[]) { this.bytes.push(...b); return this; }
  text(s: string) { for (const ch of ascii(s)) this.bytes.push(ch.charCodeAt(0)); return this; }
  line(s = "") { return this.text(s).push(0x0a); }
  center(on = true) { return this.push(ESC, 0x61, on ? 1 : 0); }
  bold(on = true) { return this.push(ESC, 0x45, on ? 1 : 0); }
  big(on = true) { return this.push(GS, 0x21, on ? 0x11 : 0x00); }
  rule() { return this.line("-".repeat(COLS)); }
  /** "2x Marmita ........ R$ 40,00" wrapped to 32 columns. */
  row(left: string, right: string) {
    const l = ascii(left), r = ascii(right);
    const room = COLS - r.length - 1;
    const words = wrap(l, Math.max(8, room));
    words.forEach((w, i) => this.line(i === words.length - 1 ? w.padEnd(COLS - r.length) + r : w));
    return this;
  }
  wrapped(s: string) { wrap(ascii(s), COLS).forEach((w) => this.line(w)); return this; }
  feedAndCut() { return this.push(0x0a, 0x0a, 0x0a, GS, 0x56, 0x01); }
  build() { return new Uint8Array(this.bytes); }
}

function wrap(s: string, width: number): string[] {
  const out: string[] = [];
  for (const para of s.split("\n")) {
    let cur = "";
    for (const word of para.split(" ")) {
      if ((cur + " " + word).trim().length > width) { if (cur) out.push(cur); cur = word.length > width ? word.slice(0, width) : word; }
      else cur = (cur + " " + word).trim();
    }
    out.push(cur);
  }
  return out;
}

// ---------- Bluetooth (BLE) ----------
// Service UUIDs used by most BLE thermal printers (generic Chinese 58mm, Goojprt, MTP, Xprinter, etc.)
const SERVICES = [
  "000018f0-0000-1000-8000-00805f9b34fb", "e7810a71-73ae-499d-8c15-faa9aef0c3f2", "49535343-fe7d-4ae5-8fa9-9fafd205e455",
  "0000ff00-0000-1000-8000-00805f9b34fb", "0000ffe0-0000-1000-8000-00805f9b34fb", "0000fee7-0000-1000-8000-00805f9b34fb",
  "0000ae30-0000-1000-8000-00805f9b34fb",
];
/* eslint-disable @typescript-eslint/no-explicit-any */
let device: any = null;
let characteristic: any = null;

async function findWritable(server: any): Promise<any> {
  const services = await server.getPrimaryServices();
  for (const svc of services) {
    for (const ch of await svc.getCharacteristics()) {
      if (ch.properties.writeWithoutResponse || ch.properties.write) return ch;
    }
  }
  throw new Error("Essa impressora não tem um canal de impressão Bluetooth compatível. Use o modo RawBT.");
}

async function connect(dev: any) {
  const server = dev.gatt.connected ? dev.gatt : await dev.gatt.connect();
  characteristic = await findWritable(server);
  device = dev;
  savePrinterConfig({ deviceName: dev.name || "Impressora Bluetooth" });
  return dev.name || "Impressora Bluetooth";
}

/** Opens Chrome's Bluetooth picker (must be called from a click). */
export async function pairBluetoothPrinter(): Promise<string> {
  if (!bluetoothSupported()) throw new Error("Este navegador não tem Bluetooth. Use o Chrome no Android ou no computador (no iPhone não funciona).");
  const dev = await (navigator as any).bluetooth.requestDevice({ acceptAllDevices: true, optionalServices: SERVICES });
  return connect(dev);
}

async function ensureBluetooth() {
  if (characteristic && device?.gatt?.connected) return;
  if (device) { await connect(device); return; }
  const known = (navigator as any).bluetooth?.getDevices ? await (navigator as any).bluetooth.getDevices() : [];
  if (known.length) { await connect(known[0]); return; }
  throw new Error("Impressora Bluetooth não conectada. Vá em Configurações → Impressora e toque em Conectar.");
}

async function writeBluetooth(data: Uint8Array) {
  await ensureBluetooth();
  for (let i = 0; i < data.length; i += 100) { // BLE packets are small: send in chunks
    const chunk = data.slice(i, i + 100);
    if (characteristic.properties.writeWithoutResponse) await characteristic.writeValueWithoutResponse(chunk);
    else await characteristic.writeValue(chunk);
    await new Promise((r) => setTimeout(r, 20));
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ---------- RawBT (Android app) ----------
function sendRawBT(data: Uint8Array) {
  let bin = "";
  data.forEach((b) => (bin += String.fromCharCode(b)));
  window.location.href = `rawbt:base64,${btoa(bin)}`;
}

/** Sends a receipt to the configured thermal printer. Throws with a readable message on failure. */
export async function printThermal(r: Receipt) {
  const data = r.build();
  const { mode } = printerConfig();
  if (mode === "rawbt") return sendRawBT(data);
  return writeBluetooth(data);
}
