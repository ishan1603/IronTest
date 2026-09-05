import clsx from "clsx";

/*
  The ambient vocabulary: neon ticks, corner brackets, crosshairs, and tick
  strips. Purely decorative, so everything here is aria-hidden and none of it
  animates unless the page explicitly drives it.
*/

/** A single vertical neon bar. The signature mark of the system. */
export function Tick({ height = 28, className, style }) {
  return (
    <span
      aria-hidden="true"
      className={clsx("tick", className)}
      style={{ height, ...style }}
    />
  );
}

/**
 * Ticks scattered at fixed positions. Deterministic, not random, so the
 * layout is stable between renders and across reloads.
 */
const SCATTER = [
  { top: "12%", left: "4%", h: 46 },
  { top: "38%", left: "9%", h: 26 },
  { top: "68%", left: "3%", h: 34 },
  { top: "18%", right: "7%", h: 30 },
  { top: "52%", right: "3.5%", h: 52 },
  { top: "78%", right: "11%", h: 22 },
  { top: "28%", left: "46%", h: 20 },
];

export function TickField({ className }) {
  return (
    <div aria-hidden="true" className={clsx("pointer-events-none absolute inset-0", className)}>
      {SCATTER.map((t, i) => (
        <Tick
          key={i}
          height={t.h}
          className="absolute animate-tick-pulse"
          style={{
            top: t.top,
            left: t.left,
            right: t.right,
            animationDelay: `${i * 0.28}s`,
          }}
        />
      ))}
    </div>
  );
}

/** The equalizer strip that runs along a section edge. */
export function TickStrip({ count = 64, className }) {
  return (
    <div
      aria-hidden="true"
      className={clsx("flex items-end gap-[3px] overflow-hidden", className)}
    >
      {Array.from({ length: count }).map((_, i) => {
        // A fixed pseudo-random shape: stable, no Math.random on every render.
        const h = 6 + ((i * 37) % 17);
        const lit = i % 7 === 0 || i % 11 === 0;
        return (
          <span
            key={i}
            className={clsx("w-[3px] shrink-0 rounded-[1px]", lit ? "bg-accent" : "bg-line/20")}
            style={{ height: h, boxShadow: lit ? "0 0 8px rgb(var(--accent)/0.7)" : undefined }}
          />
        );
      })}
    </div>
  );
}

/** Small `+` registration mark. */
export function Crosshair({ className, size = 14 }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 14 14"
      className={clsx("text-line/40", className)}
    >
      <path d="M7 0v14M0 7h14" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

/** Framing brackets at all four corners of a block. */
export function Brackets({ className, inset = 0 }) {
  const common = "absolute h-4 w-4 border-line/30";
  return (
    <div aria-hidden="true" className={clsx("pointer-events-none absolute inset-0", className)}>
      <span className={clsx(common, "border-l border-t")} style={{ top: inset, left: inset }} />
      <span className={clsx(common, "border-r border-t")} style={{ top: inset, right: inset }} />
      <span className={clsx(common, "border-b border-l")} style={{ bottom: inset, left: inset }} />
      <span className={clsx(common, "border-b border-r")} style={{ bottom: inset, right: inset }} />
    </div>
  );
}

/** `02 ▮▮▮▯▯▯ 04` progress meter from the reference's step sequence. */
export function StepMeter({ step, total, className }) {
  const segments = 28;
  const filled = Math.round((step / total) * segments);
  return (
    <div className={clsx("flex items-center gap-3", className)}>
      <span className="font-mono text-sm tabular-nums">{String(step).padStart(2, "0")}</span>
      <div aria-hidden="true" className="flex flex-1 items-center gap-[3px]">
        {Array.from({ length: segments }).map((_, i) => (
          <span
            key={i}
            className={clsx(
              "h-3 w-[3px] rounded-[1px] transition-colors duration-300",
              i < filled ? "bg-accent" : "bg-line/20",
            )}
            style={i < filled ? { boxShadow: "0 0 6px rgb(var(--accent)/0.6)" } : undefined}
          />
        ))}
      </div>
      <span className="font-mono text-sm tabular-nums text-muted">
        {String(total).padStart(2, "0")}
      </span>
    </div>
  );
}

/** Endless horizontal ticker. Duplicated once so the loop is seamless. */
export function Marquee({ items, className }) {
  const row = [...items, ...items];
  return (
    <div aria-hidden="true" className={clsx("relative flex overflow-hidden", className)}>
      <div className="flex shrink-0 animate-marquee gap-8 pr-8">
        {row.map((item, i) => (
          <span key={i} className="flex shrink-0 items-center gap-8 whitespace-nowrap">
            <span>{item}</span>
            <Tick height={14} />
          </span>
        ))}
      </div>
    </div>
  );
}
