import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Banner, Card, EmptyState, Label, Spinner, StatusDot, Tag } from "../components/ui";
import { BarList, StatTile, TrendChart } from "../components/Charts";

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
};
const item = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
};

export default function Analytics() {
  const [data, setData] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.analytics(), api.analyticsRuns(150)])
      .then(([overview, runList]) => {
        setData(overview);
        setRuns(runList.runs);
      })
      .catch((exc) => setError(exc.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Shell>
        <div className="flex justify-center py-24">
          <Spinner />
        </div>
      </Shell>
    );
  }

  if (error) {
    return (
      <Shell>
        <div className="px-4 py-16 sm:px-6">
          <Banner>{error}</Banner>
        </div>
      </Shell>
    );
  }

  const totals = data.totals;
  const empty = totals.runs === 0;

  return (
    <Shell>
      <div className="px-4 py-8 sm:px-6 sm:py-10">
        <header className="mb-8">
          <Label>Analytics</Label>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Runs &amp; trends</h1>
        </header>

        {empty ? (
          <Card className="p-0">
            <EmptyState
              title="No completed runs yet"
              description="Run a repository test suite and this fills in with pass-rate trends, flaky tests, and per-repo history."
              action={
                <Link to="/dashboard" className="rounded-pill bg-contrast px-4 py-2 text-sm text-contrast-ink">
                  Choose a repository
                </Link>
              }
            />
          </Card>
        ) : (
          <>
            <motion.div
              variants={stagger}
              initial="hidden"
              animate="show"
              className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4"
            >
              <motion.div variants={item}>
                <StatTile label="Runs" value={totals.runs} />
              </motion.div>
              <motion.div variants={item}>
                <StatTile label="Tests executed" value={totals.tests_executed} />
              </motion.div>
              <motion.div variants={item}>
                <StatTile label="Avg pass rate" value={totals.avg_pass_rate * 100} suffix="%" decimals={0} />
              </motion.div>
              <motion.div variants={item}>
                <StatTile label="Avg confidence" value={totals.avg_confidence} decimals={0} />
              </motion.div>
            </motion.div>

            <div className="mb-6">
              <TrendChart points={data.trend} />
            </div>

            <div className="mb-6 grid gap-4 lg:grid-cols-2">
              <BarList
                title="Repositories by run count"
                rows={data.by_repository.map((r) => ({
                  label: r.repository,
                  value: r.avg_pass_rate,
                  runs: r.runs,
                }))}
                format={(r) => `${Math.round(r.value * 100)}% · ${r.runs} runs`}
              />
              <BarList
                title="Modules that fail most"
                rows={data.worst_modules.map((m) => ({
                  label: m.module,
                  value: m.fail_rate,
                  failed: m.failed,
                }))}
                format={(m) => `${Math.round(m.value * 100)}% · ${m.failed} fails`}
              />
            </div>

            {data.flaky_tests.length > 0 && (
              <Card className="mb-8 overflow-hidden p-0">
                <div className="border-b border-line/12 px-5 py-3">
                  <Label>Flaky tests</Label>
                  <p className="mt-1 text-xs text-muted">
                    Same test, both passed and failed across runs of the same requirement.
                  </p>
                </div>
                <ul className="divide-y divide-line/12">
                  {data.flaky_tests.map((f, i) => (
                    <li key={i} className="flex items-center gap-3 px-5 py-3">
                      <span className="flex-1 truncate text-sm">{f.description}</span>
                      <Tag tone="warning">{Math.round(f.flip_rate * 100)}% flip</Tag>
                      <span className="font-mono text-xs text-muted">
                        {f.passed}✓ / {f.failed}✗
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            <section>
              <h2 className="label-caps mb-3">All runs</h2>
              <Card className="overflow-hidden p-0">
                <div className="scroll-x">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead>
                      <tr className="border-b border-line/12 text-left">
                        <th className="px-4 py-2 font-medium">When</th>
                        <th className="px-4 py-2 font-medium">Repository</th>
                        <th className="px-4 py-2 font-medium">Mode</th>
                        <th className="px-4 py-2 font-medium">Result</th>
                        <th className="px-4 py-2 font-medium">Pass</th>
                        <th className="px-4 py-2 font-medium">Conf.</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/12">
                      {runs.map((r) => (
                        <tr key={r.id} className="transition-colors hover:bg-line/[0.03]">
                          <td className="px-4 py-2.5">
                            <Link to={`/runs/${r.id}`} className="underline-offset-2 hover:underline">
                              {new Date(r.created_at).toLocaleString()}
                            </Link>
                          </td>
                          <td className="px-4 py-2.5 font-mono text-xs">{r.repository || "—"}</td>
                          <td className="px-4 py-2.5">
                            <Tag>{r.mode === "specification" ? "spec" : "existing"}</Tag>
                          </td>
                          <td className="px-4 py-2.5">
                            {r.status === "complete" ? (
                              <span className="font-mono text-xs">
                                {r.passed}/{r.passed + r.failed + r.errors}
                              </span>
                            ) : (
                              <StatusDot status={r.status === "failed" ? "fail" : "skipped"} />
                            )}
                          </td>
                          <td className="px-4 py-2.5 tabular-nums">
                            {r.status === "complete" ? `${Math.round(r.pass_rate * 100)}%` : "—"}
                          </td>
                          <td className="px-4 py-2.5 tabular-nums">{r.confidence_score ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </section>
          </>
        )}
      </div>
    </Shell>
  );
}
