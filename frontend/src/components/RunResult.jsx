import { useState } from "react";
import clsx from "clsx";
import { Card, Label, Meter, StatusDot, Tag } from "./ui";

const VERDICT_TONE = {
  GO: "success",
  "CONDITIONAL GO": "warning",
  "NO-GO": "danger",
};

/** Full result of one pipeline run. */
export function RunResult({ run }) {
  const execution = run.execution || {};
  const defects = run.defects || {};
  const story = run.story || {};
  const tests = run.tests || [];
  const results = execution.results || [];
  const ranOnHost = run.sandboxed === false || run.execution?.backend === "local_host";

  const counts = results.reduce(
    (acc, item) => ({ ...acc, [item.status]: (acc[item.status] || 0) + 1 }),
    {},
  );
  const executed = (counts.pass || 0) + (counts.fail || 0) + (counts.error || 0);
  const passRate = executed ? Math.round(((counts.pass || 0) / executed) * 100) : 0;
  const isSpec = run.mode === "specification";

  return (
    <div className="flex flex-col gap-4">
      {isSpec && <SpecificationNotice counts={counts} />}
      {isSpec && <BuildGuidance story={story} defects={defects} />}
      {ranOnHost && (
        <p className="font-mono text-xs text-muted">
          Ran on this machine (not a sandbox). A deployed install uses Docker or GitHub Actions.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card className="p-5">
          <Label>Execution</Label>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-semibold tabular-nums">{passRate}%</span>
            <span className="text-sm text-muted">
              {counts.pass || 0} of {executed} executed passed
            </span>
          </div>
          <div className="mt-3">
            <Meter
              value={passRate}
              label="Pass rate"
              tone={passRate >= 80 ? "success" : passRate >= 50 ? "warning" : "danger"}
            />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Passed" value={counts.pass || 0} />
            <Stat label="Failed" value={counts.fail || 0} tone={counts.fail ? "danger" : undefined} />
            <Stat label="Errors" value={counts.error || 0} tone={counts.error ? "danger" : undefined} />
            <Stat label="Skipped" value={counts.skipped || 0} />
          </dl>
          {run.duration_seconds > 0 && (
            <p className="mt-3 font-mono text-xs text-muted">
              Completed in {run.duration_seconds.toFixed(1)}s
            </p>
          )}
        </Card>

        {defects.deployment_recommendation && (
          <Card contrast className="flex flex-col justify-between p-5">
            <div>
              <Label className="text-contrast-ink/60">Verdict</Label>
              <p className="mt-3 text-xl font-semibold">{defects.deployment_recommendation}</p>
            </div>
            <div className="mt-4">
              <p className="font-mono text-xs opacity-70">
                Confidence {defects.overall_confidence_score}/100
              </p>
              {defects.recommendation_rationale && (
                <p className="mt-2 text-sm leading-relaxed opacity-90">
                  {defects.recommendation_rationale}
                </p>
              )}
            </div>
          </Card>
        )}
      </div>

      <TestTable tests={tests} results={results} />

      {Array.isArray(defects.module_risks) && defects.module_risks.length > 0 && (
        <ModuleRisks risks={defects.module_risks} />
      )}
    </div>
  );
}

function SpecificationNotice({ counts }) {
  const failing = (counts.fail || 0) + (counts.error || 0);
  return (
    <div className="rounded-md border border-warning/30 px-4 py-3">
      <p className="text-sm font-medium text-warning">Specification run — failures are expected</p>
      <p className="mt-1 text-sm text-muted">
        This feature is not built yet, so these {failing} failing test{failing === 1 ? "" : "s"} are the
        red phase of test-driven development. They describe what “done” means. Implement the code until
        they pass.
      </p>
    </div>
  );
}

function BuildGuidance({ story, defects }) {
  const cautions = [
    ...(story.risk_factors || []),
    ...(story.security_vectors || []).map((v) => `Security: ${v}`),
  ];
  if (!cautions.length && !defects.recommendation_rationale) return null;

  return (
    <Card className="p-5">
      <Label>What to watch out for while building</Label>
      {cautions.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2 text-sm">
          {cautions.map((item, index) => (
            <li key={index} className="flex gap-2">
              <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-pill bg-ink" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
      {defects.recommendation_rationale && (
        <p className="mt-3 border-t border-line/12 pt-3 text-sm text-muted">
          {defects.recommendation_rationale}
        </p>
      )}
    </Card>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div>
      <dt className="label-caps">{label}</dt>
      <dd className={clsx("mt-1 text-lg font-semibold tabular-nums", tone === "danger" && "text-danger")}>
        {value}
      </dd>
    </div>
  );
}

function TestTable({ tests, results }) {
  const [open, setOpen] = useState(null);
  const byId = Object.fromEntries(tests.map((test) => [test.id, test]));

  if (results.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-muted">No test results were produced for this run.</p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b border-line/12 px-5 py-3">
        <Label>Test cases</Label>
      </div>
      <ul className="divide-y divide-line/12">
        {results.map((result) => {
          const test = byId[result.test_id] || {};
          const isOpen = open === result.test_id;
          return (
            <li key={result.test_id}>
              <button
                onClick={() => setOpen(isOpen ? null : result.test_id)}
                aria-expanded={isOpen}
                className="flex w-full items-start gap-3 px-5 py-3 text-left hover:bg-line/[0.03]"
              >
                <span className="mt-0.5 shrink-0">
                  <StatusDot status={result.status} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-muted">{result.test_id}</span>
                    {test.type && <Tag>{test.type}</Tag>}
                    {test.risk_level === "high" && <Tag tone="danger">high risk</Tag>}
                  </span>
                  <span className="mt-1 block text-sm">
                    {test.description || "Generated test case"}
                  </span>
                </span>
                <span aria-hidden="true" className="shrink-0 text-muted">
                  {isOpen ? "−" : "+"}
                </span>
              </button>

              {isOpen && (
                <div className="border-t border-line/12 bg-line/[0.02] px-5 py-4">
                  {test.expected_result && (
                    <p className="mb-3 text-sm">
                      <span className="label-caps mr-2">Expected</span>
                      {test.expected_result}
                    </p>
                  )}
                  {Array.isArray(test.steps) && test.steps.length > 0 && (
                    <ol className="mb-3 list-inside list-decimal text-sm text-muted">
                      {test.steps.map((step, index) => (
                        <li key={index}>{step}</li>
                      ))}
                    </ol>
                  )}
                  {result.error_message && (
                    <pre className="scroll-x max-h-72 rounded-sm border border-line/12 p-3 font-mono text-xs leading-relaxed">
                      {result.error_message}
                    </pre>
                  )}
                  {test.skip_reason && (
                    <p className="mt-2 text-xs text-muted">{test.skip_reason}</p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function ModuleRisks({ risks }) {
  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b border-line/12 px-5 py-3">
        <Label>Module risk</Label>
      </div>
      <div className="scroll-x">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-line/12 text-left">
              <th scope="col" className="px-5 py-2 font-medium">Module</th>
              <th scope="col" className="px-5 py-2 font-medium">Risk</th>
              <th scope="col" className="px-5 py-2 font-medium">Pass rate</th>
              <th scope="col" className="px-5 py-2 font-medium">Trend</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/12">
            {risks.map((risk) => (
              <tr key={risk.module}>
                <td className="px-5 py-3 font-medium">{risk.module}</td>
                <td className="px-5 py-3">
                  <Tag tone={risk.regression_risk === "low" ? "success" : risk.regression_risk === "medium" ? "warning" : "danger"}>
                    {risk.regression_risk}
                  </Tag>
                </td>
                <td className="px-5 py-3 tabular-nums">{Math.round((risk.module_pass_rate || 0) * 100)}%</td>
                <td className="px-5 py-3 text-muted">
                  {risk.trend_vs_history === "first_run" ? "first run" : risk.trend_vs_history}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
