// Static Pix (BR Code, Banco Central standard) — free, no fees. Each charge is locked to the order total.
import { QrCodePix } from "qrcode-pix";
import QRCode from "qrcode";

const ascii = (v) => String(v || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^A-Za-z0-9 .\-]/g, "").trim();

/** Normalizes the key the way banks expect it inside a BR Code. */
export function normalizeKey(key, type = "") {
  const raw = String(key || "").trim();
  const t = type.toLowerCase();
  if (t.includes("cpf") || t.includes("cnpj")) return raw.replace(/\D/g, "");
  if (t.includes("mail") || raw.includes("@")) return raw.toLowerCase();
  if (t.includes("celular") || t.includes("telefone")) {
    const d = raw.replace(/\D/g, "");
    return `+${d.startsWith("55") && d.length >= 12 ? d : `55${d}`}`;
  }
  return raw; // chave aleatória (EVP)
}

/**
 * gerarPix({ chave, tipoChave, nome, cidade, valor, idPedido })
 * → { copiaECola, qrCodeBase64, valor, txid }
 */
export async function gerarPix({ chave, tipoChave, nome, cidade, valor, idPedido }) {
  const key = normalizeKey(chave, tipoChave);
  if (!key) throw new Error("Chave Pix não configurada");
  const amount = Math.round(Number(valor) * 100) / 100; // two decimal places
  if (!(amount > 0)) throw new Error("Valor inválido");
  const txid = String(idPedido || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 25) || "***";
  const pix = QrCodePix({
    version: "01",
    key,
    name: ascii(nome).slice(0, 25) || "LOJA",
    city: ascii(cidade).toUpperCase().slice(0, 15) || "SAO PAULO",
    transactionId: txid,
    value: Number(amount.toFixed(2)),
  });
  const copiaECola = pix.payload();
  const qrCodeBase64 = await QRCode.toDataURL(copiaECola, { margin: 1, width: 360 });
  return { copiaECola, qrCodeBase64, valor: amount.toFixed(2), txid };
}
