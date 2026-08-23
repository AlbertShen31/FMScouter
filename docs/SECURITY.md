# Security (P0)

FMScouter is a single-user scouting app. Treat it like a private notebook that holds FM exports, including wages and contracts from Moneyball / squad finance CSVs.

## Before any non-localhost exposure

1. **No debugger** — leave `FM_DEBUG` unset or `false`. Never deploy with the Werkzeug debugger.
2. **Bind loopback** — default `FM_HOST=127.0.0.1`. Put Cloudflare Access, Tailscale, or another reverse-proxy SSO in front before listening on `0.0.0.0`.
3. **Authentication** — set `FM_AUTH_USER` and `FM_AUTH_PASSWORD` (HTTP Basic Auth on every route, including `_dash-update-component`). Prefer proxy SSO (Cloudflare Access, etc.) in front; Basic Auth is the in-app floor.
4. **Confidential uploads** — `data/uploads/` is gitignored and not served as static files. Still:
   - Do not sync or publish that folder.
   - Prefer full-disk encryption on the host.
   - Moneyball / finance exports include contracts and wages; delete files you do not need, or avoid saving finance CSVs if the disk is not trusted.

## Local development

```bash
cp .env.example .env
# either set FM_AUTH_USER / FM_AUTH_PASSWORD, or:
# FM_AUTH_DISABLED=true   # only with FM_HOST=127.0.0.1
python app.py
```

## What you must do on the host (not automated in-app)

- Enable disk encryption (or do not persist wage/contract CSVs).
- Terminate TLS at the reverse proxy.
- Prefer Cloudflare Access / Tailscale / VPN over exposing Basic Auth alone to the public internet.
