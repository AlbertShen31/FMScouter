# Saved CSV exports (gitignored)

Managed via the Uploads page. **Confidential** — not statically hosted by the app.

Moneyball and squad-finance exports can include contracts, wages, and fees. Do not sync or publish this folder. Prefer encrypting the host disk, or delete finance CSVs when you no longer need them.

## Precompute cache

On upload (and via **Compute**), Role scores and Player stats are precomputed into `cache/{file_id}.json.gz` using the active role pack, tier weights, set-piece profiles, and stats thresholds.

- **Ready** — library load skips CSV parse / role scoring
- **Stale** — settings or packs changed; click **Compute** again
- Role scores and Player stats saved-file dropdowns show Ready / Stale / Not computed next to each file
- Hybrid IP/OOP combo weights are applied at read time (no recompute needed)

Changing display-only settings (bands, colors, filters) does not invalidate the cache.
