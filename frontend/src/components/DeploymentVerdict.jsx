import React from "react";
import clsx from "clsx";

export default function DeploymentVerdict({
  recommendation = "PENDING",
  rationale = "",
}) {
  const isGo = recommendation === "GO";
  const isNoGo = recommendation === "NO-GO";
  const color = isGo
    ? "bg-success/20 text-success"
    : isNoGo
      ? "bg-danger/20 text-danger"
      : "bg-amber-200/10 text-amber-200";
  const icon = isGo ? "✅" : isNoGo ? "❌" : "⚠️";

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/30 backdrop-blur-xl">
      <div className="flex items-center gap-3 text-xl font-semibold text-gray-100">
        <span>{icon}</span>
        <span>Deployment Verdict</span>
      </div>
      <div
        className={clsx(
          "mt-3 inline-flex rounded-full px-4 py-2 text-xs font-semibold",
          color,
        )}
      >
        {recommendation}
      </div>
      <p className="mt-3 text-sm text-gray-200">{rationale}</p>
      <p className="mt-1 text-xs text-gray-400">
        Analyzed by Defect Intelligence Agent using historical defect knowledge
        graph.
      </p>
    </div>
  );
}
