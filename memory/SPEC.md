# PedeFácil — SPEC (living document)

Multi-restaurant SaaS (formerly "Marmita Hub", based on github.com/enzodossantos3355-jpg/Feijoada) for restaurants and marmitarias: orders/PDV, menu, CRM, cash register, WhatsApp AI attendant (Baileys), delivery zones, couriers, Pix, tables, reports, backups, plus plans/billing and a master panel. UI in pt-BR, terracotta identity, logo `/frontend/public/logo.svg` (chat bubble + fork).

## Tenancy & auth
- Every signup (`POST /api/auth/register`, with `store_name`) creates a **store** (`stores` collection) and its admin user, on a 7-day trial.
- `lib/tenant.py`: `db` is a ScopedDB. Tenant collections (orders, products, customers, delivery_zones, store_settings, couriers, chats, day_status, day_closes, tables) automatically get `{"store_id": current}` on every filter/insert. Global: users, sessions, stores, payment_transactions, support_tickets, platform_settings.
- `lib/access.py`: session cookie `marmita_session` → user → `enter_store()` sets the tenant and plan contextvars. `active_store` returns 402 when the plan has expired; `need(feature)` returns 403 `{code: plan_required, required_plan, message}`; `check_limit()` returns 403 `plan_limit`.
- Roles: `admin` and `atendente` (both see the whole store panel), plus `master` (PedeFácil owner, `/master` only). The master is bootstrapped at startup from `.env` MASTER_EMAIL / MASTER_PASSWORD (`routers/auth.py: ensure_master`). There is no demo data or demo login: all demo/test stores were removed and nothing seeds them. New stores start with empty settings. Credentials: memory/test_credentials.md.

- Google login/signup (Emergent-managed OAuth): `components/AuthCallback.tsx` (button → auth.emergentagent.com, redirect `origin + /dashboard`; App.tsx detects `#session_id` via useLocation().hash) → `POST /api/auth/google {session_id}`. The backend verifies it with Emergent session-data. An existing email logs into that account (any role, including master); a new email creates its own store on the trial via `create_store_account`. Our own `marmita_session` cookie is used. Google-only users have no password. See /app/auth_testing.md.

## Plans (`lib/plans.py` ↔ `frontend/src/lib/plans.ts`)
- trial (7 days): pedidos, pdv, cardapio, clientes, caixa. Limits: 20 orders, 8 products, 20 customers, 1 user.
- basico R$49/month: same features as the trial, 2 users.
- padrao R$99/month: + whatsapp_ia, pix_qr, zonas, motoboys, mesas. 3 users.
- pro R$199/month: + relatorios_ia, voz, audio_whatsapp, backup, multi_atendentes. 20 users.
- Locked UI: `FeatureGate` / `LockedFeature` show "Disponível no plano X" with a "Fazer upgrade" button that goes to `/planos`. Nav items show a lock icon. An expired plan redirects to `/planos` (`/suporte` stays allowed).
- Billing: Stripe claimable sandbox (Flow A), subscription mode. Lookup keys are `pedefacil_{basico,padrao,pro}_mensal` (setup_stripe.py, BRL). `POST /api/billing/checkout {plan, origin_url}` → `/payment/success?session_id=` polls `GET /api/payments/status/{id}`, which activates the store for 31 days. Webhook `/api/stripe/webhook` handles checkout.session.completed, invoice.paid (renewal) and customer.subscription.deleted. Stripe Tax is not available in BR, so checkout is card-only with no automatic tax.
- Master: `GET/PUT /api/master/stores` (plan, status, extend_days), `GET/PUT /api/master/settings` (footer_text, site_url → appended to the WhatsApp "Concluído" message), `/api/master/tickets`.

## Public landing
- `/` and `/login` (`pages/Login.tsx`): landing page with "Entrar" (opens the login dialog; `/login` opens it automatically) and "Cadastrar" (`/register`) in the top-right corner, a hero, 10 feature cards and the 3 plans from the public `GET /api/billing/plans`. A master login goes to `/master`.

## Core flows
- Caixa do dia: Pedidos, PDV, Mesas, Atendimento and the AI only operate while the caixa is open (`OPEN_DAY` dependency returns 409; frontend `DayGate`).
- Orders: statuses Em Análise (AI orders) → Novo → Em Preparo → Pronto → Em Entrega → Concluído / Cancelado. Payments: Pendente, Dinheiro, Cartão Crédito, Cartão Débito, Pix, Outro. Pedidos page: kitchen summary, type/payment/status filters, cards with Editar + Mais menu (status, payment, edit, Pix QR, print, courier sheet, delete), voice order (Pro).
- WhatsApp AI (`routers/whatsapp.py`, Claude Sonnet 5.5): short replies. Closes the order immediately, defaults to Retirada, never asks for payment unless the customer mentions it. Re-confirmation updates the open order. Cancel keeps the order in history. Asking for a human pauses the AI. Tastes: the AI saves preferences/restrictions it detects (`customers.preferences`) and `lib/tastes.py` learns favorites, usual add-ons, usual delivery/payment and the last order from history. These go into the prompt (it offers "o de sempre" and respects restrictions) and appear on the Clientes cards ("Gostos (IA)"; computed fields on `GET /customers`). It never invents a store address or hours that aren't registered. Robust JSON extraction (`extract_reply`/`clean_text`) means no technical text ever leaks. Only private chats are handled (groups and channels are ignored in both the bridge and the backend). Audio is transcribed with whisper-1 (ffmpeg via imageio-ffmpeg, Pro plan). Conversations and individual messages can be deleted.
- Pix: `pix_mode` is "chave" (key + copy button) or "brcode" (static BR Code locked to the order total, txid = order id, via `whatsapp-service/pix.js` using qrcode-pix + qrcode; `GET /api/orders/{id}/pix`; Padrão+).
- Delivery fee (`lib/geo.py`): polygon → radius → CEP rules (prefix/exact/range) → keyword/bairro (ViaCEP enrichment). Google Maps links and GPS locations from WhatsApp are parsed. The store location is geocoded from its address or Maps link (Nominatim), or set by clicking the map. The map uses Leaflet + OpenStreetMap (no key).
- Tables (`routers/tables.py`, optional `tables_enabled`, Padrão+): open a table, launch orders (delivery_type "Mesa", table_number), close the bill.
- Central de Suporte (`routers/support.py`): stores open tickets; the master replies and resolves them.
- Dashboard: pause/reopen orders (`/store/toggle-accepting`).

## Products
- Structured editor (no typed text): nickname tags (`aliases`, the names customers use), optional sizes (rows of name + price), add-ons (rows of name + price + nickname tags) and photo upload from a file (resized in the browser to a JPEG data URL stored in `image_url`). The AI menu prompt includes the nicknames, and `price_items` matches add-ons by name or nickname. The AI never writes totals itself: the system appends the official receipt.

## Customer location → courier
- A GPS point sent on WhatsApp is saved to the chat (`last_lat/lng`), to every open order of that phone (`latitude/longitude`) and to the CRM (`customers.last_lat/lng`). The order card shows "Localização GPS do cliente" (Maps route). Mais → "Enviar ficha ao motoboy (WhatsApp)" calls `POST /api/orders/{id}/send-courier` (needs `motoboys`, an assigned courier with a phone, and WhatsApp connected).
- Zones map: when the store has no coordinates, the browser asks for location permission and the map starts there. "Estou na loja: usar minha localização" saves the store position.

## WhatsApp bridge (`whatsapp-service/index.js`, supervisor program `whatsapp`, port 8002)
- PRODUCTION has no supervisor program and no Node in the image. `backend/lib/wa_bridge.py` (started in the server.py lifespan) runs the **bundled** `whatsapp-service/dist/bridge.mjs` (esbuild, no node_modules needed) with the Node runtime from the pip package `nodejs-wheel-binaries`, and restarts it if it dies. Embedded mode = no `/etc/supervisor/conf.d/*whatsapp*` (override with WHATSAPP_EMBEDDED). Baileys session files are backed up to Mongo `wa_auth` every 15s and restored on boot, so no QR re-scan after a redeploy. **After editing index.js/pix.js run `cd whatsapp-service && yarn bundle`.**
- One Baileys session per store (`x-store-id` header), auth at `auth/<store_id>/`. It forwards `{store_id, jid, phone, text, latitude, longitude, audio_base64}` to `/api/whatsapp/incoming` (internal token). Endpoints: /status /start /disconnect /reconnect /send /pix.

## Update — order linking, payments, receipts, couriers, notifications
- WhatsApp chat has `order_id`: any change (items, address, notes) EDITS that order (`linked_order`), even after the store approved it — never a duplicate. Cancel keeps it in history as Cancelado.
- Payment: `payment_intent` = what the customer SAID; `payment_status` pendente|em_verificacao|pago. The AI never marks paid. Payment question only for Entrega. Pix only after the order is closed; bot then asks for the receipt.
- Receipts (photo/PDF) → `lib/receipt.py` (Gemini reads the file; strict Python check: amount == total AND recipient key/name matches AND status completed) → pago, else em_verificacao + needs_human; panel shows "Confirmar pago".
- Staff choosing a payment method in the panel marks it pago.
- Menu sent only on request (`send_menu`), with product photos (bridge `/send` images[]). No menu in greeting. Notes from customer requests go to order.notes.
- Manual order form: sections Cliente (Salvar cliente) / Entrega & Pagamento / Itens (product select) / Valores (Acréscimo, Desconto, Observações) / Total; modes Balcão, Voz, Preencher com IA. Order has surcharge/discount.
- /entregadores page (plan feature motoboys) — courier CRUD. Header bell: GET /api/notifications (new orders, human requests, receipts to check), 15s poll, sound + browser notification.
- Day close (POST /api/day/close) archives EVERYTHING: open-day orders get archived=true + close_id (Pedidos/notifications/bot only see non-archived), courier earnings snapshot saved in day_closes.couriers, ALL WhatsApp chats deleted (chats_deleted), couriers' working_date reset. Courier balance = fees of non-archived Entrega orders in Em Entrega/Concluído. Armazenamento lists closes with courier earnings + "Ver pedidos" (GET /api/day/closes/{id}). Reports/CRM still use all orders.
- Bot confirmation flow: AI sends a summary + "Posso confirmar o pedido?" (intent chat, no order yet); order is created only after the customer confirms. Payment only after confirmation: Retirada → never asks payment unless the customer brings it up; Entrega → asks method once after confirmation. Pix blocked in code until the order exists.
- Courier phone: UI has fixed +55 prefix + mask; backend CourierCreate validator normalizes to 55+DDD+number (12-13 digits), rejects invalid with 422.
- Pix sending: customer text mentioning pix/chave/QR (not 'paguei') or AI send_pix triggers Pix when a confirmed open order exists; no order → bot says Pix comes after confirmation; no pix_key → 'atendente envia' + needs_human (never silent).

## Update — day, mesas, split payment, Mercado Pago, handoff
- "Caixa" is now "Novo dia / Fechar dia" (no initial cash). Day closed → POST /orders 409 "Dia fechado…", bot replies closed_message, Pedidos/PDV/Atendimento gated (DayGate).
- Mesas: in maintenance — /mesas shows Maintenance page, /api/tables* return 503, plans/landing label "Mesas (em manutenção)".
- Split payment: Order.payments [{method, amount}] (max 2; 2nd = remainder of total). Manual form checkbox "Pagar com 2 formas" → payment_method "Pix + Dinheiro" (paid). AI fills order.payments + payment_intent; Pix is charged only for the Pix part (`pix_amount`).
- Pix to customer: only "Pix Copia e Cola" code; QR image only if the customer asks "QR".
- Mercado Pago (Pix Automático, optional): settings.pix_provider manual|mercadopago; token per store in mp_credentials (PUT/GET/DELETE /api/payments/mercadopago, validated with /users/me, never returned). Pix via POST /v1/orders; paid only when GET /v1/orders/{id} is processed/accredited. Confirmation: webhook POST /api/webhooks/mercadopago?store=ID, polling POST /api/payments/mercadopago/check (Pedidos every 20s), GET /api/orders/{id}/payment-status, and on any customer message.
- Receipts: favorecido name + amount + not scheduled (key not required).
- Human handoff: "Assumir" sends "👋 Um atendente…" and pauses AI; returning sends "🤖 voltou para a assistente". Any AI→human escalation sets is_human_controlled.
- Bot: summary without asking confirmation; changes (incl. pickup→delivery with zone fee) edit the same order; per-chat lock prevents duplicates. Status messages sent for all statuses except "Novo", to the chat JID, numbers normalized with 55.
- Manual order: delivery fee picked from the store's zones (or automatic by address).
- WhatsApp bridge: one socket per store (no duplicate sockets → no connected/disconnected flapping); 440 waits 60s; backoff. Bundle at whatsapp-service/bundle/bridge.mjs ships to production.
- Armazenamento: 'Dias fechados' list (ClosedDays) → 'Relatório do dia' (GET /api/day/closes/{id}: opened_at→closed, revenue, by_type Entrega/Retirada, by_payment (split parts counted per method), couriers, top_products, orders). DELETE /api/day/closes/{id} removes the record + its archived orders (customers kept).
- WhatsApp bridge bundle now at backend/whatsapp_bridge/bridge.mjs (published image ships only backend/ + frontend/). Build: cd whatsapp-service && yarn bundle (outputs there). Leader election (wa_leader lease) + session backup stay in backend/lib/wa_bridge.py; prod auth dir = backend/whatsapp_bridge/auth (restored from Mongo wa_auth).
- Add-ons have quantity (Additional.quantity, default 1): unit price = base/size + Σ add.price × qty. Manual form: − N× +; AI: additionals [{name, quantity}] or '2x ovo' or repeated names.
- Preview never backs up WhatsApp sessions to Mongo (only production does) to avoid two servers with the same credentials ('conflict: replaced'). wa_send retries 3× (4s/8s); handoff/resume + status messages are sent in background tasks.
- Production runs 2 replicas; only the lease holder runs the Baileys bridge. Non-leader replicas reach it ONLY through the Mongo queue `wa_rpc` (rpc_call → leader's rpc_serve → local bridge → reply). Never go back to pod-to-pod HTTP (/api/wa-bridge proxy was removed: it failed in prod and caused online/offline flapping + lost status messages). Background sends use wa_send_later() (keeps task references). AI order approved (Em Análise → Novo) sends APPROVED_MESSAGE; manual 'Novo' sends nothing.
