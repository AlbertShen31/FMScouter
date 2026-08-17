# FMScouter
Based on the python evaluation script created by https://www.youtube.com/@squirrel_plays_fof4318

## Role scores

FM26 roles (SKP, BCB, IF, and so on) with no Attack/Support/Defend duty. Each role is tagged IP, OOP, or GK.

1. Run the app: `python app.py`
2. Open http://127.0.0.1:8050
3. Upload an FM **attribute** CSV (semicolon or comma). A stats-only export will be rejected.
4. Pick roles to score. Reset defaults loads SKP, BCB, WB, CM, CHM, IF.
5. Filter with position cards, foot, eligible, age, and min score, then download a scored CSV or a Cursor `.canvas.tsx`.

Place a downloaded canvas at `~/.cursor/projects/<workspace>/canvases/fm26-role-scores.canvas.tsx` to open it beside chat.

Squad and Formation still use the older FM24 duty-based roles.
