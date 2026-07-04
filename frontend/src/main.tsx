import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Database, Mail, Play, RefreshCw, Search, Settings } from "lucide-react";
import "./styles.css";

type View = "dashboard" | "candidates" | "jobs" | "config";

type Stats = {
  domains: number;
  available: number;
  spam: number;
  jobs: number;
};

type Candidate = {
  domain: string;
  status: string;
  deleted_date: string;
  total_score: number | null;
  reasons: string | null;
  archive: number | null;
  spam: number | null;
  notes: string | null;
};

type Job = {
  id: number;
  status: string;
  source: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  total_deleted: number;
  total_filtered: number;
  total_scored: number;
  total_available: number;
};

type Config = Record<string, string | number | boolean>;

const API = "";

function App() {
  const [view, setView] = useState<View>("dashboard");
  const [stats, setStats] = useState<Stats>({ domains: 0, available: 0, spam: 0, jobs: 0 });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [config, setConfig] = useState<Config>({});
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");

  async function loadAll() {
    const [statsData, jobsData, candidatesData, configData] = await Promise.all([
      api<Stats>("/api/stats"),
      api<Job[]>("/api/jobs"),
      api<Candidate[]>(`/api/domains?limit=100${status ? `&status=${status}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`),
      api<Config>("/api/config")
    ]);
    setStats(statsData);
    setJobs(jobsData);
    setCandidates(candidatesData);
    setConfig(configData);
  }

  useEffect(() => {
    loadAll().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (view === "candidates") {
      api<Candidate[]>(`/api/domains?limit=100${status ? `&status=${status}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`)
        .then(setCandidates)
        .catch((error) => setMessage(error.message));
    }
  }, [search, status, view]);

  const nav = useMemo(
    () => [
      ["dashboard", Activity, "Dashboard"],
      ["candidates", Database, "Candidates"],
      ["jobs", Play, "Jobs"],
      ["config", Settings, "Config"]
    ] as const,
    []
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">Domain Hunter</div>
        <nav>
          {nav.map(([key, Icon, label]) => (
            <button className={view === key ? "active" : ""} key={key} onClick={() => setView(key)}>
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <h1>{titleFor(view)}</h1>
            <p>Deleted .com discovery pipeline</p>
          </div>
          <button className="iconButton" onClick={() => loadAll().catch((error) => setMessage(error.message))} title="Refresh">
            <RefreshCw size={18} />
          </button>
        </header>

        {message && <div className="notice">{message}</div>}
        {view === "dashboard" && <Dashboard stats={stats} jobs={jobs} candidates={candidates} onRun={runJob} setMessage={setMessage} />}
        {view === "candidates" && (
          <Candidates candidates={candidates} search={search} setSearch={setSearch} status={status} setStatus={setStatus} />
        )}
        {view === "jobs" && <Jobs jobs={jobs} onRun={runJob} setMessage={setMessage} />}
        {view === "config" && <ConfigView config={config} setConfig={setConfig} setMessage={setMessage} />}
      </main>
    </div>
  );

  async function runJob() {
    const result = await api<{ job_id: number }>("/api/jobs/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    setMessage(`Job ${result.job_id} started`);
    await loadAll();
  }
}

function Dashboard({ stats, jobs, candidates, onRun, setMessage }: { stats: Stats; jobs: Job[]; candidates: Candidate[]; onRun: () => Promise<void>; setMessage: (value: string) => void }) {
  return (
    <section className="stack">
      <div className="metrics">
        <Metric label="Domains" value={stats.domains} />
        <Metric label="Available" value={stats.available} />
        <Metric label="Spam history" value={stats.spam} />
        <Metric label="Jobs" value={stats.jobs} />
      </div>
      <div className="toolbar">
        <button onClick={() => onRun().catch((error) => setMessage(error.message))}>
          <Play size={18} />
          Run pipeline
        </button>
        <UploadButton setMessage={setMessage} />
      </div>
      <h2>Top Candidates</h2>
      <CandidateTable candidates={candidates.slice(0, 10)} />
      <h2>Recent Jobs</h2>
      <JobTable jobs={jobs.slice(0, 5)} />
    </section>
  );
}

function Candidates({ candidates, search, setSearch, status, setStatus }: { candidates: Candidate[]; search: string; setSearch: (value: string) => void; status: string; setStatus: (value: string) => void }) {
  return (
    <section className="stack">
      <div className="filters">
        <label className="search">
          <Search size={17} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search domain" />
        </label>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All statuses</option>
          <option value="available">Available</option>
          <option value="registered">Registered</option>
          <option value="deleted">Deleted</option>
        </select>
      </div>
      <CandidateTable candidates={candidates} />
    </section>
  );
}

function Jobs({ jobs, onRun, setMessage }: { jobs: Job[]; onRun: () => Promise<void>; setMessage: (value: string) => void }) {
  return (
    <section className="stack">
      <div className="toolbar">
        <button onClick={() => onRun().catch((error) => setMessage(error.message))}>
          <Play size={18} />
          Run pipeline
        </button>
        <UploadButton setMessage={setMessage} />
      </div>
      <JobTable jobs={jobs} />
    </section>
  );
}

function ConfigView({ config, setConfig, setMessage }: { config: Config; setConfig: (value: Config) => void; setMessage: (value: string) => void }) {
  const fields = [
    ["app_env", "App environment"],
    ["database_url", "Database path"],
    ["data_dir", "Data directory"],
    ["cache_dir", "Cache directory"],
    ["czds_zone_url", "CZDS zone URL"],
    ["czds_bearer_token", "CZDS bearer token"],
    ["availability_provider", "Availability provider"],
    ["availability_concurrency", "Availability concurrency"],
    ["availability_timeout_seconds", "Availability timeout"],
    ["wayback_enabled", "Wayback enabled"],
    ["wayback_timeout_seconds", "Wayback timeout"],
    ["top_candidates", "Top candidates"],
    ["min_score", "Minimum score"],
    ["schedule_enabled", "Schedule enabled"],
    ["schedule_hour", "Schedule hour"],
    ["schedule_minute", "Schedule minute"],
    ["smtp_host", "SMTP host"],
    ["smtp_port", "SMTP port"],
    ["smtp_username", "SMTP username"],
    ["smtp_password", "SMTP password"],
    ["smtp_use_tls", "SMTP TLS"],
    ["email_from", "Email from"],
    ["email_to", "Email to"],
    ["send_empty_report", "Send empty report"]
  ] as const;

  async function save() {
    const saved = await api<Config>("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    setConfig(saved);
    setMessage("Config saved");
  }

  return (
    <section className="configGrid">
      {fields.map(([key, label]) => (
        <label key={key}>
          <span>{label}</span>
          {typeof config[key] === "boolean" ? (
            <input type="checkbox" checked={Boolean(config[key])} onChange={(event) => setConfig({ ...config, [key]: event.target.checked })} />
          ) : (
            <input
              type={key.includes("password") ? "password" : typeof config[key] === "number" ? "number" : "text"}
              value={String(config[key] ?? "")}
              onChange={(event) => setConfig({ ...config, [key]: typeof config[key] === "number" ? Number(event.target.value) : event.target.value })}
            />
          )}
        </label>
      ))}
      <button className="save" onClick={() => save().catch((error) => setMessage(error.message))}>
        <Mail size={18} />
        Save config
      </button>
    </section>
  );
}

function UploadButton({ setMessage }: { setMessage: (value: string) => void }) {
  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    const result = await api<{ job_id: number }>("/api/jobs/upload", { method: "POST", body: form });
    setMessage(`Upload job ${result.job_id} started`);
  }

  return (
    <label className="upload">
      Upload deleted list
      <input type="file" accept=".txt,.csv" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0]).catch((error) => setMessage(error.message))} />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CandidateTable({ candidates }: { candidates: Candidate[] }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Score</th>
            <th>Status</th>
            <th>History</th>
            <th>Reasons</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((item) => (
            <tr key={item.domain}>
              <td>{item.domain}</td>
              <td>{item.total_score ?? "-"}</td>
              <td><span className={`pill ${item.status}`}>{item.status}</span></td>
              <td>{item.spam ? "Spam" : item.notes || "Clean"}</td>
              <td>{item.reasons || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobTable({ jobs }: { jobs: Job[] }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Source</th>
            <th>Deleted</th>
            <th>Filtered</th>
            <th>Scored</th>
            <th>Available</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>{job.id}</td>
              <td><span className={`pill ${job.status}`}>{job.status}</span></td>
              <td>{job.source}</td>
              <td>{job.total_deleted}</td>
              <td>{job.total_filtered}</td>
              <td>{job.total_scored}</td>
              <td>{job.total_available}</td>
              <td>{job.error || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function titleFor(view: View) {
  return view.charAt(0).toUpperCase() + view.slice(1);
}

createRoot(document.getElementById("root")!).render(<App />);
