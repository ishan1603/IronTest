import React from "react";

function pct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function EquationLine({ label, value }) {
  return (
    <div className="rounded-lg border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/20 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-gray-800 dark:text-gray-200">
        {value}
      </div>
    </div>
  );
}

export default function LearningEvidencePanel({ summary }) {
  if (!summary) {
    return null;
  }

  const novelty = Number(summary.novelty_ratio || 0);
  const targetedCoverage = Number(summary.targeted_coverage || 0);
  const resolutionRate = Number(summary.resolution_rate || 0);

  return (
    <div className="rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
      <div className="flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white mb-4">
        <span>🧬</span>
        <span>Learning Evidence</span>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4">
          <div className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Novelty Ratio
          </div>
          <div className="mt-1 text-2xl font-black text-emerald-700 dark:text-emerald-300">
            {pct(novelty)}
          </div>
          <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
            {summary.new_test_fingerprints || 0} new fingerprints out of{" "}
            {summary.current_total_tests || 0} tests.
          </p>
        </div>

        <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4">
          <div className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Targeted Coverage
          </div>
          <div className="mt-1 text-2xl font-black text-sky-700 dark:text-sky-300">
            {pct(targetedCoverage)}
          </div>
          <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
            Covered {summary.prior_failure_signatures_covered || 0} of{" "}
            {summary.prior_failure_signatures || 0} prior failure signatures.
          </p>
        </div>

        <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4">
          <div className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Resolution Rate
          </div>
          <div className="mt-1 text-2xl font-black text-fuchsia-700 dark:text-fuchsia-300">
            {pct(resolutionRate)}
          </div>
          <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
            {summary.resolved_recurring_failure_signatures || 0} previously
            failing signatures are now passing.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <EquationLine
          label="Current Test Mix"
          value={`${summary.baseline_tests || 0} baseline / ${summary.adaptive_tests || 0} adaptive`}
        />
        <EquationLine
          label="Failure-Targeted Tests"
          value={`${summary.failure_targeted_tests || 0} tests explicitly mapped to prior failure signatures`}
        />
      </div>

      {Array.isArray(summary.recurring_failure_signatures) &&
        summary.recurring_failure_signatures.length > 0 && (
          <div className="mt-4 rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4">
            <div className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">
              Recurring Failure Signatures
            </div>
            <div className="space-y-1">
              {summary.recurring_failure_signatures.map((item) => (
                <div
                  key={`${item.signature}-${item.count}`}
                  className="text-xs text-gray-700 dark:text-gray-300"
                >
                  {item.signature} ({item.count} runs)
                </div>
              ))}
            </div>
          </div>
        )}
    </div>
  );
}
