# ONEID

ONEID is the shared web login service for PIGSTY, FAKEPRESS, NOVA, and Inkvoid.

## Agreed account model

- One shared username, nickname, and password per person.
- Usernames are unique without case sensitivity. The public login form asks for the shared username.
- ONEID is the source of truth for the stable user ID and central administrator role.
- Site content remains in each site's existing database and is linked by the stable ONEID user ID.
- Email is not the username. This first version does not implement account recovery.

## What exists in this first version

- FastAPI account API: create account, sign in, and get the current profile.
- Admin account API: list ONEID accounts and grant or remove the global admin role. These endpoints require a valid ONEID bearer token belonging to an administrator.
- Minimal Korean home, registration, login, and account pages.
- Supabase profile/role schema and Supabase Auth integration path.
- Local SQLite development mode when Supabase settings are absent.
- A PKCE-protected ONEID site SSO flow for registered websites.

Local SQLite mode supports local SSO development. Site login uses a short-lived, single-use authorization code and returns a short-lived ONEID token to the registered callback. Site APIs exchange that identity for their existing local user record, preserving site content ownership. Existing users connect once with their prior site credential; new users can create a site profile from their ONEID profile. The previous site login and registration API routes are disabled after this switch.

## Run locally

From the project root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r .\backend\requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000`. With no Supabase keys configured, accounts are stored in `backend/oneid.local.db`. This local mode is for development only.

To assign a local development admin at registration time, set `ONEID_BOOTSTRAP_ADMIN_USERNAME` before launching. This is only for local development; never expose that mechanism on a public server.

## Connect Supabase

1. Create a Supabase project.
2. Run `backend/supabase/001_oneid_schema.sql` and then `backend/supabase/002_oneid_sso.sql` in its SQL editor.
3. Copy `.env.example` to `.env` in this project root.
4. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`. The service-role key is server-only and must never be put in the frontend or committed.
5. Restart FastAPI. The app uses Supabase Auth for credentials and Postgres for ONEID profiles/roles.
6. To create the first Supabase-backed admin, first create the account, verify its identity, then assign `admin` to its `user_id` in `public.oneid_roles` through a trusted administrator session.

Supabase Auth's password API accepts email or phone identifiers, while ONEID's public identifier is the shared username. The backend therefore uses a private, non-routable `.invalid` email alias internally; it is not the user's email and must not be shared with sites. Do not request the `email` OIDC scope for site clients. This version has no password-recovery flow.

## Prepare site SSO

Set `ONEID_CLIENT_REDIRECT_URIS` to a JSON map of each client ID to its exact allowed callback URLs. Set `ONEID_ALLOWED_ORIGINS` to the exact frontend origins that call ONEID from a browser. Add both each development URL and each deployed HTTPS URL. Site frontends set `ONEID_API_URL` and `ONEID_CLIENT_ID` in `oneid-config.js`; site backends set `ONEID_API_URL` to the same central API. Do not use wildcard callback URLs.

The SSO flow uses PKCE, two-minute single-use authorization codes, exact callback matching, and a two-hour ONEID identity token. Site backends verify that token against `/api/auth/me`; admin decisions are checked against the central role at request time. Supabase mode stores short-lived code hashes in the private schema through server-only RPC functions; local mode uses SQLite.

The central admin endpoints are `GET /api/admin/users` and `PATCH /api/admin/users/{user_id}/role` with JSON `{ "role": "user" }` or `{ "role": "admin" }`. The API requires an administrator's ONEID bearer token and does not allow changing the current administrator's role or removing the final administrator. The service-role credential stays on the ONEID server. Site account-management screens should continue to handle site-specific moderation separately.

For local integration, serve FAKEPRESS from `localhost:5500`, INKVOID from `localhost:5501`, PIGSTY from `localhost:5502`, and NOVA from `localhost:5503` (NOVA callback is `/login.html`). When ONEID is hosted, set each frontend config to the HTTPS ONEID URL and register each exact deployed callback URL under its client ID (`fakepress`, `inkvoid`, `pigsty`, `nova`). Add each deployed site origin to `ONEID_ALLOWED_ORIGINS`.

## Before public deployment

This is an initial implementation, not production-ready yet. Add and verify rate limiting, abuse protection/CAPTCHA, account recovery, admin management UI and audit log, verified profile updates, production HTTPS/cookie/session policy, and the Supabase OIDC claims/client integration before connecting live sites. Existing accounts must be linked deliberately; matching usernames or nicknames alone is not proof that two records belong to the same person.
