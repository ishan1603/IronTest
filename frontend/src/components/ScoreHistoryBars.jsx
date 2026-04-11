import React from "react";

export default function ScoreHistoryBars({ runs = [], currentScore = 0 }) {
  const data = Array.isArray(runs) ? runs.slice(-7) : [];
  const hasCurrent = data.some(
    (item) => Number(item.score) === Number(currentScore),
  );

  const chartData = hasCurrent
    ? data
    : [
        ...data,
        { label: "Current", score: Number(currentScore || 0), isCurrent: true },
      ].slice(-8);

  const maxScore = Math.max(
    100,
    ...chartData.map((item) => Number(item.score || 0)),
  );

  return (
    <div className="w-full h-full">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-bold tracking-widest uppercase text-gray-500 dark:text-gray-400">
          Score Trend (History + Current)
        </h3>
      </div>
      {chartData.length === 0 ? (
        <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-black/20 p-4 text-sm text-gray-500 dark:text-gray-400">
          No historical score data available yet.
        </div>
      ) : (
        <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-black/20 p-4">
          <div className="flex items-end gap-3 h-48">
            {chartData.map((item, idx) => {
              const score = Number(item.score || 0);
              const height = Math.max(10, Math.round((score / maxScore) * 100));
              const isCurrent = item.isCurrent || item.label === "Current";
              return (
                <div key={`${item.label}-${idx}`} className="flex-1 min-w-0">
                  <div className="flex h-40 items-end justify-center">
                    <div
                      className={`w-full max-w-[52px] rounded-t-md transition-all ${
                        isCurrent
                          ? "bg-gradient-to-t from-emerald-500 to-emerald-300"
                          : "bg-gradient-to-t from-slate-500 to-slate-300 dark:from-slate-600 dark:to-slate-400"
                      }`}
                      style={{ height: `${height}%` }}
                      title={`${item.label}: ${score}`}
                    />
                  </div>
                  <div className="mt-2 text-center text-[10px] font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400 truncate">
                    {item.label || `Run ${idx + 1}`}
                  </div>
                  <div className="text-center text-xs font-semibold text-gray-800 dark:text-gray-200">
                    {score}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
