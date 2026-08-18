# FMScouter
Based on the python evaluation script created by https://www.youtube.com/@squirrel_plays_fof4318

## Role scores

FM26 roles, with each role tagged IP, OOP, or GK.

1. Run the app: `python app.py`
2. Open http://127.0.0.1:8050
3. Upload an FM **attribute** CSV (semicolon or comma). A stats-only export will be rejected.
4. Pick roles to score. Reset defaults loads SKP, BCB, WB, CM, CHM, IF.
5. Filter with position cards, foot, eligible, age, and min score, then download a scored CSV or a Cursor `.canvas.tsx`.
6. Open **Role configs** to view and edit each role’s key (×5), green (×3), and blue (×1) attributes. Clicks cycle Off → Key → Green → Blue. Use **Positions** chips to assign a role to multiple buckets (Inside Winger is wingers and wide attackers by default). Use **Save as new file** to write a named pack under `config/packs/`, then pick that file on Role scores. **Set as defaults** overrides Built-in / Reset with the current weights; **Restore factory** goes back to the Python config.

Place a downloaded canvas at `~/.cursor/projects/<workspace>/canvases/fm26-role-scores.canvas.tsx` to open it beside chat.
