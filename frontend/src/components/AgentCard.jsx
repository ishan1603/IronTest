import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import clsx from "clsx";

const statusStyles = {
  idle: "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border border-transparent dark:border-white/5",
  processing: "bg-accent/10 dark:bg-accent/20 text-accent border border-accent/30 dark:border-accent/40 animate-pulse shadow-inner",
  done: "bg-success/10 dark:bg-success/10 text-emerald-600 dark:text-success border border-success/30 dark:border-success/40",
  error: "bg-danger/10 text-red-600 dark:text-danger border border-danger/30 dark:border-danger/40",
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
        "flex flex-col gap-2 rounded-2xl p-4 shadow-lg backdrop-blur-xl transition-all duration-300 h-full min-h-[140px] lg:min-h-[160px] border",
        statusStyles[status]
      )}
    >
      <div className="flex justify-between items-center mb-1">
        <div className="flex items-center gap-1.5 font-bold text-gray-900 dark:text-white min-w-0">
          <span className="text-lg drop-shadow-sm flex-shrink-0">{icon}</span>
          <span className="tracking-tight text-[11px] uppercase whitespace-nowrap overflow-hidden text-ellipsis">{title}</span>
        </div>
        <span
          className={clsx(
            "rounded-full px-2 py-0.5 text-[8px] font-black uppercase tracking-tighter shadow-sm flex-shrink-0",
            status === "processing" && "bg-accent text-white",
            status === "done" && "bg-success text-white dark:text-black",
            status === "idle" && "bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-white",
            status === "error" && "bg-danger text-white",
          )}
        >
          {status === "processing"
            ? "Run"
            : status === "done"
              ? "Done"
              : status === "error"
                ? "Err"
                : "Idle"}
        </span>
      </div>
      <div className="flex-1 flex flex-col overflow-hidden">
        {status === "processing" ? (
          <div className="font-mono text-[9px] text-emerald-600 dark:text-emerald-400 flex flex-col gap-0.5 mt-1 p-2 bg-black/5 dark:bg-black/40 rounded-lg border border-black/5 dark:border-white/5 flex-1 overflow-hidden">
            <div className="font-bold border-b border-black/5 dark:border-white/10 pb-0.5 mb-1 truncate">{message}</div>
            {logs.map((log, i) => (
              <motion.div
                initial={{ opacity: 0, x: -2 }}
                animate={{ opacity: 1, x: 0 }}
                key={i}
                className="truncate"
              >
                {log}
              </motion.div>
            ))}
          </div>
        ) : (
          <p className="text-[10px] text-gray-600 dark:text-gray-300 leading-tight line-clamp-4 mt-1">
            {summary || message || "Waiting for signal..."}
          </p>
        )}
      </div>
    </motion.div>
  );
}
