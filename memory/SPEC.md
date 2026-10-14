# PedeFácil — SPEC (living document)

Multi-restaurant SaaS (formerly "Marmita Hub", based on github.com/enzodossantos3355-jpg/Feijoada) for restaurants and marmitarias: orders/PDV, menu, CRM, cash register, WhatsApp AI attendant (Baileys), delivery zones, couriers, Pix, tables, reports, backups, plus plans/billing and a master panel. UI in pt-BR, terracotta identity, logo `/frontend/public/logo.svg` (chat bubble + fork).

## Tenancy & auth
- Every signup (`POST /api/auth/register`, with `store_name`) creates a **store** (`stores` collection) and its admin user, on a 7-day trial.
- `lib/tenant.py`: `db` is a ScopedDB. Tenant collections (orders, products, customers, delivery_zones, store_settings, couriers, chats, day_status, day_closes, tables) automatically get `{"store_id": current}` on every filter/insert. Global: users, sessions, stores, payment_transactions, support_tickets, platform_settings.
- `lib/access.py`: session cookie `marmita_session` → user → `enter_store()` sets the tenant and plan contextvars. `active_store` returns 402 when the plan has expired; `need(feature)` returns 403 `{code: plan_required, required_plan, message}`; `check_limit()` returns 403 `plan_limit`.
- Roles: `admin` and `atendente` (both see the whole store panel), plus `master` (PedeFácil owner, `/master` only). The master is bootstrapped at startup from `.env` MASTER_EMAIL / MASTER_PASSWORD (`routers/auth.py: ensure_master`). There is no demo data or demo login: all demo/test stores were removed and nothing seeds them. New stores start with empty settings. Credentials: memory/test_credentials.md.

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

## WhatsApp bridge (`whatsapp-service/index.js`, supervisor program `whatsapp`, port 8002)
- One Baileys session per store (`x-store-id` header), auth at `auth/<store_id>/`. It forwards `{store_id, jid, phone, text, latitude, longitude, audio_base64}` to `/api/whatsapp/incoming` (internal token). Endpoints: /status /start /disconnect /reconnect /send /pix.
