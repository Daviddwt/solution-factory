export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  (typeof window === "undefined" ? process.env.API_BASE || "http://127.0.0.1:8000" : "");
export const MAX_UPLOAD_MB = 200;

function apiEndpoint(path: string): string {
  return `${API_BASE}${path}`;
}

function apiUrl(path: string): URL {
  const base = typeof window === "undefined" ? API_BASE || "http://127.0.0.1:8000" : window.location.origin;
  return new URL(apiEndpoint(path), base);
}

export type PipelineStatus =
  | "created"
  | "queued"
  | "running"
  | "requirement_intake"
  | "image_ppt_generation"
  | "editable_rebuild"
  | "done"
  | "failed"
  | "needs_human_review";

export const PIPELINE_STATUS_LABELS: Record<PipelineStatus, string> = {
  created: "已创建",
  queued: "排队中",
  running: "运行中",
  requirement_intake: "需求梳理中",
  image_ppt_generation: "图片生成未接入",
  editable_rebuild: "可编辑转化未接入",
  done: "已完成",
  failed: "失败",
  needs_human_review: "待人工审阅",
};

export function pipelineStatusLabel(status: PipelineStatus): string {
  return PIPELINE_STATUS_LABELS[status] ?? status;
}

export type UploadedFileInfo = {
  filename: string;
  stored_name: string;
  size_bytes: number;
};

export type StylePreset = {
  id: string;
  name: string;
  summary: string;
  prompt: string;
  example: string;
};

export type IntakePreset = {
  id: string;
  name: string;
  summary: string;
  prompt: string;
};

export type IntakePresets = {
  scenario: IntakePreset[];
  audience: IntakePreset[];
};

export type KnowledgeBaseItem = {
  name: string;
  size_bytes: number;
  kind: string;
  updated_at: number;
  editable: boolean;
};

export type KnowledgeBaseDigest = {
  status: "empty" | "ready";
  content: string;
  updated_at: number | null;
  stale: boolean;
  item_count: number;
  provider: string;
  processing?: boolean;
  error?: string | null;
};

export type KnowledgeBaseDigestStart = {
  accepted: boolean;
  digest: KnowledgeBaseDigest;
};

export type Job = {
  job_id: string;
  workspace_id: string;
  requester_name: string;
  job_type: string;
  status: PipelineStatus;
  title: string;
  pages?: number | null;
  scenario: string;
  scenario_prompt: string;
  audience: string;
  audience_prompt: string;
  style: string;
  style_prompt: string;
  custom_style_prompt: string;
  user_instruction: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  output_file?: string | null;
  notify_target?: string;
  notify_sent_at?: string | null;
  notify_error?: string | null;
  uploaded_files: UploadedFileInfo[];
  stage_artifacts: Record<string, string[]>;
};

export type JobSummary = Pick<
  Job,
  "job_id" | "requester_name" | "status" | "title" | "created_at" | "updated_at" | "output_file"
>;

export type DeckPage = {
  page_id: string;
  page_no: number;
  title: string;
  script_path: string;
  prompt_path: string;
  result_path: string;
  script_state: string;
  prompt_state: string;
  result_state: string;
  updated_at: string;
};

export type CodexStage1Result = {
  accepted: boolean;
  status: PipelineStatus;
  note: string;
};

export type ImagePptPackage = {
  package_state: "ready";
  slide_count: number;
  output_file: string;
  package_file: string;
  artifacts: string[];
  note: string;
};

export type ImagePptGenerationStart = {
  accepted: boolean;
  state: PipelineStatus;
  mode: string;
  note: string;
};

export async function apiErrorMessage(response: Response, fallback: string): Promise<string> {
  const raw = await response.text();
  let detail = raw;
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      detail = parsed.detail;
    }
  } catch {
    detail = raw;
  }

  if (detail.includes("Uploaded file is too large")) {
    return `文件过大：单个文件不能超过 ${MAX_UPLOAD_MB} MB。请压缩后再上传，或拆成更小的基线材料。`;
  }
  if (detail.includes("Unsupported file type")) {
    return "暂不支持这种文件类型。知识库支持 PPT、PDF、Word、Excel、图片、Markdown、TXT 和 CSV。";
  }
  if (detail.includes("No files uploaded")) {
    return "没有检测到文件，请重新选择或拖拽文件。";
  }
  return detail || fallback;
}

export async function fetchStyles(): Promise<StylePreset[]> {
  const response = await fetch(apiEndpoint("/api/styles"), { cache: "no-store" });
  if (!response.ok) return [];
  const data = (await response.json()) as { styles: StylePreset[] };
  return data.styles;
}

export async function fetchIntakePresets(): Promise<IntakePresets> {
  const response = await fetch(apiEndpoint("/api/intake-presets"), { cache: "no-store" });
  if (!response.ok) return { scenario: [], audience: [] };
  return (await response.json()) as IntakePresets;
}

export async function saveIntakePresetPrompt(
  kind: "scenario" | "audience",
  id: string,
  prompt: string,
): Promise<IntakePreset | null> {
  const response = await fetch(apiEndpoint(`/api/intake-presets/${kind}/${id}`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!response.ok) return null;
  const data = (await response.json()) as { preset: IntakePreset };
  return data.preset;
}

export async function fetchKnowledgeBase(): Promise<KnowledgeBaseItem[]> {
  const response = await fetch(apiEndpoint("/api/knowledge-base"), { cache: "no-store" });
  if (!response.ok) return [];
  const data = (await response.json()) as { items: KnowledgeBaseItem[] };
  return data.items;
}

export async function fetchKnowledgeBaseDigest(): Promise<KnowledgeBaseDigest | null> {
  const response = await fetch(apiEndpoint("/api/knowledge-base/digest"), { cache: "no-store" });
  if (!response.ok) return null;
  const data = (await response.json()) as { digest: KnowledgeBaseDigest };
  return data.digest;
}

export async function generateKnowledgeBaseDigest(): Promise<KnowledgeBaseDigestStart> {
  const response = await fetch(apiEndpoint("/api/knowledge-base/digest"), {
    method: "POST",
  });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "整理基线失败"));
  return (await response.json()) as KnowledgeBaseDigestStart;
}

export async function uploadKnowledgeBaseFiles(files: File[]): Promise<KnowledgeBaseItem[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await fetch(apiEndpoint("/api/knowledge-base/upload"), {
    method: "POST",
    body: formData,
  });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "上传失败"));
  const data = (await response.json()) as { items: KnowledgeBaseItem[] };
  return data.items;
}

export async function fetchKnowledgeBaseContent(name: string): Promise<string> {
  const response = await fetch(apiEndpoint(`/api/knowledge-base/${encodeURIComponent(name)}/content`), {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "打开失败"));
  return response.text();
}

export async function saveKnowledgeBaseContent(name: string, content: string): Promise<KnowledgeBaseItem[]> {
  const response = await fetch(apiEndpoint(`/api/knowledge-base/${encodeURIComponent(name)}/content`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "保存失败"));
  const data = (await response.json()) as { items: KnowledgeBaseItem[] };
  return data.items;
}

export async function deleteKnowledgeBaseItem(name: string): Promise<KnowledgeBaseItem[]> {
  const response = await fetch(apiEndpoint(`/api/knowledge-base/${encodeURIComponent(name)}`), {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "删除失败"));
  const data = (await response.json()) as { items: KnowledgeBaseItem[] };
  return data.items;
}

export async function fetchJobs(): Promise<JobSummary[]> {
  const response = await fetch(apiEndpoint("/api/jobs"), { cache: "no-store" });
  if (!response.ok) return [];
  const data = (await response.json()) as { jobs: JobSummary[] };
  return data.jobs;
}

export async function fetchJob(jobId: string): Promise<Job | null> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}`), { cache: "no-store" });
  if (!response.ok) return null;
  return (await response.json()) as Job;
}

export async function fetchLogs(jobId: string): Promise<string> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/logs`), { cache: "no-store" });
  if (!response.ok) return "";
  return response.text();
}

export async function fetchArtifact(jobId: string, path = "work/01_requirements/requirement-reminders.md"): Promise<string> {
  const url = apiUrl(`/api/jobs/${jobId}/artifact`);
  url.searchParams.set("path", path);
  const response = await fetch(url.toString(), { cache: "no-store" });
  if (!response.ok) return "";
  return response.text();
}

export async function fetchDeckPages(jobId: string): Promise<DeckPage[]> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/pages`), { cache: "no-store" });
  if (!response.ok) return [];
  const data = (await response.json()) as { pages: DeckPage[] };
  return data.pages;
}

export async function generateCodexStage1(jobId: string): Promise<CodexStage1Result> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/codex-stage1`), { method: "POST" });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "大模型生成逐页脚本失败，请稍后重试。"));
  return (await response.json()) as CodexStage1Result;
}

export async function startImagePptGeneration(jobId: string): Promise<ImagePptGenerationStart> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/image-ppt-generation/start`), { method: "POST" });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "图片版 PPT 生成启动失败，请稍后重试。"));
  return (await response.json()) as ImagePptGenerationStart;
}

export async function buildScriptPackage(jobId: string): Promise<ImagePptPackage> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/script-package`), { method: "POST" });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "脚本包生成失败，请先生成生产脚本。"));
  return (await response.json()) as ImagePptPackage;
}

export async function buildScriptMarkdown(jobId: string): Promise<ImagePptPackage> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/script-markdown`), { method: "POST" });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "Markdown 脚本文档生成失败，请先生成生产脚本。"));
  return (await response.json()) as ImagePptPackage;
}

export async function buildPromptMarkdown(jobId: string): Promise<ImagePptPackage> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/prompt-markdown`), { method: "POST" });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "图片生产提示词 Markdown 生成失败，请先生成生产脚本。"));
  return (await response.json()) as ImagePptPackage;
}

export async function fetchPageContent(jobId: string, pageId: string, kind = "script"): Promise<string> {
  const url = apiUrl(`/api/jobs/${jobId}/pages/${pageId}/content`);
  url.searchParams.set("kind", kind);
  const response = await fetch(url.toString(), { cache: "no-store" });
  if (!response.ok) return "";
  return response.text();
}

export async function savePageScript(jobId: string, pageId: string, content: string): Promise<DeckPage | null> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/pages/${pageId}/script`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) return null;
  const data = (await response.json()) as { page: DeckPage };
  return data.page;
}

export async function regeneratePagePrompt(jobId: string, pageId: string): Promise<{ page: DeckPage; prompt: string } | null> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/pages/${pageId}/regenerate-prompt`), { method: "POST" });
  if (!response.ok) return null;
  return (await response.json()) as { page: DeckPage; prompt: string };
}

export async function downloadJobFile(jobId: string, filename: string): Promise<Blob> {
  const response = await fetch(downloadUrl(jobId, filename), { cache: "no-store" });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "下载失败，请确认文件已经生成。"));
  return response.blob();
}

export async function runJob(jobId: string): Promise<void> {
  const response = await fetch(apiEndpoint(`/api/jobs/${jobId}/run`), { method: "POST" });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "运行失败，请稍后重试。"));
}

export function pageImageUrl(jobId: string, pageId: string, version = ""): string {
  const url = apiUrl(`/api/jobs/${jobId}/pages/${pageId}/image`);
  if (version) url.searchParams.set("v", version);
  return url.toString();
}

export function downloadUrl(jobId: string, filename = "result.pptx"): string {
  const url = apiUrl(`/api/jobs/${jobId}/download`);
  url.searchParams.set("filename", filename);
  return url.toString();
}
