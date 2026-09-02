import clsx from "clsx";
import { Spinner } from "./ui";

const STAGES = [
  { key: "story", label: "Story", hint: "Reads the requirement" },
  { key: "test", label: "Tests", hint: "Writes cases against your code" },
  { key: "execution", label: "Execution", hint: "Runs them in a sandbox" },
  { key: "defect", label: "Risk", hint: "Scores release confidence" },
];

/**
 * Live view of the four agents.
 *
 * `stages` maps an agent key to "pending" | "running" | "done" | "failed".
 */
export function Pipeline({ stages, message }) {
  return (
    <div className="hairline rounded-md p-4">
      <ol className="grid gap-3 sm:grid-cols-4" role="list">
        {STAGES.map((stage, index) => {
          const state = stages[stage.key] || "pending";
          return (
            <li key={stage.key} className="flex gap-3 sm:flex-col sm:gap-2">
              <div className="flex items-center gap-2 sm:w-full">
                <StageMark state={state} index={index} />
                {/* Connector between stages, horizontal on desktop only. */}
                <span
                  aria-hidden="true"
                  className={clsx(
                    "hidden h-px flex-1 sm:block",
                    state === "done" ? "bg-line/40" : "bg-line/12",
                    index === STAGES.length - 1 && "sm:hidden",
                  )}
                />
              </div>
              <div className="min-w-0">
                <p
                  className={clsx(
                    "text-sm font-medium",
                    state === "pending" ? "text-muted" : "text-ink",
                  )}
                >
                  {stage.label}
                </p>
                <p className="text-xs text-muted">{stage.hint}</p>
              </div>
            </li>
          );
        })}
      </ol>
      {message && (
        <p className="mt-4 border-t border-line/12 pt-3 font-mono text-xs text-muted" aria-live="polite">
          {message}
        </p>
      )}
    </div>
  );
}

function StageMark({ state, index }) {
  if (state === "running") return <Spinner className="h-5 w-5 shrink-0" />;

  return (
    <span
      className={clsx(
        "flex h-5 w-5 shrink-0 items-center justify-center rounded-pill border font-mono text-[10px]",
        state === "done" && "border-transparent bg-contrast text-contrast-ink",
        state === "failed" && "border-danger text-danger",
        state === "pending" && "border-line/25 text-muted",
      )}
      aria-hidden="true"
    >
      {state === "done" ? "✓" : state === "failed" ? "!" : index + 1}
    </span>
  );
}
