import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { Download, LogOut, Play, RotateCcw } from "lucide-react";
import {
  AuthRequiredError,
  createRun,
  fetchAuthStatus,
  fetchRun,
  login,
  logout,
  pdfUrl,
  zipUrl,
} from "./api";
import type { OfacResult, OfacRun, ResultStatus, RunStatus } from "./types";

const ACTIVE_RUNS = new Set<RunStatus>(["queued", "running"]);
const LAST_RUN_KEY = "ofac:lastRunId";

export function App() {
  const [namesText, setNamesText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<OfacRun | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [authConfigured, setAuthConfigured] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    const lastRunId = window.localStorage.getItem(LAST_RUN_KEY);
    if (lastRunId) loadRun(lastRunId);
  }, [authenticated]);

  useEffect(() => {
    if (!run || !ACTIVE_RUNS.has(run.status)) return;

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const next = await fetchRun(run.id);
        if (!cancelled) setRun(next);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof AuthRequiredError) {
          endSession();
        } else {
          setError(
            err instanceof Error ? err.message : "Could not refresh run.",
          );
        }
      }
    }, 1500);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [run]);

  async function checkAuth() {
    try {
      const status = await fetchAuthStatus();
      setAuthConfigured(status.configured);
      setAuthenticated(status.authenticated);
    } catch {
      setAuthConfigured(false);
      setAuthenticated(false);
    } finally {
      setAuthChecked(true);
    }
  }

  function endSession() {
    window.localStorage.removeItem(LAST_RUN_KEY);
    setAuthenticated(false);
    setRun(null);
    setError(null);
  }

  async function loadRun(runId: string) {
    try {
      setRun(await fetchRun(runId));
      setError(null);
    } catch (err) {
      if (err instanceof AuthRequiredError) {
        endSession();
        return;
      }
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
      if (err instanceof AuthRequiredError) {
        endSession();
      } else {
        setError(err instanceof Error ? err.message : "Could not start run.");
      }
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

  if (!authChecked) {
    return (
      <main className="loginShell">
        <section className="panel loginPanel">
          <h1>OFAC Batch Checker</h1>
        </section>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <LoginScreen
        configured={authConfigured}
        onSignedIn={() => {
          setAuthenticated(true);
        }}
      />
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <h1>OFAC Batch Checker</h1>
        <div className="topbarActions">
          {run && (
            <a
              className={`downloadButton ${run.completed_count === 0 ? "disabled" : ""}`}
              href={zipUrl(run.id)}
            >
              <Download size={17} />
              ZIP
            </a>
          )}
          <button
            className="secondaryButton"
            type="button"
            onClick={async () => {
              await logout();
              endSession();
            }}
          >
            <LogOut size={16} />
            Sign out
          </button>
        </div>
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

function LoginScreen({
  configured,
  onSignedIn,
}: {
  configured: boolean;
  onSignedIn: () => void;
}) {
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);

  async function submitLogin(event: FormEvent) {
    event.preventDefault();
    if (!configured) return;
    setSigningIn(true);
    setLoginError(null);
    try {
      await login(password);
      onSignedIn();
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Could not sign in.");
    } finally {
      setSigningIn(false);
    }
  }

  return (
    <main className="loginShell">
      <form className="panel loginPanel" onSubmit={submitLogin}>
        <div>
          <h1>OFAC Batch Checker</h1>
          <p>Sign in to continue.</p>
        </div>
        {!configured && (
          <div className="errorBox">Authentication is not configured.</div>
        )}
        <label className="field">
          <span>Password</span>
          <input
            autoComplete="current-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {loginError && <div className="errorBox">{loginError}</div>}
        <button
          className="primaryButton"
          type="submit"
          disabled={!configured || signingIn}
        >
          {signingIn ? "Signing in..." : "Sign in"}
        </button>
      </form>
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
