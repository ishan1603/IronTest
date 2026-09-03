import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { Spinner } from "./ui";

const BASE_STAGES = [
  { key: "story", label: "Story", hint: "Reads the requirement" },
  { key: "test", label: "Tests", hint: "Writes cases against your code" },
  { key: "execution", label: "Execution", hint: "Runs them in a sandbox" },
  { key: "defect", label: "Risk", hint: "Scores release confidence" },
];
const COMPARE_STAGE = { key: "compare", label: "Compare", hint: "Runs the suite on the base branch" };
const FIX_STAGE = { key: "fix", label: "Fixes", hint: "Drafts a change per failure" };

/**
 * Live view of the four agents.
 *
 * `stages` maps an agent key to "pending" | "running" | "done" | "failed".
 */
export function Pipeline({ stages, message }) {
  // The fix stage only exists on repo runs that had failures.
  let STAGES = BASE_STAGES;
  if (stages.compare) STAGES = [...STAGES.slice(0, 3), COMPARE_STAGE, ...STAGES.slice(3)];
  if (stages.fix) STAGES = [...STAGES, FIX_STAGE];

  return (
    <div className="hairline rounded-md p-4">
      <ol className={clsx("grid gap-3", {4:"sm:grid-cols-4",5:"sm:grid-cols-5",6:"sm:grid-cols-6"}[STAGES.length] || "sm:grid-cols-4")} role="list">
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
        "flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded-pill border font-mono text-[10px]",
        state === "done" && "border-transparent bg-contrast text-contrast-ink",
        state === "failed" && "border-danger text-danger",
        state === "pending" && "border-line/25 text-muted",
      )}
      aria-hidden="true"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={state}
          initial={{ scale: 0.4, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.4, opacity: 0 }}
          transition={{ type: "spring", stiffness: 600, damping: 26 }}
        >
          {state === "done" ? "✓" : state === "failed" ? "!" : index + 1}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
