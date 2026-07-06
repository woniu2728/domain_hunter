import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, ChevronDown, Database, Folder, Play, RefreshCw, RotateCw, Search, Settings, Square } from "lucide-react";
import "./styles.css";

type View = "dashboard" | "candidates" | "config";

type Stats = {
  domains: number;
  available: number;
  spam: number;
  jobs: number;
  deleted_domains?: number;
  deleted_tlds?: number;
  crawler_runs?: number;
  crawler_failed_runs?: number;
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

type ConfigValue = string | number | boolean | CrawlerAccount[] | CrawlerProxy[] | TldSchedule[] | undefined;
type Config = Record<string, ConfigValue>;
type CrawlerAccount = {
  id: string;
  username: string;
  password: string;
  proxy_id: string;
  enabled: boolean;
  status?: string;
  last_error?: string;
  last_used_at?: string;
};
type CrawlerProxy = {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  status?: string;
  last_error?: string;
  last_used_at?: string;
};
type TldSchedule = {
  tld: string;
  enabled: boolean;
  crawl_hour: number;
  crawl_minute: number;
  timezone: string;
  max_pages: number;
  request_delay_seconds: number;
};
type AppConfig = Config & {
  expireddomains_accounts?: CrawlerAccount[];
  expireddomains_proxies?: CrawlerProxy[];
  expireddomains_tld_schedules?: TldSchedule[];
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
  manual: "手动运行",
  "schedule-retry": "定时重试"
};

const ERROR_LABELS: Record<string, string> = {};

const CRAWLER_STATUS_LABELS: Record<string, string> = {
  healthy: "正常",
  cooldown: "冷却中",
  login_failed: "登录失败",
  limited: "访问受限",
  captcha: "验证码",
  disabled: "已禁用",
  failed: "失败"
};

const TLD_OPTIONS = ["com", "net", "org", "io", "co", "ai", "app", "dev", "xyz", "info", "biz", "me", "us", "cn"];

const TIMEZONE_OPTIONS = ["Asia/Shanghai", "UTC", "America/New_York", "Europe/London"];

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
  const hasCrawlerSource = Boolean(
    config.expireddomains_accounts?.some((account) => account.enabled && account.username && account.password) &&
    config.expireddomains_tld_schedules?.some((schedule) => schedule.enabled && schedule.tld)
  );

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
            onRestartJob={runJob}
            onStopJob={stopJob}
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
            tldSchedules={config.expireddomains_tld_schedules ?? []}
          />
        )}
        {view === "config" && (
          <ConfigView
            config={config}
            hasDirectRunSource={hasCrawlerSource}
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

  async function stopJob() {
    await api<{ status: string }>("/api/jobs/stop", { method: "POST" });
    setMessage("任务已停止");
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
    const hasCrawlerConfig = Boolean(
      config.expireddomains_accounts?.some((account) => account.enabled && account.username && account.password) &&
      config.expireddomains_tld_schedules?.some((schedule) => schedule.enabled && schedule.tld)
    );
    if (!hasCrawlerConfig) {
      window.alert("请先配置可用账号并启用至少一个后缀爬取计划。");
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
  candidates,
  onRestartJob,
  onStopJob
}: {
  stats: Stats;
  jobs: Job[];
  candidates: Candidate[];
  onRestartJob: () => Promise<void>;
  onStopJob: () => Promise<void>;
}) {
  const hasRunningJob = jobs.some((job) => job.status === "running");

  return (
    <section className="stack">
      <div className="metrics">
        <Metric label="域名总数" value={stats.domains} />
        <Metric label="可注册" value={stats.available} />
        <Metric label="疑似垃圾历史" value={stats.spam} />
        <Metric label="任务数" value={stats.jobs} />
        <Metric label="今日源域名" value={stats.deleted_domains ?? 0} />
      </div>
      <div className="hint">
        流程会抓取 ExpiredDomains.net 今日源数据，依次执行规则过滤、品牌评分、可注册二次查询、Wayback 历史检查和邮件通知。
      </div>
      <h2>高分候选</h2>
      <CandidateTable candidates={candidates.slice(0, 10)} />
      <div className="sectionTitleRow">
        <h2>最近任务</h2>
        <div className="taskActions">
          <button
            className="taskButton"
            disabled={!hasRunningJob}
            onClick={() => onStopJob().catch((error) => window.alert(error.message))}
            type="button"
          >
            <Square size={16} />
            停止任务
          </button>
          <button
            className="taskButton"
            onClick={() => onRestartJob().catch((error) => window.alert(error.message))}
            type="button"
          >
            <RotateCw size={16} />
            重启任务
          </button>
        </div>
      </div>
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
  tldSchedules
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
  tldSchedules: TldSchedule[];
}) {
  const tldOptions = Array.from(
    new Set(tldSchedules.map((schedule) => schedule.tld.trim().toLowerCase().replace(/^\./, "")).filter(Boolean))
  );

  return (
    <section className="stack">
      <section className="candidatePreview">
        <div className="sectionHeader">
          <h2>临时过滤预览</h2>
          <p>只读取今日抓取的 ExpiredDomains.net 源数据重新过滤和评分，不重新抓取网页，不查询可注册状态，不发送通知。</p>
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
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    "大模型评分": true,
    "定时任务": true,
    "邮件通知": true
  });
  const groups = [
    {
      title: "运行路径",
      description: "只配置运行目录；数据库、数据和缓存路径会固定在该目录下生成。",
      runtimePaths: true,
      fields: []
    },
    {
      title: "数据源",
      description: "配置 ExpiredDomains.net 账号、可选代理和各后缀的每日爬取计划。",
      dataSource: true,
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
      title: "大模型评分",
      description: "配置后优先使用 OpenAI 兼容接口评分；不可用时自动回退到本地评分规则。",
      llmSettings: true,
      fields: [
        ["llm_base_url", "Base URL"],
        ["llm_api_key", "API Key"],
        ["llm_model_id", "Model ID"]
      ]
    },
    {
      title: "定时任务",
      description: "启用后，后端会按每个后缀计划中的时间自动抓取并运行完整流程。",
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
      <div className="configActionBar">
        <div>
          <strong>{hasRunningJob ? "任务正在运行" : "任务未运行"}</strong>
          {!hasDirectRunSource && <span>需要可用账号和至少一个启用后缀计划。</span>}
        </div>
        <button
          className="save"
          onClick={() => onStartJob().catch((error) => setMessage(error.message))}
        >
          <Play size={18} />
          {hasRunningJob ? "按当前配置重启任务" : "启动任务"}
        </button>
      </div>
      {groups.map((group) => {
        const collapsed = Boolean(collapsedGroups[group.title]);
        return (
          <section className={`configSection ${collapsed ? "isCollapsed" : ""}`} key={group.title}>
            <button
              aria-expanded={!collapsed}
              className="sectionHeader sectionToggle"
              onClick={() => setCollapsedGroups({ ...collapsedGroups, [group.title]: !collapsed })}
              type="button"
            >
              <span>
                <h2>{group.title}</h2>
                <p>{group.description}</p>
              </span>
              <ChevronDown size={18} />
            </button>
            {!collapsed && (
              <div className="configGrid">
                {"dataSource" in group && group.dataSource ? (
                  <DataSourceEditor config={config} onSaveConfig={onSaveConfig} setConfig={setConfig} setMessage={setMessage} />
                ) : "runtimePaths" in group && group.runtimePaths ? (
                  <RuntimePathsEditor config={config} setConfig={setConfig} />
                ) : "schedule" in group && group.schedule ? (
                  <ScheduleEditor config={config} setConfig={setConfig} />
                ) : "llmSettings" in group && group.llmSettings ? (
                  <LlmSettingsEditor config={config} onSaveConfig={onSaveConfig} setConfig={setConfig} setMessage={setMessage} />
                ) : "emailSettings" in group && group.emailSettings ? (
                  <EmailSettingsEditor config={config} onSaveConfig={onSaveConfig} setConfig={setConfig} setMessage={setMessage} />
                ) : (
                  group.fields.map(([key, label]) => (
                    <ConfigField config={config} fieldKey={key} key={key} label={label} setConfig={setConfig} />
                  ))
                )}
              </div>
            )}
          </section>
        );
      })}
    </section>
  );
}

function DataSourceEditor({
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
  const accounts = config.expireddomains_accounts ?? [];
  const proxies = config.expireddomains_proxies ?? [];
  const schedules = config.expireddomains_tld_schedules ?? [];
  const enabledAccounts = accounts.filter((account) => account.enabled && account.username && account.password).length;
  const enabledSchedules = schedules.filter((schedule) => schedule.enabled && schedule.tld).length;

  return (
    <div className="dataSourceEditor">
      <div className="sourceSummary">
        <SummaryItem label="可用账号" value={`${enabledAccounts}/${accounts.length}`} />
        <SummaryItem label="代理出口" value={String(proxies.filter((proxy) => proxy.enabled).length)} />
        <SummaryItem label="启用后缀" value={`${enabledSchedules}/${schedules.length}`} />
      </div>
      <DataSourcePanel title="账号池" description="至少保留一个可登录账号；账号异常时后端会换用其他启用账号。">
        <AccountsEditor config={config} onSaveConfig={onSaveConfig} setConfig={setConfig} setMessage={setMessage} />
      </DataSourcePanel>
      <DataSourcePanel title="代理池（可选）" description="代理用于固定账号出口，不配置则使用当前服务器直连。">
        <ProxiesEditor config={config} onSaveConfig={onSaveConfig} setConfig={setConfig} setMessage={setMessage} />
      </DataSourcePanel>
      <DataSourcePanel title="后缀爬取计划" description="每个后缀按自己的每日时间抓取 ExpiredDomains.net 当日可注册删除列表。">
        <TldSchedulesEditor config={config} onSaveConfig={onSaveConfig} setConfig={setConfig} setMessage={setMessage} />
      </DataSourcePanel>
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DataSourcePanel({ children, description, title }: { children: React.ReactNode; description: string; title: string }) {
  return (
    <section className="sourcePanel">
      <div className="sourcePanelHeader">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function LlmSettingsEditor({
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
    ["llm_base_url", "Base URL"],
    ["llm_api_key", "API Key"],
    ["llm_model_id", "Model ID"]
  ];

  async function testLlm() {
    setTesting(true);
    setTestMessage("正在测试大模型评分...");
    try {
      await onSaveConfig();
      const result = await api<{ domain: string; score: number; reasons: string[] }>("/api/config/test-llm", { method: "POST" });
      const message = `测试通过：${result.domain} 评分 ${result.score}`;
      setTestMessage(message);
      setMessage(message);
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
        <button type="button" className="secondaryButton" disabled={testing} onClick={testLlm}>
          {testing ? "测试中" : "测试连接"}
        </button>
        {testMessage && <span className="actionMessage">{testMessage}</span>}
      </div>
    </>
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
    <div className="runtimePaths">
      <label className="runtimeInput">
        <span>
          <Folder size={16} />
          运行目录
        </span>
        <input
          value={String(config.runtime_dir ?? "runtime")}
          onChange={(event) => setConfig({ ...config, runtime_dir: event.target.value })}
          placeholder="runtime"
        />
      </label>
    </div>
  );
}

function ScheduleEditor({ config, setConfig }: { config: AppConfig; setConfig: (value: AppConfig) => void }) {
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
        <span>失败重试次数</span>
        <input
          min="0"
          type="number"
          value={String(config.failure_retry_count ?? 2)}
          onChange={(event) => setConfig({ ...config, failure_retry_count: Number(event.target.value) })}
        />
      </label>
      <label>
        <span>失败重试间隔秒数</span>
        <input
          min="0"
          type="number"
          value={String(config.failure_retry_delay_seconds ?? 300)}
          onChange={(event) => setConfig({ ...config, failure_retry_delay_seconds: Number(event.target.value) })}
        />
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

function MobileField({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <label className="mobileField">
      <span className="mobileFieldLabel">{label}</span>
      {children}
    </label>
  );
}

function AccountsEditor({
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
  const accounts = config.expireddomains_accounts ?? [];
  const proxies = config.expireddomains_proxies ?? [];

  function updateAccount(index: number, patch: Partial<CrawlerAccount>) {
    setConfig({ ...config, expireddomains_accounts: accounts.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)) });
  }

  async function testAccount(account: CrawlerAccount) {
    await onSaveConfig();
    await api<{ status: string }>(`/api/crawler/accounts/${encodeURIComponent(account.id)}/test`, { method: "POST" });
    setMessage(`账号 ${account.username} 测试通过`);
  }

  return (
    <div className="sourceRows">
      <div className="accountHeader">
        <span>启用</span><span>账号</span><span>密码</span><span>绑定代理</span><span>状态</span><span>操作</span>
      </div>
      {accounts.length === 0 && <div className="emptyState">至少添加一个 ExpiredDomains.net 账号后才能启动任务。</div>}
      {accounts.map((account, index) => (
        <div className="accountRow" key={account.id || index}>
          <MobileField label="启用"><input type="checkbox" checked={account.enabled} onChange={(event) => updateAccount(index, { enabled: event.target.checked })} /></MobileField>
          <MobileField label="账号"><input value={account.username} onChange={(event) => updateAccount(index, { username: event.target.value })} placeholder="用户名" /></MobileField>
          <MobileField label="密码"><input type="password" value={account.password ?? ""} onChange={(event) => updateAccount(index, { password: event.target.value })} placeholder="密码" /></MobileField>
          <MobileField label="绑定代理">
            <select value={account.proxy_id ?? ""} onChange={(event) => updateAccount(index, { proxy_id: event.target.value })}>
              <option value="">默认/不使用</option>
              {proxies.map((proxy) => <option key={proxy.id} value={proxy.id}>{proxy.name || proxy.id}</option>)}
            </select>
          </MobileField>
          <MobileField label="状态"><span className={`pill ${account.status || "healthy"}`} title={account.last_error || ""}>{crawlerStatusLabel(account.status)}</span></MobileField>
          <div className="rowActions">
            <button type="button" onClick={() => testAccount(account).catch((error) => setMessage(error.message))}>测试</button>
            <button type="button" onClick={() => setConfig({ ...config, expireddomains_accounts: accounts.filter((_, itemIndex) => itemIndex !== index) })}>删除</button>
          </div>
        </div>
      ))}
      <button className="secondaryButton" type="button" onClick={() => setConfig({ ...config, expireddomains_accounts: [...accounts, newAccount(accounts.length + 1)] })}>添加账号</button>
    </div>
  );
}

function ProxiesEditor({
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
  const proxies = config.expireddomains_proxies ?? [];

  function updateProxy(index: number, patch: Partial<CrawlerProxy>) {
    setConfig({ ...config, expireddomains_proxies: proxies.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)) });
  }

  async function testProxy(proxy: CrawlerProxy) {
    await onSaveConfig();
    await api<{ status: string }>(`/api/crawler/proxies/${encodeURIComponent(proxy.id)}/test`, { method: "POST" });
    setMessage(`代理 ${proxy.name || proxy.id} 测试通过`);
  }

  return (
    <div className="sourceRows">
      <div className="proxyHeader">
        <span>启用</span><span>名称</span><span>代理 URL</span><span>状态</span><span>操作</span>
      </div>
      {proxies.length === 0 && <div className="emptyState">代理可选，不配置则使用当前服务器直连。</div>}
      {proxies.map((proxy, index) => (
        <div className="proxyRow" key={proxy.id || index}>
          <MobileField label="启用"><input type="checkbox" checked={proxy.enabled} onChange={(event) => updateProxy(index, { enabled: event.target.checked })} /></MobileField>
          <MobileField label="名称"><input value={proxy.name} onChange={(event) => updateProxy(index, { name: event.target.value })} placeholder="proxy-us-1" /></MobileField>
          <MobileField label="代理 URL"><input type="password" value={proxy.url ?? ""} onChange={(event) => updateProxy(index, { url: event.target.value })} placeholder="http://user:pass@host:port" /></MobileField>
          <MobileField label="状态"><span className={`pill ${proxy.status || "healthy"}`} title={proxy.last_error || ""}>{crawlerStatusLabel(proxy.status)}</span></MobileField>
          <div className="rowActions">
            <button type="button" onClick={() => testProxy(proxy).catch((error) => setMessage(error.message))}>测试</button>
            <button type="button" onClick={() => setConfig({ ...config, expireddomains_proxies: proxies.filter((_, itemIndex) => itemIndex !== index) })}>删除</button>
          </div>
        </div>
      ))}
      <button className="secondaryButton" type="button" onClick={() => setConfig({ ...config, expireddomains_proxies: [...proxies, newProxy(proxies.length + 1)] })}>添加代理</button>
    </div>
  );
}

function TldSchedulesEditor({
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
  const schedules = config.expireddomains_tld_schedules ?? [];

  function updateSchedule(index: number, patch: Partial<TldSchedule>) {
    setConfig({ ...config, expireddomains_tld_schedules: schedules.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)) });
  }

  async function testFetch(schedule: TldSchedule) {
    await onSaveConfig();
    const result = await api<{ pages_fetched: number; domains_seen: number; available_seen: number }>(`/api/crawler/tlds/${encodeURIComponent(schedule.tld)}/test-fetch`, { method: "POST" });
    setMessage(`${schedule.tld} 测试抓取完成：${result.pages_fetched} 页，发现 ${result.domains_seen} 个，可注册初筛 ${result.available_seen} 个`);
  }

  return (
    <div className="sourceRows">
      <div className="scheduleHeader">
        <span>启用</span><span>后缀</span><span>每日时间</span><span>时区</span><span>最大页数</span><span>间隔秒</span><span>操作</span>
      </div>
      {schedules.length === 0 && <div className="emptyState">至少添加一个后缀计划后才能启动任务。</div>}
      {schedules.map((schedule, index) => (
        <div className="scheduleRow" key={`${schedule.tld}-${index}`}>
          <MobileField label="启用"><input type="checkbox" checked={schedule.enabled} onChange={(event) => updateSchedule(index, { enabled: event.target.checked })} /></MobileField>
          <MobileField label="后缀">
            <select value={normalizeTld(schedule.tld)} onChange={(event) => updateSchedule(index, { tld: event.target.value })}>
              {schedule.tld && !TLD_OPTIONS.includes(normalizeTld(schedule.tld)) && <option value={normalizeTld(schedule.tld)}>{normalizeTld(schedule.tld)}</option>}
              {TLD_OPTIONS.map((tld) => <option key={tld} value={tld}>{tld}</option>)}
            </select>
          </MobileField>
          <MobileField label="每日时间"><input type="time" value={timeFromSchedule(schedule)} onChange={(event) => updateSchedule(index, scheduleTimePatch(event.target.value))} /></MobileField>
          <MobileField label="时区">
            <select value={schedule.timezone || "Asia/Shanghai"} onChange={(event) => updateSchedule(index, { timezone: event.target.value })}>
              {TIMEZONE_OPTIONS.map((timezone) => <option key={timezone} value={timezone}>{timezone}</option>)}
            </select>
          </MobileField>
          <MobileField label="最大页数"><input type="number" min="1" value={String(schedule.max_pages ?? 20)} onChange={(event) => updateSchedule(index, { max_pages: Number(event.target.value) })} /></MobileField>
          <MobileField label="间隔秒"><input type="number" min="0" value={String(schedule.request_delay_seconds ?? 12)} onChange={(event) => updateSchedule(index, { request_delay_seconds: Number(event.target.value) })} /></MobileField>
          <div className="rowActions">
            <button type="button" onClick={() => testFetch(schedule).catch((error) => setMessage(error.message))}>测试</button>
            <button type="button" onClick={() => setConfig({ ...config, expireddomains_tld_schedules: schedules.filter((_, itemIndex) => itemIndex !== index) })}>删除</button>
          </div>
        </div>
      ))}
      <button className="secondaryButton" type="button" onClick={() => setConfig({ ...config, expireddomains_tld_schedules: [...schedules, newSchedule()] })}>添加后缀计划</button>
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

function crawlerStatusLabel(status?: string) {
  return CRAWLER_STATUS_LABELS[status || "healthy"] ?? status ?? "正常";
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

function normalizeTld(tld: string) {
  return tld.trim().toLowerCase().replace(/^\./, "");
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

function newAccount(index: number): CrawlerAccount {
  return {
    id: `acc-${Date.now()}-${index}`,
    username: "",
    password: "",
    proxy_id: "",
    enabled: true,
    status: "healthy"
  };
}

function newProxy(index: number): CrawlerProxy {
  return {
    id: `proxy-${Date.now()}-${index}`,
    name: `proxy-${index}`,
    url: "",
    enabled: true,
    status: "healthy"
  };
}

function newSchedule(): TldSchedule {
  return {
    tld: "com",
    enabled: true,
    crawl_hour: 2,
    crawl_minute: 0,
    timezone: "Asia/Shanghai",
    max_pages: 20,
    request_delay_seconds: 12
  };
}

function timeFromSchedule(schedule: TldSchedule) {
  return `${String(clampTime(Number(schedule.crawl_hour ?? 2), 0, 23)).padStart(2, "0")}:${String(clampTime(Number(schedule.crawl_minute ?? 0), 0, 59)).padStart(2, "0")}`;
}

function scheduleTimePatch(value: string): Partial<TldSchedule> {
  const [hour, minute] = value.split(":");
  return {
    crawl_hour: clampTime(Number(hour), 0, 23),
    crawl_minute: clampTime(Number(minute), 0, 59)
  };
}

createRoot(document.getElementById("root")!).render(<App />);
