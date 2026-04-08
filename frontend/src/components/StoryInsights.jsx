import React from "react";
import clsx from "clsx";

export default function StoryInsights({ story }) {
  if (!story) return null;

  return (
    <div className="flex flex-col gap-6">
      <div className="border-b border-black/5 dark:border-white/10 pb-4">
        <h3 className="text-xl font-bold tracking-tight text-gray-900 dark:text-white">
          Story Intelligence
        </h3>
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mt-1">
          Deep structural and semantic analysis of intent
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-5 shadow-sm">
          <h4 className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-accent mb-4">
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
            Security Vectors
          </h4>
          <ul className="flex flex-col gap-2">
            {story.security_vectors?.map((v, i) => (
              <li
                key={i}
                className="flex gap-2 text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                <span className="text-accent">•</span>
                <span>{v}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-5 shadow-sm">
          <h4 className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-emerald-500 dark:text-emerald-400 mb-4">
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
              />
            </svg>
            Microservices Identified
          </h4>
          <div className="flex flex-wrap gap-2">
            {story.microservices?.map((m, i) => (
              <span
                key={i}
                className="rounded-lg bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 px-3 py-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300 shadow-sm"
              >
                {m}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-5 shadow-sm">
        <h4 className="text-xs font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400 mb-3">
          Extracted Business Intent
        </h4>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 leading-relaxed border-l-2 border-accent pl-4">
          {story.intent}
        </p>
      </div>
    </div>
  );
}
