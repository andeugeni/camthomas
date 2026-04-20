"use client";

import { PlayerCard } from "@/data/mockPlayers";
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import styles from "@/styles/PlayerCardView.module.css";

// ─── helpers ───────────────────────────────────────────────────────────────

function fmtPct(v: number) { return `${(v * 100).toFixed(1)}%`; }
function fmtInches(inches: number) {
  const ft = Math.floor(inches / 12);
  const i  = inches % 12;
  return `${ft}'${i}"`;
}
function pctColor(pct: number) {
  if (pct >= 75) return "var(--good)";
  if (pct >= 40) return "var(--mid)";
  return "var(--bad)";
}
function pctDot(pct: number) {
  const color = pctColor(pct);
  return <span className={styles.dot} style={{ background: color }} />;
}

// ─── StatBar ───────────────────────────────────────────────────────────────

function StatBar({ label, value, pct, format }: {
  label: string;
  value: string;
  pct: number;
  format?: "pct" | "raw";
}) {
  return (
    <div className={styles.statBar}>
      <span className={styles.statBarLabel}>{label}</span>
      <span className={`${styles.statBarValue} mono`}>{value}</span>
      <div className={styles.statBarTrack}>
        <div
          className={styles.statBarFill}
          style={{ width: `${pct}%`, background: pctColor(pct) }}
        />
      </div>
      {pctDot(pct)}
    </div>
  );
}

// ─── ProjectionChart ────────────────────────────────────────────────────────

function ProjectionChart({ player }: { player: PlayerCard }) {
  const BASE_YEAR = 2025;

  // Build actuals series (only non-zero seasons)
  const actuals = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025].map(yr => {
    const v = player[`actual_${yr}` as keyof PlayerCard] as number;
    return v > 0 ? { year: String(yr), actual: v } : null;
  }).filter(Boolean) as { year: string; actual: number }[];

  // Build projection series
  const projData = [1, 2, 3, 4, 5].map(i => ({
    year: String(BASE_YEAR + i),
    proj:  player[`proj_y${i}`  as keyof PlayerCard] as number,
    lo:    player[`ci_lo_y${i}` as keyof PlayerCard] as number,
    hi:    player[`ci_hi_y${i}` as keyof PlayerCard] as number,
  }));

  // Combine for chart — actual runs up to 2025, proj from 2025 forward
  const lastActual = actuals[actuals.length - 1];
  const bridgePoint = lastActual ? { year: "2025", actual: lastActual.actual, proj: lastActual.actual, lo: lastActual.actual, hi: lastActual.actual } : null;

  const combined = [
    ...actuals.slice(0, -1).map(d => ({ ...d, proj: null as number | null, lo: null as number | null, hi: null as number | null })),
    bridgePoint ? bridgePoint : { year: "2025", actual: null, proj: null, lo: null, hi: null },
    ...projData.map(d => ({ actual: null as number | null, year: d.year, proj: d.proj, lo: d.lo, hi: d.hi })),
  ];

  const allVals = [
    ...actuals.map(d => d.actual),
    ...projData.map(d => d.hi),
  ].filter(Boolean) as number[];
  const maxVal = Math.max(...allVals) * 1.15;

  return (
    <div className={styles.chartWrap}>
      <div className={styles.chartHeader}>
        <span className={`${styles.chartTitle} cond`}>Fantasy Pts Projection</span>
        <span className={styles.chartCategory}>{player.category}</span>
        <div className={styles.chartLegend}>
          <span className={styles.legendActual}>— Actual</span>
          <span className={styles.legendProj}>- - Proj</span>
          <span className={styles.legendCI}>CI</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={combined} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <defs>
            <linearGradient id="ciGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--proj)" stopOpacity={0.25} />
              <stop offset="95%" stopColor="var(--proj)" stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="year"
            tick={{ fill: "var(--text3)", fontSize: 10, fontFamily: "DM Mono" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis
            domain={[0, maxVal]}
            tick={{ fill: "var(--text3)", fontSize: 10, fontFamily: "DM Mono" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg2)", border: "1px solid var(--border2)",
              borderRadius: 6, fontSize: 11, fontFamily: "DM Mono",
            }}
            labelStyle={{ color: "var(--text2)" }}
            itemStyle={{ color: "var(--text)" }}
            formatter={(val: number) => val?.toFixed(1)}
          />
          <ReferenceLine x="2025" stroke="var(--border2)" strokeDasharray="3 3" />

          {/* CI band */}
          <Area
            type="monotone"
            dataKey="hi"
            stroke="none"
            fill="url(#ciGrad)"
            isAnimationActive={false}
          />

          {/* Actual line */}
          <Line
            type="monotone"
            dataKey="actual"
            stroke="var(--text2)"
            strokeWidth={1.5}
            dot={{ r: 2.5, fill: "var(--text2)", strokeWidth: 0 }}
            activeDot={{ r: 4, fill: "var(--accent)" }}
            connectNulls={false}
            isAnimationActive={false}
          />

          {/* Projection line */}
          <Line
            type="monotone"
            dataKey="proj"
            stroke="var(--proj)"
            strokeWidth={1.5}
            strokeDasharray="5 3"
            dot={{ r: 2.5, fill: "var(--proj)", strokeWidth: 0 }}
            activeDot={{ r: 4 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Main component ─────────────────────────────────────────────────────────

export default function PlayerCardView({ player }: { player: PlayerCard }) {
  return (
    <div className={`${styles.card} fade-up`}>

      {/* ── Header ─────────────────────────────────────── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={`${styles.playerName} cond`}>{player.player}</h1>
          <div className={styles.headerMeta}>
            <span className={styles.team}>{player.team}</span>
            <span className={styles.sep}>·</span>
            <span className={styles.pos}>{player.pos}</span>
            <span className={styles.sep}>·</span>
            <span className={styles.age}>{player.age} yrs old</span>
          </div>
        </div>
        <div className={styles.headerRight}>
          <div className={styles.bigStat}>
            <span className={`${styles.bigStatVal} mono`}>{player.fantasy_pts.toFixed(1)}</span>
            <span className={styles.bigStatLabel}>proj fpts/g</span>
          </div>
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────── */}
      <div className={styles.body}>

        {/* Left col */}
        <div className={styles.leftCol}>

          {/* Vitals */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Vitals</h3>
            <div className={styles.vitalGrid}>
              <VitalRow label="Height"        value={fmtInches(player.ht_inches)} />
              <VitalRow label="Weight"        value={`${player.wt} lb`} />
              <VitalRow label="Draft pick"    value={player.draft_pick != null ? `#${player.draft_pick}` : "Undrafted"} />
              <VitalRow label="Proj MPG"      value={player.proj_mpg.toFixed(1)} />
            </div>
          </section>

          {/* Scoring */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Scoring</h3>
            <StatBar label="True Shoot %"  value={fmtPct(player.ts_pct)}   pct={player.ts_pct_pct} />
            <StatBar label="Free Throw %"  value={fmtPct(player.ft_pct)}   pct={Math.round(player.ft_pct * 100)} />
            <StatBar label="Usage %"       value={fmtPct(player.usg_pct)}  pct={player.usg_pct_pct} />
          </section>

          {/* Tendencies */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Tendencies</h3>
            <StatBar label="3PT Freq"   value={fmtPct(player.x3_freq)}  pct={Math.round(player.x3_freq * 100 * 3)} />
            <StatBar label="FT Freq"    value={fmtPct(player.ft_freq)}  pct={Math.round(player.ft_freq * 100 * 2.5)} />
          </section>

          {/* Passing */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Passing / Ball Handling</h3>
            <StatBar label="Assist %"    value={fmtPct(player.ast_pct)}  pct={player.ast_pct_pct} />
            <StatBar label="Turnover %"  value={fmtPct(player.tov_pct)}  pct={Math.round((1 - player.tov_pct / 0.25) * 100)} />
          </section>

          {/* Defense */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Defense / Rebounding</h3>
            <StatBar label="Rebound %"  value={fmtPct(player.trb_pct)}  pct={player.trb_pct_pct} />
            <StatBar label="Block %"    value={fmtPct(player.blk_pct)}  pct={player.blk_pct_pct} />
            <StatBar label="Steal %"    value={fmtPct(player.stl_pct)}  pct={player.stl_pct_pct} />
          </section>
        </div>

        {/* Right col */}
        <div className={styles.rightCol}>

          {/* Projection chart */}
          <ProjectionChart player={player} />

          {/* Per-game projection breakdown */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Projected Per Game</h3>
            <div className={styles.projGrid}>
              <ProjStat label="PTS"   value={(player.proj_x2p_pg * 2 + player.proj_x3p_pg * 3 + player.proj_ft_pg).toFixed(1)} />
              <ProjStat label="REB"   value={player.proj_trb_pg.toFixed(1)} />
              <ProjStat label="AST"   value={player.proj_ast_pg.toFixed(1)} />
              <ProjStat label="3PM"   value={player.proj_x3p_pg.toFixed(1)} />
              <ProjStat label="FTM"   value={player.proj_ft_pg.toFixed(1)} />
              <ProjStat label="STL"   value={player.proj_stl_pg.toFixed(1)} />
              <ProjStat label="BLK"   value={player.proj_blk_pg.toFixed(1)} />
              <ProjStat label="TOV"   value={player.proj_tov_pg.toFixed(1)} neg />
            </div>
          </section>

          {/* 5-year table */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>5-Year Projection</h3>
            <FiveYearTable player={player} />
          </section>

        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function VitalRow({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.vitalRow}>
      <span className={styles.vitalLabel}>{label}</span>
      <span className={`${styles.vitalValue} mono`}>{value}</span>
    </div>
  );
}

function ProjStat({ label, value, neg }: { label: string; value: string; neg?: boolean }) {
  return (
    <div className={styles.projStat}>
      <span className={`${styles.projStatVal} mono`} style={{ color: neg ? "var(--bad)" : "var(--text)" }}>{value}</span>
      <span className={styles.projStatLabel}>{label}</span>
    </div>
  );
}

function FiveYearTable({ player }: { player: PlayerCard }) {
  const BASE = 2025;
  const rows = [1, 2, 3, 4, 5].map(i => ({
    year: `${BASE + i - 1}–${String(BASE + i).slice(2)}`,
    age:  player.age + i,
    proj: player[`proj_y${i}` as keyof PlayerCard] as number,
    lo:   player[`ci_lo_y${i}` as keyof PlayerCard] as number,
    hi:   player[`ci_hi_y${i}` as keyof PlayerCard] as number,
  }));

  const maxVal = Math.max(...rows.map(r => r.proj));

  return (
    <table className={styles.fiveYearTable}>
      <thead>
        <tr>
          <th>Season</th>
          <th>Age</th>
          <th>Proj</th>
          <th>Range</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.year}>
            <td className="mono">{r.year}</td>
            <td className="mono">{r.age}</td>
            <td className="mono" style={{ color: "var(--proj)", fontWeight: 500 }}>{r.proj.toFixed(1)}</td>
            <td className="mono" style={{ color: "var(--text3)", fontSize: "0.75rem" }}>
              {r.lo.toFixed(0)}–{r.hi.toFixed(0)}
            </td>
            <td>
              <div className={styles.miniBar}>
                <div className={styles.miniBarFill} style={{ width: `${(r.proj / (maxVal * 1.1)) * 100}%` }} />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
