import React from "react";
import clsx from "clsx";

export default function DeploymentVerdict({
  recommendation = "PENDING",
  rationale = "",
}) {
  const isGo = recommendation === "GO";
  const isNoGo = recommendation === "NO-GO";
  const color = isGo
    ? "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30"
    : isNoGo
      ? "bg-red-100 dark:bg-red-500/20 text-red-800 dark:text-red-400 border border-red-200 dark:border-red-500/30"
      : "bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30";
  const icon = isGo ? "✅" : isNoGo ? "🚫" : "⚠️";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 text-lg font-bold text-gray-900 dark:text-white">
        <span className="text-2xl drop-shadow-sm">{icon}</span>
        <span>Deployment Verdict</span>
      </div>
      <div className="flex items-start gap-4">
        <div
          className={clsx(
            "mt-1 inline-flex rounded-xl px-4 py-2 text-xs font-black tracking-widest uppercase shadow-sm whitespace-nowrap",
            color,
          )}
        >
          {recommendation}
        </div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 leading-relaxed border-l-2 border-black/5 dark:border-white/10 pl-4">{rationale}</p>
      </div>
      <p className="mt-2 text-xs font-semibold text-gray-400 dark:text-gray-500 tracking-wide uppercase">
        Analyzed by IronTest Defect Intelligence Engine
      </p>
    </div>
  );
}
