import React from "react";
import clsx from "clsx";

const riskColor = {
  critical:
    "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/30",
  high: "bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-400 border border-orange-200 dark:border-orange-500/30",
  medium:
    "bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30",
  low: "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30",
};

const trendColor = {
  improving:
    "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30",
  stable:
    "bg-slate-100 dark:bg-slate-500/20 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-500/30",
  declining:
    "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-500/30",
};

const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(0)}%`;

export default function RiskHeatmap({ moduleRisks = [] }) {
  return (
    <div className="w-full h-full flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold tracking-widest uppercase text-gray-500 dark:text-gray-400">
          Module Risk Heatmap
        </h3>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-2 auto-rows-max">
        {moduleRisks.map((module) => (
          <div
            key={module.module}
            className="flex flex-col justify-between rounded-2xl border border-black/5 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-5 transition-transform hover:-translate-y-1 shadow-sm"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="text-sm font-bold text-gray-900 dark:text-white break-words">
                {module.module}
              </div>
              <div className="flex items-center gap-1.5">
                <span
                  className={clsx(
                    "rounded-lg px-2 py-1 text-[10px] font-black uppercase tracking-wider whitespace-nowrap",
                    riskColor[module.regression_risk] ||
                      "bg-gray-100 text-gray-500",
                  )}
                >
                  {module.regression_risk} Risk
                </span>
                <span
                  className={clsx(
                    "rounded-lg px-2 py-1 text-[10px] font-black uppercase tracking-wider whitespace-nowrap",
                    trendColor[module.trend_vs_history] || trendColor.stable,
                  )}
                >
                  {module.trend_vs_history || "stable"}
                </span>
              </div>
            </div>

            <div className="mt-3">
              <div className="mb-1 flex items-center justify-between text-[11px] font-semibold text-gray-600 dark:text-gray-300">
                <span>Risk Intensity</span>
                <span>{toPercent(module.defect_probability)}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-amber-400 via-orange-500 to-red-500"
                  style={{
                    width: `${Math.max(6, Math.min(100, Number(module.defect_probability || 0) * 100))}%`,
                  }}
                />
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-1">
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">
                  Failure Probability:
                </span>
                <span className="text-gray-900 dark:text-gray-200">
                  {toPercent(module.defect_probability)}
                </span>
              </div>
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">
                  Prior Defects:
                </span>
                <span className="text-gray-900 dark:text-gray-200">
                  {module.historical_defect_count}
                </span>
              </div>
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">
                  Current Pass Rate:
                </span>
                <span className="text-gray-900 dark:text-gray-200">
                  {toPercent(module.module_pass_rate)}
                </span>
              </div>
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">
                  Historical Pass Rate:
                </span>
                <span className="text-gray-900 dark:text-gray-200">
                  {toPercent(module.historical_pass_rate)}
                </span>
              </div>
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">
                  Delta vs History:
                </span>
                <span
                  className={clsx(
                    "font-bold",
                    Number(module.pass_rate_delta || 0) < 0
                      ? "text-red-600 dark:text-red-300"
                      : "text-emerald-600 dark:text-emerald-300",
                  )}
                >
                  {`${Number(module.pass_rate_delta || 0) >= 0 ? "+" : ""}${toPercent(module.pass_rate_delta)}`}
                </span>
              </div>
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">
                  Module Tests:
                </span>
                <span className="text-gray-900 dark:text-gray-200">
                  {module.module_test_count || 0}
                </span>
              </div>
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">
                  Failures / Errors:
                </span>
                <span className="text-gray-900 dark:text-gray-200">
                  {module.module_failed || 0} / {module.module_errors || 0}
                </span>
              </div>
            </div>
            <div className="mt-3 text-[11px] font-medium text-amber-600 dark:text-amber-400 border-t border-black/5 dark:border-white/10 pt-3">
              <span className="block text-[10px] uppercase text-gray-400 mb-1">
                Top Failure Patterns:
              </span>
              {Array.isArray(module.top_defect_types) &&
              module.top_defect_types.length > 0
                ? module.top_defect_types.join(", ")
                : "No recurring pattern detected"}
            </div>

            <div className="mt-3 border-t border-black/5 dark:border-white/10 pt-3">
              <span className="block text-[10px] uppercase text-gray-400 mb-1 font-bold">
                Risk Drivers:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(module.risk_drivers || []).slice(0, 4).map((driver) => (
                  <span
                    key={`${module.module}-driver-${driver}`}
                    className="rounded-md border border-amber-200/80 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 px-2 py-1 text-[10px] font-semibold text-amber-700 dark:text-amber-300"
                  >
                    {driver}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-3 border-t border-black/5 dark:border-white/10 pt-3">
              <span className="block text-[10px] uppercase text-gray-400 mb-1 font-bold">
                Recommended Action:
              </span>
              <p className="text-[11px] font-medium text-gray-700 dark:text-gray-200">
                {
                  (module.recommended_actions || [
                    "Continue monitoring with routine regression checks",
                  ])[0]
                }
              </p>
            </div>

            {module.vulnerability_heatmap && (
              <div className="mt-3 rounded-xl bg-red-50 dark:bg-red-500/10 p-3 text-[11px] text-red-700 dark:text-red-400 font-mono shadow-inner border border-red-200 dark:border-red-500/20">
                <div className="font-bold mb-1 uppercase tracking-wider">
                  ⚠️ Vulnerability Vector
                </div>
                {module.vulnerability_heatmap}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
