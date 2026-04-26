"use client";

import { useEffect, useRef } from "react";
import styles from "@/styles/AboutModal.module.css";

export default function AboutModal({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    ref.current?.showModal();
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  return (
    <dialog ref={ref} className={styles.dialog} onClick={e => { if (e.target === ref.current) onClose(); }}>
      <div className={styles.inner}>
        <button className={styles.close} onClick={onClose} aria-label="Close">✕</button>

        <h1 className={`${styles.title} cond`}>I&apos;m Sick of Losing at Fantasy Sports.</h1>

        <p>
          That&apos;s why I built <strong>CAMTHOMAS</strong> — a backronym for{" "}
          <em>Career Arc Model for Tracking Historical Outputs, Mapping Athletic Statistics</em>.
          It&apos;s a silly-goofy project inspired by the now-defunct FiveThirtyEight (ABC, I will
          never forgive you) and its career projection model{" "}
          <a href="https://fivethirtyeight.com/features/how-were-predicting-nba-player-career/" target="_blank" rel="noreferrer">
            CARMELO
          </a>
          . CARMELO&apos;s premise is simple: for each current NBA player, find similar players
          throughout modern NBA history and use their careers to forecast the future.
        </p>

        <p>
          CARMELO cares about player <em>value</em>. I don&apos;t. I care about winning my fantasy
          leagues. So while those nerds obsess over impact and advanced stats, degenerates like me
          care about counting stats we can attempt to monetize before inevitably losing to the same
          guy in all our leagues at once.
        </p>

        <h2 className={`${styles.step} cond`}>(1) Define the Player</h2>
        <p>
          Biographical info (height, weight, draft position) comes from Ball Don&apos;t Lie.
          Stats come from Basketball Reference. Advanced stats are collected too — but the{" "}
          <a href="https://fivethirtyeight.com/features/how-were-predicting-nba-player-career/" target="_blank" rel="noreferrer">
            FiveThirtyEight nerds
          </a>{" "}
          have already written about advanced stats extensively. Moving on.
        </p>

        <h2 className={`${styles.step} cond`}>(2) Identify Comparisons</h2>
        <p>
          Stats and bio data combine into a player profile, which gets compared against every
          player in the modern NBA era. Take Keegan Murray — historically good shooter, recently
          inconsistent, solid defensive wing. His top historical comps at age 25 include Danny
          Granger, Jeff Green, and Al-Farouq Aminu (I swear he was cash from three on 2K). Not
          exactly a ceiling of greatness. Frankly, neither is Murray&apos;s. Light the beam, I
          guess.
        </p>

        <h2 className={`${styles.step} cond`}>(3) Generate Projections</h2>
        <p>
          Prior stats for comparable players feed into SPS and minute projections, mapping
          potential in-game stats into fantasy PPG. These original vectors are style-agnostic.
          But we also look at how historical comps performed <em>against</em> their SPS baseline
          to inform what&apos;s likely to happen to our guy.
        </p>
        <p>
          Take De&apos;Aaron Fox (sad light the beam) — a hyper-athletic guard nearing his probable peak. Two of his
          top-four comps are Kemba Walker and Grant Hill: players who fell off a cliff. The
          system predicts a player of his profile is likely to hit a wall, perhaps injury-related.
          Knock on wood. Other players may have similar potential quirks tying them to players
          of the past.
        </p>

        <h2 className={`${styles.step} cond`}>Does Cam Thomas Get a Good CAMTHOMAS Projection?</h2>
        <p>
          No. Not really. Inefficient chuckers with no defense aren&apos;t exactly darlings of
          projection systems. Why did I give up James Harden and Zubac for him and a first?
          Because I&apos;m stupid. That&apos;s why.
        </p>
      </div>
    </dialog>
  );
}