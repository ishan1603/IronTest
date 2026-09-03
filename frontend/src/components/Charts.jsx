import { useEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";
import { Card, Label } from "./ui";

/*
  Hand-rolled SVG, no chart library. Codex-flavoured: hairline axes, one ink
  stroke, colour only where it means something. Everything animates in on
  scroll and respects reduced-motion.
*/

/** Animated integer / percentage that counts up when it scrolls into view. */
export function CountUp({ value, suffix = "", decimals = 0, className }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);

  useEffect(() => {
    if (!inView || reduce) {
      setShown(value);
      return undefined;
    }
    const start = performance.now();
    const duration = 700;
    let raf = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      // easeOutCubic
      setShown(value * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, value, reduce]);

  return (
    <span ref={ref} className={className}>
      {shown.toFixed(decimals)}
      {suffix}
    </span>
  );
}

export function StatTile({ label, value, suffix = "", decimals = 0, sub }) {
  return (
    <Card className="p-4">
      <Label>{label}</Label>
      <p className="mt-2 text-2xl font-semibold tabular-nums">
        <CountUp value={value} suffix={suffix} decimals={decimals} />
      </p>
      {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
    </Card>
  );
}

/**
 * Dual-line trend: pass rate (0-1) as the ink line, confidence (0-100) as a
 * lighter dashed line on a second scale. `points` is oldest-first.
 */
export function TrendChart({ points, height = 160 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduce = useReducedMotion();

  if (!points || points.length < 2) {
    return (
      <Card className="p-5">
        <Label>Trend</Label>
        <p className="mt-3 text-sm text-muted">
          Two or more completed runs are needed to plot a trend.
        </p>
      </Card>
    );
  }

  const w = 640;
  const h = height;
  const padX = 8;
  const padY = 14;
  const n = points.length;
  const x = (i) => padX + (i / (n - 1)) * (w - padX * 2);
  const yRate = (v) => padY + (1 - v) * (h - padY * 2);
  const yConf = (v) => padY + (1 - (v ?? 0) / 100) * (h - padY * 2);

  const line = (accessor, y) =>
    points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(accessor(p)).toFixed(1)}`).join(" ");

  const ratePath = line((p) => p.pass_rate, yRate);
  const confPath = line((p) => p.confidence, yConf);

  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <Label>Pass rate &amp; confidence over time</Label>
        <span className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-wider text-muted">
          <span className="flex items-center gap-1">
            <span className="h-px w-4 bg-ink" /> pass rate
          </span>
          <span className="flex items-center gap-1">
            <span className="h-px w-4 border-t border-dashed border-muted" /> confidence
          </span>
        </span>
      </div>

      <svg ref={ref} viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Trend chart">
        {[0, 0.25, 0.5, 0.75, 1].map((g) => (
          <line key={g} x1={padX} x2={w - padX} y1={yRate(g)} y2={yRate(g)} className="stroke-line/10" strokeWidth="1" />
        ))}
        <motion.path
          d={confPath}
          fill="none"
          className="stroke-muted"
          strokeWidth="1.5"
          strokeDasharray="4 4"
          initial={reduce ? false : { pathLength: 0 }}
          animate={inView ? { pathLength: 1 } : {}}
          transition={{ duration: 0.9, ease: "easeInOut" }}
        />
        <motion.path
          d={ratePath}
          fill="none"
          className="stroke-ink"
          strokeWidth="2"
          strokeLinecap="round"
          initial={reduce ? false : { pathLength: 0 }}
          animate={inView ? { pathLength: 1 } : {}}
          transition={{ duration: 1, ease: "easeInOut" }}
        />
        {points.map((p, i) => (
          <motion.circle
            key={p.run_id || i}
            cx={x(i)}
            cy={yRate(p.pass_rate)}
            r="2.5"
            className="fill-ink"
            initial={reduce ? false : { opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ delay: 0.6 + i * 0.02 }}
          />
        ))}
      </svg>

      <div className="mt-2 flex justify-between font-mono text-[10px] text-muted">
        <span>{new Date(points[0].at).toLocaleDateString()}</span>
        <span>{new Date(points[n - 1].at).toLocaleDateString()}</span>
      </div>
    </Card>
  );
}

/** Horizontal bars for a labelled list of ratios (0-1). */
export function BarList({ title, rows, valueKey = "value", labelKey = "label", format }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });

  if (!rows || rows.length === 0) return null;
  const max = Math.max(...rows.map((r) => r[valueKey]), 0.0001);

  return (
    <Card className="p-5" ref={ref}>
      <Label>{title}</Label>
      <ul className="mt-3 flex flex-col gap-2.5">
        {rows.map((row, i) => (
          <li key={row[labelKey] || i} className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm">{row[labelKey]}</p>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-pill bg-line/10">
                <motion.div
                  className="h-full rounded-pill bg-ink"
                  initial={{ width: 0 }}
                  animate={inView ? { width: `${(row[valueKey] / max) * 100}%` } : {}}
                  transition={{ duration: 0.6, delay: i * 0.04, ease: "easeOut" }}
                />
              </div>
            </div>
            <span className="font-mono text-xs text-muted">
              {format ? format(row) : row[valueKey]}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
