import React from "react";
import clsx from "clsx";

export default function StoryInsights({ story }) {
  if (!story) return null;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/30 backdrop-blur-xl">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-100">Story Intelligence</h3>
        <p className="text-sm text-gray-400">Deep structural analysis</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-black/20 p-4">
          <h4 className="text-sm font-semibold text-accent mb-2">Security Vectors</h4>
          <ul className="list-inside list-disc text-sm text-gray-300">
            {story.security_vectors?.map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-white/10 bg-black/20 p-4">
          <h4 className="text-sm font-semibold text-indigo-400 mb-2">Microservices Mapped</h4>
          <div className="flex flex-wrap gap-2 text-xs">
            {story.microservices?.map((m, i) => (
              <span key={i} className="rounded-full bg-white/10 px-3 py-1 text-gray-200">
                {m}
              </span>
            ))}
          </div>
        </div>
      </div>
      
      <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-4">
        <h4 className="text-sm font-semibold text-gray-300 mb-2">Business Intent</h4>
        <p className="text-sm text-gray-400">{story.intent}</p>
      </div>
    </div>
  );
}
