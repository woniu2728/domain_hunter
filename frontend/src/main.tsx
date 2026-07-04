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

type ConfigValue = string | number | boolean | ZoneSource[] | undefined;
type Config = Record<string, ConfigValue>;
type ZoneSource = {
  tld: string;
  zone_url: string;
  bearer_token: string;
  enabled: boolean;
};
type AppConfig = Config & {
  zone_sources?: ZoneSource[];
};

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
  cli: "命令行",
  schedule: "定时任务",
  manual: "手动运行"
};

const ERROR_LABELS: Record<string, string> = {
  "Provide deleted_file or both today_zone and yesterday_zone.": "请先在配置中添加启用的 Zone 来源。"
};

function App() {
  const [view, setView] = useState<View>("dashboard");
  const [stats, setStats] = useState<Stats>({ domains: 0, available: 0, spam: 0, jobs: 0 });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [config, setConfig] = useState<AppConfig>({});
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");
  const hasRunningJob = jobs.some((job) => job.status === "running");
  const hasDirectRunSource = Boolean(config.zone_sources?.some((source) => source.enabled && source.tld && source.zone_url));

  async function loadAll() {
    const [statsData, jobsData, candidatesData, configData] = await Promise.all([
      api<Stats>("/api/stats"),
      api<Job[]>("/api/jobs"),
      api<Candidate[]>(`/api/domains?limit=100${status ? `&status=${status}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`),
      api<AppConfig>("/api/config")
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
            <p>已删除域名发现流程</p>
          </div>
          <button className="iconButton" onClick={() => loadAll().catch((error) => setMessage(error.message))} title="刷新">
            <RefreshCw size={18} />
          </button>
        </header>

        {message && <div className="notice">{message}</div>}
        {view === "dashboard" && (
          <Dashboard
            stats={stats}
            jobs={jobs}
            candidates={candidates}
            onRun={runJob}
            setMessage={setMessage}
            hasRunningJob={hasRunningJob}
            hasDirectRunSource={hasDirectRunSource}
          />
        )}
        {view === "candidates" && (
          <Candidates candidates={candidates} search={search} setSearch={setSearch} status={status} setStatus={setStatus} />
        )}
        {view === "jobs" && (
          <Jobs
            jobs={jobs}
            onRun={runJob}
            setMessage={setMessage}
            hasRunningJob={hasRunningJob}
            hasDirectRunSource={hasDirectRunSource}
          />
        )}
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

function Dashboard({
  stats,
  jobs,
  candidates,
  onRun,
  setMessage,
  hasRunningJob,
  hasDirectRunSource
}: {
  stats: Stats;
  jobs: Job[];
  candidates: Candidate[];
  onRun: () => Promise<void>;
  setMessage: (value: string) => void;
  hasRunningJob: boolean;
  hasDirectRunSource: boolean;
}) {
  return (
    <section className="stack">
      <div className="metrics">
        <Metric label="域名总数" value={stats.domains} />
        <Metric label="可注册" value={stats.available} />
        <Metric label="疑似垃圾历史" value={stats.spam} />
        <Metric label="任务数" value={stats.jobs} />
      </div>
      <div className="toolbar">
        <button disabled={hasRunningJob || !hasDirectRunSource} onClick={() => onRun().catch((error) => setMessage(error.message))}>
          <Play size={18} />
          {hasRunningJob ? "任务运行中" : "从 CZDS 运行"}
        </button>
      </div>
      <div className="hint">
        流程会读取已删除域名来源，依次执行规则过滤、品牌评分、可注册查询、Wayback 历史检查和邮件通知。
        {!hasDirectRunSource && " 从 CZDS 运行需要先在配置中添加启用的 Zone 来源。"}
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

function Jobs({
  jobs,
  onRun,
  setMessage,
  hasRunningJob,
  hasDirectRunSource
}: {
  jobs: Job[];
  onRun: () => Promise<void>;
  setMessage: (value: string) => void;
  hasRunningJob: boolean;
  hasDirectRunSource: boolean;
}) {
  return (
    <section className="stack">
      <div className="toolbar">
        <button disabled={hasRunningJob || !hasDirectRunSource} onClick={() => onRun().catch((error) => setMessage(error.message))}>
          <Play size={18} />
          {hasRunningJob ? "任务运行中" : "从 CZDS 运行"}
        </button>
      </div>
      <div className="hint">
        流程会读取已删除域名来源，依次执行规则过滤、品牌评分、可注册查询、Wayback 历史检查和邮件通知。
        {!hasDirectRunSource && " 从 CZDS 运行需要启用的 Zone 来源。"}
      </div>
      <JobTable jobs={jobs} />
    </section>
  );
}

function ConfigView({ config, setConfig, setMessage }: { config: AppConfig; setConfig: (value: AppConfig) => void; setMessage: (value: string) => void }) {
  const groups = [
    {
      title: "运行路径",
      description: "后端启动和运行时使用的本地路径。",
      fields: [
        ["app_env", "运行环境"],
        ["database_url", "数据库路径"],
        ["data_dir", "数据目录"],
        ["cache_dir", "缓存目录"]
      ]
    },
    {
      title: "数据源",
      description: "可配置多个后缀的 Zone 来源。运行时会下载启用来源；有对应昨日 Zone 文件才计算差分，没有则跳过。",
      zoneSources: true,
      fields: []
    },
    {
      title: "域名过滤规则",
      description: "这些规则会在评分前执行，用来减少低质量候选。",
      fields: [
        ["filter_min_length", "最小长度"],
        ["filter_max_length", "最大长度"],
        ["filter_letters_only", "仅允许字母"],
        ["filter_require_vowel", "要求至少一个元音"],
        ["filter_no_digits", "拒绝数字"],
        ["filter_no_hyphen", "拒绝连字符"],
        ["filter_max_consecutive_consonants", "最大连续辅音数"]
      ]
    },
    {
      title: "评分与查询",
      description: "控制候选规模、最低分和外部查询超时。",
      fields: [
        ["top_candidates", "候选数量上限"],
        ["min_score", "最低评分"],
        ["availability_provider", "可用性查询方式"],
        ["availability_concurrency", "可用性查询并发数"],
        ["availability_timeout_seconds", "可用性查询超时秒数"],
        ["wayback_enabled", "启用 Wayback 检查"],
        ["wayback_timeout_seconds", "Wayback 超时秒数"]
      ]
    },
    {
      title: "定时任务",
      description: "控制自动运行时间。",
      fields: [
        ["schedule_enabled", "启用定时任务"],
        ["schedule_hour", "定时小时"],
        ["schedule_minute", "定时分钟"]
      ]
    },
    {
      title: "邮件通知",
      description: "配置 SMTP 后，流程完成时会发送候选域名报告。",
      fields: [
        ["smtp_host", "SMTP 主机"],
        ["smtp_port", "SMTP 端口"],
        ["smtp_username", "SMTP 用户名"],
        ["smtp_password", "SMTP 密码"],
        ["smtp_use_tls", "启用 SMTP TLS"],
        ["email_from", "发件人"],
        ["email_to", "收件人"],
        ["send_empty_report", "无结果时发送报告"]
      ]
    }
  ] as const;

  async function save() {
    const saved = await api<AppConfig>("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    setConfig(saved);
    setMessage("配置已保存");
  }

  return (
    <section className="configSections">
      {groups.map((group) => (
        <section className="configSection" key={group.title}>
          <div className="sectionHeader">
            <h2>{group.title}</h2>
            <p>{group.description}</p>
          </div>
          <div className="configGrid">
            {"zoneSources" in group && group.zoneSources ? (
              <ZoneSourcesEditor config={config} setConfig={setConfig} />
            ) : (
              group.fields.map(([key, label]) => (
                <ConfigField config={config} fieldKey={key} key={key} label={label} setConfig={setConfig} />
              ))
            )}
          </div>
        </section>
      ))}
      <button className="save" onClick={() => save().catch((error) => setMessage(error.message))}>
        <Mail size={18} />
        保存配置
      </button>
    </section>
  );
}

function ConfigField({
  config,
  fieldKey,
  label,
  setConfig
}: {
  config: AppConfig;
  fieldKey: string;
  label: string;
  setConfig: (value: AppConfig) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      {typeof config[fieldKey] === "boolean" ? (
        <input
          type="checkbox"
          checked={Boolean(config[fieldKey])}
          onChange={(event) => setConfig({ ...config, [fieldKey]: event.target.checked })}
        />
      ) : (
        <input
          type={fieldKey.includes("password") || fieldKey.includes("token") ? "password" : typeof config[fieldKey] === "number" ? "number" : "text"}
          value={String(config[fieldKey] ?? "")}
          onChange={(event) =>
            setConfig({
              ...config,
              [fieldKey]: typeof config[fieldKey] === "number" ? Number(event.target.value) : event.target.value
            })
          }
        />
      )}
    </label>
  );
}

function ZoneSourcesEditor({ config, setConfig }: { config: AppConfig; setConfig: (value: AppConfig) => void }) {
  const sources = config.zone_sources ?? [];

  function updateSource(index: number, patch: Partial<ZoneSource>) {
    setConfig({
      ...config,
      zone_sources: sources.map((source, itemIndex) => (itemIndex === index ? { ...source, ...patch } : source))
    });
  }

  function addSource() {
    setConfig({
      ...config,
      zone_sources: [...sources, { tld: "", zone_url: "", bearer_token: "", enabled: true }]
    });
  }

  function removeSource(index: number) {
    setConfig({
      ...config,
      zone_sources: sources.filter((_, itemIndex) => itemIndex !== index)
    });
  }

  return (
    <div className="zoneSources">
      <div className="zoneHeader">
        <span>启用</span>
        <span>后缀</span>
        <span>Zone 地址</span>
        <span>Bearer Token</span>
        <span>操作</span>
      </div>
      {sources.map((source, index) => (
        <div className="zoneRow" key={`${source.tld}-${index}`}>
          <input type="checkbox" checked={source.enabled} onChange={(event) => updateSource(index, { enabled: event.target.checked })} />
          <input value={source.tld} onChange={(event) => updateSource(index, { tld: event.target.value })} placeholder="com" />
          <input value={source.zone_url} onChange={(event) => updateSource(index, { zone_url: event.target.value })} placeholder="https://..." />
          <input
            type="password"
            value={source.bearer_token ?? ""}
            onChange={(event) => updateSource(index, { bearer_token: event.target.value })}
            placeholder="可选"
          />
          <button type="button" onClick={() => removeSource(index)}>删除</button>
        </div>
      ))}
      <button className="secondaryButton" type="button" onClick={addSource}>添加后缀来源</button>
    </div>
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
              <td>{errorLabel(job.error)}</td>
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
    const text = await response.text();
    let message = text;
    try {
      const data = JSON.parse(text) as { detail?: string };
      if (data.detail) {
        message = data.detail;
      }
    } catch {
      message = text;
    }
    throw new Error(message);
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

function errorLabel(error: string | null) {
  if (!error) {
    return "-";
  }
  return ERROR_LABELS[error] ?? error;
}

createRoot(document.getElementById("root")!).render(<App />);
