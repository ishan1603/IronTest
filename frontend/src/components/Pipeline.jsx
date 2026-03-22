import React from "react";
import { motion } from "framer-motion";
import AgentCard from "./AgentCard";

function Arrow({ active }) {
  return (
    <motion.div
      animate={{ opacity: active ? [0.2, 1, 0.2] : 0.2 }}
      transition={{ repeat: active ? Infinity : 0, duration: 1.2 }}
      className="flex items-center justify-center px-4"
    >
      <div className="h-1 w-16 bg-gradient-to-r from-accent to-transparent" />
    </motion.div>
  );
}

export default function Pipeline({ agents }) {
  return (
    <div className="flex w-full flex-col gap-4 rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/40 backdrop-blur-xl">
      <div className="flex items-center justify-between text-sm text-gray-300">
        <span>Live Multi-Agent Pipeline</span>
        <span className="text-accent">Story → Tests → Defects</span>
      </div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <AgentCard
          title="Story Intelligence"
          icon="🧠"
          status={agents.story.status}
          summary={agents.story.summary}
          message={agents.story.message}
        />
        <Arrow
          active={
            agents.story.status === "done" &&
            agents.test.status === "processing"
          }
        />
        <AgentCard
          title="Test Generation"
          icon="⚙️"
          status={agents.test.status}
          summary={agents.test.summary}
          message={agents.test.message}
        />
        <Arrow
          active={
            agents.test.status === "done" &&
            agents.defect.status === "processing"
          }
        />
        <AgentCard
          title="Defect Intelligence"
          icon="🔍"
          status={agents.defect.status}
          summary={agents.defect.summary}
          message={agents.defect.message}
        />
      </div>
    </div>
  );
}
