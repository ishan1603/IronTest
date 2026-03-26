import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import clsx from "clsx";

const statusStyles = {
  idle: "bg-gray-700 text-gray-300",
  processing: "bg-accent/20 text-accent border border-accent/40 animate-pulse",
  done: "bg-success/10 text-success border border-success/40",
  error: "bg-danger/10 text-danger border border-danger/40",
};

export default function AgentCard({
  title,
  icon,
  status = "idle",
  summary = "",
  message = "",
}) {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    if (status === "processing") {
      const phrases = [
        "[sys] Allocating neural paths...",
        "[ai] Parsing dimensional arrays...",
        "[sec] Inspecting edge vectors...",
        "[sys] Compiling threat modules...",
        "[net] Resolving microservices...",
        "[ai] Synthesizing conditions...",
      ];
      let i = 0;
      const interval = setInterval(() => {
        setLogs((prev) => {
          const next = [...prev, phrases[i % phrases.length]];
          return next.slice(-4); // keep last 4
        });
        i++;
      }, 600);
      return () => clearInterval(interval);
    } else {
      setLogs([]);
    }
  }, [status]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        "flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-4 shadow-2xl shadow-black/30 backdrop-blur-xl",
        statusStyles[status],
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <span className="text-2xl">{icon}</span>
          <span>{title}</span>
        </div>
        <span
          className={clsx(
            "rounded-full px-3 py-1 text-xs font-semibold",
            status === "processing" && "bg-accent text-white",
            status === "done" && "bg-success text-black",
            status === "idle" && "bg-gray-500 text-white",
            status === "error" && "bg-danger text-white",
          )}
        >
          {status === "processing"
            ? "Running"
            : status === "done"
              ? "Complete"
              : status === "error"
                ? "Error"
                : "Idle"}
        </span>
      </div>
      <div className="text-sm text-gray-200 min-h-[80px]">
        {status === "processing" ? (
          <div className="font-mono text-xs text-green-400 flex flex-col gap-1 mt-2">
            <div>{message}</div>
            {logs.map((log, i) => (
              <motion.div
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: 1, x: 0 }}
                key={i}
              >
                {log}
              </motion.div>
            ))}
            <motion.div animate={{ opacity: [0, 1] }} transition={{ repeat: Infinity, duration: 0.8 }} className="w-2 h-3 bg-green-400 mt-1" />
          </div>
        ) : (
          <p className="mt-2">{summary || message}</p>
        )}
      </div>
    </motion.div>
  );
}
