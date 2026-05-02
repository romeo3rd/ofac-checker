import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { Download, Play, RotateCcw } from "lucide-react";
import { createRun, fetchRun, pdfUrl, zipUrl } from "./api";
import type { OfacResult, OfacRun, ResultStatus, RunStatus } from "./types";

const ACTIVE_RUNS = new Set<RunStatus>(["queued", "running"]);
const LAST_RUN_KEY = "ofac:lastRunId";

export function App() {
  const [namesText, setNamesText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<OfacRun | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const lastRunId = window.localStorage.getItem(LAST_RUN_KEY);
    if (lastRunId) {
      loadRun(lastRunId);
    }
  }, []);

  useEffect(() => {
    if (!run || !ACTIVE_RUNS.has(run.status)) return;

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const next = await fetchRun(run.id);
        if (!cancelled) setRun(next);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Could not refresh run.",
          );
      }
    }, 1500);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [run]);

  async function loadRun(runId: string) {
    try {
      setRun(await fetchRun(runId));
      setError(null);
    } catch {
      window.localStorage.removeItem(LAST_RUN_KEY);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const nextRun = await createRun(namesText, file);
      window.localStorage.setItem(LAST_RUN_KEY, nextRun.id);
      setRun(nextRun);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start run.");
    } finally {
      setSubmitting(false);
    }
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.currentTarget.files?.[0] ?? null);
  }

  function resetForm() {
    setNamesText("");
    setFile(null);
    setError(null);
  }

  const progress = useMemo(() => {
    if (!run || run.total_count === 0) return 0;
    return Math.round((run.completed_count / run.total_count) * 100);
  }, [run]);

  return (
    <main className="shell">
      <header className="topbar">
        <h1>OFAC Batch Checker</h1>
        {run && (
          <a
            className={`downloadButton ${run.completed_count === 0 ? "disabled" : ""}`}
            href={zipUrl(run.id)}
          >
            <Download size={17} />
            ZIP
          </a>
        )}
      </header>

      <section className="singlePageGrid">
        <form className="panel submitPanel" onSubmit={submit}>
          <div className="panelHeader">
            <h2>Run Checks</h2>
          </div>
          <label className="field">
            <span>Names or companies</span>
            <textarea
              value={namesText}
              onChange={(event) => setNamesText(event.target.value)}
              placeholder={"Christian Poole\nAcme Holdings LLC\nJane Doe"}
            />
          </label>
          <label className="fileDrop">
            <span>{file ? file.name : "Attach .txt or .csv"}</span>
            <input
              accept=".txt,.csv,text/plain,text/csv"
              type="file"
              onChange={chooseFile}
            />
          </label>
          {error && <div className="errorBox">{error}</div>}
          <div className="buttonRow">
            <button
              className="primaryButton"
              type="submit"
              disabled={submitting}
            >
              <Play size={17} />
              {submitting ? "Starting..." : "Run checks"}
            </button>
            <button
              className="secondaryButton"
              type="button"
              onClick={resetForm}
            >
              <RotateCcw size={17} />
              Clear
            </button>
          </div>
        </form>

        <section className="panel resultPanel">
          {run ? (
            <>
              <div className="panelHeader resultHeader">
                <div>
                  <h2>Current Batch</h2>
                  <p>Run {run.id}</p>
                </div>
                <RunBadge status={run.status} />
              </div>
              <section className="statsBand compact">
                <Metric
                  label="Progress"
                  value={`${run.completed_count}/${run.total_count}`}
                />
                <Metric label="Clear" value={String(run.no_hit_count)} />
                <Metric
                  label="Hits"
                  value={String(run.hit_count)}
                  tone="danger"
                />
                <Metric
                  label="Errors"
                  value={String(run.error_count)}
                  tone="warn"
                />
              </section>
              <div className="progressTrack">
                <div style={{ width: `${progress}%` }} />
              </div>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Status</th>
                      <th>Result</th>
                      <th>PDF</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(run.results ?? []).map((result) => (
                      <ResultRow
                        key={result.id}
                        runId={run.id}
                        result={result}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="emptyState large">
              <strong>No batch</strong>
              <span>Paste names or upload a file.</span>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

function ResultRow({ runId, result }: { runId: string; result: OfacResult }) {
  return (
    <tr>
      <td className="nameCell">{result.name}</td>
      <td>
        <ResultBadge status={result.status} />
      </td>
      <td className={result.error_message ? "errorText" : ""}>
        {result.error_message || result.result_text || "Waiting..."}
      </td>
      <td>
        {result.pdf_path ? (
          <a className="iconLink" href={pdfUrl(runId, result.id)}>
            <Download size={16} />
            PDF
          </a>
        ) : (
          <span className="muted">Not ready</span>
        )}
      </td>
    </tr>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "danger" | "warn";
}) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ResultBadge({ status }: { status: ResultStatus }) {
  return <span className={`badge ${status}`}>{statusLabel(status)}</span>;
}

function RunBadge({ status }: { status: RunStatus }) {
  return <span className={`badge ${status}`}>{runStatusLabel(status)}</span>;
}

function statusLabel(status: ResultStatus) {
  return {
    pending: "Pending",
    checking: "Checking",
    no_hit: "No Hit",
    hit_found: "Hit Found",
    error: "Error",
  }[status];
}

function runStatusLabel(status: RunStatus) {
  return {
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    completed_with_errors: "Completed With Errors",
    error: "Error",
  }[status];
}
