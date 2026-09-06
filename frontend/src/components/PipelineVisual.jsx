import { useEffect, useState } from "react";
import clsx from "clsx";
import { Crosshair, Tick } from "./motifs";

/*
  The schematic beside the pinned step list. Each stage draws what that agent
  actually does, so the panel carries meaning rather than being decoration.
  Pure CSS transitions on a small fixed dataset; nothing heavy runs per frame.
*/

const FILES = [
  "src/billing/discount.py",
  "src/checkout/session.py",
  "src/pricing/rules.py",
  "src/auth/tokens.py",
  "src/orders/repository.py",
];

const SYMBOLS = ["apply_discount(total, pct)", "class PricingEngine", "validate_code(code)", "Session.total()"];

const CASES = [
  { id: "TC-001", label: "applies percentage discount", status: "pass" },
  { id: "TC-002", label: "rejects an expired code", status: "pass" },
  { id: "TC-003", label: "never drops below zero", status: "fail" },
  { id: "TC-004", label: "stacks with a sale price", status: "pass" },
];

const RISKS = [
  { module: "Billing", level: 0.72 },
  { module: "Checkout", level: 0.34 },
  { module: "Auth", level: 0.12 },
];

export function PipelineVisual({ step = 1, className }) {
  // A slow tick drives the scan line and the streaming rows.
  const [beat, setBeat] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    const id = setInterval(() => setBeat((b) => b + 1), 620);
    return () => clearInterval(id);
  }, []);

  return (
    <div className={clsx("relative", className)}>
      <div className="bracketed relative min-h-[300px] rounded-md bg-surface/40 p-5 sm:min-h-[340px]">
        <div className="mb-4 flex items-center justify-between">
          <span className="label-caps">
            {["Reading", "Generating", "Executing", "Assessing"][step - 1]}
          </span>
          <Crosshair size={12} />
        </div>

        {step === 1 && <ReadStage beat={beat} />}
        {step === 2 && <WriteStage beat={beat} />}
        {step === 3 && <RunStage beat={beat} />}
        {step === 4 && <RiskStage />}
      </div>
    </div>
  );
}

function Row({ children, lit, className }) {
  return (
    <div
      className={clsx(
        "flex items-center gap-2 rounded-sm px-2 py-1.5 font-mono text-[11px] transition-all duration-500",
        lit ? "bg-accent/10 text-ink" : "text-muted",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Files scanning, one highlighted at a time. */
function ReadStage({ beat }) {
  const cursor = beat % FILES.length;
  return (
    <div className="flex flex-col gap-1">
      {FILES.map((file, i) => (
        <Row key={file} lit={i === cursor}>
          <Tick height={i === cursor ? 12 : 8} className={i === cursor ? "" : "opacity-25"} />
          <span className="truncate">{file}</span>
          {i === cursor && <span className="ml-auto text-accent">scanning</span>}
        </Row>
      ))}
    </div>
  );
}

/** Extracted symbols accumulating into generated cases. */
function WriteStage({ beat }) {
  const shown = (beat % (SYMBOLS.length + 1)) + 1;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5">
        {SYMBOLS.slice(0, shown).map((symbol) => (
          <span
            key={symbol}
            className="animate-fade-up rounded-pill border border-accent/30 px-2 py-0.5 font-mono text-[10px] text-accent"
          >
            {symbol}
          </span>
        ))}
      </div>
      <div className="flex flex-col gap-1 border-t border-line/10 pt-3">
        {CASES.slice(0, Math.max(1, shown)).map((c) => (
          <Row key={c.id} lit>
            <span className="text-accent">{c.id}</span>
            <span className="truncate text-muted">{c.label}</span>
          </Row>
        ))}
      </div>
    </div>
  );
}

/** Results streaming in, with real-looking outcomes. */
function RunStage({ beat }) {
  const shown = (beat % (CASES.length + 1)) + 1;
  return (
    <div className="flex flex-col gap-1">
      {CASES.slice(0, shown).map((c) => (
        <Row key={c.id} lit className="animate-fade-up">
          <span
            className={clsx(
              "h-1.5 w-1.5 shrink-0 rounded-pill",
              c.status === "pass" ? "bg-accent" : "bg-danger",
            )}
          />
          <span className={c.status === "pass" ? "text-accent" : "text-danger"}>
            {c.status.toUpperCase()}
          </span>
          <span className="truncate text-muted">{c.id}</span>
        </Row>
      ))}
      {shown > CASES.length - 1 && (
        <p className="mt-2 font-mono text-[11px] text-muted">
          3 passed · <span className="text-danger">1 failed</span> · 1.9s
        </p>
      )}
    </div>
  );
}

/** Module risk bars plus the verdict. */
function RiskStage() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2.5">
        {RISKS.map((r, i) => (
          <div key={r.module}>
            <div className="flex justify-between font-mono text-[10px] text-muted">
              <span>{r.module}</span>
              <span>{Math.round(r.level * 100)}%</span>
            </div>
            <div className="mt-1 h-1 w-full overflow-hidden rounded-pill bg-line/10">
              <div
                className={clsx("h-full rounded-pill", r.level > 0.5 ? "bg-danger" : "bg-accent")}
                style={{
                  width: `${r.level * 100}%`,
                  transition: `width 700ms ${i * 120}ms cubic-bezier(0.22,1,0.36,1)`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div className="rounded-md border border-warning/30 px-3 py-2">
        <p className="font-mono text-[10px] uppercase tracking-wider text-warning">Conditional go</p>
        <p className="mt-1 text-[11px] text-muted">
          One checkout case fails. Fix suggested in <span className="text-ink">pricing/rules.py</span>.
        </p>
      </div>
    </div>
  );
}
