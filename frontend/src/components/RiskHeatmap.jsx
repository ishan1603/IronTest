import React from "react";
import clsx from "clsx";

const riskColor = {
  critical: "bg-danger",
  high: "bg-orange-500",
  medium: "bg-amber-400",
  low: "bg-success",
};

export default function RiskHeatmap({ moduleRisks = [] }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/30 backdrop-blur-xl">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-100">
          Module Risk Heatmap
        </h3>
        <span className="text-sm text-gray-400">Regression outlook</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {moduleRisks.map((module) => (
          <div
            key={module.module}
            className="rounded-xl border border-white/10 bg-black/20 p-4"
          >
            <div className="flex items-center justify-between">
              <div className="text-base font-semibold text-gray-100">
                {module.module}
              </div>
              <span
                className={clsx(
                  "rounded-full px-3 py-1 text-xs font-semibold capitalize text-black",
                  riskColor[module.regression_risk] || "bg-gray-500",
                )}
              >
                {module.regression_risk}
              </span>
            </div>
            <div className="mt-2 text-sm text-gray-300">
              Defect probability: {(module.defect_probability * 100).toFixed(0)}
              %
            </div>
            <div className="text-sm text-gray-400">
              Historical defects: {module.historical_defect_count}
            </div>
            <div className="mt-2 text-xs text-amber-200">
              Top defects: {module.top_defect_types.join(", ")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
