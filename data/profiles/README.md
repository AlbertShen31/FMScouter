# Saved player profiles

Named profile libraries live under `packs/<id>/` (`meta.json`, `index.json`,
`slot_depth.json`). `active.json` points at the current library, or
`{"id": null}` when none is selected (the default). The navbar Profile control
and the Profiles page share that selection. Timestamped library backups from
the Profiles page live under `backups/`.

Create libraries on the Profiles page (name + formation required). Role scores
can save marked players into any library.
