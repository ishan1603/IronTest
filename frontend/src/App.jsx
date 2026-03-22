import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import Pipeline from "./components/Pipeline.jsx";
import Dashboard from "./components/Dashboard.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const PRESET_STORIES = [
  {
    name: "Payment Flow",
    text: "As a customer, I want to complete a checkout using my saved credit card so that I can make purchases without re-entering payment details. Acceptance Criteria: - Saved card must be retrieved securely via tokenized vault API - 3DS authentication must trigger for transactions over $500 - Payment confirmation email sent within 30 seconds - Failed payments must not decrement inventory - Refund must process within 5 business days",
  },
  {
    name: "Auth Module",
    text: "As a user, I want to log in using Single Sign-On (SSO) with my corporate Google account so that I don't need to maintain a separate password. Acceptance Criteria: - OAuth 2.0 PKCE flow must be implemented - Session token must expire after 8 hours of inactivity - Failed login attempts > 5 must trigger account lockout - MFA must be enforced for admin roles - Audit log must record all login events with IP and timestamp",
  },
  {
    name: "Notification Service",
    text: "As a platform admin, I want the notification service to deliver real-time alerts to users via push, email, and SMS so that critical events are never missed. Acceptance Criteria: - Push notifications delivered within 2 seconds of event trigger - Email fallback if push fails after 3 retries - SMS sent only for CRITICAL severity events - User preferences must be respected per channel - Notification delivery status tracked in audit log",
  },
];

const initialAgents = {
  story: { status: "idle", summary: "", message: "" },
  test: { status: "idle", summary: "", message: "" },
  defect: { status: "idle", summary: "", message: "" },
};

export default function App() {
  const [userStory, setUserStory] = useState(PRESET_STORIES[0].text);
  const [useSample, setUseSample] = useState(true);
  const [agents, setAgents] = useState(initialAgents);
  const [pipelineVisible, setPipelineVisible] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const eventSourceRef = useRef(null);

  const resetAgents = () => setAgents(initialAgents);

  const handleRun = async () => {
    if (!userStory.trim() || isRunning) return;
    setError("");
    setPipelineVisible(true);
    setDashboardData(null);
    resetAgents();
    setAgents((prev) => ({
      ...prev,
      story: {
        status: "processing",
        summary: "",
        message: "Analyzing user story...",
      },
    }));
    setIsRunning(true);

    try {
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_story: userStory }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to start analysis");
      }
      const { session_id } = await res.json();
      startStream(session_id);
    } catch (err) {
      setError(err.message);
      setIsRunning(false);
    }
  };

  const startStream = (sessionId) => {
    const es = new EventSource(`${API_BASE}/api/stream/${sessionId}`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const type = data.event;
        if (type === "agent_start") {
          setAgents((prev) => ({
            ...prev,
            [data.agent]: {
              status: "processing",
              summary: "",
              message: data.message,
            },
          }));
        } else if (type === "agent_complete") {
          if (data.agent === "story") {
            const result = data.result;
            setAgents((prev) => ({
              ...prev,
              story: {
                status: "done",
                summary: `Intent captured, ${result.modules.length} modules, ${result.risk_factors.length} risks identified.`,
              },
            }));
          }
          if (data.agent === "test") {
            const count = data.result.length;
            setAgents((prev) => ({
              ...prev,
              test: {
                status: "done",
                summary: `Generated ${count} test cases across functional, boundary, and regression.`,
              },
            }));
          }
          if (data.agent === "defect") {
            const score = data.result.overall_confidence_score;
            setAgents((prev) => ({
              ...prev,
              defect: {
                status: "done",
                summary: `Confidence Score: ${score} - ${data.result.deployment_recommendation}.`,
              },
            }));
          }
        } else if (type === "pipeline_complete") {
          setDashboardData({
            story: data.dashboard.story,
            tests: data.dashboard.tests,
            defects: data.dashboard.defects,
          });
          setIsRunning(false);
          setTimeout(() => {
            es.close();
          }, 400);
        } else if (type === "error") {
          setError(data.message || "Pipeline error");
          setIsRunning(false);
          es.close();
        }
      } catch (err) {
        setError("Failed to parse stream event");
        setIsRunning(false);
        es.close();
      }
    };

    es.onerror = () => {
      setError("Stream connection failed. Please retry.");
      setIsRunning(false);
      es.close();
    };
  };

  useEffect(() => {
    // Keep textarea in sync with sample toggle
    if (useSample) {
      setUserStory(PRESET_STORIES[0].text);
    }
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, []);

  useEffect(() => {
    if (!useSample) {
      setUserStory("");
    }
  }, [useSample]);

  const handleDownload = () => {
    if (!dashboardData) return;
    const payload = {
      generated_at: new Date().toISOString(),
      story: dashboardData.story,
      tests: dashboardData.tests,
      defects: dashboardData.defects,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "qa-report.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-br from-[#05060c] via-[#0b0f1c] to-[#05060c] text-white">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-32 top-0 h-72 w-72 rounded-full bg-indigo-500/25 blur-3xl" />
        <div className="absolute right-[-10%] top-16 h-96 w-96 rounded-full bg-cyan-400/25 blur-[140px]" />
        <div className="absolute left-1/3 bottom-[-10%] h-80 w-80 rounded-full bg-pink-400/15 blur-[140px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(255,255,255,0.06),transparent_35%)]" />
      </div>

      <div className="relative">
        <header className="border-b border-white/10 bg-white/5 backdrop-blur-xl">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent text-2xl font-black text-white shadow-lg shadow-accent/30">
                A
              </div>
              <div>
                <div className="text-xl font-bold">ATOS QA Intelligence</div>
                <div className="text-sm text-gray-300">
                  Multi-Agent Quality Copilot
                </div>
              </div>
            </div>
            <div className="rounded-full bg-gradient-to-r from-accent to-purple-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-purple-500/30">
              Autonomous Testing Agent
            </div>
          </div>
        </header>

        <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
          <section className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/40 backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-2xl font-bold text-white">
                  Paste your Jira User Story
                </h2>
                <p className="text-sm text-gray-400">
                  Select a preset or paste a live story. The multi-agent
                  pipeline will generate tests and risk insights.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setUseSample((v) => !v)}
                  className={
                    useSample
                      ? "rounded-full bg-accent/20 px-4 py-2 text-sm font-semibold text-white shadow shadow-accent/30"
                      : "rounded-full bg-white/5 px-4 py-2 text-sm font-semibold text-gray-200 hover:bg-accent/20 hover:text-white"
                  }
                >
                  {useSample ? "Sample story active" : "Use sample story"}
                </button>
                {PRESET_STORIES.map((story) => (
                  <button
                    key={story.name}
                    onClick={() => setUserStory(story.text)}
                    className="rounded-full bg-white/5 px-4 py-2 text-sm font-semibold text-gray-200 hover:bg-accent/20 hover:text-white"
                  >
                    {story.name}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              className="mt-4 w-full rounded-xl border border-white/10 bg-black/40 p-4 text-sm text-gray-100 shadow-inner focus:border-accent"
              rows={6}
              placeholder="Paste your Jira User Story here..."
              value={userStory}
              onChange={(e) => setUserStory(e.target.value)}
              disabled={useSample}
            />
            <div className="mt-4 flex items-center gap-3">
              <button
                onClick={handleRun}
                disabled={isRunning}
                className="flex items-center gap-2 rounded-full bg-gradient-to-r from-accent via-indigo-500 to-purple-500 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:-translate-y-0.5 hover:shadow-purple-500/40 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isRunning ? (
                  <span className="flex items-center gap-2">
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />{" "}
                    Running...
                  </span>
                ) : (
                  "Run Analysis"
                )}
              </button>
              {error && <span className="text-sm text-danger">{error}</span>}
            </div>
          </section>

          {pipelineVisible && <Pipeline agents={agents} />}

          {dashboardData && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white">QA Report</h3>
                <button
                  onClick={handleDownload}
                  className="rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-white/20"
                >
                  Download report (JSON)
                </button>
              </div>
              <Dashboard data={dashboardData} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
