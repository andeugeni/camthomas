"use client";

import { useState } from "react";
import { PlayerCard } from "@/data/mockPlayers";
import {
  currentFantasyPts, perGame, trueShooting, ftPct,
  fmtPct, fmtNum, pctColor, shortTeam, shortPos, normaliseActual,
} from "@/data/playerUtils";
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import styles from "@/styles/PlayerCardView.module.css";

// ── Model type ────────────────────────────────────────────────────────────────

type ProjectionModel = "sps" | "carmelo";

function getProj(player: PlayerCard, model: ProjectionModel, i: number): number {
  if (model === "carmelo") {
    return (player[`carmelo_y${i}` as keyof PlayerCard] as number | null) ?? 0;
  }
  return (player[`proj_fpts_y${i}` as keyof PlayerCard] as number) ?? 0;
}

// ── ModelToggle ───────────────────────────────────────────────────────────────

function ModelToggle({ model, onChange }: {
  model: ProjectionModel;
  onChange: (m: ProjectionModel) => void;
}) {
  return (
    <div className={styles.modelToggle}>
      <button
        className={`${styles.modelBtn} ${model === "sps" ? styles.modelBtnActive : ""}`}
        onClick={() => onChange("sps")}
      >
        SPS
      </button>
      <button
        className={`${styles.modelBtn} ${model === "carmelo" ? styles.modelBtnActive : ""}`}
        onClick={() => onChange("carmelo")}
        disabled={player => !player?.carmelo_y1}
      >
        CARMELO
      </button>
    </div>
  );
}

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

function ProjectionChart({ player, model }: { player: PlayerCard; model: ProjectionModel }) {
  const BASE_YEAR = 2026;

  const ACTUAL_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026] as const;

  const actuals = ACTUAL_YEARS.map(yr => {
    const raw = player[`actual_fpts_${yr}` as keyof PlayerCard] as number | null;
    const val = raw != null ? normaliseActual(raw, player.g) : (yr === BASE_YEAR ? 0 : null);
    if (val === null) return null;
    return { year: String(yr), actual: val };
  }).filter((d): d is { year: string; actual: number } => d !== null);

  const projData = [1, 2, 3, 4, 5].map(i => ({
    year: String(BASE_YEAR + i),
    proj: getProj(player, model, i),
    lo:   player[`ci_lo_y${i}` as keyof PlayerCard] as number ?? 0,
    hi:   player[`ci_hi_y${i}` as keyof PlayerCard] as number ?? 0,
  }));

  const allYears = [
    ...ACTUAL_YEARS.map(String),
    ...projData.map(d => d.year),
  ].filter((y, i, arr) => arr.indexOf(y) === i);

  const actualMap = Object.fromEntries(actuals.map(d => [d.year, d.actual]));

  const combined = allYears.map(year => {
    const isProj = Number(year) > BASE_YEAR;
    const isBase = year === String(BASE_YEAR);
    const actual = actualMap[year] ?? null;
    const proj   = isProj ? (projData.find(d => d.year === year)?.proj ?? null) : isBase ? actual : null;
    const lo     = isProj ? (projData.find(d => d.year === year)?.lo   ?? null) : isBase ? actual : null;
    const hi     = isProj ? (projData.find(d => d.year === year)?.hi   ?? null) : isBase ? actual : null;
    return { year, actual, proj, lo, hi };
  });

  const allVals = [
    ...actuals.map(d => d.actual),
    ...projData.map(d => d.hi),
  ].filter(v => v != null && v > 0) as number[];
  const maxVal = Math.floor(allVals.length > 0 ? Math.max(...allVals) * 1.2 : 60);

  const projColor = model === "carmelo" ? "#a855f7" : "#8884d8";

  return (
    <div className={styles.chartWrap}>
      <div className={styles.chartHeader}>
        <span className={`${styles.chartTitle} cond`}>Fantasy Pts Projection</span>
        <div className={styles.chartLegend}>
          <span className={styles.legendActual}>— Actual</span>
          <span className={styles.legendProj} style={{ color: projColor }}>
            - - {model === "carmelo" ? "CARMELO" : "SPS"}
          </span>
          <span className={styles.legendCI}>CI</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={combined} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <defs>
            <linearGradient id="ciGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={projColor} stopOpacity={0.25} />
              <stop offset="95%" stopColor={projColor} stopOpacity={0.03} />
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
          <Area type="monotone" dataKey="hi" stroke="none" fill="url(#ciGrad)" connectNulls isAnimationActive={false} />
          <Area type="monotone" dataKey="lo" stroke="none" fill="url(#ciGrad)" connectNulls isAnimationActive={false} />
          <Area
            type="monotone" dataKey="actual"
            stroke="#2563eb" strokeWidth={3} fill="transparent"
            name="Actual" activeDot={{ r: 6 }} connectNulls
          />
          <Area
            type="monotone" dataKey="proj"
            stroke={projColor} strokeWidth={3} strokeDasharray="5 5"
            fill="transparent" name={model === "carmelo" ? "CARMELO" : "SPS"}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── CompSparkline ─────────────────────────────────────────────────────────────

function CompSparkline({ trajectory }: { trajectory: (number | null)[] }) {
  const labels = ["−3", "−2", "−1", "0", "+1", "+2", "+3"];
  const data = trajectory.map((v, i) => ({ x: labels[i], v }));
  const vals = trajectory.filter((v): v is number => v !== null && v > 0);
  const maxV = vals.length > 0 ? Math.max(...vals) : 30;

  return (
    <ResponsiveContainer width="100%" height={52}>
      <LineChart data={data} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
        <ReferenceLine x="0" stroke="var(--border2)" strokeDasharray="2 2" />
        <Line
          type="monotone" dataKey="v"
          stroke="var(--proj)" strokeWidth={1.5}
          dot={false} connectNulls isAnimationActive={false}
        />
        <YAxis domain={[0, Math.ceil(maxV * 1.15)]} hide />
        <XAxis dataKey="x" hide />
        <Tooltip
          contentStyle={{
            background: "var(--bg2)", border: "1px solid var(--border2)",
            borderRadius: 4, fontSize: 10, fontFamily: "DM Mono", padding: "2px 6px",
          }}
          labelStyle={{ color: "var(--text3)", fontSize: 9 }}
          itemStyle={{ color: "var(--text)" }}
          formatter={(val: number) => [val?.toFixed(1) ?? "—", "fpts/g"]}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── CompsSection ──────────────────────────────────────────────────────────────

export type PlayerComp = {
  rank: number;
  player: string;
  player_id: string;
  comp_year: number;
  comp_age: number;
  similarity: number;
  trajectory: (number | null)[];
};

function simColor(score: number): string {
  if (score >= 80) return "var(--good)";
  if (score >= 55) return "var(--avg, #f59e0b)";
  return "var(--text3)";
}

function CompsSection({ comps }: { comps: PlayerComp[] }) {
  if (!comps || comps.length === 0) return null;
  return (
    <section className={styles.section}>
      <h3 className={`${styles.sectionTitle} cond`}>10 Most Comparable Players</h3>
      <div className={styles.compGrid}>
        {comps.map((comp) => (
          <div key={comp.player_id + comp.comp_year} className={styles.compCard}>
            <div className={styles.compHeader}>
              <span className={styles.compRank}>{comp.rank}</span>
              <div className={styles.compMeta}>
                <span className={`${styles.compName} cond`}>{comp.player}</span>
                <span className={styles.compSub}>
                  YEAR: {comp.comp_year} · AGE: {comp.comp_age}
                </span>
              </div>
              <span
                className={`${styles.compSim} mono`}
                style={{ color: simColor(comp.similarity) }}
              >
                SIMILARITY SCORE: {comp.similarity.toFixed(0)}
              </span>
            </div>
            <CompSparkline trajectory={comp.trajectory} />
          </div>
        ))}
      </div>
    </section>
  );
}

// ── FiveYearTable ─────────────────────────────────────────────────────────────

function FiveYearTable({ player, model }: { player: PlayerCard; model: ProjectionModel }) {
  const baseYear = 2026;

  const rows = [1, 2, 3, 4, 5].map(i => ({
    season: `${baseYear + i - 1}–${String(baseYear + i).slice(2)}`,
    age:    player.age + (baseYear - (player.season ?? 2026)) + i,
    proj:   getProj(player, model, i),
    lo:     player[`ci_lo_y${i}` as keyof PlayerCard] as number ?? 0,
    hi:     player[`ci_hi_y${i}` as keyof PlayerCard] as number ?? 0,
  }));

  const maxVal = Math.max(...rows.map(r => r.proj), 1);
  const projColor = model === "carmelo" ? "#a855f7" : "var(--proj)";

  return (
    <table className={styles.fiveYearTable}>
      <thead>
        <tr><th>Season</th><th>Age</th><th>Proj</th><th>Range</th><th></th></tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.season}>
            <td className="mono">{r.season}</td>
            <td className="mono">{r.age}</td>
            <td className="mono" style={{ color: projColor, fontWeight: 500 }}>
              {r.proj > 0 ? r.proj.toFixed(1) : "—"}
            </td>
            <td className="mono" style={{ color: "var(--text3)", fontSize: "0.72rem" }}>
              {r.lo > 0 ? `${r.lo.toFixed(0)}–${r.hi.toFixed(0)}` : "—"}
            </td>
            <td>
              <div className={styles.miniBar}>
                <div
                  className={styles.miniBarFill}
                  style={{
                    width: `${(r.proj / (maxVal * 1.1)) * 100}%`,
                    background: projColor,
                  }}
                />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PlayerCardView({ player, comps }: {
  player: PlayerCard;
  comps?: PlayerComp[];
}) {
  const [model, setModel] = useState<ProjectionModel>("sps");

  const hasCarmelo = player.carmelo_y1 != null;

  const pg     = perGame(player);
  const fpts   = currentFantasyPts(player);
  const ts     = trueShooting(player);
  const ftPct_ = ftPct(player);
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
          {hasCarmelo && (
            <div className={styles.modelToggle}>
              <button
                className={`${styles.modelBtn} ${model === "sps" ? styles.modelBtnActive : ""}`}
                onClick={() => setModel("sps")}
              >
                SPS
              </button>
              <button
                className={`${styles.modelBtn} ${model === "carmelo" ? styles.modelBtnActive : ""}`}
                onClick={() => setModel("carmelo")}
              >
                CARMELO
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────── */}
      <div className={styles.body}>

        {/* ── Left col ─────────────────────────────────── */}
        <div className={styles.leftCol}>
          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Vitals</h3>
            <div className={styles.vitalGrid}>
              <VitalRow label="MPG"        value={fmtNum(player.mpg)} />
              <VitalRow label="Draft pick" value={player.draft_pick != null ? `#${player.draft_pick}` : "Undrafted"} />
            </div>
          </section>

          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Scoring</h3>
            <StatBar label="True Shoot %" value={fmtPct(ts)}             rank={player.ts_pct_rank ?? 50} />
            <StatBar label="Free Throw %" value={fmtPct(ftPct_)}         rank={player.ft_pct_rank ?? 50} />
            <StatBar label="Usage %"      value={fmtPct(player.usg_pct)} rank={player.usg_pct_rank ?? 50} />
          </section>

          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Tendencies</h3>
            <StatBar label="3PT Freq" value={fmtPct(player.x3_freq)} rank={player.x3_freq_rank ?? 50} />
            <StatBar label="FT Freq"  value={fmtPct(player.ft_freq)} rank={player.ft_freq_rank ?? 50} />
          </section>

          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Passing / Ball Handling</h3>
            <StatBar label="Assist %"   value={fmtPct(player.ast_pct)} rank={player.ast_pct_rank ?? 50} />
            <StatBar label="Turnover %" value={fmtPct(player.tov_pct)} rank={100 - (player.tov_pct_rank ?? 50)} />
          </section>

          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>Defense / Rebounding</h3>
            <StatBar label="Rebound %" value={fmtPct(player.trb_pct)} rank={player.trb_pct_rank ?? 50} />
            <StatBar label="Block %"   value={fmtPct(player.blk_pct)} rank={player.blk_pct_rank ?? 50} />
            <StatBar label="Steal %"   value={fmtPct(player.stl_pct)} rank={player.stl_pct_rank ?? 50} />
          </section>
        </div>

        {/* ── Right col ────────────────────────────────── */}
        <div className={styles.rightCol}>

          <ProjectionChart player={player} model={model} />

          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>This Season · Per Game</h3>
            <div className={styles.projGrid}>
              <ProjStat label="PTS" value={fmtNum(pts_pg)} />
              <ProjStat label="REB" value={fmtNum(pg.trb)} />
              <ProjStat label="AST" value={fmtNum(pg.ast)} />
              <ProjStat label="3PM" value={fmtNum(pg.x3p)} />
              <ProjStat label="FTM" value={fmtNum(pg.ft)} />
              <ProjStat label="STL" value={fmtNum(pg.stl)} />
              <ProjStat label="BLK" value={fmtNum(pg.blk)} />
              <ProjStat label="TOV" value={fmtNum(pg.tov)} neg />
            </div>
          </section>

          <section className={styles.section}>
            <h3 className={`${styles.sectionTitle} cond`}>
              5-Year Projection · Fpts/G
              {model === "carmelo" && (
                <span className={styles.modelBadge}>CARMELO</span>
              )}
            </h3>
            <FiveYearTable player={player} model={model} />
          </section>

          {comps && <CompsSection comps={comps} />}
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
      <span className={`${styles.projStatVal} mono`} style={{ color: neg ? "var(--bad)" : "var(--text)" }}>
        {value}
      </span>
      <span className={styles.projStatLabel}>{label}</span>
    </div>
  );
}