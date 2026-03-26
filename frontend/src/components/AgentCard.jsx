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
        "flex flex-col gap-3 rounded-2xl p-5 shadow-lg backdrop-blur-xl transition-all duration-300",
        statusStyles[status]
      )}
    >
      <div className="flex justify-between items-start">
        <div className="flex items-center gap-3 font-semibold text-gray-900 dark:text-white">
          <span className="text-2xl drop-shadow-sm">{icon}</span>
          <span className="tracking-tight text-lg">{title}</span>
        </div>
        <span
          className={clsx(
            "rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider shadow-sm",
            status === "processing" && "bg-accent text-white",
            status === "done" && "bg-success text-white dark:text-black",
            status === "idle" && "bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-white",
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
      <div className="text-sm text-gray-600 dark:text-gray-300 min-h-[80px] leading-relaxed">
        {status === "processing" ? (
          <div className="font-mono text-[11px] text-emerald-600 dark:text-emerald-400 flex flex-col gap-1 mt-3 p-3 bg-black/5 dark:bg-black/40 rounded-lg border border-black/5 dark:border-white/5">
            <div className="font-bold border-b border-black/5 dark:border-white/10 pb-1 mb-1">{message}</div>
            {logs.map((log, i) => (
              <motion.div
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: 1, x: 0 }}
                key={i}
              >
                {log}
              </motion.div>
            ))}
            <motion.div animate={{ opacity: [0, 1] }} transition={{ repeat: Infinity, duration: 0.8 }} className="w-2 h-3 bg-emerald-500 mt-1" />
          </div>
        ) : (
          <p className="mt-2">{summary || message}</p>
        )}
      </div>
    </motion.div>
  );
}
