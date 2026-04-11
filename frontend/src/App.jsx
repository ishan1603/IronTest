import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Pipeline from "./components/Pipeline.jsx";
import TestCaseTable from "./components/TestCaseTable.jsx";
import ConfidenceGauge from "./components/ConfidenceGauge.jsx";
import RiskHeatmap from "./components/RiskHeatmap.jsx";
import DeploymentVerdict from "./components/DeploymentVerdict.jsx";
import ScoreHistoryBars from "./components/ScoreHistoryBars.jsx";
import StoryInsights from "./components/StoryInsights.jsx";
import VantaGlobeBackground from "./components/VantaGlobeBackground.jsx";

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
  const [jiraToken, setJiraToken] = useState("");
  const [ingestSource, setIngestSource] = useState("jira");
  const [adoUrl, setAdoUrl] = useState("");
  const [adoPat, setAdoPat] = useState("");
  const [ingestMessage, setIngestMessage] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [storyScoreHistory, setStoryScoreHistory] = useState([]);

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
  const targetVectorRef = useRef(null);

  const agentOutputCards = useMemo(() => {
    const base = [
      {
        key: "story",
        icon: "🧠",
        title: "Story Agent",
        primary: "Story extraction in progress...",
        secondary: "Waiting for parsed intent output.",
      },
      {
        key: "test",
        icon: "⚙️",
        title: "Test Generation Agent",
        primary: "Test vectors are being generated...",
        secondary: "Coverage distribution will appear here.",
      },
      {
        key: "execution",
        icon: "🚀",
        title: "Execution Agent",
        primary: "Execution run is pending...",
        secondary: "Pass/fail/error split will appear here.",
      },
      {
        key: "defect",
        icon: "🔍",
        title: "Defect Agent",
        primary: "Risk synthesis is pending...",
        secondary: "Recommendation and confidence will appear here.",
      },
    ];

    if (!dashboardData) {
      return base.map((item) => {
        const agent = agents[item.key];
        return {
          ...item,
          primary: agent?.summary || item.primary,
          secondary: agent?.message || item.secondary,
          details: [],
        };
      });
    }

    const typeCounts = (dashboardData.tests || []).reduce((acc, test) => {
      const key = test.type || "other";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});

    const results = dashboardData.execution?.results || [];
    const passed = results.filter((r) => r.status === "pass").length;
    const failed = results.filter((r) => r.status === "fail").length;
    const errors = results.filter((r) => r.status === "error").length;

    return [
      {
        key: "story",
        icon: "🧠",
        title: "Story Agent",
        primary: "Story extracted successfully from user input.",
        secondary: `${dashboardData.story?.modules?.length || 0} modules and ${dashboardData.story?.acceptance_criteria?.length || 0} acceptance criteria identified.`,
        details: [
          `Intent: ${dashboardData.story?.intent || "N/A"}`,
          `Risk factors mapped: ${(dashboardData.story?.risk_factors || []).slice(0, 3).join(", ") || "None"}`,
        ],
      },
      {
        key: "test",
        icon: "⚙️",
        title: "Test Generation Agent",
        primary: "Generated test cases by coverage profile.",
        secondary: `${typeCounts.functional || 0} functional, ${typeCounts.boundary || 0} boundary, ${typeCounts.edge_case || 0} edge, ${typeCounts.regression || 0} regression.`,
        details: [
          `Total vectors executed: ${dashboardData.tests?.length || 0}`,
          `High-risk vectors: ${(dashboardData.tests || []).filter((x) => x.risk_level === "high").length}`,
        ],
      },
      {
        key: "execution",
        icon: "🚀",
        title: "Execution Agent",
        primary: "Execution run completed and validated.",
        secondary: `${passed} passed, ${failed} failed, ${errors} errors across ${results.length} tests.`,
        details: [
          `Pass rate: ${((passed / Math.max(1, passed + failed + errors)) * 100).toFixed(1)}% (excluding skipped)`,
          `Duration: ${dashboardData.execution?.duration_seconds || 0}s`,
        ],
      },
      {
        key: "defect",
        icon: "🔍",
        title: "Defect Agent",
        primary: `Recommendation: ${dashboardData.defects?.deployment_recommendation || "PENDING"}.`,
        secondary: `Confidence score: ${dashboardData.defects?.overall_confidence_score ?? 0} with prioritized critical vectors.`,
        details: [
          `Trend: ${dashboardData.defects?.historical_comparison?.trend || "stable"}`,
          `Critical tests: ${(dashboardData.defects?.critical_test_ids || []).slice(0, 3).join(", ") || "None"}`,
        ],
      },
    ];
  }, [agents, dashboardData]);

  useEffect(() => {
    const fetchHistory = async () => {
      if (!dashboardData) {
        setStoryScoreHistory([]);
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/history/story`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            story_text: userStory,
            story_intent: dashboardData.story?.intent || "",
            modules: dashboardData.story?.modules || [],
            limit: 8,
          }),
        });
        if (!res.ok) {
          setStoryScoreHistory([]);
          return;
        }
        const payload = await res.json();
        const normalized = (payload.runs || []).map((run, idx) => ({
          label: `Run ${idx + 1}`,
          score: Number.isFinite(Number(run.confidence_score))
            ? Number(run.confidence_score)
            : Math.round(Number(run.pass_rate || 0) * 100),
          created_at: run.created_at,
        }));
        setStoryScoreHistory(normalized.reverse());
      } catch {
        setStoryScoreHistory([]);
      }
    };

    fetchHistory();
  }, [dashboardData, userStory]);

  const scoreImprovementSuggestions = useMemo(() => {
    if (!dashboardData) return [];

    const tests = dashboardData.tests || [];
    const results = dashboardData.execution?.results || [];
    const moduleRisks = dashboardData.defects?.module_risks || [];
    const criticalIds = new Set(dashboardData.defects?.critical_test_ids || []);
    const score = dashboardData.defects?.overall_confidence_score ?? 0;

    const testById = new Map(tests.map((t) => [t.id, t]));
    const failing = results.filter(
      (r) => r.status === "fail" || r.status === "error",
    );
    const infrastructureErrors = results.filter(
      (r) => r.status === "error",
    ).length;

    const suggestions = [];

    const failedCritical = failing
      .filter((r) => criticalIds.has(r.test_id))
      .slice(0, 3)
      .map((r) => {
        const test = testById.get(r.test_id);
        return test ? `${r.test_id} (${test.module})` : r.test_id;
      });

    if (failedCritical.length > 0) {
      suggestions.push(
        `Resolve critical failing tests first: ${failedCritical.join(", ")}. These have the highest impact on deployment confidence.`,
      );
    }

    if (infrastructureErrors > 0) {
      suggestions.push(
        "Stabilize execution infrastructure errors (service connectivity, auth, environment setup) before functional tuning to quickly lift confidence score.",
      );
    }

    const highRiskModules = moduleRisks
      .filter(
        (m) =>
          m.regression_risk === "critical" ||
          m.regression_risk === "high" ||
          (m.defect_probability ?? 0) >= 0.6,
      )
      .slice(0, 3)
      .map((m) => m.module);

    if (highRiskModules.length > 0) {
      suggestions.push(
        `Increase regression and boundary coverage for high-risk modules: ${highRiskModules.join(", ")}.`,
      );
    }

    if (score < 80) {
      suggestions.push(
        "Align failing test assertions directly with acceptance criteria and add targeted negative-path checks for each risky module.",
      );
    }

    if (suggestions.length === 0) {
      suggestions.push(
        "Current quality signal is healthy. Keep the score stable by adding one regression test for every future bug fix and monitoring pass-rate drift.",
      );
    }

    return suggestions;
  }, [dashboardData]);

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

  const handleManualMode = () => {
    setUseSample(false);
    setUserStory("");
    requestAnimationFrame(() => {
      targetVectorRef.current?.focus();
      targetVectorRef.current?.setSelectionRange(0, 0);
    });
  };

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
          token: jiraToken || undefined,
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
          ? `Imported ${issue_key} from Jira successfully.`
          : "Jira issue imported successfully.",
      );
    } catch (err) {
      console.error("[Jira] Ingestion failed", err);
      setError(err.message);
    } finally {
      setIngesting(false);
    }
  };

  const handleAzureDevOpsIngest = async () => {
    if (!adoUrl.trim()) return;
    setIngesting(true);
    setError("");
    setIngestMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/ingest/azure-devops`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: adoUrl,
          pat: adoPat || undefined,
        }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(payload.detail || "Azure DevOps ingestion failed");
      }
      const { user_story, issue_key } = payload;
      setUserStory(user_story);
      setUseSample(false);
      setIngestMessage(
        issue_key
          ? `Imported ${issue_key} from Azure DevOps successfully.`
          : "Azure DevOps work item imported successfully.",
      );
    } catch (err) {
      console.error("[Azure DevOps] Ingestion failed", err);
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

  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const handleDownload = async () => {
    if (!dashboardData) return;

    let storyHistory = null;
    try {
      const historyResponse = await fetch(`${API_BASE}/api/history/story`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          story_text: userStory,
          story_intent: dashboardData.story?.intent || "",
          modules: dashboardData.story?.modules || [],
          limit: 120,
        }),
      });
      if (historyResponse.ok) {
        storyHistory = await historyResponse.json();
      }
    } catch (historyErr) {
      console.error("History lookup failed during export", historyErr);
    }

    const executionById = new Map(
      (dashboardData.execution?.results || []).map((item) => [
        item.test_id,
        item,
      ]),
    );

    const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
    const formatDateTime = (value) => {
      try {
        return new Date(value).toLocaleString();
      } catch {
        return String(value || "-");
      }
    };

    const testRows = (dashboardData.tests || [])
      .map((test) => {
        const exec = executionById.get(test.id) || {};
        const snippet = Array.isArray(test.automation_snippet)
          ? test.automation_snippet.join("\n")
          : String(test.automation_snippet || "");
        return `
          <section class="card">
            <div class="head">
              <h3>${escapeHtml(test.id)} - ${escapeHtml(test.module)}</h3>
              <span class="badge ${escapeHtml(exec.status || "unknown")}">${escapeHtml((exec.status || "unknown").toUpperCase())}</span>
            </div>
            <p><strong>Type:</strong> ${escapeHtml(test.type)}</p>
            <p><strong>Risk:</strong> ${escapeHtml(test.risk_level)}</p>
            <p><strong>Description:</strong> ${escapeHtml(test.description)}</p>
            <p><strong>Expected:</strong> ${escapeHtml(test.expected_result)}</p>
            <p><strong>Steps:</strong></p>
            <ul>${(test.steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ul>
            <p><strong>Snippet:</strong></p>
            <pre>${escapeHtml(snippet || "No snippet")}</pre>
            <p><strong>Execution Output:</strong></p>
            <pre>${escapeHtml(exec.error_message || "No output")}</pre>
          </section>
        `;
      })
      .join("\n");

    const moduleRiskRows = (dashboardData.defects?.module_risks || [])
      .map(
        (risk) => `
          <tr>
            <td>${escapeHtml(risk.module)}</td>
            <td>${escapeHtml(risk.regression_risk)}</td>
            <td>${escapeHtml((risk.defect_probability * 100).toFixed(1))}%</td>
            <td>${escapeHtml(risk.historical_defect_count)}</td>
            <td>${escapeHtml((risk.top_defect_types || []).join(", "))}</td>
          </tr>
        `,
      )
      .join("");

    const historyRuns = storyHistory?.runs || [];
    const historyRows = historyRuns
      .map(
        (run) => `
          <tr>
            <td>${escapeHtml(formatDateTime(run.created_at))}</td>
            <td>${escapeHtml(run.source || "pipeline")}</td>
            <td>${escapeHtml(toPercent(run.pass_rate))}</td>
            <td>${escapeHtml(run.passed || 0)}/${escapeHtml(run.total_tests || 0)}</td>
            <td>${escapeHtml((Number(run.failed || 0) + Number(run.errors || 0)).toString())}</td>
            <td>${escapeHtml(Number(run.duration || 0).toFixed(2))}s</td>
          </tr>
        `,
      )
      .join("");

    const trendClass =
      storyHistory?.trend === "improving"
        ? "trend improving"
        : storyHistory?.trend === "declining"
          ? "trend declining"
          : "trend stable";

    const historicalComparison = dashboardData.defects?.historical_comparison;

    const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>IronTest Report</title>
    <style>
      body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #0f172a; }
      h1, h2 { margin: 0 0 10px 0; }
      .meta, .summary { margin-bottom: 18px; }
      .grid { display: grid; grid-template-columns: repeat(2,minmax(280px,1fr)); gap: 12px; }
      .card { border: 1px solid #dbe3ee; border-radius: 12px; padding: 14px; margin-bottom: 14px; background: #ffffff; }
      .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
      .badge { padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
      .badge.pass { background: #dcfce7; color: #166534; }
      .badge.fail, .badge.error { background: #fee2e2; color: #991b1b; }
      .badge.skipped { background: #e2e8f0; color: #334155; }
      pre { white-space: pre-wrap; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #f8fafc; }
      table { width: 100%; border-collapse: collapse; margin-top: 8px; }
      th, td { border: 1px solid #dbe3ee; padding: 8px; text-align: left; font-size: 13px; }
      th { background: #f1f5f9; }
      .trend { display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 12px; font-weight: 700; text-transform: uppercase; }
      .trend.improving { background: #dcfce7; color: #166534; }
      .trend.declining { background: #fee2e2; color: #991b1b; }
      .trend.stable { background: #e2e8f0; color: #334155; }
    </style>
  </head>
  <body>
    <h1>IronTest Structured Report</h1>
    <div class="meta"><strong>Generated:</strong> ${escapeHtml(new Date().toISOString())}</div>
    <div class="summary card">
      <h2>Deployment Summary</h2>
      <p><strong>Confidence Score:</strong> ${escapeHtml(dashboardData.defects?.overall_confidence_score)}</p>
      <p><strong>Recommendation:</strong> ${escapeHtml(dashboardData.defects?.deployment_recommendation)}</p>
      <p><strong>Rationale:</strong> ${escapeHtml(dashboardData.defects?.recommendation_rationale)}</p>
      <p><strong>Critical Tests:</strong> ${escapeHtml((dashboardData.defects?.critical_test_ids || []).join(", "))}</p>
    </div>

    <div class="summary card">
      <h2>Historical Comparison</h2>
      <p><strong>Total Historical Runs:</strong> ${escapeHtml(historicalComparison?.total_runs ?? storyHistory?.total_runs ?? 0)}</p>
      <p><strong>Current Pass Rate:</strong> ${escapeHtml(toPercent(historicalComparison?.current_pass_rate ?? dashboardData.execution?.results?.filter((x) => x.status === "pass").length / Math.max(1, dashboardData.execution?.results?.length || 1)))}</p>
      <p><strong>Historical Average Pass Rate:</strong> ${escapeHtml(toPercent(historicalComparison?.historical_average_pass_rate ?? storyHistory?.average_pass_rate ?? 0))}</p>
      <p><strong>Recent Pass Rate:</strong> ${escapeHtml(toPercent(historicalComparison?.recent_pass_rate ?? storyHistory?.recent_pass_rate ?? 0))}</p>
      <p><strong>Trend:</strong> <span class="${escapeHtml(trendClass)}">${escapeHtml((historicalComparison?.trend || storyHistory?.trend || "stable").toUpperCase())}</span></p>
    </div>

    <div class="summary card">
      <h2>Story Intelligence</h2>
      <p><strong>Intent:</strong> ${escapeHtml(dashboardData.story?.intent)}</p>
      <p><strong>Modules:</strong> ${escapeHtml((dashboardData.story?.modules || []).join(", "))}</p>
      <p><strong>Acceptance Criteria:</strong></p>
      <ul>${(dashboardData.story?.acceptance_criteria || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
      <p><strong>Risk Factors:</strong> ${escapeHtml((dashboardData.story?.risk_factors || []).join(", "))}</p>
      <p><strong>Security Vectors:</strong> ${escapeHtml((dashboardData.story?.security_vectors || []).join(", "))}</p>
      <p><strong>Microservices:</strong> ${escapeHtml((dashboardData.story?.microservices || []).join(", "))}</p>
    </div>

    <div class="summary card">
      <h2>Module Risk Matrix</h2>
      <table>
        <thead>
          <tr><th>Module</th><th>Regression Risk</th><th>Defect Probability</th><th>Historical Defects</th><th>Top Defect Types</th></tr>
        </thead>
        <tbody>${moduleRiskRows}</tbody>
      </table>
    </div>

    <div class="summary card">
      <h2>Per-Story Run Timeline</h2>
      <p><strong>Story Key:</strong> ${escapeHtml(storyHistory?.story_key || "Unavailable")}</p>
      <p><strong>Story Label:</strong> ${escapeHtml(storyHistory?.story_label || dashboardData.story?.intent || "Unavailable")}</p>
      <table>
        <thead>
          <tr><th>Run Time</th><th>Source</th><th>Pass Rate</th><th>Pass/Total</th><th>Failures+Errors</th><th>Duration</th></tr>
        </thead>
        <tbody>${historyRows || "<tr><td colspan='6'>No historical runs found for this story.</td></tr>"}</tbody>
      </table>
    </div>

    <h2>Test Cases and Execution</h2>
    <div class="grid">${testRows}</div>
  </body>
</html>`;

    const blob = new Blob([html], {
      type: "text/html",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "irontest-analysis-report.html";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative min-h-screen font-inter overflow-x-hidden transition-colors duration-300">
      <div className="fixed inset-0 z-[-1] overflow-hidden">
        <VantaGlobeBackground theme={theme} />
        <div className="pointer-events-none absolute inset-0 bg-transparent dark:bg-gradient-to-b dark:from-[#030c07]/85 dark:via-[#030c07]/55 dark:to-[#030c07]/25" />
      </div>

      <header className="sticky top-3 z-50 px-3 transition-colors duration-300">
        <motion.div
          initial={{ opacity: 0.95, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mx-auto flex w-full max-w-7xl items-center justify-between rounded-full border border-black/10 dark:border-white/15 bg-white/55 dark:bg-[#07130e]/55 px-4 py-2.5 shadow-[0_8px_30px_rgba(0,0,0,0.16)] dark:shadow-[0_8px_30px_rgba(34,197,94,0.2)] backdrop-blur-2xl"
        >
          <motion.div
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex cursor-pointer items-center gap-3 group"
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
          </motion.div>

          <div className="flex items-center gap-4">
            {(pipelineVisible || dashboardData) && (
              <button
                onClick={() => setActiveTab(isRunning ? "pipeline" : "score")}
                className="flex items-center gap-2 rounded-full border border-emerald-300/50 dark:border-emerald-400/30 bg-emerald-500/15 dark:bg-emerald-500/20 px-4 py-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-200 shadow-[0_0_18px_rgba(34,197,94,0.24)] hover:bg-emerald-500/25 transition"
              >
                Resume Last Run
              </button>
            )}
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
              className="group flex h-9 w-9 items-center justify-center rounded-full border border-gray-200/80 dark:border-white/20 bg-white/75 dark:bg-white/10 text-gray-600 dark:text-gray-200 shadow-[0_0_14px_rgba(255,255,255,0.1)] transition-all hover:bg-white dark:hover:bg-white/15 hover:rotate-12 active:scale-90"
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
        </motion.div>
      </header>

      {/* Tabs Navigation (Visible when pipeline active or dashboard exists) */}
      <AnimatePresence>
        {(pipelineVisible || dashboardData) && activeTab !== "hero" && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="sticky top-[73px] z-40 border-b border-black/5 dark:border-white/10 bg-transparent dark:bg-transparent"
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
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-emerald-400">
                    QA Engine
                  </span>
                </h1>
                <p className="max-w-2xl text-lg text-gray-600 dark:text-gray-400 mb-10 leading-relaxed">
                  Transform raw product specs into production-ready test suites
                  using the IronTest multi-agent architecture. Define the
                  intent, and let intelligence do the rest.
                </p>

                <div className="w-full max-w-5xl rounded-3xl border border-black/10 dark:border-emerald-400/20 bg-white/60 dark:bg-white/5 p-2 shadow-2xl dark:shadow-[0_0_30px_rgba(34,197,94,0.2)] backdrop-blur-3xl transition-all">
                  <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-wider">
                        Target Vector
                      </span>
                      <button
                        onClick={handleManualMode}
                        className={`inline-flex items-center gap-1 rounded-full px-3 py-1 border text-[11px] font-semibold transition ${!useSample ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" : "border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:border-emerald-300/30 hover:text-emerald-600 dark:hover:text-emerald-300"}`}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
                        Manual Mode
                      </button>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 py-3 px-1 sm:pb-2">
                      {PRESET_STORIES.map((story) => (
                        <button
                          key={story.name}
                          onClick={() => {
                            setUserStory(story.text);
                            setUseSample(true);
                          }}
                          className={`rounded-full border px-4 py-1.5 text-[11px] font-bold transition-all whitespace-nowrap shadow-sm ${
                            userStory === story.text && useSample
                              ? "bg-emerald-500/10 border-emerald-500/50 text-emerald-600 dark:text-emerald-400 shadow-[0_0_20px_rgba(34,197,94,0.25)]"
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
                      ref={targetVectorRef}
                      className="w-full rounded-2xl border border-black/5 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-accent resize-none transition-all"
                      rows={6}
                      placeholder="Paste your raw user story or technical spec here to initiate generation..."
                      value={userStory}
                      onChange={(e) => {
                        setUserStory(e.target.value);
                        setUseSample(false);
                      }}
                    />
                  </div>

                  {/* Work Item Ingestion Section */}
                  <div className="mx-2 mb-2 rounded-2xl border border-dashed border-black/10 dark:border-emerald-400/20 p-4 bg-gray-50/90 dark:!bg-white/5 grid gap-3 sm:grid-cols-2 lg:grid-cols-12 items-end backdrop-blur-xl">
                    <div className="sm:col-span-2 lg:col-span-12 flex items-center gap-2 rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-1">
                      <button
                        onClick={() => setIngestSource("jira")}
                        className={`rounded-lg px-3 py-1.5 text-[11px] font-bold transition ${
                          ingestSource === "jira"
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-400/40"
                            : "text-gray-600 dark:text-gray-300"
                        }`}
                      >
                        Jira
                      </button>
                      <button
                        onClick={() => setIngestSource("azure_devops")}
                        className={`rounded-lg px-3 py-1.5 text-[11px] font-bold transition ${
                          ingestSource === "azure_devops"
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-400/40"
                            : "text-gray-600 dark:text-gray-300"
                        }`}
                      >
                        Azure DevOps
                      </button>
                    </div>

                    {ingestSource === "jira" ? (
                      <>
                        <div className="w-full space-y-1 sm:col-span-2 lg:col-span-5">
                          <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                            Jira Ticket URL
                          </label>
                          <input
                            className="w-full bg-white dark:bg-white/[0.06] border border-black/5 dark:border-white/10 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                            placeholder="https://company.atlassian.net/browse/PROJ-123"
                            value={jiraUrl}
                            onChange={(e) => setJiraUrl(e.target.value)}
                          />
                        </div>
                        <div className="w-full space-y-1 lg:col-span-7">
                          <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                            Access Token / PAT
                          </label>
                          <input
                            type="password"
                            className="w-full bg-white dark:bg-white/[0.06] border border-black/5 dark:border-white/10 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                            placeholder="ATATT3xFf..."
                            value={jiraToken}
                            onChange={(e) => setJiraToken(e.target.value)}
                          />
                        </div>
                        <button
                          onClick={handleJiraIngest}
                          disabled={ingesting || !jiraUrl}
                          className="rounded-lg bg-gradient-to-r from-emerald-500 to-green-600 text-white text-xs font-bold px-4 py-2 shadow-[0_0_22px_rgba(34,197,94,0.35)] hover:brightness-110 disabled:opacity-50 transition sm:col-span-2 lg:col-span-12"
                        >
                          {ingesting ? "Ingesting..." : "Import Jira"}
                        </button>
                      </>
                    ) : (
                      <>
                        <div className="w-full space-y-1 sm:col-span-2 lg:col-span-8">
                          <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                            Azure DevOps Work Item URL
                          </label>
                          <input
                            className="w-full bg-white dark:bg-white/[0.06] border border-black/5 dark:border-white/10 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                            placeholder="https://dev.azure.com/org/project/_workitems/edit/123"
                            value={adoUrl}
                            onChange={(e) => setAdoUrl(e.target.value)}
                          />
                        </div>
                        <div className="w-full space-y-1 lg:col-span-4">
                          <label className="text-[10px] uppercase font-bold text-gray-500 dark:text-gray-400">
                            Azure DevOps PAT
                          </label>
                          <input
                            type="password"
                            className="w-full bg-white dark:bg-white/[0.06] border border-black/5 dark:border-white/10 rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-accent"
                            placeholder="azdpat..."
                            value={adoPat}
                            onChange={(e) => setAdoPat(e.target.value)}
                          />
                        </div>
                        <button
                          onClick={handleAzureDevOpsIngest}
                          disabled={ingesting || !adoUrl}
                          className="rounded-lg bg-gradient-to-r from-emerald-500 to-green-600 text-white text-xs font-bold px-4 py-2 shadow-[0_0_22px_rgba(34,197,94,0.35)] hover:brightness-110 disabled:opacity-50 transition sm:col-span-2 lg:col-span-12"
                        >
                          {ingesting ? "Ingesting..." : "Import Azure DevOps"}
                        </button>
                      </>
                    )}
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
                      className="group flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-green-600 px-8 py-3.5 text-sm font-bold text-white shadow-[0_0_24px_rgba(34,197,94,0.35)] hover:brightness-110 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed"
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

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                {agentOutputCards.map((card, index) => (
                  <motion.div
                    key={card.key}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.08 * index, duration: 0.28 }}
                    className="rounded-2xl border border-black/10 dark:border-emerald-400/25 bg-white/55 dark:bg-[#11172a]/70 p-4 shadow-lg dark:shadow-[0_0_20px_rgba(34,197,94,0.2)] backdrop-blur-xl"
                  >
                    <div className="mb-2 flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                      <span>{card.icon}</span>
                      <span>{card.title}</span>
                    </div>
                    <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                      {card.primary}
                    </p>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {card.secondary}
                    </p>
                    {Array.isArray(card.details) && card.details.length > 0 && (
                      <ul className="mt-2 list-disc pl-5 space-y-1 text-[11px] text-gray-600 dark:text-gray-300">
                        {card.details.map((detail) => (
                          <li key={`${card.key}-${detail}`}>{detail}</li>
                        ))}
                      </ul>
                    )}
                  </motion.div>
                ))}
              </div>

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

              <div className="rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
                <RiskHeatmap moduleRisks={dashboardData.defects.module_risks} />
              </div>

              <div className="grid gap-6 lg:grid-cols-3">
                <div className="lg:col-span-1 rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-4 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
                  <ConfidenceGauge
                    score={dashboardData.defects.overall_confidence_score}
                    recommendation={
                      dashboardData.defects.deployment_recommendation
                    }
                  />
                </div>
                <div className="lg:col-span-2 rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
                  <DeploymentVerdict
                    recommendation={
                      dashboardData.defects.deployment_recommendation
                    }
                    rationale={dashboardData.defects.recommendation_rationale}
                  />
                </div>
              </div>

              <div className="rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
                <ScoreHistoryBars
                  currentScore={dashboardData.defects.overall_confidence_score}
                  runs={storyScoreHistory}
                />
              </div>

              <div className="rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
                <StoryInsights story={dashboardData.story} />
              </div>

              <div className="rounded-2xl border border-black/5 dark:border-emerald-400/20 bg-white/50 dark:bg-white/5 p-6 backdrop-blur-xl shadow-xl dark:shadow-[0_0_22px_rgba(34,197,94,0.18)]">
                <div className="flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white mb-3">
                  <span>📈</span>
                  <span>Suggestions To Improve Score</span>
                </div>
                <ul className="list-disc pl-5 space-y-2 text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                  {scoreImprovementSuggestions.map((suggestion, idx) => (
                    <li key={`improve-score-${idx}`}>{suggestion}</li>
                  ))}
                </ul>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
