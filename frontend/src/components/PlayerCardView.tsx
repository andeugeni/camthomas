"use client";

import { PlayerCard } from "@/data/mockPlayers";
import {
  currentFantasyPts, perGame, trueShooting, ftPct,
  fmtPct, fmtNum, pctColor, shortTeam, shortPos, category, normaliseActual,
} from "@/data/playerUtils";
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import styles from "@/styles/PlayerCardView.module.css";

// ── StatBar ──────────────────────────────────────────────────────────────────

function StatBar({ label, value, rank }: {
  label: string; value: string; rank: number;
}) {
  const color = pctColor(rank);
  return (
    <div className={styles.statBar}>
      <span className={styles.statBarLabel}>{label}</span>
      <span className={`${styles.statBarValue} mono`}>{value}</span>
      <div className={styles.statBarTrack}>
        <div className={styles.statBarFill} style={{ width: `${rank}%`, background: color }} />
      </div>
      <span className={styles.dot} style={{ background: color }} />
    </div>
  );
}

// ── ProjectionChart ───────────────────────────────────────────────────────────

function ProjectionChart({ player }: { player: PlayerCard }) {
  const BASE_YEAR = player.season ?? 2025;
  const fpts = currentFantasyPts(player);

  // Historical actuals — normalise season totals → per-game
  const ACTUAL_YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] as const;
  const actuals = ACTUAL_YEARS.map(yr => {
    const raw = player[`actual_${yr}` as keyof PlayerCard] as number ?? 0;
    const val = normaliseActual(raw, player.g);
    return val > 0 ? { year: String(yr), actual: val } : null;
  }).filter(Boolean) as { year: string; actual: number }[];

  // Replace the current-year actual with computed fpts if it's 0
  const hasCurrentActual = actuals.some(a => a.year === String(BASE_YEAR));
  if (!hasCurrentActual && fpts > 0) {
    actuals.push({ year: String(BASE_YEAR), actual: fpts });
  }

  const projData = [1, 2, 3, 4, 5].map(i => ({
    year: String(BASE_YEAR + i),
    proj: player[`proj_y${i}` as keyof PlayerCard] as number ?? 0,
    lo:   player[`ci_lo_y${i}` as keyof PlayerCard] as number ?? 0,
    hi:   player[`ci_hi_y${i}` as keyof PlayerCard] as number ?? 0,
  }));

  // Bridge: last actual point also starts the proj line
  const lastActual = actuals[actuals.length - 1];
  const combined = [
    ...actuals.slice(0, -1).map(d => ({
      year: d.year, actual: d.actual,
      proj: null as number | null, lo: null as number | null, hi: null as number | null,
    })),
    lastActual ? {
      year: lastActual.year, actual: lastActual.actual,
      proj: lastActual.actual, lo: lastActual.actual, hi: lastActual.actual,
    } : { year: String(BASE_YEAR), actual: null, proj: null, lo: null, hi: null },
    ...projData.map(d => ({
      year: d.year, actual: null as number | null,
      proj: d.proj, lo: d.lo, hi: d.hi,
    })),
  ];

  const allVals = [
    ...actuals.map(d => d.actual),
    ...projData.map(d => d.hi),
  ].filter(v => v > 0);
  const maxVal = Math.floor(allVals.length > 0 ? Math.max(...allVals) * 1.2 : 60);

  console.log(combined)
  console.log(actuals)
  console.log(projData)

  return (
    <div className={styles.chartWrap}>
      <div className={styles.chartHeader}>
        <span className={`${styles.chartTitle} cond`}>Fantasy Pts Projection</span>
        <span className={styles.chartCategory}>{category(player.proj_y1 ?? 0)}</span>
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
              <stop offset="5%"  stopColor="var(--proj)" stopOpacity={0.25} />
              <stop offset="95%" stopColor="var(--proj)" stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="year"
            tick={{ fill: "var(--text3)", fontSize: 10, fontFamily: "DM Mono" }}
            axisLine={{ stroke: "var(--border)" }} tickLine={false}
          />
          <YAxis
            domain={[0, maxVal]}
            tick={{ fill: "var(--text3)", fontSize: 10, fontFamily: "DM Mono" }}
            axisLine={false} tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg2)", border: "1px solid var(--border2)",
              borderRadius: 6, fontSize: 11, fontFamily: "DM Mono",
            }}
            labelStyle={{ color: "var(--text2)" }}
            itemStyle={{ color: "var(--text)" }}
            formatter={(val: number) => val?.toFixed(1) ?? "—"}
          />
          <ReferenceLine x={String(BASE_YEAR)} stroke="var(--border2)" strokeDasharray="3 3" />
          <Area type="monotone" dataKey="hi" stroke="none" fill="url(#ciGrad)" isAnimationActive={false} />
          {/* <Line
            type="linear" dataKey="proj"
            stroke="#8a95a3" strokeWidth={1.5}
            dot={{ r: 2.5, fill: "#8a95a3", strokeWidth: 0 }}
            activeDot={{ r: 4, fill: "#3b7eff" }}
            connectNulls={true} isAnimationActive={false}
          /> */}
          <Area
            type="monotone"
            dataKey="actual"
            stroke="#2563eb"
            strokeWidth={3}
            fill="transparent"
            name="Actual"
            activeDot={{ r: 6 }}
          />

          {/* 3. Projected Line (Starts at 2025) */}
          <Area
            type="monotone"
            dataKey="proj"
            stroke="#8884d8"
            strokeWidth={3}
            strokeDasharray="5 5"
            fill="transparent"
            name="Projected"
          />
          {/* <Line
            type="linear" dataKey="proj"
            stroke="#a78bfa" strokeWidth={1.5} strokeDasharray="5 3"
            dot={{ r: 2.5, fill: "#a78bfa", strokeWidth: 0 }}
            activeDot={{ r: 4 }}
            connectNulls={true} isAnimationActive={false}
          /> */}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PlayerCardView({ player }: { player: PlayerCard }) {
  const pg    = perGame(player);
  const fpts  = currentFantasyPts(player);
  const ts    = trueShooting(player);
  const ftPct_ = ftPct(player);

  // Points per game from raw: (x2p*2 + x3p*3 + ft*1) / g
  const pts_pg = pg.pts;

  return (
    <div className={`${styles.card} fade-up`}>

      {/* ── Header ───────────────────────────────────────── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={`${styles.playerName} cond`}>{player.player}</h1>
          <div className={styles.headerMeta}>
            <span className={styles.team}>{shortTeam(player.tm)}</span>
            <span className={styles.sep}>·</span>
            <span className={styles.pos}>{shortPos(player.pos)}</span>
            <span className={styles.sep}>·</span>
            <span className={styles.age}>{player.age} YRS</span>
            <span className={styles.sep}>·</span>
            <span className={styles.age}>{player.g} G</span>
          </div>
        </div>
        <div className={styles.headerRight}>
          <div className={styles.bigStat}>
            <span className={`${styles.bigStatVal} mono`}>{fpts.toFixed(1)}</span>
            <span className={styles.bigStatLabel}>fpts / game</span>
          </div>
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────── */}
      <div className={styles.body}>

        {/* ── Left col ─────────────────────────────────── */}
        <div className={styles.leftCol}>

          {/* Vitals */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Vitals</h3>
            <div className={styles.vitalGrid}>
              <VitalRow label="MPG"        value={fmtNum(player.mpg)} />
              <VitalRow label="Draft pick" value={player.draft_pick != null ? `#${player.draft_pick}` : "Undrafted"} />
            </div>
          </section>

          {/* Scoring */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Scoring</h3>
            <StatBar
              label="True Shoot %"
              value={fmtPct(ts)}
              rank={player.ts_pct_rank ?? 50}
            />
            <StatBar
              label="Free Throw %"
              value={fmtPct(ftPct_)}
              rank={player.ft_pct_rank ?? 50}
            />
            <StatBar
              label="Usage %"
              value={fmtPct(player.usg_pct)}
              rank={player.usg_pct_rank ?? 50}
            />
          </section>

          {/* Tendencies */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Tendencies</h3>
            <StatBar
              label="3PT Freq"
              value={fmtPct(player.x3_freq)}
              rank={player.x3_freq_rank ?? 50}
            />
            <StatBar
              label="FT Freq"
              value={fmtPct(player.ft_freq)}
              rank={player.ft_freq_rank ?? 50}
            />
          </section>

          {/* Passing */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Passing / Ball Handling</h3>
            <StatBar
              label="Assist %"
              value={fmtPct(player.ast_pct)}
              rank={player.ast_pct_rank ?? 50}
            />
            <StatBar
              label="Turnover %"
              value={fmtPct(player.tov_pct)}
              rank={100 - (player.tov_pct_rank ?? 50)}  // lower TOV = better
            />
          </section>

          {/* Defense */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Defense / Rebounding</h3>
            <StatBar
              label="Rebound %"
              value={fmtPct(player.trb_pct)}
              rank={player.trb_pct_rank ?? 50}
            />
            <StatBar
              label="Block %"
              value={fmtPct(player.blk_pct)}
              rank={player.blk_pct_rank ?? 50}
            />
            <StatBar
              label="Steal %"
              value={fmtPct(player.stl_pct)}
              rank={player.stl_pct_rank ?? 50}
            />
          </section>
        </div>

        {/* ── Right col ────────────────────────────────── */}
        <div className={styles.rightCol}>

          <ProjectionChart player={player} />

          {/* Per-game this season */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>This Season · Per Game</h3>
            <div className={styles.projGrid}>
              <ProjStat label="PTS"  value={fmtNum(pts_pg)} />
              <ProjStat label="REB"  value={fmtNum(pg.trb)} />
              <ProjStat label="AST"  value={fmtNum(pg.ast)} />
              <ProjStat label="3PM"  value={fmtNum(pg.x3p)} />
              <ProjStat label="FTM"  value={fmtNum(pg.ft)} />
              <ProjStat label="STL"  value={fmtNum(pg.stl)} />
              <ProjStat label="BLK"  value={fmtNum(pg.blk)} />
              <ProjStat label="TOV"  value={fmtNum(pg.tov)} neg />
            </div>
          </section>

          {/* 5-year table */}
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>5-Year Projection · Fpts/G</h3>
            <FiveYearTable player={player} baseYear={player.season ?? 2025} />
          </section>

        </div>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

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
      <span
        className={`${styles.projStatVal} mono`}
        style={{ color: neg ? "var(--bad)" : "var(--text)" }}
      >
        {value}
      </span>
      <span className={styles.projStatLabel}>{label}</span>
    </div>
  );
}

function FiveYearTable({ player, baseYear }: { player: PlayerCard; baseYear: number }) {
  const rows = [1, 2, 3, 4, 5].map(i => ({
    season: `${baseYear + i - 1}–${String(baseYear + i).slice(2)}`,
    age:    player.age + i,
    proj:   player[`proj_y${i}` as keyof PlayerCard] as number ?? 0,
    lo:     player[`ci_lo_y${i}` as keyof PlayerCard] as number ?? 0,
    hi:     player[`ci_hi_y${i}` as keyof PlayerCard] as number ?? 0,
  }));

  const maxVal = Math.max(...rows.map(r => r.proj), 1);

  return (
    <table className={styles.fiveYearTable}>
      <thead>
        <tr>
          <th>Season</th><th>Age</th><th>Proj</th><th>Range</th><th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.season}>
            <td className="mono">{r.season}</td>
            <td className="mono">{r.age}</td>
            <td className="mono" style={{ color: "var(--proj)", fontWeight: 500 }}>
              {r.proj > 0 ? r.proj.toFixed(1) : "—"}
            </td>
            <td className="mono" style={{ color: "var(--text3)", fontSize: "0.72rem" }}>
              {r.lo > 0 ? `${r.lo.toFixed(0)}–${r.hi.toFixed(0)}` : "—"}
            </td>
            <td>
              <div className={styles.miniBar}>
                <div
                  className={styles.miniBarFill}
                  style={{ width: `${(r.proj / (maxVal * 1.1)) * 100}%` }}
                />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
