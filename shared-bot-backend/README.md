# JoinQueue shared backend 0.1.2

Server-only Cloudflare Worker. Never include this folder in the Windows plugin ZIP.
Bot OAuth secrets and encrypted refresh tokens remain in Cloudflare. No credential files belong in this repository.

`pnpm install --frozen-lockfile` then `pnpm check` verifies contracts, rate limits, OAuth and runtime persistence with mocked Google responses. `pnpm worker:dry-run` does not upload.

Do not blindly run wrangler deploy: preserve existing Secrets, bindings and URL flags. The fixed Durable Object name and namespace must not change. Posting remains disabled until separately approved. See ../docs/BOT.md for the client flow.

2026-09-22 deployment: validated bundle deployed through Cloudflare Quick Edit (code version 4a059afc), existing Durable Object and encrypted credentials retained. Production URL and CHANNEL_CONNECT_ENABLED are enabled; previews, BOT_AUTH_ENABLED and BOT_POSTING_ENABLED remain disabled. Google consent configuration includes youtube.readonly and /connect/callback alongside the existing operator callback. Public health, temporary pairing start/browser/status/disconnect and posting-disabled rejection were verified without Google consent or a real chat post. Google testing-audience restrictions and live posting still require operator verification before general availability.

2026-09-23 audit fixes: Quick Edit active version `b05ade34`; validated bundle SHA256 `60cf9768b83caf8d6ea25bc37f16917d0581059ecae3925385149cae4fd88966`. Per-source HMAC admission budgets replace the unauthenticated shared start/ingress caps. IPv6 sources share a /64 budget; raw IPs are not stored. YouTube OAuth lookup quota is reserved only after successful Google authentication. Shared NAT limits and distributed abuse remain operational considerations. Existing secrets/binding retained, BOT_POSTING_ENABLED and BOT_AUTH_ENABLED confirmed false, CHANNEL_CONNECT_ENABLED true. Production health and one disposable pending pairing (start/status/revocation) passed; posting-disabled rejection was verified with an unprovisioned random key, without Google authorization or chat posting. See ../docs/AUDIT_FIXES_2026-09-23.md.
