import Link from "next/link";
import { ArrowLeft, ListPlus } from "lucide-react";
import { fetchJobs, pipelineStatusLabel } from "@/lib/api";

export default async function JobsPage() {
  const jobs = await fetchJobs();
  return (
    <main className="shell">
      <header className="topBar">
        <div className="brandBlock">
          <h1>任务池</h1>
          <span>按提交人隔离的本地任务</span>
        </div>
        <nav className="navActions">
          <Link className="navButton" href="/">
            <ArrowLeft size={18} />
            工作台
          </Link>
          <Link className="navButton" href="/create">
            <ListPlus size={18} />
            新任务
          </Link>
        </nav>
      </header>
      <section className="panel" style={{ maxWidth: 1180, margin: "0 auto" }}>
        <div className="jobList">
          {jobs.length ? (
            jobs.map((job) => (
              <Link className="jobRow" href={`/jobs/${job.job_id}`} key={job.job_id}>
                <div>
                  <strong>{job.title}</strong>
                  <div className="jobMeta">
                    <span>提交人：{job.requester_name}</span>
                    <span>创建：{job.created_at}</span>
                    <span>{job.updated_at}</span>
                  </div>
                </div>
                <span className={`badge ${job.status}`}>{pipelineStatusLabel(job.status)}</span>
              </Link>
            ))
          ) : (
            <div className="emptyState">任务池为空</div>
          )}
        </div>
      </section>
    </main>
  );
}
