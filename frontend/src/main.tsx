import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Database, Play, RefreshCw, Search, Settings } from "lucide-react";
import "./styles.css";

type View = "dashboard" | "candidates" | "config";

type Stats = {
  domains: number;
  available: number;
  spam: number;
  jobs: number;
  deleted_domains?: number;
  deleted_tlds?: number;
};

type Candidate = {
  domain: string;
  status: string;
  deleted_date?: string;
  total_score: number | null;
  reasons: string | null;
  archive?: number | null;
  spam?: number | null;
  notes?: string | null;
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

type PreviewConfig = {
  tlds: string;
  search: string;
  source_limit: number;
  filter_min_length: number;
  filter_max_length: number;
  filter_letters_only: boolean;
  filter_require_vowel: boolean;
  filter_no_digits: boolean;
  filter_no_hyphen: boolean;
  filter_max_consecutive_consonants: number;
  top_candidates: number;
  min_score: number;
};

type PreviewResult = {
  total_source: number;
  total_filtered: number;
  total_scored: number;
  items: Candidate[];
};

const API = "";
const VIEW_TITLES: Record<View, string> = {
  dashboard: "仪表盘",
  candidates: "候选域名",
  config: "配置"
};

const STATUS_LABELS: Record<string, string> = {
  available: "可注册",
  registered: "已注册",
  deleted: "已删除",
  preview: "临时预览",
  running: "运行中",
  cancelled: "已取消",
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
  const [view, setView] = useState<View>(() => viewFromHash(window.location.hash));
  const [stats, setStats] = useState<Stats>({ domains: 0, available: 0, spam: 0, jobs: 0 });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [config, setConfig] = useState<AppConfig>({});
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");
  const [previewConfig, setPreviewConfig] = useState<PreviewConfig>(defaultPreviewConfig());
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);
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
    const onHashChange = () => setView(viewFromHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) {
      window.history.replaceState(null, "", "#dashboard");
    }
    return () => window.removeEventListener("hashchange", onHashChange);
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
            <button className={view === key ? "active" : ""} key={key} onClick={() => navigateTo(key)}>
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
          />
        )}
        {view === "candidates" && (
          <Candidates
            candidates={previewResult?.items ?? candidates}
            previewConfig={previewConfig}
            previewResult={previewResult}
            runPreview={runPreview}
            search={search}
            clearPreview={() => setPreviewResult(null)}
            setMessage={setMessage}
            setPreviewConfig={setPreviewConfig}
            setSearch={setSearch}
            setStatus={setStatus}
            status={status}
            zoneSources={config.zone_sources ?? []}
          />
        )}
        {view === "config" && (
          <ConfigView
            config={config}
            hasDirectRunSource={hasDirectRunSource}
            hasRunningJob={hasRunningJob}
            onSaveConfig={saveConfig}
            onStartJob={startJobFromConfig}
            setConfig={setConfig}
            setMessage={setMessage}
          />
        )}
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

  async function saveConfig() {
    const saved = await api<AppConfig>("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    setConfig(saved);
    return saved;
  }

  async function startJobFromConfig() {
    const hasZoneSource = Boolean(config.zone_sources?.some((source) => source.enabled && source.tld && source.zone_url));
    if (!hasZoneSource) {
      window.alert("请先在配置中添加并启用至少一个 Zone 来源。");
      return;
    }
    await saveConfig();
    await runJob();
  }

  async function runPreview() {
    const result = await api<PreviewResult>("/api/domains/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(previewConfig)
    });
    setPreviewResult(result);
    setMessage(`预览完成：原始 ${result.total_source} 个，过滤后 ${result.total_filtered} 个，展示 ${result.total_scored} 个。`);
  }
}

function navigateTo(view: View) {
  window.location.hash = view;
}

function viewFromHash(hash: string): View {
  const value = hash.replace(/^#/, "");
  return value === "candidates" || value === "config" ? value : "dashboard";
}

function Dashboard({
  stats,
  jobs,
  candidates
}: {
  stats: Stats;
  jobs: Job[];
  candidates: Candidate[];
}) {
  return (
    <section className="stack">
      <div className="metrics">
        <Metric label="域名总数" value={stats.domains} />
        <Metric label="可注册" value={stats.available} />
        <Metric label="疑似垃圾历史" value={stats.spam} />
        <Metric label="任务数" value={stats.jobs} />
        <Metric label="原始删除域名" value={stats.deleted_domains ?? 0} />
      </div>
      <div className="hint">
        流程会读取已删除域名来源，依次执行规则过滤、品牌评分、可注册查询、Wayback 历史检查和邮件通知。
      </div>
      <h2>高分候选</h2>
      <CandidateTable candidates={candidates.slice(0, 10)} />
      <h2>最近任务</h2>
      <JobTable jobs={jobs.slice(0, 5)} />
    </section>
  );
}

function Candidates({
  candidates,
  previewConfig,
  previewResult,
  runPreview,
  search,
  clearPreview,
  setMessage,
  setPreviewConfig,
  setSearch,
  status,
  setStatus,
  zoneSources
}: {
  candidates: Candidate[];
  previewConfig: PreviewConfig;
  previewResult: PreviewResult | null;
  runPreview: () => Promise<void>;
  search: string;
  clearPreview: () => void;
  setMessage: (value: string) => void;
  setPreviewConfig: (value: PreviewConfig) => void;
  setSearch: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
  zoneSources: ZoneSource[];
}) {
  const tldOptions = Array.from(
    new Set(zoneSources.map((source) => source.tld.trim().toLowerCase().replace(/^\./, "")).filter(Boolean))
  );

  return (
    <section className="stack">
      <section className="candidatePreview">
        <div className="sectionHeader">
          <h2>临时过滤预览</h2>
          <p>只读取已保存的 deleted domains 重新过滤和评分，不下载 Zone，不查询可注册状态，不发送通知。</p>
        </div>
        <div className="previewGrid">
          <label>
            <span>后缀</span>
            <select
              value={previewConfig.tlds}
              onChange={(event) => setPreviewConfig({ ...previewConfig, tlds: event.target.value })}
            >
              <option value="">全部后缀</option>
              {tldOptions.map((tld) => (
                <option key={tld} value={tld}>{tld}</option>
              ))}
            </select>
          </label>
          <PreviewField label="域名包含" fieldKey="search" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="原始读取上限" fieldKey="source_limit" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="最小长度" fieldKey="filter_min_length" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="最大长度" fieldKey="filter_max_length" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="最低评分" fieldKey="min_score" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="候选数量上限" fieldKey="top_candidates" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="最大连续辅音数" fieldKey="filter_max_consecutive_consonants" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="仅允许字母" fieldKey="filter_letters_only" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="要求至少一个元音" fieldKey="filter_require_vowel" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="拒绝数字" fieldKey="filter_no_digits" config={previewConfig} setConfig={setPreviewConfig} />
          <PreviewField label="拒绝连字符" fieldKey="filter_no_hyphen" config={previewConfig} setConfig={setPreviewConfig} />
        </div>
        <div className="toolbar">
          <button onClick={() => runPreview().catch((error) => setMessage(error.message))}>
            <Search size={18} />
            预览候选
          </button>
          {previewResult && <button className="secondaryAction" onClick={clearPreview}>清除预览</button>}
        </div>
        {previewResult && (
          <div className="hint">表格正在展示临时预览结果。原始 {previewResult.total_source} 个，过滤后 {previewResult.total_filtered} 个，当前展示 {previewResult.total_scored} 个。</div>
        )}
      </section>
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

function PreviewField({
  config,
  fieldKey,
  label,
  setConfig
}: {
  config: PreviewConfig;
  fieldKey: keyof PreviewConfig;
  label: string;
  setConfig: (value: PreviewConfig) => void;
}) {
  const value = config[fieldKey];
  return (
    <label>
      <span>{label}</span>
      {typeof value === "boolean" ? (
        <input type="checkbox" checked={value} onChange={(event) => setConfig({ ...config, [fieldKey]: event.target.checked })} />
      ) : (
        <input
          type={typeof value === "number" ? "number" : "text"}
          value={value}
          onChange={(event) =>
            setConfig({
              ...config,
              [fieldKey]: typeof value === "number" ? Number(event.target.value) : event.target.value
            })
          }
        />
      )}
    </label>
  );
}

function ConfigView({
  config,
  hasDirectRunSource,
  hasRunningJob,
  onSaveConfig,
  onStartJob,
  setConfig,
  setMessage
}: {
  config: AppConfig;
  hasDirectRunSource: boolean;
  hasRunningJob: boolean;
  onSaveConfig: () => Promise<AppConfig>;
  onStartJob: () => Promise<void>;
  setConfig: (value: AppConfig) => void;
  setMessage: (value: string) => void;
}) {
  const groups = [
    {
      title: "运行路径",
      description: "只配置运行目录；数据库、数据和缓存路径会固定在该目录下生成。",
      runtimePaths: true,
      fields: []
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
      title: "大模型评分",
      description: "配置后优先使用 OpenAI 兼容接口评分；不可用时自动回退到本地评分规则。",
      fields: [
        ["llm_base_url", "Base URL"],
        ["llm_api_key", "API Key"],
        ["llm_model_id", "Model ID"]
      ]
    },
    {
      title: "定时任务",
      description: "启用后，后端服务会每天按固定时间自动运行完整流程。",
      schedule: true,
      fields: []
    },
    {
      title: "邮件通知",
      description: "配置 SMTP 后，流程完成时会发送候选域名报告。",
      emailSettings: true,
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
            ) : "runtimePaths" in group && group.runtimePaths ? (
              <RuntimePathsEditor config={config} setConfig={setConfig} />
            ) : "schedule" in group && group.schedule ? (
              <ScheduleEditor config={config} setConfig={setConfig} />
            ) : "emailSettings" in group && group.emailSettings ? (
              <EmailSettingsEditor config={config} onSaveConfig={onSaveConfig} setConfig={setConfig} setMessage={setMessage} />
            ) : (
              group.fields.map(([key, label]) => (
                key === "availability_provider" ? (
                  <label key={key}>
                    <span>{label}</span>
                    <select
                      value={String(config.availability_provider ?? "mock")}
                      onChange={(event) => setConfig({ ...config, availability_provider: event.target.value })}
                    >
                      <option value="mock">mock</option>
                      <option value="rdap">rdap</option>
                    </select>
                  </label>
                ) : (
                  <ConfigField config={config} fieldKey={key} key={key} label={label} setConfig={setConfig} />
                )
              ))
            )}
          </div>
        </section>
      ))}
      <button
        className="save"
        onClick={() => onStartJob().catch((error) => setMessage(error.message))}
      >
        <Play size={18} />
        {hasRunningJob ? "按当前配置重启任务" : "启动任务"}
      </button>
      {!hasDirectRunSource && <div className="hint">启动任务需要先添加并启用至少一个 Zone 来源；点击启动会弹出提示。</div>}
    </section>
  );
}

function EmailSettingsEditor({
  config,
  onSaveConfig,
  setConfig,
  setMessage
}: {
  config: AppConfig;
  onSaveConfig: () => Promise<AppConfig>;
  setConfig: (value: AppConfig) => void;
  setMessage: (value: string) => void;
}) {
  const [testing, setTesting] = useState(false);
  const [testMessage, setTestMessage] = useState("");
  const fields = [
    ["smtp_host", "SMTP 主机"],
    ["smtp_port", "SMTP 端口"],
    ["smtp_username", "SMTP 用户名"],
    ["smtp_password", "SMTP 密码"],
    ["smtp_use_tls", "启用 SMTP TLS"],
    ["email_from", "发件人"],
    ["email_to", "收件人"],
    ["send_empty_report", "无结果时发送报告"]
  ];

  async function testEmail() {
    setTesting(true);
    setTestMessage("正在发送测试邮件...");
    try {
      await onSaveConfig();
      await api<{ status: string }>("/api/config/test-email", { method: "POST" });
      setTestMessage("测试邮件已发送");
      setMessage("测试邮件已发送");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTestMessage(message);
      setMessage(message);
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      {fields.map(([key, label]) => (
        <ConfigField config={config} fieldKey={key} key={key} label={label} setConfig={setConfig} />
      ))}
      <div className="configActions">
        <button type="button" className="secondaryButton" disabled={testing} onClick={testEmail}>
          {testing ? "发送中" : "测试发送"}
        </button>
        {testMessage && <span className="actionMessage">{testMessage}</span>}
      </div>
    </>
  );
}

function RuntimePathsEditor({ config, setConfig }: { config: AppConfig; setConfig: (value: AppConfig) => void }) {
  return (
    <>
      <label>
        <span>运行目录</span>
        <input
          value={String(config.runtime_dir ?? "runtime")}
          onChange={(event) => setConfig({ ...config, runtime_dir: event.target.value })}
          placeholder="runtime"
        />
      </label>
      <div className="derivedPaths">
        <div>
          <span>数据库路径</span>
          <strong>{String(config.database_url ?? "")}</strong>
        </div>
        <div>
          <span>数据目录</span>
          <strong>{String(config.data_dir ?? "")}</strong>
        </div>
        <div>
          <span>缓存目录</span>
          <strong>{String(config.cache_dir ?? "")}</strong>
        </div>
      </div>
    </>
  );
}

function ScheduleEditor({ config, setConfig }: { config: AppConfig; setConfig: (value: AppConfig) => void }) {
  const hour = Number(config.schedule_hour ?? 2);
  const minute = Number(config.schedule_minute ?? 0);
  const timeValue = `${String(clampTime(hour, 0, 23)).padStart(2, "0")}:${String(clampTime(minute, 0, 59)).padStart(2, "0")}`;

  function updateTime(value: string) {
    const [rawHour, rawMinute] = value.split(":");
    setConfig({
      ...config,
      schedule_hour: clampTime(Number(rawHour), 0, 23),
      schedule_minute: clampTime(Number(rawMinute), 0, 59)
    });
  }

  return (
    <>
      <label>
        <span>启用定时任务</span>
        <input
          type="checkbox"
          checked={Boolean(config.schedule_enabled)}
          onChange={(event) => setConfig({ ...config, schedule_enabled: event.target.checked })}
        />
      </label>
      <label>
        <span>每日执行时间</span>
        <input type="time" value={timeValue} onChange={(event) => updateTime(event.target.value)} />
      </label>
    </>
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

function clampTime(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

function defaultPreviewConfig(): PreviewConfig {
  return {
    tlds: "",
    search: "",
    source_limit: 5000,
    filter_min_length: 4,
    filter_max_length: 12,
    filter_letters_only: true,
    filter_require_vowel: true,
    filter_no_digits: true,
    filter_no_hyphen: true,
    filter_max_consecutive_consonants: 3,
    top_candidates: 100,
    min_score: 40
  };
}

createRoot(document.getElementById("root")!).render(<App />);
