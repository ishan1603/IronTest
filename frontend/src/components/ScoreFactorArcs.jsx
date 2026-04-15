import React from "react";
import clsx from "clsx";
import { PolarAngleAxis, RadialBar, RadialBarChart } from "recharts";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function pct(value) {
  return `${Number(value || 0).toFixed(0)}%`;
}

export default function ScoreFactorArcs({ scoreBreakdown }) {
  if (!scoreBreakdown) {
    return null;
  }

  const items = [
    {
      key: "final",
      title: "Final Score",
      value: clamp(Number(scoreBreakdown.final_score || 0), 0, 100),
      display: `${scoreBreakdown.final_score || 0}`,
      color: "#10b981",
      note: "Final release confidence after blending AI signal, current run quality, history, and penalties.",
    },
    {
      key: "ai",
      title: "AI Signal",
      value: clamp(Number(scoreBreakdown.llm_score || 0), 0, 100),
      display: `${scoreBreakdown.llm_score || 0}`,
      color: "#3b82f6",
      note: "Model-derived risk confidence from story intent, test vectors, and execution traces.",
    },
    {
      key: "current",
      title: "Current Run",
      value: clamp(Number(scoreBreakdown.current_score || 0), 0, 100),
      display: `${scoreBreakdown.current_score || 0}`,
      color: "#14b8a6",
      note: `Mapped from current pass rate (${pct((scoreBreakdown.current_pass_rate || 0) * 100)}).`,
    },
    {
      key: "historical",
      title: "Historical",
      value: clamp(Number(scoreBreakdown.historical_score || 0), 0, 100),
      display: `${scoreBreakdown.historical_score || 0}`,
      color: "#8b5cf6",
      note: `Baseline from prior runs (avg ${pct((scoreBreakdown.historical_average_pass_rate || 0) * 100)}).`,
    },
    {
      key: "exec_penalty",
      title: "Execution Penalty",
      value: clamp(
        (Number(scoreBreakdown.execution_penalty || 0) / 40) * 100,
        0,
        100,
      ),
      display: `-${scoreBreakdown.execution_penalty || 0}`,
      color: "#ef4444",
      note: "Penalty from failed/error/skipped tests in this run; larger penalty lowers final confidence.",
      negative: true,
    },
    {
      key: "risk_penalty",
      title: "Risk Penalty",
      value: clamp(
        (Number(scoreBreakdown.module_risk_penalty || 0) / 18) * 100,
        0,
        100,
      ),
      display: `-${scoreBreakdown.module_risk_penalty || 0}`,
      color: "#f59e0b",
      note: "Penalty from module-level defect probability and regression-risk concentration.",
      negative: true,
    },
  ];

  return (
    <div className="rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-bold tracking-widest uppercase text-gray-500 dark:text-gray-400">
          Score Factor Breakdown
        </h3>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <div
            key={item.key}
            className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4"
          >
            <div className="flex items-center justify-between">
              <div className="text-xs font-black uppercase tracking-wider text-gray-600 dark:text-gray-300">
                {item.title}
              </div>
              <div
                className={clsx(
                  "text-xs font-black",
                  item.negative
                    ? "text-red-600 dark:text-red-300"
                    : "text-emerald-700 dark:text-emerald-300",
                )}
              >
                {item.display}
              </div>
            </div>

            <div className="mt-2 flex items-center gap-3">
              <RadialBarChart
                width={74}
                height={74}
                cx={37}
                cy={37}
                innerRadius={20}
                outerRadius={32}
                data={[
                  { name: item.title, value: item.value, fill: item.color },
                ]}
                startAngle={90}
                endAngle={-270}
              >
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar
                  dataKey="value"
                  background={{ fill: "rgba(148,163,184,0.2)" }}
                  cornerRadius={8}
                  clockWise
                />
              </RadialBarChart>
              <p className="text-[11px] leading-relaxed text-gray-600 dark:text-gray-300">
                {item.note}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
