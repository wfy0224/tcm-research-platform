import { useEffect, useState } from "react";
import { apiErrorText, requestJson } from "./api";

type JobProgress = { stage: string; processed: number; total: number; percent: number };
type JobRow = {
  job_id: string; job_type: string; status: string; attempts: number; max_attempts: number;
  created_at: string; updated_at: string; last_error: string | null; progress: JobProgress | null;
};

const typeNames: Record<string, string> = {
  "knowledge.publish": "知识发布与索引构建",
  "source.parse": "文献解析",
  "source.segment": "原文分段",
  "research.run": "理论研究",
  "research.report_export": "报告导出",
};
const stateNames: Record<string, string> = {
  PENDING: "排队中", RUNNING: "执行中", COMPLETED: "完成",
  SUCCEEDED: "完成", FAILED: "失败", CANCELLED: "已取消",
};
const stageNames: Record<string, string> = {
  SNAPSHOT: "准备快照", FTS: "全文索引", VECTOR: "向量索引", VALIDATE: "校验",
};

const isLive = (row: JobRow) => row.status === "PENDING" || row.status === "RUNNING";

function stamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

export function JobsPanel() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    const load = async () => {
      try {
        const data = await requestJson<{ jobs: JobRow[] }>("/api/v1/knowledge/jobs?limit=20");
        if (!current) return;
        setJobs(data.jobs);
        setError(null);
      } catch (cause) {
        if (current) setError(apiErrorText(cause));
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 2000);
    return () => { current = false; window.clearInterval(timer); };
  }, []);

  const live = jobs.find(isLive) ?? null;
  const progress = live?.progress ?? null;
  const percent = progress?.percent ?? 0;

  return (
    <section className="kwJobs" aria-label="后台任务">
      <h3>后台任务</h3>
      <p role="status">{error ? error : live
        ? (typeNames[live.job_type] ?? live.job_type) + " 执行中"
        : jobs.length ? "当前没有正在执行的任务" : "正在读取任务…"}</p>
      {live && progress && (
        <div className="kwJobProgress">
          <div className="kwProgressTrack"><span className="kwProgressFill" style={{ width: percent + "%" }} /></div>
          <p>阶段：{stageNames[progress.stage] ?? progress.stage} · 已处理 {progress.processed}/{progress.total}（{percent}%）· 第 {live.attempts} 次执行</p>
        </div>
      )}
      {live && !progress && <p className="kwHint">阶段：执行中（该任务类型不提供细项进度）。</p>}
      <div className="kwJobList">
        {jobs.map(row => (
          <div className="kwJobRow" key={row.job_id}>
            <div>
              <strong>{typeNames[row.job_type] ?? row.job_type}</strong>
              <small>{row.job_id} · {stamp(row.created_at)} · 执行 {row.attempts}/{row.max_attempts} 次</small>
              {row.last_error && <p className="kwJobError">{row.last_error}</p>}
            </div>
            <span className={"kwJobState" + (isLive(row) ? " running" : row.status === "FAILED" ? " failed" : "")}>
              {stateNames[row.status] ?? row.status}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}