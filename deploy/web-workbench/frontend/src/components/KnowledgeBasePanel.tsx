"use client";

import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";
import { BookOpen, FileText, Pencil, RefreshCw, Save, Sparkles, Trash2, UploadCloud, X } from "lucide-react";
import {
  deleteKnowledgeBaseItem,
  fetchKnowledgeBase,
  fetchKnowledgeBaseContent,
  fetchKnowledgeBaseDigest,
  generateKnowledgeBaseDigest,
  KnowledgeBaseDigest,
  KnowledgeBaseItem,
  MAX_UPLOAD_MB,
  saveKnowledgeBaseContent,
  uploadKnowledgeBaseFiles,
} from "@/lib/api";

type KnowledgeBasePanelProps = {
  initialItems: KnowledgeBaseItem[];
  initialDigest: KnowledgeBaseDigest | null;
};

function formatSize(bytes: number): string {
  return `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}

function oversizedFileMessage(files: File[]): string {
  const limit = MAX_UPLOAD_MB * 1024 * 1024;
  const oversized = files.filter((file) => file.size > limit);
  if (!oversized.length) return "";
  const names = oversized.slice(0, 2).map((file) => file.name).join("、");
  const suffix = oversized.length > 2 ? ` 等 ${oversized.length} 个文件` : "";
  return `${names}${suffix} 超过 ${MAX_UPLOAD_MB} MB，不能上传。请先压缩或拆成更小的基线材料。`;
}

function formatDigestTime(value: number | null): string {
  if (!value) return "尚未整理";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function KnowledgeBasePanel({ initialItems, initialDigest }: KnowledgeBasePanelProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [items, setItems] = useState(initialItems);
  const [digest, setDigest] = useState<KnowledgeBaseDigest | null>(initialDigest);
  const [activeName, setActiveName] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [digestBusy, setDigestBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [dragActive, setDragActive] = useState(false);

  useEffect(() => {
    if (!digest?.processing) return;
    let alive = true;
    setDigestBusy(true);
    const timer = window.setInterval(() => {
      void fetchKnowledgeBaseDigest().then((nextDigest) => {
        if (!alive || !nextDigest) return;
        setDigest(nextDigest);
        if (!nextDigest.processing) {
          setDigestBusy(false);
          setMessage(nextDigest.error ? `整理失败：${nextDigest.error}` : "大模型已整理公司知识库摘要");
        }
      }).catch(() => undefined);
    }, 4000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [digest?.processing]);

  async function refresh() {
    setBusy(true);
    setMessage("");
    try {
      const [nextItems, nextDigest] = await Promise.all([fetchKnowledgeBase(), fetchKnowledgeBaseDigest()]);
      setItems(nextItems);
      if (nextDigest) setDigest(nextDigest);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "刷新失败");
    } finally {
      setBusy(false);
    }
  }

  async function uploadFiles(files: File[]) {
    if (!files.length) return;
    const sizeError = oversizedFileMessage(files);
    if (sizeError) {
      setMessage(sizeError);
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      setItems(await uploadKnowledgeBaseFiles(files));
      setDigest((current) => (current ? { ...current, stale: true } : current));
      setMessage("已更新知识库清单。基线摘要可能已过期，请重新整理。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    await uploadFiles(files);
  }

  function hasDraggedFiles(event: DragEvent<HTMLElement>) {
    return Array.from(event.dataTransfer.types || []).includes("Files");
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragActive(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    const nextTarget = event.relatedTarget;
    if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
      setDragActive(false);
    }
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    setDragActive(false);
    await uploadFiles(Array.from(event.dataTransfer.files || []));
  }

  async function openEditor(item: KnowledgeBaseItem) {
    if (!item.editable) return;
    setBusy(true);
    setMessage("");
    try {
      setActiveName(item.name);
      setContent(await fetchKnowledgeBaseContent(item.name));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "打开失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveEditor() {
    if (!activeName) return;
    setBusy(true);
    setMessage("");
    try {
      setItems(await saveKnowledgeBaseContent(activeName, content));
      setDigest((current) => (current ? { ...current, stale: true } : current));
      setMessage("已保存知识库内容。基线摘要可能已过期，请重新整理。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function deleteItem(item: KnowledgeBaseItem) {
    const confirmed = window.confirm(`确定删除知识库基线“${item.name}”吗？删除后后续脚本不会再引用它。`);
    if (!confirmed) return;
    setBusy(true);
    setMessage("");
    try {
      setItems(await deleteKnowledgeBaseItem(item.name));
      if (activeName === item.name) {
        setActiveName("");
        setContent("");
      }
      setDigest((current) => (current ? { ...current, stale: true } : current));
      setMessage("已删除知识库基线。基线摘要可能已过期，请重新整理。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function digestKnowledgeBase() {
    setDigestBusy(true);
    setMessage("已提交给当前大模型后台整理。页面会自动刷新摘要。");
    try {
      const previousUpdatedAt = digest?.updated_at || 0;
      const start = await generateKnowledgeBaseDigest();
      setDigest(start.digest);
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await wait(3000);
        const nextDigest = await fetchKnowledgeBaseDigest();
        if (!nextDigest) continue;
        setDigest(nextDigest);
        if (nextDigest.error) {
          setMessage(`整理失败：${nextDigest.error}`);
          return;
        }
        if (!nextDigest.processing && nextDigest.updated_at && nextDigest.updated_at !== previousUpdatedAt) {
          setMessage("大模型已整理公司知识库摘要");
          return;
        }
      }
      setMessage("当前大模型仍在整理公司知识库，稍后刷新本页可查看结果。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "整理基线失败");
    } finally {
      setDigestBusy(false);
    }
  }

  return (
    <div
      className={dragActive ? "knowledgePanel dragActive" : "knowledgePanel"}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="knowledgeHeader">
        <BookOpen size={22} />
        <div>
          <h2>公司知识库</h2>
          <p>David 登记的公司通用口径，会自动参与需求梳理；本次客户资料请放左侧表单。</p>
        </div>
      </div>
      <div className="knowledgeActions">
        <button type="button" className="knowledgeActionButton primary" onClick={() => inputRef.current?.click()} disabled={busy}>
          <UploadCloud size={16} />
          上传基线
        </button>
        <button type="button" className="knowledgeActionButton" onClick={refresh} disabled={busy}>
          <RefreshCw size={16} />
          刷新
        </button>
        <input ref={inputRef} className="srOnly" aria-hidden="true" tabIndex={-1} type="file" multiple onChange={handleUpload} />
      </div>
      <div className="knowledgeDropHint">也可以把文件直接拖到这张卡片里上传。</div>
      <div className="knowledgeList">
        {items.length ? (
          items.map((item) => (
            <div className={activeName === item.name ? "knowledgeItem active" : "knowledgeItem"} key={item.name}>
              <div className="knowledgeItemMain">
                <FileText size={16} />
                <div>
                  <strong>{item.name}</strong>
                  <span>
                    {item.kind} · {formatSize(item.size_bytes)}
                  </span>
                </div>
              </div>
              <div className="knowledgeItemActions">
                {item.editable ? (
                  <button type="button" className="knowledgeMiniButton" onClick={() => openEditor(item)} disabled={busy}>
                    <Pencil size={14} />
                    编辑
                  </button>
                ) : (
                  <span className="knowledgeReadonly">仅展示</span>
                )}
                <button
                  type="button"
                  className="knowledgeMiniButton danger"
                  onClick={() => deleteItem(item)}
                  disabled={busy}
                >
                  <Trash2 size={14} />
                  删除
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="emptyState">暂无基线内容</div>
        )}
      </div>
      <div className="knowledgeDigest">
        <div className="knowledgeDigestHeader">
          <div>
            <strong>基线消化摘要</strong>
            <span>
              {digest?.processing
                ? "大模型正在整理"
                : digest?.status === "ready"
                  ? `${digest.provider || "大模型"} 整理于 ${formatDigestTime(digest.updated_at)}`
                  : "还没有让大模型整理过"}
            </span>
          </div>
          <button type="button" className="knowledgeActionButton primary" onClick={digestKnowledgeBase} disabled={busy || digestBusy}>
            <Sparkles size={16} />
            {digestBusy ? "整理中" : "交给大模型整理基线"}
          </button>
        </div>
        {digest?.stale ? (
          <div className="knowledgeDigestWarning">知识库文件有变化，下面摘要可能不是最新，请重新整理。</div>
        ) : null}
        <textarea
          readOnly
          value={digest?.content || "尚未整理公司知识库。请点击“交给大模型整理基线”，让当前模型读取基线并生成可审阅摘要。"}
          aria-label="基线消化摘要"
        />
      </div>
      {activeName ? (
        <div className="knowledgeEditor">
          <div className="knowledgeEditorHeader">
            <strong>{activeName}</strong>
            <button type="button" className="knowledgeIconButton" aria-label="关闭编辑" onClick={() => setActiveName("")}>
              <X size={16} />
            </button>
          </div>
          <textarea value={content} onChange={(event) => setContent(event.target.value)} />
          <button type="button" className="knowledgeSaveButton" onClick={saveEditor} disabled={busy}>
            <Save size={16} />
            保存内容
          </button>
        </div>
      ) : null}
      {message ? <div className="knowledgeMessage">{message}</div> : null}
    </div>
  );
}
