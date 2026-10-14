# Auth testing notes (Emergent Google Auth, adapted to PedeFácil's session)

- Google login: frontend redirects to `https://auth.emergentagent.com/?redirect=<window.location.origin>/dashboard`. On return, the URL is `/dashboard#session_id=...`. `AuthCallback` (detected in App.tsx via `useLocation().hash`) POSTs `/api/auth/google {session_id}`. The backend calls Emergent's session-data endpoint, then finds the user by email or creates a new store (7-day trial), and sets OUR cookie `marmita_session` (token in the `sessions` collection, `{token, user_id}`).
- Users have an `id` field (not `user_id`). Google-only users have `password_hash: null`, so password login fails for them by design.
- To test gated pages without Google: register a throwaway store via `POST /api/auth/register` (it sets the cookie), or insert `{token, user_id, created_at}` into `sessions` and set cookie `marmita_session=<token>` on the preview domain.
- Negative check: `POST /api/auth/google {"session_id":"invalid"}` → 401.
