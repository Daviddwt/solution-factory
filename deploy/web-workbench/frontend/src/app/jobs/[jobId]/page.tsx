import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { notFound } from "next/navigation";
import { StageRail } from "@/components/StageRail";
import { fetchJob, pipelineStatusLabel } from "@/lib/api";
import { ArtifactWorkspace } from "./ArtifactWorkspace";

export default async function JobDetailPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const job = await fetchJob(jobId);
  if (!job) notFound();
  return (
    <main className="shell">
      <header className="topBar">
        <div className="brandBlock">
          <h1>{job.title}</h1>
        </div>
        <nav className="navActions">
          <Link className="navButton" href="/jobs">
            <ArrowLeft size={18} />
            任务池
          </Link>
        </nav>
      </header>
      <section className="detailGrid">
        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2>任务状态</h2>
              <p>{job.updated_at}</p>
            </div>
            <span className={`badge ${job.status}`}>{pipelineStatusLabel(job.status)}</span>
          </div>
          <StageRail status={job.status} artifacts={job.stage_artifacts} />
          <div style={{ height: 18 }} />
          <div className="factGrid">
            <div className="fact">
              <span>提交人</span>
              <strong>{job.requester_name}</strong>
            </div>
            <div className="fact">
              <span>页数</span>
              <strong>{job.pages ?? "待建议"}</strong>
            </div>
            <div className="fact">
              <span>风格</span>
              <strong>{job.style}</strong>
            </div>
            <div className="fact">
              <span>场景</span>
              <strong>{job.scenario || "未填写"}</strong>
            </div>
            <div className="fact">
              <span>受众</span>
              <strong>{job.audience || "未填写"}</strong>
            </div>
          </div>
          {job.error ? <p className="errorText">{job.error}</p> : null}
        </section>
        <aside className="panel">
          <div className="panelHeader">
            <div>
              <h2>输入资料</h2>
              <p>{job.uploaded_files.length} 个文件</p>
            </div>
          </div>
          <div className="jobList">
            {job.uploaded_files.length ? (
              job.uploaded_files.map((file) => (
                <div className="jobRow" key={file.stored_name}>
                  <div>
                    <strong>{file.filename}</strong>
                    <div className="jobMeta">
                      <span>{Math.ceil(file.size_bytes / 1024)} KB</span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="emptyState">无上传文件</div>
            )}
          </div>
        </aside>
      </section>
      <ArtifactWorkspace jobId={job.job_id} />
    </main>
  );
}
