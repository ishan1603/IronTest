import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Pipeline from "./components/Pipeline.jsx";
import TestCaseTable from "./components/TestCaseTable.jsx";
import ConfidenceGauge from "./components/ConfidenceGauge.jsx";
import RiskHeatmap from "./components/RiskHeatmap.jsx";
import DeploymentVerdict from "./components/DeploymentVerdict.jsx";
import StoryInsights from "./components/StoryInsights.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const PRESET_STORIES = [
  {
    name: "Payment Gateway Core",
    text: "As a customer, I require a frictionless checkout experience using my tokenized credit card across the ecosystem. Acceptance Criteria: - Vault API must securely retrieve tokenized cards with sub-100ms latency - 3DS authentication triggers dynamically for risk transactions > $500 - Inventory must remain locked during transaction, rolling back strictly on payment failure - Automated refunds trigger SLA workflows within 5 business days.",
  },
  {
    name: "Identity & Access Auth",
    text: "As an enterprise user, I need to authenticate via secure Single Sign-On (SSO) to seamlessly access distributed microservices. Acceptance Criteria: - OAuth 2.0 PKCE flow integrated with strict enterprise identity providers - Idle session tokens expire predictably within 8 hours - Intelligent lockout engages upon 5 consecutive failed attempts - Mandatory Multi-Factor Authentication (MFA) step-up for administrative operations - Immutable audit logs capture IP and timestamp per login event.",
  },
  {
    name: "Real-time Notification Fabric",
    text: "As a platform administrator, I expect the notification fabric to broadcast critical alerts synchronously across Push, Email, and SMS endpoints. Acceptance Criteria: - Push delivery maintains a 2-second SLA from event origination - Email gracefully serves as the tertiary fallback after 3 rapid retries - SMS gateways activate exclusively for CRITICAL severity tags - Granular user preferences override global channel broadcasts - Delivery handshakes logged persistently for auditing.",
  },
];

const initialAgents = {
  story: { status: "idle", summary: "", message: "" },
  test: { status: "idle", summary: "", message: "" },
  execution: { status: "idle", summary: "", message: "" },
  defect: { status: "idle", summary: "", message: "" },
};

function TypingEffect({ text }) {
  const [displayed, setDisplayed] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [loop, setLoop] = useState(0);

  useEffect(() => {
    let timer;
    if (!isDeleting && displayed.length < text.length) {
      timer = setTimeout(
        () => setDisplayed(text.slice(0, displayed.length + 1)),
        100,
      );
    } else if (!isDeleting && displayed.length === text.length) {
      timer = setTimeout(() => setIsDeleting(true), 3000);
    } else if (isDeleting && displayed.length > 0) {
      timer = setTimeout(
        () => setDisplayed(text.slice(0, displayed.length - 1)),
        50,
      );
    } else if (isDeleting && displayed.length === 0) {
      setIsDeleting(false);
      setLoop(loop + 1);
    }
    return () => clearTimeout(timer);
  }, [displayed, isDeleting, text, loop]);

  return (
    <span className="relative border-r-2 border-accent pr-1 animate-pulse">
      {displayed}
    </span>
  );
}

export default function App() {
  const [userStory, setUserStory] = useState(PRESET_STORIES[0].text);
  const [useSample, setUseSample] = useState(true);
  const [agents, setAgents] = useState(initialAgents);
  const [pipelineVisible, setPipelineVisible] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [error, setError] = useState("");
  const [pipelineError, setPipelineError] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [jiraUrl, setJiraUrl] = useState("");
  const [jiraEmail, setJiraEmail] = useState("");
  const [jiraToken, setJiraToken] = useState("");
  const [jiraIssueKey, setJiraIssueKey] = useState("");
  const [ingestMessage, setIngestMessage] = useState("");
  const [ingesting, setIngesting] = useState(false);

  // Tabs: 'hero', 'pipeline', 'tests', 'score'
  const [activeTab, setActiveTab] = useState("hero");

  // Theme: light | dark
  const [theme, setTheme] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("theme") || "dark";
    }
    return "dark";
  });

  const eventSourceRef = useRef(null);
  const streamClosedRef = useRef(false);

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () =>
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));

  const resetAgents = () => setAgents(initialAgents);

  const handleRun = async () => {
    if (!userStory.trim() || isRunning) return;
    setError("");
    setPipelineError("");
    setIngestMessage("");
    setPipelineVisible(true);
    setDashboardData(null);
    setActiveTab("pipeline");
    resetAgents();
    setAgents((prev) => ({
      ...prev,
      story: {
        status: "processing",
        summary: "",
        message: "Analyzing intent architecture...",
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
        throw new Error(err.detail || "Failed to engage IronTest intelligence");
      }
      const { session_id } = await res.json();
      startStream(session_id);
    } catch (err) {
      console.error("[Pipeline] Failed to start analysis", err);
      setError(err.message);
      setPipelineError(err.message);
      setIsRunning(false);
    }
  };

  const handleJiraIngest = async () => {
    if (!jiraUrl.trim()) return;
    setIngesting(true);
    setError("");
    setIngestMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/ingest/jira`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: jiraUrl,
          email: jiraEmail || undefined,
          token: jiraToken || undefined,
          issue_key: jiraIssueKey || undefined,
        }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(payload.detail || "Jira ingestion failed");
      }
      const { user_story, issue_key } = payload;
      setUserStory(user_story);
      setUseSample(false);
      setIngestMessage(
        issue_key
          ? `Imported ${issue_key} successfully.`
          : "Jira issue imported successfully.",
      );
    } catch (err) {
      console.error("[Jira] Ingestion failed", err);
      setError(err.message);
    } finally {
      setIngesting(false);
    }
  };

  const startStream = (sessionId) => {
    if (eventSourceRef.current) {
      streamClosedRef.current = true;
      eventSourceRef.current.close();
    }

    const es = new EventSource(`${API_BASE}/api/stream/${sessionId}`);
    eventSourceRef.current = es;
    streamClosedRef.current = false;

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
                summary: `Intent captured, ${result.modules.length} microservices mapped, ${result.risk_factors.length} critical risks identified.`,
              },
            }));
          }
          if (data.agent === "test") {
            const count = data.result.length;
            setAgents((prev) => ({
              ...prev,
              test: {
                status: "done",
                summary: `Synthesized ${count} automated test vectors across edge, boundary, and core domains.`,
              },
            }));
          }
          if (data.agent === "execution") {
            const results = data.result.results;
            const passed = results.filter((r) => r.status === "pass").length;
            setAgents((prev) => ({
              ...prev,
              execution: {
                status: "done",
                summary: `${passed}/${results.length} tests passed in ${data.result.duration_seconds}s.`,
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
            execution: data.dashboard.execution,
            defects: data.dashboard.defects,
          });
          setIsRunning(false);
          // Auto switch to tests dashboard tab when done
          setTimeout(() => {
            setActiveTab("score");
            streamClosedRef.current = true;
            es.close();
          }, 1500);
        } else if (type === "error") {
          console.error("[Pipeline] Streamed backend error", data);
          setError(data.message || "Pipeline trace failure");
          setPipelineError(data.message || "Pipeline trace failure");
          setIsRunning(false);
          streamClosedRef.current = true;
          es.close();
        }
      } catch (err) {
        console.error(
          "[Pipeline] Failed to parse SSE payload",
          err,
          event.data,
        );
        setError("Failed to parse event stream payload");
        setPipelineError("Failed to parse event stream payload");
        setIsRunning(false);
        streamClosedRef.current = true;
        es.close();
      }
    };

    es.onerror = () => {
      if (streamClosedRef.current) {
        return;
      }
      console.error("[Pipeline] Stream connection error");
      setError("Stream connection severed. Please re-engage.");
      setPipelineError("Stream connection severed. Please re-engage.");
      setIsRunning(false);
      streamClosedRef.current = true;
      es.close();
    };
  };

  useEffect(() => {
    if (useSample) {
      setUserStory(PRESET_STORIES[0].text);
    }
    return () => {
      if (eventSourceRef.current) {
        streamClosedRef.current = true;
        eventSourceRef.current.close();
      }
    };
  }, []);

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
    a.download = "irontest-analysis-report.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative min-h-screen font-inter overflow-x-hidden transition-colors duration-300">
      {/* Background Grid - Awwwards Style */}
      <div className="fixed inset-0 pointer-events-none z-[-1]">
        <div className="absolute inset-0 bg-grid opacity-80" />
        <div className="absolute -left-[20%] top-[-10%] h-[600px] w-[600px] rounded-full bg-indigo-500/10 blur-[120px] dark:bg-indigo-500/20" />
        <div className="absolute right-[-10%] bottom-[-10%] h-[500px] w-[500px] rounded-full bg-cyan-500/10 blur-[140px] dark:bg-cyan-500/20" />
      </div>

      <header className="sticky top-0 z-50 border-b border-black/5 dark:border-white/10 bg-white/70 dark:bg-[#05070d]/70 backdrop-blur-xl transition-colors duration-300">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div
            className="flex items-center gap-3 cursor-pointer group"
            onClick={() => setActiveTab("hero")}
          >
            <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-black dark:bg-white overflow-hidden shadow-lg transition-transform hover:scale-105 active:scale-95">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="w-6 h-6 text-white dark:text-black z-10"
                stroke="currentColor"
                strokeWidth="3"
              >
                <path d="M12 2L3 7v10l9 5 9-5V7l-9-5z" />
                <path
                  d="M9 12l2 2 4-4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 bg-gradient-to-tr from-accent/20 to-transparent opacity-50"
              />
            </div>
            <div>
              <div className="text-lg font-bold tracking-tight text-gray-900 dark:text-white group-hover:text-accent transition-colors">
                IronTest
              </div>
              <div className="text-[0.65rem] uppercase tracking-widest text-gray-500 dark:text-gray-400 font-black">
                Autonomous QA
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {dashboardData && (
              <button
                onClick={handleDownload}
                className="hidden md:flex items-center gap-2 rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/50 px-4 py-1.5 text-xs font-semibold text-gray-700 dark:text-gray-300 shadow-sm hover:bg-gray-50 dark:hover:bg-white/5 transition"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Export Data
              </button>
            )}
            <button
              onClick={toggleTheme}
              className="group flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/50 text-gray-600 dark:text-gray-300 shadow-sm transition-all hover:bg-gray-50 dark:hover:bg-white/10 hover:rotate-12 active:scale-90"
              aria-label="Toggle Theme"
            >
              {theme === "dark" ? (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="12" cy="12" r="5" />
                  <line x1="12" y1="1" x2="12" y2="3" />
                  <line x1="12" y1="21" x2="12" y2="23" />
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                  <line x1="1" y1="12" x2="3" y2="12" />
                  <line x1="21" y1="12" x2="23" y2="12" />
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                </svg>
              ) : (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Tabs Navigation (Visible when pipeline active or dashboard exists) */}
      <AnimatePresence>
        {(pipelineVisible || dashboardData) && activeTab !== "hero" && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="sticky top-[73px] z-40 border-b border-black/5 dark:border-white/10 bg-white/50 dark:bg-[#05070d]/50 backdrop-blur-md"
          >
            <div className="mx-auto flex max-w-7xl gap-6 px-6 overflow-x-auto no-scrollbar">
              {["pipeline", "tests", "score"].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`py-4 text-sm font-semibold capitalize transition-all border-b-2 ${
                    activeTab === tab
                      ? "border-accent text-accent"
                      : "border-transparent text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="mx-auto w-full max-w-7xl px-6 py-12">
        <AnimatePresence mode="wait">
          {activeTab === "hero" && (
            <motion.div
              key="hero"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              className="flex flex-col gap-12"
            >
              <div className="flex flex-col items-center justify-center text-center py-12 lg:py-20">
                <div className="inline-block rounded-full border border-black/10 dark:border-white/10 bg-white/50 dark:bg-white/5 px-4 py-1.5 mb-6 text-xs font-semibold text-gray-800 dark:text-gray-200 backdrop-blur-sm">
                  ✨ Engineering Excellence. Automated.
                </div>
                <h1 className="text-5xl lg:text-7xl font-black tracking-tight text-gray-900 dark:text-white mb-6">
                  <TypingEffect text="Intelligent" />{" "}
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-purple-500">
                    QA Engine
                  </span>
                </h1>
                <p className="max-w-2xl text-lg text-gray-600 dark:text-gray-400 mb-10 leading-relaxed">
                  Transform raw product specs into production-ready test suites
                  using the IronTest multi-agent architecture. Define the
                  intent, and let intelligence do the rest.
                </p>

                <div className="w-full max-w-3xl rounded-3xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-black/40 p-2 shadow-2xl backdrop-blur-3xl transition-all">
                  <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-wider">
                      Target Vector
                    </span>
                    <div className="flex items-center gap-2 text-[11px] font-semibold">
                      <button
                        onClick={() => setUseSample(true)}
                        className={`rounded-full px-3 py-1 border transition ${useSample ? "border-accent text-accent bg-accent/10" : "border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400"}`}
                      >
                        Presets
                      </button>
                      <button
                        onClick={() => setUseSample(false)}
                        className={`rounded-full px-3 py-1 border transition ${!useSample ? "border-accent text-accent bg-accent/10" : "border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400"}`}
                      >
                        Manual
                      </button>
                    </div>
                    <div className="flex gap-3 shrink-0 overflow-x-auto no-scrollbar py-3 px-1 sm:pb-2">
                      {PRESET_STORIES.map((story) => (
                        <button
                          key={story.name}
                          onClick={() => {
                            setUserStory(story.text);
                            setUseSample(true);
                          }}
                          className={`rounded-full border px-5 py-2 text-xs font-bold transition-all whitespace-nowrap shadow-sm ${
                            userStory === story.text && useSample
                              ? "bg-purple-500/10 border-purple-500/50 text-purple-600 dark:text-purple-400 shadow-[0_0_20px_rgba(168,85,247,0.25)] scale-105"
                              : "bg-white dark:bg-white/5 border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-white/20"
                          }`}
                        >
                          {story.name}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="px-2 pb-2">
                    <textarea
                      className="w-full rounded-2xl border-none bg-black/5 dark:bg-black/60 p-5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-accent resize-none transition-all"
                      rows={6}
                      placeholder="Paste your raw user story or technical spec here to initiate generation..."
                      value={userStory}
                      onChange={(e) => {
                        setUserStory(e.target.value);
                        setUseSample(false);
                      }}
                    />
                  </div>

                  {/* Jira Ingestion Section */}
                  <div className="mx-2 mb-2 rounded-2xl border border-dashed border-black/10 dark:border-white/10 p-4 bg-gray-50 dark:bg-white/5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 items-end">
                    <div className="w-full space-y-1 sm:col-span-2">
                      <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                        Jira Ticket URL
                      </label>
                      <input
                        className="w-full bg-white dark:bg-black/40 border border-black/5 dark:border-white/5 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                        placeholder="https://company.atlassian.net/browse/PROJ-123"
                        value={jiraUrl}
                        onChange={(e) => setJiraUrl(e.target.value)}
                      />
                    </div>
                    <div className="w-full space-y-1">
                      <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                        Jira Email
                      </label>
                      <input
                        className="w-full bg-white dark:bg-black/40 border border-black/5 dark:border-white/5 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                        placeholder="name@company.com"
                        value={jiraEmail}
                        onChange={(e) => setJiraEmail(e.target.value)}
                      />
                    </div>
                    <div className="w-full space-y-1">
                      <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                        Access Token / PAT
                      </label>
                      <input
                        type="password"
                        className="w-full bg-white dark:bg-black/40 border border-black/5 dark:border-white/5 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                        placeholder="ATATT3xFf..."
                        value={jiraToken}
                        onChange={(e) => setJiraToken(e.target.value)}
                      />
                    </div>
                    <div className="w-full space-y-1">
                      <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                        Issue Key (Optional)
                      </label>
                      <input
                        className="w-full bg-white dark:bg-black/40 border border-black/5 dark:border-white/5 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                        placeholder="PROJ-123"
                        value={jiraIssueKey}
                        onChange={(e) => setJiraIssueKey(e.target.value)}
                      />
                    </div>
                    <button
                      onClick={handleJiraIngest}
                      disabled={ingesting || !jiraUrl}
                      className="rounded-lg bg-gray-900 dark:bg-white text-white dark:text-black text-xs font-bold px-4 py-2 hover:opacity-90 disabled:opacity-50 transition sm:col-span-2 lg:col-span-4"
                    >
                      {ingesting ? "Ingesting..." : "Import"}
                    </button>
                  </div>

                  {ingestMessage && (
                    <div className="px-4 pb-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                      {ingestMessage}
                    </div>
                  )}

                  <div className="flex justify-end p-2 border-t border-black/5 dark:border-white/10 mt-2">
                    <button
                      onClick={handleRun}
                      disabled={isRunning}
                      className="group flex items-center justify-center gap-2 rounded-xl bg-black dark:bg-white px-8 py-3.5 text-sm font-bold text-white dark:text-black shadow-lg hover:shadow-xl transition-all hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isRunning ? (
                        <>
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 dark:border-black/40 border-t-white dark:border-t-black" />
                          <span>Engaging Systems...</span>
                        </>
                      ) : (
                        <>
                          <span>Initiate Analysis</span>
                          <svg
                            className="w-4 h-4 group-hover:translate-x-1 transition-transform"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M14 5l7 7m0 0l-7 7m7-7H3"
                            />
                          </svg>
                        </>
                      )}
                    </button>
                  </div>
                </div>
                {error && !pipelineVisible && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="mt-4 text-sm font-medium text-danger"
                  >
                    {error}
                  </motion.div>
                )}
              </div>
            </motion.div>
          )}

          {activeTab === "pipeline" && (
            <motion.div
              key="pipeline"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="w-full"
            >
              <div className="mb-6">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Execution Stream
                </h2>
                <p className="text-gray-500 dark:text-gray-400 text-sm">
                  Real-time trace of the IronTest autonomous agent pipeline.
                </p>
              </div>
              <Pipeline agents={agents} isRunning={isRunning} />

              {pipelineError && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-4 rounded-xl border border-red-300/50 bg-red-100/60 dark:bg-red-950/30 px-4 py-3 text-sm font-medium text-red-700 dark:text-red-300"
                >
                  {pipelineError}
                </motion.div>
              )}

              {!isRunning && dashboardData && (
                <div className="mt-8 flex justify-center">
                  <button
                    onClick={() => setActiveTab("score")}
                    className="flex items-center gap-2 rounded-full border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-6 py-2.5 text-sm font-semibold text-gray-800 dark:text-white hover:bg-gray-50 dark:hover:bg-white/10 transition"
                  >
                    View Final Report →
                  </button>
                </div>
              )}
            </motion.div>
          )}

          {activeTab === "tests" && dashboardData && (
            <motion.div
              key="tests"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="w-full"
            >
              <div className="mb-6">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Generated Test Vectors
                </h2>
                <p className="text-gray-500 dark:text-gray-400 text-sm">
                  Comprehensive functional, boundary, and edge test cases
                  mathematically derived from intent.
                </p>
              </div>
              <TestCaseTable
                tests={dashboardData.tests}
                execution={dashboardData.execution.results || []}
                criticalIds={dashboardData.defects.critical_test_ids}
              />
            </motion.div>
          )}

          {activeTab === "score" && dashboardData && (
            <motion.div
              key="score"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="w-full flex flex-col gap-8"
            >
              <div className="mb-2">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Intelligence Dashboard
                </h2>
                <p className="text-gray-500 dark:text-gray-400 text-sm">
                  Deployment readiness and structural risk analysis.
                </p>
              </div>

              <div className="grid gap-6 lg:grid-cols-3">
                <div className="lg:col-span-1 rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                  <ConfidenceGauge
                    score={dashboardData.defects.overall_confidence_score}
                    recommendation={
                      dashboardData.defects.deployment_recommendation
                    }
                  />
                </div>
                <div className="lg:col-span-2 rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                  <RiskHeatmap
                    moduleRisks={dashboardData.defects.module_risks}
                  />
                </div>
              </div>

              <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                <StoryInsights story={dashboardData.story} />
              </div>

              <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                <DeploymentVerdict
                  recommendation={
                    dashboardData.defects.deployment_recommendation
                  }
                  rationale={dashboardData.defects.recommendation_rationale}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
