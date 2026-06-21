import Link from "next/link";
import { ArrowRight, BookOpen, FileText, ListPlus, ScrollText } from "lucide-react";
import { fetchJobs, pipelineStatusLabel } from "@/lib/api";

const stageCards = [
  {
    icon: BookOpen,
    title: "知识库基线",
    text: "先维护公司标准口径、能力说明和禁用表述。",
  },
  {
    icon: FileText,
    title: "需求到脚本",
    text: "读取客户材料，生成可审阅的逐页 PPT 脚本。",
  },
  {
    icon: ScrollText,
    title: "提示词包",
    text: "输出逐页图片生产提示词，交给后续制作流程。",
  },
];

export default async function HomePage() {
  const jobs = await fetchJobs();
  return (
    <main className="shell">
      <header className="topBar">
        <div className="brandBlock">
          <h1>解决方案部 PPT 脚本生产台</h1>
          <span>公司知识库 &rarr; 需求材料 &rarr; 逐页脚本和图片生产提示词</span>
        </div>
        <nav className="navActions">
          <Link className="navButton" href="/create">
            <ListPlus size={18} />
            新任务
          </Link>
          <Link className="navButton" href="/jobs">
            <ArrowRight size={18} />
            任务池
          </Link>
        </nav>
      </header>
      <section className="homeWorkspace">
        <section className="panel homeHeroPanel">
          <div className="homeHeroText">
            <span>PPT 生产工作台</span>
            <h2>把材料变成可审阅的 PPT 生产脚本</h2>
            <p>维护公司知识库，上传客户需求，生成逐页脚本和图片生产提示词。第一版不生成图片，不用 HTML/SVG/本地渲染补位。</p>
          </div>
          <div className="homeActions">
            <Link className="primaryButton" href="/create">
              <ListPlus size={18} />
              创建新任务
            </Link>
            <Link className="secondaryButton" href="/jobs">
              <ArrowRight size={18} />
              查看任务池
            </Link>
          </div>
          <div className="homeStageCards">
            {stageCards.map((stage, index) => {
              const Icon = stage.icon;
              return (
                <div className="homeStageCard" key={stage.title}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <Icon size={20} />
                  <strong>{stage.title}</strong>
                  <p>{stage.text}</p>
                </div>
              );
            })}
          </div>
        </section>
        <section className="panel recentPanel">
          <div className="panelHeader">
            <div>
              <h2>最近任务</h2>
              <p>{jobs.length ? `${jobs.length} 个任务` : "暂无任务"}</p>
            </div>
          </div>
          <div className="jobList">
            {jobs.length ? (
              jobs.slice(0, 8).map((job) => (
                <Link className="jobRow" href={`/jobs/${job.job_id}`} key={job.job_id}>
                  <div>
                    <strong>{job.title}</strong>
                    <div className="jobMeta">
                      <span>{job.requester_name}</span>
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
      </section>
    </main>
  );
}
