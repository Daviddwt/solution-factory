"use client";

import { useRouter } from "next/navigation";
import { DragEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Brush, FileStack, Play, Presentation, Save, UploadCloud, Users, X } from "lucide-react";
import {
  API_BASE,
  MAX_UPLOAD_MB,
  apiErrorMessage,
  fetchIntakePresets,
  fetchStyles,
  saveIntakePresetPrompt,
  type IntakePreset,
  type IntakePresets,
  type StylePreset,
} from "@/lib/api";

const EMPTY_INTAKE_PRESETS: IntakePresets = { scenario: [], audience: [] };
type FieldErrors = Partial<Record<"requester_name" | "pages" | "title", string>>;

type JobCreateFormProps = {
  initialNotifyTarget?: string;
  initialRequesterName?: string;
};

export function JobCreateForm({ initialNotifyTarget = "", initialRequesterName = "" }: JobCreateFormProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [styles, setStyles] = useState<StylePreset[]>([]);
  const [selectedStyle, setSelectedStyle] = useState("解决方案风");
  const [intakePresets, setIntakePresets] = useState<IntakePresets>(EMPTY_INTAKE_PRESETS);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [selectedAudienceId, setSelectedAudienceId] = useState("");
  const [scenarioPromptDrafts, setScenarioPromptDrafts] = useState<Record<string, string>>({});
  const [audiencePromptDrafts, setAudiencePromptDrafts] = useState<Record<string, string>>({});
  const [presetMessage, setPresetMessage] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    void fetchStyles().then((styleData) => {
      setStyles(styleData);
      if (styleData[0]) setSelectedStyle(styleData[0].name);
    });
    void fetchIntakePresets().then((presetData) => {
      setIntakePresets(presetData);
      setSelectedScenarioId((current) => current || presetData.scenario[0]?.id || "");
      setSelectedAudienceId((current) => current || presetData.audience[0]?.id || "");
      setScenarioPromptDrafts(Object.fromEntries(presetData.scenario.map((item) => [item.id, item.prompt])));
      setAudiencePromptDrafts(Object.fromEntries(presetData.audience.map((item) => [item.id, item.prompt])));
    });
  }, []);

  const currentStyle = useMemo(() => {
    return styles.find((item) => item.name === selectedStyle) ?? styles[0];
  }, [selectedStyle, styles]);

  const currentScenario = useMemo(() => {
    return intakePresets.scenario.find((item) => item.id === selectedScenarioId) ?? intakePresets.scenario[0];
  }, [intakePresets.scenario, selectedScenarioId]);

  const currentAudience = useMemo(() => {
    return intakePresets.audience.find((item) => item.id === selectedAudienceId) ?? intakePresets.audience[0];
  }, [intakePresets.audience, selectedAudienceId]);

  const currentScenarioPrompt = currentScenario
    ? scenarioPromptDrafts[currentScenario.id] ?? currentScenario.prompt
    : "";
  const currentAudiencePrompt = currentAudience
    ? audiencePromptDrafts[currentAudience.id] ?? currentAudience.prompt
    : "";

  function addFiles(nextFiles: FileList | File[]) {
    const incoming = Array.from(nextFiles);
    const maxBytes = MAX_UPLOAD_MB * 1024 * 1024;
    const oversized = incoming.filter((file) => file.size > maxBytes);
    if (oversized.length) {
      setError(`文件过大：单个文件不能超过 ${MAX_UPLOAD_MB} MB。请压缩后再上传，或拆成更小的基线材料。`);
      return;
    }
    setError("");
    setFiles((current) => {
      const known = new Set(current.map((file) => `${file.name}-${file.size}`));
      const merged = [...current];
      for (const file of incoming) {
        const key = `${file.name}-${file.size}`;
        if (!known.has(key)) merged.push(file);
      }
      return merged;
    });
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    addFiles(event.dataTransfer.files);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = event.currentTarget;
    const formData = new FormData(form);
    const requesterName = String(formData.get("requester_name") || "").trim();
    const title = String(formData.get("title") || "").trim();
    const pages = String(formData.get("pages") || "").trim();
    const nextFieldErrors: FieldErrors = {};
    if (!requesterName) nextFieldErrors.requester_name = "请填写提交人，用于自动区分任务归属。";
    if (!title) nextFieldErrors.title = "请填写 PPT 标题，后续脚本会围绕标题生成。";
    if (pages && (!Number.isInteger(Number(pages)) || Number(pages) < 1 || Number(pages) > 80)) {
      nextFieldErrors.pages = "页数请填写 1 到 80 的整数；不确定可以留空。";
    }
    setFieldErrors(nextFieldErrors);
    const firstErrorName = Object.keys(nextFieldErrors)[0];
    if (firstErrorName) {
      const firstField = form.elements.namedItem(firstErrorName);
      if (firstField instanceof HTMLElement) firstField.focus();
      return;
    }
    setBusy(true);
    formData.set("auto_run", "false");
    formData.set("style_prompt", currentStyle?.prompt ?? "");
    formData.set("scenario", currentScenario?.name ?? "");
    formData.set("scenario_prompt", currentScenarioPrompt);
    formData.set("audience", currentAudience?.name ?? "");
    formData.set("audience_prompt", currentAudiencePrompt);
    formData.set("notify_target", initialNotifyTarget);
    for (const file of files) {
      formData.append("files", file);
    }
    const response = await fetch(`${API_BASE}/api/jobs`, {
      method: "POST",
      body: formData,
    });
    setBusy(false);
    if (!response.ok) {
      setError(await apiErrorMessage(response, "创建任务失败，请检查必填项后重试。"));
      return;
    }
    const job = (await response.json()) as { job_id: string };
    router.push(`/jobs/${job.job_id}`);
  }

  async function savePreset(kind: "scenario" | "audience", preset: IntakePreset | undefined, prompt: string) {
    if (!preset) return;
    setPresetMessage("");
    const saved = await saveIntakePresetPrompt(kind, preset.id, prompt);
    if (!saved) {
      setPresetMessage("提示词保存失败，请检查后端服务。");
      return;
    }
    setIntakePresets((current) => ({
      ...current,
      [kind]: current[kind].map((item) => (item.id === saved.id ? saved : item)),
    }));
    setPresetMessage(`${saved.name} 的预置提示词已保存。`);
  }

  return (
    <form className="jobForm guidedForm" noValidate onSubmit={submit}>
      {Object.keys(fieldErrors).length ? (
        <div className="formErrorSummary" role="alert">
          <AlertCircle size={17} />
          <div>
            <strong>先补全这些信息</strong>
            <ul>
              {Object.values(fieldErrors).map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      <section className="formSection">
        <header className="formSectionHeader">
          <span className="sectionStep">01</span>
          <div>
            <h2>任务归属</h2>
            <p>提交人用于自动隔离任务；标题决定后续脚本主线。</p>
          </div>
        </header>
        <div className="formGrid">
          <label>
            <span>提交人</span>
            <input
              aria-describedby={fieldErrors.requester_name ? "requester-name-error" : undefined}
              aria-invalid={fieldErrors.requester_name ? "true" : "false"}
              className={fieldErrors.requester_name ? "fieldInvalid" : ""}
              name="requester_name"
              placeholder="请输入姓名"
              defaultValue={initialRequesterName}
              required
            />
            {fieldErrors.requester_name ? <small className="fieldError" id="requester-name-error">{fieldErrors.requester_name}</small> : null}
          </label>
          <label>
            <span>页数</span>
            <input
              aria-describedby={fieldErrors.pages ? "pages-error" : undefined}
              aria-invalid={fieldErrors.pages ? "true" : "false"}
              className={fieldErrors.pages ? "fieldInvalid" : ""}
              name="pages"
              type="number"
              min="1"
              max="80"
              placeholder="不确定可先空着"
            />
            {fieldErrors.pages ? <small className="fieldError" id="pages-error">{fieldErrors.pages}</small> : null}
          </label>
        </div>
        <label>
          <span>PPT 标题</span>
          <input
            aria-describedby={fieldErrors.title ? "title-error" : undefined}
            aria-invalid={fieldErrors.title ? "true" : "false"}
            className={fieldErrors.title ? "fieldInvalid" : ""}
            name="title"
            placeholder="某客户解决方案汇报"
            required
          />
          {fieldErrors.title ? <small className="fieldError" id="title-error">{fieldErrors.title}</small> : null}
        </label>
      </section>

      <section className="formSection">
        <header className="formSectionHeader">
          <span className="sectionStep">02</span>
          <div>
            <h2>汇报口径</h2>
            <p>先选给谁看，再决定脚本是讲价值、讲业务，还是讲技术细节。</p>
          </div>
        </header>
        <div className="formGrid">
          <label>
            <span>使用场景</span>
            <select
              value={selectedScenarioId}
              onChange={(event) => {
                setSelectedScenarioId(event.target.value);
                setPresetMessage("");
              }}
            >
              {intakePresets.scenario.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>受众对象</span>
            <select
              value={selectedAudienceId}
              onChange={(event) => {
                setSelectedAudienceId(event.target.value);
                setPresetMessage("");
              }}
            >
              {intakePresets.audience.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="promptPresetGrid">
          <section className="promptPresetCard">
            <header>
              <Presentation size={17} />
              <div>
                <strong>{currentScenario?.name ?? "使用场景"}</strong>
                <span>{currentScenario?.summary ?? "选择场景后显示对应生成口径。"}</span>
              </div>
            </header>
            <div className="promptPresetPreview">{currentScenarioPrompt}</div>
            <details className="promptAdvanced">
              <summary>高级：编辑场景提示词</summary>
              <textarea
                aria-label="使用场景提示词"
                rows={5}
                value={currentScenarioPrompt}
                onChange={(event) => {
                  if (!currentScenario) return;
                  setScenarioPromptDrafts((current) => ({ ...current, [currentScenario.id]: event.target.value }));
                }}
              />
              <button
                className="secondaryButton compactButton"
                onClick={() => savePreset("scenario", currentScenario, currentScenarioPrompt)}
                type="button"
              >
                <Save size={15} />
                保存场景提示词
              </button>
            </details>
          </section>
          <section className="promptPresetCard">
            <header>
              <Users size={17} />
              <div>
                <strong>{currentAudience?.name ?? "受众对象"}</strong>
                <span>{currentAudience?.summary ?? "选择受众后显示对应表达口径。"}</span>
              </div>
            </header>
            <div className="promptPresetPreview">{currentAudiencePrompt}</div>
            <details className="promptAdvanced">
              <summary>高级：编辑受众提示词</summary>
              <textarea
                aria-label="受众对象提示词"
                rows={5}
                value={currentAudiencePrompt}
                onChange={(event) => {
                  if (!currentAudience) return;
                  setAudiencePromptDrafts((current) => ({ ...current, [currentAudience.id]: event.target.value }));
                }}
              />
              <button
                className="secondaryButton compactButton"
                onClick={() => savePreset("audience", currentAudience, currentAudiencePrompt)}
                type="button"
              >
                <Save size={15} />
                保存受众提示词
              </button>
            </details>
          </section>
        </div>
        {presetMessage ? <p className="presetMessage">{presetMessage}</p> : null}
      </section>

      <section className="formSection">
        <header className="formSectionHeader">
          <span className="sectionStep">03</span>
          <div>
            <h2>风格、资料和边界</h2>
            <p>默认先用解决方案风；补充说明只写重点、禁区和客户关注点。第一版只生成脚本和提示词。</p>
          </div>
        </header>
        <div className="styleWorkbench">
          <div className="stylePromptPane">
            <label>
              <span>风格</span>
              <select name="style" value={selectedStyle} onChange={(event) => setSelectedStyle(event.target.value)}>
                {(styles.length
                  ? styles
                  : [
                      { id: "solution", name: "解决方案风" },
                    ] as StylePreset[]
                ).map((style) => (
                  <option key={style.id} value={style.name}>
                    {style.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="stylePromptText">
              <div className="stylePreviewTitle">
                <Brush size={16} />
                <strong>{currentStyle?.summary ?? "选择风格后显示提示词"}</strong>
              </div>
              <pre>{currentStyle?.prompt ?? "风格提示词会写入本任务 prompt，作为逐页脚本和图片生产提示词的统一视觉口径。"}</pre>
            </div>
          </div>
          <div className="styleEffectPreview" aria-label="风格效果预览">
            <div className="mockSlide">
              <div className="mockSlideTitle">PPT 页面效果预览</div>
              <div className="mockSlideBody">
                <div className="mockVisualBlock">
                  <span>架构/流程主图</span>
                </div>
                <div className="mockMetricGrid">
                  <span>核心观点</span>
                  <span>关键能力</span>
                  <span>待确认</span>
                </div>
              </div>
              <div className="mockSlideFooter">{currentStyle?.example ?? "选择风格后显示页面结构预览。"}</div>
            </div>
          </div>
        </div>
        <label>
          <span>自定义风格提示词</span>
          <textarea
            name="custom_style_prompt"
            rows={3}
            placeholder="可不填；只在需要覆盖默认风格时补充。"
          />
        </label>
        <label>
          <span>补充说明</span>
          <textarea name="user_instruction" rows={4} placeholder="重点、边界、不要编造的内容、客户关注点" />
        </label>
        <label>
          <span>粘贴文字资料</span>
          <textarea
            name="source_text"
            rows={5}
            placeholder="可以直接粘贴会议纪要、聊天记录、客户邮件、口头需求整理。创建任务后会和上传文件一起进入需求梳理。"
          />
        </label>
        <div
          className={`fileDrop ${isDragging ? "dragging" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
        >
          <UploadCloud size={24} />
          <span>拖拽资料到这里，或点击选择</span>
          <small>支持 docx / pdf / xlsx / pptx / png / jpg / md / txt</small>
          <button className="secondaryButton compact" onClick={() => fileInputRef.current?.click()} type="button">
            选择文件
          </button>
          <input
            className="hiddenFileInput"
            aria-hidden="true"
            ref={fileInputRef}
            tabIndex={-1}
            type="file"
            multiple
            onChange={(event) => {
              if (event.target.files) addFiles(event.target.files);
              event.target.value = "";
            }}
          />
        </div>
        {files.length ? (
          <div className="fileQueue">
            {files.map((file) => (
              <div className="fileChip" key={`${file.name}-${file.size}`}>
                <FileStack size={15} />
                <span>{file.name}</span>
                <small>{Math.ceil(file.size / 1024)} KB</small>
                <button
                  aria-label={`移除 ${file.name}`}
                  onClick={() => setFiles((current) => current.filter((item) => item !== file))}
                  type="button"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {error ? <p className="errorText">{error}</p> : null}
      <div className="submitDock">
        <div>
          <strong>准备好了就创建任务</strong>
          <span>创建后生成并审阅逐页 PPT 生产脚本。</span>
        </div>
        <button className="primaryButton" disabled={busy} type="submit">
          <Play size={18} />
          {busy ? "创建中" : "创建任务"}
        </button>
      </div>
    </form>
  );
}
