// WhatsApp bridge (Baileys). Exposes a small internal HTTP API on WHATSAPP_PORT and forwards
// incoming messages to the FastAPI backend at BACKEND_URL/api/whatsapp/incoming.
import express from "express";
import pino from "pino";
import QRCode from "qrcode";
import { generateWAMessageFromContent, proto } from "@whiskeysockets/baileys";
import makeWASocket, { Browsers, DisconnectReason, fetchLatestBaileysVersion, useMultiFileAuthState } from "@whiskeysockets/baileys";

const PORT = Number(process.env.WHATSAPP_PORT || 8002);
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8001";
const TOKEN = process.env.WHATSAPP_INTERNAL_TOKEN || "";
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || "./auth";
const logger = pino({ level: "warn" });

let sock = null;
let state = { status: "disconnected", is_connected: false, qr_code: null, pairing_code: null, phone: null, last_error: null };
let starting = false;
let manualStop = false;

const digits = (value) => String(value || "").replace(/\D/g, "");
const jidToPhone = (jid) => digits(String(jid || "").split("@")[0].split(":")[0]);

async function start({ pairingPhone } = {}) {
  if (starting) return;
  starting = true;
  manualStop = false;
  try {
    const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }));
    sock = makeWASocket({ auth, version, logger, browser: Browsers.ubuntu("Chrome"), markOnlineOnConnect: false });
    state = { ...state, status: "connecting", last_error: null, pairing_code: null };
    sock.ev.on("creds.update", saveCreds);

    if (pairingPhone && !auth.creds.registered) {
      await new Promise((r) => setTimeout(r, 2500));
      const code = await sock.requestPairingCode(digits(pairingPhone));
      state = { ...state, status: "pairing_code", pairing_code: code };
    }

    sock.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;
      if (qr && !pairingPhone) state = { ...state, status: "qr_ready", qr_code: await QRCode.toDataURL(qr) };
      if (connection === "open") {
        state = { ...state, status: "connected", is_connected: true, qr_code: null, pairing_code: null, phone: jidToPhone(sock.user?.id) };
      }
      if (connection === "close") {
        const code = lastDisconnect?.error?.output?.statusCode;
        state = { ...state, status: "disconnected", is_connected: false, last_error: lastDisconnect?.error?.message || null };
        sock = null;
        if (code === DisconnectReason.loggedOut) {
          const fs = await import("node:fs");
          fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        } else if (!manualStop) {
          setTimeout(() => start().catch(() => {}), 3000); // automatic reconnect
        }
      }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      if (type !== "notify") return;
      for (const msg of messages) {
        if (!msg.message || msg.key.fromMe) continue;
        const remote = msg.key.remoteJid || "";
        if (remote.endsWith("@g.us") || remote === "status@broadcast") continue;
        const phoneJid = msg.key.remoteJidAlt || msg.key.senderPn || remote;
        const m = msg.message;
        const loc = m.locationMessage || m.liveLocationMessage;
        const text = m.conversation || m.extendedTextMessage?.text || m.imageMessage?.caption || (loc ? "[localização enviada]" : "");
        if (!text) continue;
        try {
          await fetch(`${BACKEND_URL}/api/whatsapp/incoming`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "x-internal-token": TOKEN },
            body: JSON.stringify({ jid: remote, phone: jidToPhone(phoneJid), name: msg.pushName || "", text, latitude: loc?.degreesLatitude ?? null, longitude: loc?.degreesLongitude ?? null }),
          });
        } catch (err) {
          logger.error({ err }, "falha ao repassar mensagem");
        }
      }
    });
  } finally {
    starting = false;
  }
}

async function sendText(to, text) {
  if (!sock || !state.is_connected) throw new Error("WhatsApp não conectado");
  const jid = to.includes("@") ? to : `${digits(to)}@s.whatsapp.net`;
  await sock.sendMessage(jid, { text });
  return jid;
}

async function sendPix(to, text, pixKey) {
  const jid = await sendText(to, text);
  try {
    // Native "Copiar chave Pix" button (cta_copy). Some clients don't render it, so the key also goes as plain text.
    const content = proto.Message.fromObject({
      interactiveMessage: {
        body: { text: "Toque no botão abaixo para copiar a chave Pix:" },
        nativeFlowMessage: { buttons: [{ name: "cta_copy", buttonParamsJson: JSON.stringify({ display_text: "Copiar chave Pix", copy_code: pixKey }) }] },
      },
    });
    const wa = generateWAMessageFromContent(jid, { viewOnceMessage: { message: content } }, { userJid: sock.user.id });
    await sock.relayMessage(jid, wa.message, { messageId: wa.key.id });
  } catch (err) {
    logger.warn({ err }, "botão Pix indisponível");
  }
  await sock.sendMessage(jid, { text: pixKey });
}

const app = express();
app.use(express.json());
app.use((req, res, next) => (TOKEN && req.get("x-internal-token") !== TOKEN ? res.status(401).json({ detail: "unauthorized" }) : next()));
app.get("/status", (_req, res) => res.json(state));
app.post("/start", async (req, res) => {
  try { await start({ pairingPhone: req.body?.pairing_phone }); res.json(state); } catch (e) { res.status(500).json({ detail: e.message }); }
});
app.post("/disconnect", async (_req, res) => {
  manualStop = true;
  try { await sock?.logout(); } catch { /* ignore */ }
  sock = null;
  state = { status: "disconnected", is_connected: false, qr_code: null, pairing_code: null, phone: null, last_error: null };
  res.json(state);
});
app.post("/reconnect", async (_req, res) => {
  manualStop = true;
  try { sock?.end(undefined); } catch { /* ignore */ }
  sock = null;
  await start();
  res.json(state);
});
app.post("/send", async (req, res) => {
  try {
    const { to, text, pix_key } = req.body || {};
    if (pix_key) await sendPix(to, text, pix_key); else await sendText(to, text);
    res.json({ ok: true });
  } catch (e) { res.status(409).json({ detail: e.message }); }
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`whatsapp-service on ${PORT}`);
  import("node:fs").then((fs) => { if (fs.existsSync(`${AUTH_DIR}/creds.json`)) start().catch(() => {}); });
});
