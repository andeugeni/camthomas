"use client";

import { useState } from "react";
import dynamic from "next/dynamic";

const AboutModal = dynamic(() => import("./AboutModal"), { ssr: false });

export default function AboutButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        style={{
          position: "fixed",
          bottom: "1.25rem",
          right: "1.25rem",
          background: "var(--bg2, #0f1117)",
          border: "1px solid var(--border2, #2a2d3a)",
          color: "var(--text3, #64748b)",
          borderRadius: "8px",
          padding: "0.45rem 0.9rem",
          fontSize: "0.72rem",
          fontFamily: "inherit",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          cursor: "pointer",
          transition: "color 0.15s, border-color 0.15s",
          zIndex: 50,
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLButtonElement).style.color = "var(--text, #e2e8f0)";
          (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--proj, #8884d8)";
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLButtonElement).style.color = "var(--text3, #64748b)";
          (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border2, #2a2d3a)";
        }}
      >
        About CAMTHOMAS
      </button>
      {open && <AboutModal onClose={() => setOpen(false)} />}
    </>
  );
}