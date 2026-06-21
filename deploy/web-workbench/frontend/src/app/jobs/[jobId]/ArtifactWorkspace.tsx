"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, FileText, Loader2, Save, ScrollText } from "lucide-react";
import {
  buildScriptMarkdown,
  buildScriptPackage,
  buildPromptMarkdown,
  DeckPage,
  downloadJobFile,
  fetchArtifact,
  fetchDeckPages,
  fetchJob,
  fetchPageContent,
  generateCodexStage1,
  PipelineStatus,
  savePageScript,
} from "@/lib/api";

type ViewKey = "script" | "prompt";
type GlobalKey = "summary" | "facts" | "questions" | "sources" | "knowledge";

const VIEWS: Record<ViewKey, { label: string; description: string; icon: typeof FileText }> = {
  script: {
    label: "页面脚本",
    description: "逐页 PPT 生产脚本，可直接审阅和修改。",
    icon: FileText,
  },
  prompt: {
    label: "图片生产提示词",
    description: "给后续图片 PPT 制作流程使用的逐页提示词。",
    icon: ScrollText,
  },
};

const GLOBAL_ARTIFACTS: Record<GlobalKey, { label: string; description: string; path: string }> = {
  summary: {
    label: "需求梳理",
    description: "当前任务的整体需求摘要。",
    path: "work/01_requirements/01_requirements.md",
  },
  facts: {
    label: "事实摘录",
    description: "从表单和上传资料中抽取出的当前任务事实。",
    path: "work/01_requirements/facts.md",
  },
  questions: {
    label: "待确认事项",
    description: "材料不足、不能编造成确定事实的内容。",
    path: "work/01_requirements/open-questions.md",
  },
  sources: {
    label: "资料清单",
    description: "上传资料、抽取状态和可读摘要。",
    path: "work/01_requirements/source-inventory.md",
  },
  knowledge: {
    label: "知识库清单",
    description: "本次生成可引用的公司基线内容。",
    path: "work/01_requirements/knowledge-base-inventory.md",
  },
};

const PAGE_STATE_LABELS: Record<string, string> = {
  draft: "脚本待审",
  bootstrap_draft: "需重新生成",
  codex_draft: "Codex脚本待审",
  hermes_draft: "Hermes脚本待审",
  edited: "脚本已修改",
  ready: "提示词就绪",
  bootstrap_prompt: "待 Codex 深化",
  needs_regeneration: "提示词待重生成",
  prompt_ready: "提示词就绪",
  not_started: "未导出",
  stale: "需重新导出",
  generated: "已生成脚本",
};

function stateLabel(value: string): string {
  return PAGE_STATE_LABELS[value] || value;
}

function cacheKey(pageId: string, view: ViewKey): string {
  return `${pageId}:${view}`;
}

export function ArtifactWorkspace({ jobId }: { jobId: string }) {
  const scriptEditorRef = useRef<HTMLTextAreaElement | null>(null);
  const [pages, setPages] = useState<DeckPage[]>([]);
  const [activePageId, setActivePageId] = useState("");
  const [activeView, setActiveView] = useState<ViewKey>("script");
  const [activeGlobal, setActiveGlobal] = useState<GlobalKey | null>(null);
  const [contentByKey, setContentByKey] = useState<Record<string, string>>({});
  const [scriptDrafts, setScriptDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [downloadingMarkdown, setDownloadingMarkdown] = useState(false);
  const [downloadingPromptMarkdown, setDownloadingPromptMarkdown] = useState(false);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [jobStatus, setJobStatus] = useState<PipelineStatus | "">("");
  const [jobError, setJobError] = useState("");
  const [message, setMessage] = useState("");

  const reloadWorkspace = useCallback(async (showLoading = false) => {
    if (showLoading) setWorkspaceReady(false);
    const [nextPages, job] = await Promise.all([fetchDeckPages(jobId), fetchJob(jobId)]);
    setPages(nextPages);
    setJobStatus(job?.status || "");
    setJobError(job?.error || "");
    setGenerating(job?.status === "requirement_intake");
    setActivePageId((current) => {
      if (current && nextPages.some((page) => page.page_id === current)) return current;
      return nextPages[0]?.page_id || "";
    });
    setWorkspaceReady(true);
  }, [jobId]);

  useEffect(() => {
    let alive = true;
    void reloadWorkspace(true).catch(() => {
      if (alive) setWorkspaceReady(true);
    });
    return () => {
      alive = false;
    };
  }, [reloadWorkspace]);

  const activePage = useMemo(
    () => pages.find((page) => page.page_id === activePageId) || pages[0],
    [activePageId, pages],
  );
  const hasScripts = pages.length > 0;
  const scriptGenerationRunning = generating || jobStatus === "requirement_intake";
  const scriptGenerationFailed = jobStatus === "failed" && !hasScripts;

  useEffect(() => {
    if (!scriptGenerationRunning) return;
    let alive = true;
    const tick = async () => {
      const [nextPages, job] = await Promise.all([fetchDeckPages(jobId), fetchJob(jobId)]);
      if (!alive) return;
      setPages(nextPages);
      setJobStatus(job?.status || "");
      setJobError(job?.error || "");
      setGenerating(job?.status === "requirement_intake");
      if (nextPages.length) {
        setActivePageId((current) => current || nextPages[0].page_id);
        setContentByKey({});
        setScriptDrafts({});
        setMessage("大模型已生成逐页 PPT 生产脚本，请审阅后下载页面脚本、图片生产提示词或完整脚本包。");
      } else if (job?.status === "failed") {
        setMessage(job.error || "大模型生成失败，请查看日志后重试。");
        setActiveGlobal((current) => current || "summary");
      }
    };
    const timer = window.setInterval(() => {
      void tick().catch(() => undefined);
    }, 4000);
    void tick().catch(() => undefined);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [jobId, scriptGenerationRunning]);

  useEffect(() => {
    if (!activePage && !activeGlobal) return;
    let alive = true;
    const key = activeGlobal ? `global:${activeGlobal}` : cacheKey(activePage!.page_id, activeView);
    async function loadContent() {
      if (contentByKey[key] !== undefined) return;
      setLoading(true);
      const text = activeGlobal
        ? await fetchArtifact(jobId, GLOBAL_ARTIFACTS[activeGlobal].path)
        : await fetchPageContent(jobId, activePage!.page_id, activeView);
      if (!alive) return;
      setContentByKey((current) => ({ ...current, [key]: text }));
      if (!activeGlobal && activeView === "script" && activePage) {
        setScriptDrafts((current) => ({ ...current, [activePage.page_id]: current[activePage.page_id] ?? text }));
      }
      setLoading(false);
    }
    void loadContent();
    return () => {
      alive = false;
    };
  }, [activeGlobal, activePage, activeView, contentByKey, jobId]);

  const activeKey = activeGlobal ? `global:${activeGlobal}` : activePage ? cacheKey(activePage.page_id, activeView) : "";
  const activeContent = activeKey ? contentByKey[activeKey] || "" : "";
  const scriptContentKey = activePage ? cacheKey(activePage.page_id, "script") : "";
  const savedScript = scriptContentKey ? contentByKey[scriptContentKey] || "" : "";
  const scriptDraft = activePage ? scriptDrafts[activePage.page_id] ?? savedScript : "";
  const scriptDirty = !!activePage && scriptDraft !== savedScript;
  const lineCount = useMemo(() => {
    const text = activeGlobal ? activeContent : activeView === "script" ? scriptDraft : activeContent;
    return text ? text.split("\n").length : 0;
  }, [activeContent, activeGlobal, activeView, scriptDraft]);

  useEffect(() => {
    const editor = scriptEditorRef.current;
    if (!editor || activeView !== "script" || loading) return;
    editor.style.height = "auto";
    editor.style.height = `${editor.scrollHeight}px`;
  }, [activePageId, activeView, loading, scriptDraft]);

  async function saveActiveScript(nextMessage = true): Promise<DeckPage | null> {
    if (!activePage || !scriptDirty) return activePage ?? null;
    setSaving(true);
    setMessage("");
    const nextPage = await savePageScript(jobId, activePage.page_id, scriptDraft);
    if (nextPage) {
      setPages((current) => current.map((page) => (page.page_id === nextPage.page_id ? nextPage : page)));
      setContentByKey((current) => ({ ...current, [cacheKey(nextPage.page_id, "script")]: scriptDraft }));
      if (nextMessage) setMessage(`P${nextPage.page_no.toString().padStart(2, "0")} 已保存。`);
    } else {
      setMessage("保存失败，请检查后端服务。");
    }
    setSaving(false);
    return nextPage;
  }

  function guardUnsaved(): boolean {
    if (!scriptDirty) return true;
    return window.confirm("当前页脚本还没保存，切换后这次修改不会写入文件。继续吗？");
  }

  function handleSelectPage(pageId: string) {
    if (pageId !== activePage?.page_id && !guardUnsaved()) return;
    setActivePageId(pageId);
    setActiveGlobal(null);
    setMessage("");
  }

  function handleSelectGlobal(key: GlobalKey) {
    if (!guardUnsaved()) return;
    setActiveGlobal(key);
    setMessage("");
  }

  async function handleGenerateScripts() {
    setGenerating(true);
    setJobStatus("requirement_intake");
    setMessage("已交给当前大模型后台生成。页面会自动刷新，你可以稍后回来查看。");
    try {
      const result = await generateCodexStage1(jobId);
      setActiveView("script");
      setActiveGlobal(null);
      setJobStatus(result.status);
      setMessage(result.note);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "大模型生成生产脚本失败，请稍后重试。");
      setGenerating(false);
    } finally {
      await reloadWorkspace(false).catch(() => undefined);
    }
  }

  async function handleDownloadMarkdown() {
    if (scriptDirty) {
      setMessage("请先保存当前页脚本，再下载页面脚本 Markdown。");
      return;
    }
    setDownloadingMarkdown(true);
    setMessage("正在生成页面脚本 Markdown...");
    try {
      const result = await buildScriptMarkdown(jobId);
      const blob = await downloadJobFile(jobId, result.output_file);
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = result.output_file;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
      setMessage("页面脚本 Markdown 已生成并开始下载。");
      await reloadWorkspace(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "页面脚本 Markdown 下载失败。");
    } finally {
      setDownloadingMarkdown(false);
    }
  }

  async function handleDownloadPromptMarkdown() {
    if (scriptDirty) {
      setMessage("请先保存当前页脚本，再下载图片生产提示词 Markdown。");
      return;
    }
    setDownloadingPromptMarkdown(true);
    setMessage("正在生成图片生产提示词 Markdown...");
    try {
      const result = await buildPromptMarkdown(jobId);
      const blob = await downloadJobFile(jobId, result.output_file);
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = result.output_file;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
      setMessage("图片生产提示词 Markdown 已生成并开始下载。");
      await reloadWorkspace(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "图片生产提示词 Markdown 下载失败。");
    } finally {
      setDownloadingPromptMarkdown(false);
    }
  }

  async function handleExportScriptPackage() {
    if (scriptDirty) {
      setMessage("请先保存当前页脚本，再导出脚本包。");
      return;
    }
    setExporting(true);
    setMessage("正在生成脚本包...");
    try {
      const result = await buildScriptPackage(jobId);
      const blob = await downloadJobFile(jobId, result.output_file);
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = result.output_file;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
      setMessage("脚本包已生成并开始下载。");
      await reloadWorkspace(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "脚本包导出失败。");
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="artifactWorkspace pageWorkspace">
      <div className="artifactRail pageRail">
        <div>
          <h2>脚本工作台</h2>
          <p>只生成和审阅 PPT 生产脚本；不生成图片、不打包图片 PPT。</p>
        </div>
        <div className={`nextStepPanel ${hasScripts ? "done" : scriptGenerationRunning || scriptGenerationFailed ? "blocked" : "ready"}`}>
          <div>
            <span>下一步</span>
            <strong>
              {hasScripts
                ? "审阅并下载脚本"
                : scriptGenerationRunning
                  ? "大模型正在生成脚本"
                  : scriptGenerationFailed
                    ? "生成失败，需重试或调整"
                    : "生成 PPT 生产脚本"}
            </strong>
            <p>
              {hasScripts
                ? "页面脚本和逐页图片生产提示词已就绪。审阅修改后可分别下载，或导出完整 ZIP 脚本包。"
                : scriptGenerationRunning
                  ? "后台正在生成逐页脚本。页面会自动刷新；如果材料较多，可以稍后回到任务页查看。"
                  : scriptGenerationFailed
                    ? "当前任务没有生成出可审阅页面脚本。请查看失败原因；可以重试，但本次 Hermes 通道对长脚本任务不稳定。"
                    : "读取公司知识库、上传材料和页面要求，生成逐页 PPT 脚本与图片生产提示词。"}
            </p>
          </div>
          {scriptDirty ? (
            <button className="saveStepButton" disabled={saving || generating} onClick={() => saveActiveScript()} type="button">
              {saving ? <Loader2 className="spinIcon" size={14} /> : <Save size={14} />}
              保存当前页修改
            </button>
          ) : null}
          {hasScripts ? (
            <div className="nextActionGroup">
              <button className="nextActionButton" disabled={downloadingMarkdown || saving || scriptDirty} onClick={handleDownloadMarkdown} type="button">
                {downloadingMarkdown ? <Loader2 className="spinIcon" size={14} /> : <Download size={14} />}
                下载页面脚本 Markdown
              </button>
              <button className="secondaryStepButton" disabled={downloadingPromptMarkdown || saving || scriptDirty} onClick={handleDownloadPromptMarkdown} type="button">
                {downloadingPromptMarkdown ? <Loader2 className="spinIcon" size={14} /> : <Download size={14} />}
                下载图片生产提示词 Markdown
              </button>
              <button className="secondaryStepButton" disabled={exporting || saving || scriptDirty} onClick={handleExportScriptPackage} type="button">
                {exporting ? <Loader2 className="spinIcon" size={14} /> : <Download size={14} />}
                下载完整脚本包 ZIP
              </button>
            </div>
          ) : (
            <button className="nextActionButton" disabled={scriptGenerationRunning || !workspaceReady} onClick={handleGenerateScripts} type="button">
              {scriptGenerationRunning ? <Loader2 className="spinIcon" size={14} /> : <FileText size={14} />}
              {scriptGenerationRunning ? "生成中" : "交给大模型生成脚本"}
            </button>
          )}
          {jobStatus === "failed" || jobError ? <div className="stepError">{jobError || "生成失败，请查看日志。"}</div> : null}
        </div>
        <div className="globalArtifactList" aria-label="需求梳理产物">
          {(Object.keys(GLOBAL_ARTIFACTS) as GlobalKey[]).map((key) => (
            <button
              className={`globalArtifactButton ${activeGlobal === key ? "active" : ""}`}
              key={key}
              onClick={() => handleSelectGlobal(key)}
              type="button"
            >
              <strong>{GLOBAL_ARTIFACTS[key].label}</strong>
              <span>{GLOBAL_ARTIFACTS[key].description}</span>
            </button>
          ))}
        </div>
        <nav className="pageList" aria-label="PPT 页面列表">
          {!workspaceReady ? <div className="emptyState">正在加载页面脚本...</div> : null}
          {workspaceReady && !pages.length ? <div className="emptyState">暂无页面脚本，请先生成。</div> : null}
          {workspaceReady && pages.map((page) => (
            <button
              aria-current={!activeGlobal && activePage?.page_id === page.page_id ? "page" : undefined}
              aria-label={`第 ${page.page_no} 页，${page.title}，${stateLabel(page.script_state)}，${stateLabel(page.prompt_state)}`}
              className={`pageListItem ${!activeGlobal && activePage?.page_id === page.page_id ? "active" : ""}`}
              key={page.page_id}
              onClick={() => handleSelectPage(page.page_id)}
              type="button"
            >
              <span>P{page.page_no.toString().padStart(2, "0")}</span>
              <strong>{page.title}</strong>
              <small>{stateLabel(page.script_state)} · {stateLabel(page.prompt_state)}</small>
            </button>
          ))}
        </nav>
      </div>
      <article className="artifactReader pageEditor">
        {scriptGenerationFailed && !activeGlobal ? (
          <div className="emptyState">
            <strong>生成失败，未产生页面脚本</strong>
            <p>{jobError || "大模型没有返回可解析的逐页脚本。"}</p>
            <p>已保留需求梳理、事实摘录、资料清单和日志，可切换左侧产物查看。</p>
          </div>
        ) : activeGlobal ? (
          <>
            <header>
              <div>
                <span>全局产物</span>
                <h2>{GLOBAL_ARTIFACTS[activeGlobal].label}</h2>
                <p>{GLOBAL_ARTIFACTS[activeGlobal].description}</p>
              </div>
              <small>{loading ? "加载中" : `${lineCount} 行`}</small>
            </header>
            {loading ? <div className="pageLoading"><Loader2 className="spinIcon" size={24} /></div> : <pre>{activeContent}</pre>}
          </>
        ) : activePage ? (
          <>
            <header>
              <div>
                <span>当前页 P{activePage.page_no.toString().padStart(2, "0")}</span>
                <h2>{activePage.title}</h2>
                <p>{VIEWS[activeView].description}</p>
              </div>
              <small>{loading ? "加载中" : `${lineCount} 行`}</small>
            </header>
            <div className="pageToolbar">
              <div className="viewTabs" role="tablist" aria-label="页面工作区">
                {(Object.keys(VIEWS) as ViewKey[]).map((view) => {
                  const Icon = VIEWS[view].icon;
                  return (
                    <button
                      aria-selected={activeView === view}
                      className={`viewTab ${activeView === view ? "active" : ""}`}
                      key={view}
                      onClick={() => {
                        setActiveView(view);
                        setMessage("");
                      }}
                      role="tab"
                      type="button"
                    >
                      <Icon size={16} />
                      {VIEWS[view].label}
                    </button>
                  );
                })}
              </div>
              <div className="pageActions">
                {activeView === "script" ? (
                  <button className="secondaryButton compactButton" disabled={!scriptDirty || saving || generating} onClick={() => saveActiveScript()} type="button">
                    {saving ? <Loader2 className="spinIcon" size={16} /> : <Save size={16} />}
                    保存本页
                  </button>
                ) : null}
              </div>
            </div>
            {scriptDirty ? <div className="unsavedNotice">当前页脚本尚未保存。保存后再导出脚本包。</div> : null}
            {message ? <div className="pageMessage">{message}</div> : null}
            {loading ? (
              <div className="pageLoading"><Loader2 className="spinIcon" size={24} /></div>
            ) : activeView === "script" ? (
              <textarea
                ref={scriptEditorRef}
                className="scriptEditor"
                onChange={(event) => setScriptDrafts((current) => ({ ...current, [activePage.page_id]: event.target.value }))}
                value={scriptDraft}
              />
            ) : (
              <pre>{activeContent}</pre>
            )}
          </>
        ) : (
          <div className="emptyState">{workspaceReady ? "暂无页面脚本，请先生成。" : "正在加载页面脚本..."}</div>
        )}
      </article>
    </section>
  );
}
