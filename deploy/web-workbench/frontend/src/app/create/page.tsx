import Link from "next/link";
import { ArrowLeft, BookOpen, FileText, ScrollText } from "lucide-react";
import { JobCreateForm } from "@/components/JobCreateForm";
import { KnowledgeBasePanel } from "@/components/KnowledgeBasePanel";
import { fetchKnowledgeBase, fetchKnowledgeBaseDigest } from "@/lib/api";

type CreatePageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function firstParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] || "";
  return value || "";
}

export default async function CreatePage({ searchParams }: CreatePageProps) {
  const params = searchParams ? await searchParams : {};
  const notifyTarget = firstParam(params.notify);
  const requesterName = firstParam(params.requester);
  const [knowledgeItems, knowledgeDigest] = await Promise.all([fetchKnowledgeBase(), fetchKnowledgeBaseDigest()]);
  return (
    <main className="shell">
      <header className="topBar createTopBar">
        <div className="brandBlock">
          <h1>创建 PPT 任务</h1>
          <span>填清楚人、场景、受众和资料，生成可审阅的 PPT 生产脚本</span>
        </div>
        <Link className="navButton" href="/">
          <ArrowLeft size={18} />
          返回
        </Link>
      </header>
      <section className="arrowFlow" aria-label="PPT 脚本生产步骤">
        <div className="arrowStep">
          <BookOpen size={18} />
          <strong>1. 公司知识库</strong>
          <span>引用已登记基线口径</span>
        </div>
        <div className="arrowStep">
          <FileText size={18} />
          <strong>2. 需求材料</strong>
          <span>上传文件或粘贴信息</span>
        </div>
        <div className="arrowStep">
          <ScrollText size={18} />
          <strong>3. 生产脚本</strong>
          <span>逐页脚本和提示词</span>
        </div>
      </section>
      <section className="createWorkspace">
        <section className="panel composerPanel">
          <div className="composerIntro">
            <div>
              <span>新建脚本任务</span>
              <h2>从这里开始</h2>
            </div>
          </div>
          <JobCreateForm initialNotifyTarget={notifyTarget} initialRequesterName={requesterName} />
        </section>
        <aside className="createGuide">
          <KnowledgeBasePanel initialItems={knowledgeItems} initialDigest={knowledgeDigest} />
        </aside>
      </section>
    </main>
  );
}
