import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Pipeline from "./components/Pipeline.jsx";
import Dashboard from "./components/Dashboard.jsx";
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

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme((prev) => (prev === "dark" ? "light" : "dark"));

  const resetAgents = () => setAgents(initialAgents);

  const handleRun = async () => {
    if (!userStory.trim() || isRunning) return;
    setError("");
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
          // Auto switch to tests dashboard tab when done
          setTimeout(() => {
            setActiveTab("score");
            es.close();
          }, 1500);
        } else if (type === "error") {
          setError(data.message || "Pipeline trace failure");
          setIsRunning(false);
          es.close();
        }
      } catch (err) {
        setError("Failed to parse event stream payload");
        setIsRunning(false);
        es.close();
      }
    };

    es.onerror = () => {
      setError("Stream connection severed. Please re-engage.");
      setIsRunning(false);
      es.close();
    };
  };

  useEffect(() => {
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
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => setActiveTab("hero")}>
             <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-black dark:bg-white text-xl font-black text-white dark:text-black shadow-lg">
                I
              </div>
            <div>
              <div className="text-lg font-bold tracking-tight text-gray-900 dark:text-white">IronTest</div>
              <div className="text-[0.65rem] uppercase tracking-widest text-gray-500 dark:text-gray-400 font-semibold">
                Autonomous QA Platform
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            {dashboardData && (
               <button
                  onClick={handleDownload}
                  className="hidden md:flex items-center gap-2 rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/50 px-4 py-1.5 text-xs font-semibold text-gray-700 dark:text-gray-300 shadow-sm hover:bg-gray-50 dark:hover:bg-white/5 transition"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  Export Data
                </button>
            )}
            <button
              onClick={toggleTheme}
              className="group flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/50 text-gray-600 dark:text-gray-300 shadow-sm transition hover:bg-gray-50 dark:hover:bg-white/10"
              aria-label="Toggle Theme"
            >
              {theme === "dark" ? "☀️" : "🌙"}
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
              {['pipeline', 'tests', 'score'].map((tab) => (
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
                <h1 className="text-5xl lg:text-7xl font-bold tracking-tight text-gray-900 dark:text-white mb-6">
                  Intelligent <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-purple-500">QA Engine</span>
                </h1>
                <p className="max-w-2xl text-lg text-gray-600 dark:text-gray-400 mb-10">
                  Transform raw product specs into production-ready test suites using the IronTest multi-agent architecture. Define the intent, and let intelligence do the rest.
                </p>
                
                <div className="w-full max-w-3xl rounded-3xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-black/40 p-2 shadow-2xl backdrop-blur-3xl transition-all">
                  <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-wider">
                      Target Vector
                    </span>
                    <div className="flex gap-2 shrink-0 overflow-x-auto no-scrollbar pb-2 sm:pb-0">
                      <button
                        onClick={() => setUseSample(!useSample)}
                        className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-all shadow-sm ${
                          useSample
                            ? "bg-accent text-white"
                            : "bg-white dark:bg-white/10 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-white/10"
                        }`}
                      >
                        Sample Active
                      </button>
                      {PRESET_STORIES.map((story) => (
                        <button
                          key={story.name}
                          onClick={() => setUserStory(story.text)}
                          className="rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 px-4 py-1.5 text-xs font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors whitespace-nowrap"
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
                      onChange={(e) => setUserStory(e.target.value)}
                      disabled={useSample}
                    />
                  </div>
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
                          <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
                        </>
                      )}
                    </button>
                  </div>
                </div>
                {error && <motion.div initial={{ opacity:0 }} animate={{opacity:1}} className="mt-4 text-sm font-medium text-danger">{error}</motion.div>}
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
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Execution Stream</h2>
                <p className="text-gray-500 dark:text-gray-400 text-sm">Real-time trace of the IronTest autonomous agent pipeline.</p>
              </div>
              <Pipeline agents={agents} />
              
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
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Generated Test Vectors</h2>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Comprehensive functional, boundary, and edge test cases mathematically derived from intent.</p>
                </div>
                <TestCaseTable tests={dashboardData.tests} criticalIds={dashboardData.defects.critical_test_ids} />
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
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Intelligence Dashboard</h2>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">Deployment readiness and structural risk analysis.</p>
                </div>
                
                <div className="grid gap-6 lg:grid-cols-3">
                  <div className="lg:col-span-1 rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                    <ConfidenceGauge
                      score={dashboardData.defects.overall_confidence_score}
                      recommendation={dashboardData.defects.deployment_recommendation}
                    />
                  </div>
                  <div className="lg:col-span-2 rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                    <RiskHeatmap moduleRisks={dashboardData.defects.module_risks} />
                  </div>
                </div>

                <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                  <StoryInsights story={dashboardData.story} />
                </div>
                
                <div className="rounded-2xl border border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl">
                   <DeploymentVerdict
                    recommendation={dashboardData.defects.deployment_recommendation}
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
