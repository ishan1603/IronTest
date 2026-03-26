import React, { useEffect, useState } from "react";
import { RadialBarChart, RadialBar, PolarAngleAxis } from "recharts";
import clsx from "clsx";

export default function ConfidenceGauge({ score = 0, recommendation = "" }) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    const timeout = setTimeout(() => setAnimatedScore(score), 150);
    return () => clearTimeout(timeout);
  }, [score]);

  const color = score > 65 ? "#10b981" : score > 40 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-4 w-full h-full justify-center">
      <h3 className="text-sm font-bold tracking-widest uppercase text-gray-500 dark:text-gray-400">
        Release Confidence
      </h3>
      <div className="relative flex items-center justify-center mt-2">
        <RadialBarChart
          width={240}
          height={200}
          cx={120}
          cy={100}
          innerRadius={75}
          outerRadius={100}
          barSize={12}
          data={[{ name: "score", value: animatedScore, fill: color }]}
          startAngle={180}
          endAngle={0}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar
            minAngle={15}
            clockWise
            dataKey="value"
            animationDuration={1000}
            animationEasing="ease-in-out"
            cornerRadius={10}
            background={{ fill: "rgba(0,0,0,0.05)" }}
          />
        </RadialBarChart>
        <div className="absolute flex flex-col items-center justify-center top-14">
          <div className="text-5xl font-black tracking-tighter" style={{ color }}>
            {animatedScore}
          </div>
        </div>
      </div>
      <div className="text-center -mt-6">
        <div
          className={clsx(
            "rounded-xl px-4 py-2 text-xs font-black uppercase tracking-widest shadow-sm",
            recommendation === "GO" && "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400",
            recommendation === "NO-GO" && "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/30",
            recommendation === "CONDITIONAL GO" &&
              "bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400",
          )}
        >
          {recommendation || "PENDING"}
        </div>
      </div>
    </div>
  );
}
