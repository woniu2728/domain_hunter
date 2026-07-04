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
const VIEW_TITLES: Record<View, string> = {
  dashboard: "仪表盘",
  candidates: "候选域名",
  jobs: "任务",
  config: "配置"
};

const STATUS_LABELS: Record<string, string> = {
  available: "可注册",
  registered: "已注册",
  deleted: "已删除",
  running: "运行中",
  success: "成功",
  failed: "失败"
};

const SOURCE_LABELS: Record<string, string> = {
  api: "手动运行",
  upload: "上传文件",
  cli: "命令行",
  schedule: "定时任务",
  manual: "手动运行"
};

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
      ["dashboard", Activity, "仪表盘"],
      ["candidates", Database, "候选域名"],
      ["jobs", Play, "任务"],
      ["config", Settings, "配置"]
    ] as const,
    []
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">域名猎手</div>
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
            <p>已删除 .com 域名发现流程</p>
          </div>
          <button className="iconButton" onClick={() => loadAll().catch((error) => setMessage(error.message))} title="刷新">
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
    setMessage(`任务 ${result.job_id} 已启动`);
    await loadAll();
  }
}

function Dashboard({ stats, jobs, candidates, onRun, setMessage }: { stats: Stats; jobs: Job[]; candidates: Candidate[]; onRun: () => Promise<void>; setMessage: (value: string) => void }) {
  return (
    <section className="stack">
      <div className="metrics">
        <Metric label="域名总数" value={stats.domains} />
        <Metric label="可注册" value={stats.available} />
        <Metric label="疑似垃圾历史" value={stats.spam} />
        <Metric label="任务数" value={stats.jobs} />
      </div>
      <div className="toolbar">
        <button onClick={() => onRun().catch((error) => setMessage(error.message))}>
          <Play size={18} />
          运行流程
        </button>
        <UploadButton setMessage={setMessage} />
      </div>
      <h2>高分候选</h2>
      <CandidateTable candidates={candidates.slice(0, 10)} />
      <h2>最近任务</h2>
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
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索域名" />
        </label>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">全部状态</option>
          <option value="available">可注册</option>
          <option value="registered">已注册</option>
          <option value="deleted">已删除</option>
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
          运行流程
        </button>
        <UploadButton setMessage={setMessage} />
      </div>
      <JobTable jobs={jobs} />
    </section>
  );
}

function ConfigView({ config, setConfig, setMessage }: { config: Config; setConfig: (value: Config) => void; setMessage: (value: string) => void }) {
  const fields = [
    ["app_env", "运行环境"],
    ["database_url", "数据库路径"],
    ["data_dir", "数据目录"],
    ["cache_dir", "缓存目录"],
    ["czds_zone_url", "CZDS Zone 地址"],
    ["czds_bearer_token", "CZDS Bearer Token"],
    ["availability_provider", "可用性查询方式"],
    ["availability_concurrency", "可用性查询并发数"],
    ["availability_timeout_seconds", "可用性查询超时秒数"],
    ["wayback_enabled", "启用 Wayback 检查"],
    ["wayback_timeout_seconds", "Wayback 超时秒数"],
    ["top_candidates", "候选数量上限"],
    ["min_score", "最低评分"],
    ["schedule_enabled", "启用定时任务"],
    ["schedule_hour", "定时小时"],
    ["schedule_minute", "定时分钟"],
    ["smtp_host", "SMTP 主机"],
    ["smtp_port", "SMTP 端口"],
    ["smtp_username", "SMTP 用户名"],
    ["smtp_password", "SMTP 密码"],
    ["smtp_use_tls", "启用 SMTP TLS"],
    ["email_from", "发件人"],
    ["email_to", "收件人"],
    ["send_empty_report", "无结果时发送报告"]
  ] as const;

  async function save() {
    const saved = await api<Config>("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    setConfig(saved);
    setMessage("配置已保存");
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
        保存配置
      </button>
    </section>
  );
}

function UploadButton({ setMessage }: { setMessage: (value: string) => void }) {
  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    const result = await api<{ job_id: number }>("/api/jobs/upload", { method: "POST", body: form });
    setMessage(`上传任务 ${result.job_id} 已启动`);
  }

  return (
    <label className="upload">
      上传已删除列表
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
            <th>域名</th>
            <th>评分</th>
            <th>状态</th>
            <th>历史</th>
            <th>评分原因</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((item) => (
            <tr key={item.domain}>
              <td>{item.domain}</td>
              <td>{item.total_score ?? "-"}</td>
              <td><span className={`pill ${item.status}`}>{statusLabel(item.status)}</span></td>
              <td>{item.spam ? "疑似垃圾历史" : item.notes || "干净"}</td>
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
            <th>状态</th>
            <th>来源</th>
            <th>删除数</th>
            <th>过滤后</th>
            <th>已评分</th>
            <th>可注册</th>
            <th>错误</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>{job.id}</td>
              <td><span className={`pill ${job.status}`}>{statusLabel(job.status)}</span></td>
              <td>{sourceLabel(job.source)}</td>
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
  return VIEW_TITLES[view];
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function sourceLabel(source: string) {
  return SOURCE_LABELS[source] ?? source;
}

createRoot(document.getElementById("root")!).render(<App />);
