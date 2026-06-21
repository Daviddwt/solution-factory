import { CheckCircle2, CircleDashed, FileText, FolderInput, ScrollText, XCircle } from "lucide-react";
import type { PipelineStatus } from "@/lib/api";

type StageState = "done" | "active" | "blocked" | "pending";

type StageRuntime = {
  status: PipelineStatus;
  artifacts?: Record<string, string[]>;
};

const stages = [
  {
    key: "intake",
    title: "资料入库",
    pending: "等待创建",
    active: "保存中",
    done: "资料已保存",
    blocked: "需处理",
    icon: FolderInput,
  },
  {
    key: "script",
    title: "生成脚本",
    pending: "待生成",
    active: "生成中",
    done: "脚本可审阅",
    blocked: "生成失败",
    icon: FileText,
  },
  {
    key: "export",
    title: "审阅导出",
    pending: "等待脚本",
    active: "审阅中",
    done: "可导出脚本包",
    blocked: "等待脚本",
    icon: ScrollText,
  },
] as const;

function hasArtifact(artifacts: Record<string, string[]>, stage: string, path: string) {
  return Boolean(artifacts[stage]?.includes(path));
}

function stageState(runtime: StageRuntime, stage: (typeof stages)[number]["key"]): StageState {
  const artifacts = runtime.artifacts || {};
  const hasCodexScript = hasArtifact(artifacts, "requirement_intake", "work/01_requirements/codex-generation.md");
  const hasHermesScript = hasArtifact(artifacts, "requirement_intake", "work/01_requirements/hermes_stage1-generation.md");
  const hasModelScript = hasCodexScript || hasHermesScript;
  if (runtime.status === "failed") return stage === "intake" ? "done" : "blocked";
  if (stage === "intake") return runtime.status === "created" ? "done" : "done";
  if (stage === "script") {
    if (hasModelScript) return "done";
    return ["running", "requirement_intake"].includes(runtime.status) ? "active" : "pending";
  }
  if (hasModelScript) return runtime.status === "needs_human_review" || runtime.status === "done" ? "done" : "active";
  return "blocked";
}

export function StageRail({ status, artifacts }: StageRuntime) {
  const safeArtifacts = artifacts || {};
  return (
    <div className="stageRail" aria-label="script production stages">
      {stages.map((stage) => {
        const state = stageState({ status, artifacts: safeArtifacts }, stage.key);
        const Icon = stage.icon;
        const StateIcon = state === "done" ? CheckCircle2 : state === "blocked" ? XCircle : CircleDashed;
        return (
          <div className={`stageItem ${state}`} key={stage.key}>
            <div className="stageGlyph">
              <Icon size={18} />
            </div>
            <div className="stageText">
              <strong>{stage.title}</strong>
              <span>{stage[state]}</span>
            </div>
            <StateIcon className="stageStateIcon" size={18} />
          </div>
        );
      })}
    </div>
  );
}
