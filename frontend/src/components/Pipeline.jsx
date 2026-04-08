import React from "react";
import { motion } from "framer-motion";
import clsx from "clsx";
import AgentCard from "./AgentCard.jsx";

function Arrow({ active }) {
  return (
    <motion.div
      animate={{ opacity: active ? [0.4, 1, 0.4] : 0.15 }}
      transition={{ repeat: active ? Infinity : 0, duration: 1.2 }}
      className="flex items-center justify-center px-1 lg:px-2 self-center flex-shrink-0"
    >
      <div
        className={clsx(
          "h-0.5 w-4 lg:w-8 bg-gradient-to-r from-accent to-transparent rounded-full",
          active && "shadow-[0_0_20px_rgba(34,197,94,0.9)] bg-accent",
        )}
      />
    </motion.div>
  );
}

export default function Pipeline({ agents, isRunning = false }) {
  return (
    <div className="flex w-full flex-col gap-4 rounded-3xl border border-black/5 dark:border-emerald-400/20 bg-white/40 dark:bg-white/5 p-4 lg:p-6 shadow-2xl dark:shadow-[0_0_24px_rgba(34,197,94,0.22)] backdrop-blur-3xl transition-colors duration-300 overflow-hidden">
      <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-widest text-gray-500 dark:text-gray-400 mb-2">
        <span>Live Autonomous Orchestration</span>
        <span
          className={clsx(
            "flex items-center gap-2",
            isRunning ? "text-accent" : "text-gray-400",
          )}
        >
          <span
            className={clsx(
              "h-1.5 w-1.5 rounded-full",
              isRunning ? "bg-accent animate-ping" : "bg-gray-400",
            )}
          />
          {isRunning ? "System Engaged" : "Standby"}
        </span>
      </div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch lg:justify-between lg:gap-1">
        <div className="flex-1 min-w-0">
          <AgentCard
            title="Story"
            icon="🧠"
            status={agents.story.status}
            summary={agents.story.summary}
            message={agents.story.message}
          />
        </div>
        <Arrow
          active={
            agents.story.status === "done" &&
            agents.test.status === "processing"
          }
        />
        <div className="flex-1 min-w-0">
          <AgentCard
            title="Test Gen"
            icon="⚙️"
            status={agents.test.status}
            summary={agents.test.summary}
            message={agents.test.message}
          />
        </div>
        <Arrow
          active={
            agents.test.status === "done" &&
            agents.execution.status === "processing"
          }
        />
        <div className="flex-1 min-w-0">
          <AgentCard
            title="Execution"
            icon="🚀"
            status={agents.execution.status}
            summary={agents.execution.summary}
            message={agents.execution.message}
          />
        </div>
        <Arrow
          active={
            agents.execution.status === "done" &&
            agents.defect.status === "processing"
          }
        />
        <div className="flex-1 min-w-0">
          <AgentCard
            title="Defects"
            icon="🔍"
            status={agents.defect.status}
            summary={agents.defect.summary}
            message={agents.defect.message}
          />
        </div>
      </div>
    </div>
  );
}
