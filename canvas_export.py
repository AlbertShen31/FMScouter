"""Build a Cursor canvas file from scored player rows."""
from __future__ import annotations

import json
from typing import Any

import ui_settings as us

TEMPLATE = r'''import {
  BarChart,
  Button,
  Callout,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Select,
  Stack,
  Stat,
  Table,
  Text,
  TextInput,
  Toggle,
  useCanvasState,
} from "cursor/canvas";

type Player = {
  n: string;
  a: number;
  c: string;
  dv: string;
  p: string;
  rc: string;
  inj: string;
  s: Record<string, number>;
  e: Record<string, boolean>;
};

const ROLES: string[] = __ROLES__;
const PLAYERS: Player[] = __PLAYERS__;
const SOURCE = __SOURCE__;
const PAGE = 30;
const BINS = __BINS__;
const AGE_OPTIONS = __AGE_OPTIONS__;

function dash(value: string | number | undefined | null): string {
  if (value === undefined || value === null || value === "") return "—";
  return String(value);
}

function scoreText(value: number | undefined, active: boolean): string {
  const n = Number(value);
  const text = Number.isFinite(n) ? n.toFixed(1) : "—";
  return active ? `• ${text}` : text;
}

function topFor(role: string): Player | undefined {
  return PLAYERS.filter((p) => p.e[role]).sort((a, b) => b.s[role] - a.s[role])[0];
}

export default function RoleScores() {
  const [role, setRole] = useCanvasState("role", ROLES[0] ?? "");
  const [query, setQuery] = useCanvasState("q", "");
  const [eligOnly, setEligOnly] = useCanvasState("elig", true);
  const [maxAge, setMaxAge] = useCanvasState("age", "any");
  const [minScore, setMinScore] = useCanvasState("min", "");
  const [limit, setLimit] = useCanvasState("limit", PAGE);

  const active = ROLES.includes(role) ? role : ROLES[0];
  const ageCap = maxAge === "any" ? 99 : Number(maxAge);
  const floor = Number(minScore);
  const q = query.trim().toLowerCase();

  const filtered = PLAYERS.filter((p) => {
    if (!active) return false;
    if (eligOnly && !p.e[active]) return false;
    if (p.a > ageCap) return false;
    if (Number.isFinite(floor) && floor > 0 && (p.s[active] ?? 0) < floor) return false;
    if (q && !`${p.n} ${p.c} ${p.p} ${p.dv}`.toLowerCase().includes(q)) return false;
    return true;
  }).sort((a, b) => (b.s[active] ?? 0) - (a.s[active] ?? 0));

  const values = filtered.map((p) => p.s[active] ?? 0).sort((a, b) => a - b);
  const hist = BINS.map((bin, i) =>
    values.filter((v) =>
      i === BINS.length - 1 ? v >= bin.lo : v >= bin.lo && v < bin.hi,
    ).length,
  );
  const shown = filtered.slice(0, limit);
  const median = values.length ? values[Math.floor(values.length / 2)].toFixed(1) : "—";
  const high = values.length ? values[values.length - 1].toFixed(1) : "—";

  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>FM26 role scores</H1>
        <Text tone="secondary">
          {PLAYERS.length} players · {SOURCE}. Scores use key×5 + preferred×3 +
          useful×1 divided by the role divisor.
        </Text>
      </Stack>
      <Callout tone="info" title="Filters">
        Position eligible keeps only players whose FM position matches the
        selected role. Empty club / rec values show as a dash.
      </Callout>
      <Grid columns={3} gap={16}>
        {ROLES.map((r) => {
          const top = topFor(r);
          return (
            <Stat
              value={top ? top.s[r].toFixed(1) : "—"}
              label={top ? `${r} · ${top.n}, ${top.a}` : `${r} · none eligible`}
            />
          );
        })}
      </Grid>
      <Stack gap={10}>
        <H2>Role shortlist</H2>
        <Row gap={8} wrap>
          {ROLES.map((r) => (
            <span key={r}>
              <Pill
                active={r === active}
                onClick={() => {
                  setRole(r);
                  setLimit(PAGE);
                }}
              >
                {r}
              </Pill>
            </span>
          ))}
        </Row>
      </Stack>
      <Grid columns={4} gap={12}>
        <Stat value={String(filtered.length)} label="Players matching filters" />
        <Stat value={high} label={`${active} high score`} />
        <Stat value={median} label="Median of list" />
        <Stat value={String(PLAYERS.length)} label="Players in file" />
      </Grid>
      <Row gap={10} wrap align="center">
        <TextInput
          value={query}
          onChange={setQuery}
          placeholder="Search name, club, position…"
          style={{ minWidth: 220 }}
        />
        <Select
          value={maxAge}
          onChange={setMaxAge}
          options={AGE_OPTIONS}
        />
        <TextInput
          value={minScore}
          onChange={setMinScore}
          placeholder="Min score (blank = any)"
          style={{ minWidth: 160 }}
        />
        <Row gap={8} align="center">
          <Toggle checked={eligOnly} onChange={setEligOnly} />
          <Text size="small">Position eligible only</Text>
        </Row>
      </Row>
      <Stack gap={8}>
        <H3>{active} score distribution</H3>
        <Text size="small" tone="tertiary">
          Horizontal axis is {active} score band; vertical axis is player count
          after the filters above.
        </Text>
        <BarChart
          categories={BINS.map((b) => b.label)}
          series={[{ name: "Player count", data: hist, tone: "info" }]}
          height={180}
          beginAtZero
          showValues
        />
      </Stack>
      <Stack gap={8}>
        <H2>{active} ranking</H2>
        <Text size="small" tone="tertiary">
          Showing {shown.length} of {filtered.length}. A leading bullet marks
          the active role column.
        </Text>
        <Table
          headers={["#", "Name", "Age", "Position", "Club", "Rec", ...ROLES]}
          columnAlign={[
            "right",
            "left",
            "right",
            "left",
            "left",
            "left",
            ...ROLES.map(() => "right" as const),
          ]}
          striped
          stickyHeader
          rows={shown.map((p, i) => [
            String(i + 1),
            p.inj ? `${dash(p.n)} (${p.inj})` : dash(p.n),
            dash(p.a),
            dash(p.p),
            dash(p.c),
            dash(p.rc),
            ...ROLES.map((r) => scoreText(p.s[r], r === active)),
          ])}
          rowTone={shown.map((p) => {
            if (p.inj) return "warning";
            if (p.rc === "A+" || p.rc === "A") return "success";
            return undefined;
          })}
        />
        {filtered.length > shown.length ? (
          <Button variant="secondary" onClick={() => setLimit(limit + PAGE)}>
            Show next {Math.min(PAGE, filtered.length - shown.length)} remaining
          </Button>
        ) : null}
      </Stack>
    </Stack>
  );
}
'''


def build_canvas(
    rows: list[dict[str, Any]],
    role_labels: list[str],
    source: str,
    settings: dict[str, Any] | None = None,
) -> str:
    settings = us.normalize(settings)
    compact = []
    for row in rows:
        compact.append(
            {
                "n": row.get("Name") or "",
                "a": int(row.get("Age") or 0),
                "c": row.get("Club") or "",
                "dv": row.get("Division") or "",
                "p": row.get("Position") or "",
                "rc": "" if row.get("Rec") in (None, "-", "") else row.get("Rec"),
                "inj": "" if row.get("Injury") in (None, "-", "") else row.get("Injury"),
                "s": {label: float(row.get(label) or 0) for label in role_labels},
                "e": {
                    label: bool(row.get(f"{label} eligible"))
                    for label in role_labels
                },
            }
        )
    roles_js = json.dumps(role_labels, ensure_ascii=False)
    players_js = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    source_js = json.dumps(source, ensure_ascii=False)
    bins_js = json.dumps(
        [{"label": label, "lo": lo, "hi": hi} for label, lo, hi in us.hist_bins(settings)],
        ensure_ascii=False,
    )
    age_js = json.dumps(
        [
            {"value": "any", "label": "Any age"}
            if opt["value"] in (99, "99")
            else {"value": str(int(opt["value"])), "label": f"Max {int(opt['value'])}"}
            for opt in us.age_options(settings)
        ],
        ensure_ascii=False,
    )
    if "`" in players_js or "${" in players_js:
        raise ValueError("Player data contains characters that cannot be embedded in the canvas.")
    return (
        TEMPLATE.replace("__ROLES__", roles_js)
        .replace("__PLAYERS__", players_js)
        .replace("__SOURCE__", source_js)
        .replace("__BINS__", bins_js)
        .replace("__AGE_OPTIONS__", age_js)
    )
