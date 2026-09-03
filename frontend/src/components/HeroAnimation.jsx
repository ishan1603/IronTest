import { useEffect, useReducer, useRef, useState } from "react";

/*
  A faux run log that streams line by line, then loops. Pure CSS + one timer,
  no dependencies. Codex-flavoured: hairline frame, mono type, black and white,
  colour only on a test outcome. Honours prefers-reduced-motion by rendering
  the whole log at rest.
*/

const LINES = [
  { text: "$ irontest run  acme/checkout", kind: "cmd" },
  { text: "reading  src/billing/discount.py", kind: "dim" },
  { text: "reading  src/checkout/session.py", kind: "dim" },
  { text: "generating 6 tests against real modules", kind: "dim" },
  { text: "running in sandbox", kind: "dim" },
  { text: "PASS  test_TC_001_applies_percentage", kind: "pass" },
  { text: "PASS  test_TC_002_rejects_expired_code", kind: "pass" },
  { text: "PASS  test_TC_003_stacks_with_sale_price", kind: "pass" },
  { text: "FAIL  test_TC_004_rounds_half_up", kind: "fail" },
  { text: "      assert 4.005 == 4.01", kind: "fail-detail" },
  { text: "PASS  test_TC_005_zero_percent_is_noop", kind: "pass" },
  { text: "SKIP  test_TC_006_currency_conversion", kind: "skip" },
  { text: "", kind: "dim" },
  { text: "5 passed  1 failed  1 skipped   verdict: CONDITIONAL GO", kind: "verdict" },
];

const LINE_DELAY = 520;
const LOOP_PAUSE = 3200;

const TONE = {
  cmd: "text-ink",
  dim: "text-muted",
  pass: "text-success",
  fail: "text-danger",
  "fail-detail": "text-danger/80",
  skip: "text-muted",
  verdict: "text-ink font-medium",
};

function prefersReducedMotion() {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function HeroAnimation() {
  const reduced = prefersReducedMotion();
  const [count, setCount] = useState(reduced ? LINES.length : 0);
  const [, bump] = useReducer((n) => n + 1, 0);
  const timer = useRef(null);

  useEffect(() => {
    if (reduced) return undefined;

    function tick() {
      setCount((current) => {
        if (current >= LINES.length) {
          timer.current = setTimeout(() => {
            setCount(0);
            bump();
          }, LOOP_PAUSE);
          return current;
        }
        timer.current = setTimeout(tick, LINE_DELAY);
        return current + 1;
      });
    }

    timer.current = setTimeout(tick, LINE_DELAY);
    return () => clearTimeout(timer.current);
  }, [reduced, bump]);

  const done = count >= LINES.length;

  return (
    <div
      className="hairline overflow-hidden rounded-md bg-surface"
      role="img"
      aria-label="Example IronTest run: five tests pass, one fails on rounding, one is skipped."
    >
      <div className="flex items-center gap-1.5 border-b border-line/12 px-4 py-2.5">
        <span className="h-2 w-2 rounded-pill border border-line/30" />
        <span className="h-2 w-2 rounded-pill border border-line/30" />
        <span className="h-2 w-2 rounded-pill border border-line/30" />
        <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          irontest
        </span>
      </div>

      <div className="min-h-[19rem] px-4 py-4 font-mono text-xs leading-relaxed sm:text-[13px]">
        {LINES.slice(0, count).map((line, index) => (
          <div
            key={`${index}-${line.text}`}
            className={`whitespace-pre ${TONE[line.kind] || "text-muted"} ${
              reduced ? "" : "animate-fade-up"
            }`}
          >
            {line.text || " "}
          </div>
        ))}
        {!done && !reduced && (
          <span className="inline-block h-[1.05em] w-[0.55em] translate-y-[0.15em] animate-[blink_1s_step-end_infinite] bg-ink" />
        )}
      </div>
    </div>
  );
}
