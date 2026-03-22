import React, { useEffect, useState } from "react";
import { RadialBarChart, RadialBar, PolarAngleAxis } from "recharts";
import clsx from "clsx";

export default function ConfidenceGauge({ score = 0, recommendation = "" }) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    const timeout = setTimeout(() => setAnimatedScore(score), 150);
    return () => clearTimeout(timeout);
  }, [score]);

  const color = score > 65 ? "#22c55e" : score > 40 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/30 backdrop-blur-xl">
      <h3 className="text-lg font-semibold text-gray-100">
        Release Confidence
      </h3>
      <RadialBarChart
        width={280}
        height={220}
        cx={140}
        cy={110}
        innerRadius={70}
        outerRadius={100}
        barSize={16}
        data={[{ name: "score", value: animatedScore, fill: color }]}
        startAngle={180}
        endAngle={0}
      >
        <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
        <RadialBar
          minAngle={15}
          clockWise
          dataKey="value"
          animationDuration={800}
          animationEasing="ease-out"
        />
      </RadialBarChart>
      <div className="text-center">
        <div className="text-5xl font-black" style={{ color }}>
          {animatedScore}
        </div>
        <div
          className={clsx(
            "mt-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-wide",
            recommendation === "GO" && "bg-success/20 text-success",
            recommendation === "NO-GO" && "bg-danger/20 text-danger",
            recommendation === "CONDITIONAL GO" &&
              "bg-amber-200/10 text-amber-300",
          )}
        >
          {recommendation || "PENDING"}
        </div>
      </div>
    </div>
  );
}
