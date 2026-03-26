import React from "react";
import { motion } from "framer-motion";
import clsx from "clsx";
import AgentCard from "./AgentCard.jsx";

function Arrow({ active }) {
  return (
    <motion.div
      animate={{ opacity: active ? [0.4, 1, 0.4] : 0.15 }}
      transition={{ repeat: active ? Infinity : 0, duration: 1.2 }}
      className="flex items-center justify-center px-2 lg:px-4"
    >
      <div className={clsx("h-1 w-8 lg:w-16 bg-gradient-to-r from-accent to-transparent rounded-full", active && "shadow-[0_0_20px_rgba(99,102,241,0.9)] bg-accent")} />
    </motion.div>
  );
}

export default function Pipeline({ agents }) {
  return (
    <div className="flex w-full flex-col gap-6 rounded-3xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-8 shadow-2xl backdrop-blur-3xl transition-colors duration-300">
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-widest text-gray-500 dark:text-gray-400">
        <span>Live Autonomous Orchestration</span>
        <span className="text-accent flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-accent animate-ping" />
          System Engaged
        </span>
      </div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex-1">
          <AgentCard
            title="Story Intelligence"
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
        <div className="flex-1">
          <AgentCard
            title="Test Generation"
            icon="⚙️"
            status={agents.test.status}
            summary={agents.test.summary}
            message={agents.test.message}
          />
        </div>
        <Arrow
          active={
            agents.test.status === "done" &&
            agents.defect.status === "processing"
          }
        />
        <div className="flex-1">
          <AgentCard
            title="Defect Intelligence"
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
