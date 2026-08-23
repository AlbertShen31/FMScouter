# FMScouter

Based on the python evaluation script created by https://www.youtube.com/@squirrel_plays_fof4318

How the scorer, role groups, packs, and naming are wired: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Security before any non-localhost exposure: [docs/SECURITY.md](docs/SECURITY.md).

Code layout: `pages/` (routes), `components/` (shared UI), `scoring/` (parse/score), `services/` (packs/settings), `config/` (data).

## Run locally

```bash
cp .env.example .env
# Set FM_AUTH_USER / FM_AUTH_PASSWORD, or FM_AUTH_DISABLED=true for loopback-only
python app.py
```

Defaults: bind `127.0.0.1:8050`, debugger off, HTTP Basic Auth on all routes (including Dash callbacks). Saved CSVs under `data/uploads/` are confidential (wages/contracts may be present).

## Deploy on Render

This is a Python/Dash app (not static), so GitHub Pages cannot host it. Use a [Render](https://render.com) Web Service instead.

1. Push this repo to GitHub (already: `AlbertShen31/FMScouter`).
2. In the [Render Dashboard](https://dashboard.render.com): **New → Blueprint**, select the repo (uses [render.yaml](render.yaml)).
3. When prompted, set secrets: `FM_AUTH_USER`, `FM_AUTH_PASSWORD`. `FM_SECRET_KEY` is generated automatically.
4. Deploy, then open the public `https://….onrender.com` URL and sign in with Basic Auth.

Notes: free instances may sleep after idle (cold start). Disk is **ephemeral** — saved uploads and pack edits are lost on redeploy/restart. See [docs/SECURITY.md](docs/SECURITY.md) before uploading finance/wage CSVs.

## Role scores

FM26 roles, with each role tagged IP, OOP, or GK.

1. Run the app (see above).
2. Open http://127.0.0.1:8050
3. Upload an FM **attribute** CSV (semicolon or comma). A stats-only export will be rejected.
4. Pick roles to score. Reset defaults loads SKP, BCB, WB, CM, CHM, IF.
5. Filter with position cards, foot, eligible, age, and min score, then download a scored CSV.
6. Open **Role configs** to view and edit each role’s key (×5), preferred (×3), and useful (×1) attributes. Clicks cycle Off → Key → Preferred → Useful. **Clear this role** blanks its attributes. **Reset** reloads the role from the selected config. **Save** writes a named config (Built-in is read-only). **New config** creates a file that is either a copy of the selected config or a blank slate. Use **Positions** chips to assign a role to multiple buckets (Inside Winger is Wide midfielders and Wingers by default). Pick the same config file on Role scores to score with it.
