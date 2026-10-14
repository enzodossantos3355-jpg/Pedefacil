// PedeFácil WhatsApp bridge (Baileys): one WhatsApp session per restaurant (store), selected by the
// x-store-id header. Incoming private messages are forwarded to BACKEND_URL/api/whatsapp/incoming with store_id.
import fs from "node:fs";
import express from "express";
import pino from "pino";
import QRCode from "qrcode";
import { downloadMediaMessage, generateWAMessageFromContent, proto } from "@whiskeysockets/baileys";
import makeWASocket, { Browsers, DisconnectReason, fetchLatestBaileysVersion, useMultiFileAuthState } from "@whiskeysockets/baileys";
import { gerarPix } from "./pix.js";

const PORT = Number(process.env.WHATSAPP_PORT || 8002);
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8001";
const TOKEN = process.env.WHATSAPP_INTERNAL_TOKEN || "";
const AUTH_ROOT = process.env.WHATSAPP_AUTH_DIR || "./auth";
const logger = pino({ level: "warn" });

const digits = (value) => String(value || "").replace(/\D/g, "");
const jidToPhone = (jid) => digits(String(jid || "").split("@")[0].split(":")[0]);
const blankState = () => ({ status: "disconnected", is_connected: false, qr_code: null, pairing_code: null, phone: null, last_error: null });
const sessions = new Map(); // storeId -> { sock, state, starting, manualStop }

const session = (storeId) => {
  if (!sessions.has(storeId)) sessions.set(storeId, { sock: null, state: blankState(), starting: false, manualStop: false });
  return sessions.get(storeId);
};
const authDir = (storeId) => `${AUTH_ROOT}/${storeId.replace(/[^A-Za-z0-9_-]/g, "")}`;

// Legacy single-session layout (creds directly in AUTH_ROOT) → move into the demo store's folder.
if (fs.existsSync(`${AUTH_ROOT}/creds.json`)) {
  const target = authDir("store-demo");
  fs.mkdirSync(target, { recursive: true });
  for (const f of fs.readdirSync(AUTH_ROOT)) if (f.endsWith(".json")) fs.renameSync(`${AUTH_ROOT}/${f}`, `${target}/${f}`);
}

async function start(storeId, { pairingPhone } = {}) {
  const s = session(storeId);
  if (s.starting) return;
  s.starting = true;
  s.manualStop = false;
  try {
    const { state: auth, saveCreds } = await useMultiFileAuthState(authDir(storeId));
    const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }));
    const sock = makeWASocket({ auth, version, logger, browser: Browsers.ubuntu("Chrome"), markOnlineOnConnect: false });
    s.sock = sock;
    s.state = { ...s.state, status: "connecting", last_error: null, pairing_code: null };
    sock.ev.on("creds.update", saveCreds);

    if (pairingPhone && !auth.creds.registered) {
      await new Promise((r) => setTimeout(r, 2500));
      const code = await sock.requestPairingCode(digits(pairingPhone));
      s.state = { ...s.state, status: "pairing_code", pairing_code: code };
    }

    sock.ev.on("connection.update", async ({ connection, lastDisconnect, qr }) => {
      if (qr && !pairingPhone) s.state = { ...s.state, status: "qr_ready", qr_code: await QRCode.toDataURL(qr) };
      if (connection === "open") s.state = { ...s.state, status: "connected", is_connected: true, qr_code: null, pairing_code: null, phone: jidToPhone(sock.user?.id) };
      if (connection === "close") {
        const code = lastDisconnect?.error?.output?.statusCode;
        s.state = { ...s.state, status: "disconnected", is_connected: false, last_error: lastDisconnect?.error?.message || null };
        s.sock = null;
        if (code === DisconnectReason.loggedOut) fs.rmSync(authDir(storeId), { recursive: true, force: true });
        else if (!s.manualStop) setTimeout(() => start(storeId).catch(() => {}), 3000); // automatic reconnect
      }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      if (type !== "notify") return;
      for (const msg of messages) {
        if (!msg.message || msg.key.fromMe) continue;
        const remote = msg.key.remoteJid || "";
        // Only private chats: groups (@g.us), channels (@newsletter), status and broadcasts are ignored.
        if (!(remote.endsWith("@s.whatsapp.net") || remote.endsWith("@lid"))) continue;
        const phoneJid = msg.key.remoteJidAlt || msg.key.senderPn || remote;
        const m = msg.message;
        const loc = m.locationMessage || m.liveLocationMessage;
        const audio = m.audioMessage;
        let audioBase64 = "";
        if (audio) {
          try { audioBase64 = (await downloadMediaMessage(msg, "buffer", {}, { logger, reuploadRequest: sock.updateMediaMessage })).toString("base64"); }
          catch (err) { logger.warn({ err }, "falha ao baixar áudio"); }
        }
        const media = m.imageMessage || (m.documentMessage?.mimetype?.includes("pdf") ? m.documentMessage : null) || m.documentWithCaptionMessage?.message?.documentMessage;
        let mediaBase64 = "";
        if (media) {
          try { mediaBase64 = (await downloadMediaMessage(msg, "buffer", {}, { logger, reuploadRequest: sock.updateMediaMessage })).toString("base64"); }
          catch (err) { logger.warn({ err }, "falha ao baixar arquivo"); }
        }
        const text = m.conversation || m.extendedTextMessage?.text || m.imageMessage?.caption || media?.caption || (loc ? "[localização enviada]" : "");
        if (!text && !audioBase64 && !mediaBase64) continue;
        try {
          await fetch(`${BACKEND_URL}/api/whatsapp/incoming`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "x-internal-token": TOKEN },
            body: JSON.stringify({ store_id: storeId, jid: remote, phone: jidToPhone(phoneJid), name: msg.pushName || "", text, latitude: loc?.degreesLatitude ?? null, longitude: loc?.degreesLongitude ?? null, audio_base64: audioBase64, audio_mime: audio?.mimetype || "", media_base64: mediaBase64, media_mime: media?.mimetype || "" }),
          });
        } catch (err) {
          logger.error({ err }, "falha ao repassar mensagem");
        }
      }
    });
  } finally {
    s.starting = false;
  }
}

async function sendText(s, to, text) {
  if (!s.sock || !s.state.is_connected) throw new Error("WhatsApp não conectado");
  const jid = to.includes("@") ? to : `${digits(to)}@s.whatsapp.net`;
  await s.sock.sendMessage(jid, { text });
  return jid;
}

async function sendCopyButton(s, jid, body, label, code) {
  try {
    // Native copy button (cta_copy). Some clients don't render it, so the code also goes as plain text.
    const content = proto.Message.fromObject({
      interactiveMessage: { body: { text: body }, nativeFlowMessage: { buttons: [{ name: "cta_copy", buttonParamsJson: JSON.stringify({ display_text: label, copy_code: code }) }] } },
    });
    const wa = generateWAMessageFromContent(jid, { viewOnceMessage: { message: content } }, { userJid: s.sock.user.id });
    await s.sock.relayMessage(jid, wa.message, { messageId: wa.key.id });
  } catch (err) {
    logger.warn({ err }, "botão de copiar indisponível");
  }
  await s.sock.sendMessage(jid, { text: code });
}

const app = express();
app.use(express.json({ limit: "25mb" }));
app.use((req, res, next) => (TOKEN && req.get("x-internal-token") !== TOKEN ? res.status(401).json({ detail: "unauthorized" }) : next()));
const sid = (req) => String(req.get("x-store-id") || "");
const needStore = (req, res, next) => (sid(req) ? next() : res.status(400).json({ detail: "x-store-id obrigatório" }));

app.get("/status", needStore, (req, res) => res.json(session(sid(req)).state));
app.post("/start", needStore, async (req, res) => {
  try { await start(sid(req), { pairingPhone: req.body?.pairing_phone }); res.json(session(sid(req)).state); } catch (e) { res.status(500).json({ detail: e.message }); }
});
app.post("/disconnect", needStore, async (req, res) => {
  const s = session(sid(req));
  s.manualStop = true;
  try { await s.sock?.logout(); } catch { /* ignore */ }
  s.sock = null;
  s.state = blankState();
  res.json(s.state);
});
app.post("/reconnect", needStore, async (req, res) => {
  const s = session(sid(req));
  s.manualStop = true;
  try { s.sock?.end(undefined); } catch { /* ignore */ }
  s.sock = null;
  await start(sid(req));
  res.json(s.state);
});
app.post("/send", needStore, async (req, res) => {
  try {
    const s = session(sid(req));
    const { to, text, pix_key, pix_code, pix_qr, images } = req.body || {};
    const jid = await sendText(s, to, text);
    for (const img of images || []) {  // menu photos: uploaded (data URL) or https URL
      const src = String(img.image || "");
      const image = src.startsWith("data:") ? Buffer.from(src.split(",")[1] || "", "base64") : { url: src };
      try { await s.sock.sendMessage(jid, { image, caption: img.caption || "" }); } catch (err) { logger.warn({ err }, "foto do cardápio falhou"); }
    }
    if (pix_code) {
      if (pix_qr) await s.sock.sendMessage(jid, { image: Buffer.from(pix_qr.split(",")[1] || "", "base64"), caption: "QR Code Pix com o valor do seu pedido 👆" });
      await sendCopyButton(s, jid, "Ou toque no botão para copiar o Pix Copia e Cola:", "Copiar código Pix", pix_code);
    } else if (pix_key) {
      await sendCopyButton(s, jid, "Toque no botão abaixo para copiar a chave Pix:", "Copiar chave Pix", pix_key);
    }
    res.json({ ok: true });
  } catch (e) { res.status(409).json({ detail: e.message }); }
});
app.post("/pix", async (req, res) => {
  try { res.json(await gerarPix(req.body || {})); } catch (e) { res.status(422).json({ detail: e.message }); }
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`whatsapp-service on ${PORT}`);
  // Restore every store that already has saved credentials.
  if (fs.existsSync(AUTH_ROOT)) for (const dir of fs.readdirSync(AUTH_ROOT)) if (fs.existsSync(`${AUTH_ROOT}/${dir}/creds.json`)) start(dir).catch(() => {});
});
