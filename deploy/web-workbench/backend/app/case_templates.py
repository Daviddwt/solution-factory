from __future__ import annotations

import os
import re
from pathlib import Path

SMART_LOGISTICS_SCRIPT_MD = """# 智慧后勤解决方案 PPT 逐页脚本样例

用途：作为“解决方案风”的参考案例，让需求梳理和图片 PPT 制作阶段都能看到逐页内容颗粒度。新任务可以参考结构、页面类型和表达方式，但不得直接套用客户事实。

## P01 项目背景与核心定位

- 核心观点：以数据驱动和智能赋能建设智慧后勤服务平台。
- 页面类型：background
- 关联需求：REQ-001, REQ-002, REQ-003, REQ-004, REQ-005
- 关联能力：CAP-DATA-ANALYTICS, CAP-LINGZHE-AGENT

讲稿：

先说明后勤管理从被动响应向主动预判转型的背景，明确本方案不是单点系统，而是数据采集、数据治理和场景应用的全链路平台。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P02 敢为云能力底座

- 核心观点：云、边、端一体化支撑全域后勤智慧应用。
- 页面类型：architecture
- 关联需求：REQ-001, REQ-002, REQ-005
- 关联能力：CAP-HANHAI-LOWCODE, CAP-PANSHI-IOT, CAP-CHENXING-VISUAL, CAP-LINGZHE-AGENT

讲稿：

介绍瀚海、磐石、晨星、灵哲四类能力如何共同支撑后勤场景：低代码承载流程，物联承载感知，可视化承载态势，AI承载交互和智能协同。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P03 一站式后勤保障需求拆解

- 核心观点：以钉钉为员工入口，把差旅、车辆、住宿和办公资源诉求拆成可自动执行的服务链。
- 页面类型：requirement_analysis
- 关联需求：REQ-001
- 关联能力：CAP-LINGZHE-AGENT, CAP-HANHAI-LOWCODE, CAP-SERVICE-WORKORDER, CAP-SECURITY-CONTROL

讲稿：

从员工出差和日常服务入口切入，明确员工入口优先采用钉钉；AI负责理解需求并拆成差旅、车辆、住宿、办公资源等子任务，资源确认默认自动完成，客户指定或异常节点再进入人工复核。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P04 一站式保障实现路径

- 核心观点：短期采用钉钉入口+API/RPA集成，能力缺口进入定制开发池，长期演进为AI业务代办管家。
- 页面类型：business_flow
- 关联需求：REQ-001
- 关联能力：CAP-LINGZHE-AGENT, CAP-HANHAI-LOWCODE, CAP-SERVICE-WORKORDER, CAP-SECURITY-CONTROL

讲稿：

短期优先通过差旅、车辆、住宿和办公资源系统API读取审批、库存和状态数据；无API或接口不足时，以RPA嵌入或定制开发补齐。长期由灵哲智能体理解自然语言诉求，调用流程、工单和外部系统完成业务代办，并通过钉钉反馈办理结果。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P05 全域资源管理需求拆解

- 核心观点：资源管理从台账记录升级为全生命周期和跨基地调剂。
- 页面类型：requirement_analysis
- 关联需求：REQ-002
- 关联能力：CAP-CHENXING-VISUAL, CAP-DATA-ANALYTICS

讲稿：

说明资源闲置、账实不清和跨基地调剂困难是核心痛点，方案将资源入库、使用、维修、调剂、报废串联为可追踪闭环。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P06 资源数字孪生与问数决策

- 核心观点：用空间可视化和自然语言问数支撑资源盘活。
- 页面类型：data_flow
- 关联需求：REQ-002
- 关联能力：CAP-CHENXING-VISUAL, CAP-DATA-ANALYTICS, CAP-LINGZHE-AGENT

讲稿：

展示资源地图、闲置热力、生命周期分析和自然语言问数，突出管理者可以快速获得资源利用率和采购建议。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P07 智能客服体系

- 核心观点：让高频重复问题由私域知识库和AI客服优先分流。
- 页面类型：capability_matrix
- 关联需求：REQ-003
- 关联能力：CAP-LINGZHE-AGENT, CAP-KNOWLEDGE-BASE, CAP-SERVICE-WORKORDER

讲稿：

讲清楚知识库来源、AI问答、复杂诉求转人工或工单的路径，强调客服不是只回答问题，而是进入服务闭环。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P08 统一后勤服务管理

- 核心观点：统一入口、自动派发、移动接单和评价反馈形成服务透明闭环。
- 页面类型：business_flow
- 关联需求：REQ-004
- 关联能力：CAP-HANHAI-LOWCODE, CAP-SERVICE-WORKORDER, CAP-DATA-ANALYTICS

讲稿：

通过一张流程图说明从员工提交到规则判断、自动派发、移动接单、评价反馈，最后沉淀服务质量数据。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P09 服务效能数据化

- 核心观点：用MTTR、满意度和高频问题分析驱动服务持续优化。
- 页面类型：value_metrics
- 关联需求：REQ-004
- 关联能力：CAP-DATA-ANALYTICS, CAP-SERVICE-WORKORDER

讲稿：

说明服务数据进入分析模型后，能够跟踪处理时长、报修类型、人员负载和满意度趋势，为资源排班和服务改进提供依据。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P10 第三责任区安全管理

- 核心观点：把纸质巡检升级为物联感知、视频识别和整改闭环。
- 页面类型：risk_control
- 关联需求：REQ-005
- 关联能力：CAP-PANSHI-IOT, CAP-HANHAI-LOWCODE, CAP-SECURITY-CONTROL

讲稿：

围绕办公、宿舍、食堂等责任区，说明传感器、摄像头和工单系统如何构成主动预警和强制闭环。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P11 实施路径与审核闸口

- 核心观点：先调研和高阶设计，再分批建设短期速赢和长期演进。
- 页面类型：implementation_roadmap
- 关联需求：REQ-001, REQ-002, REQ-003, REQ-004, REQ-005
- 关联能力：CAP-HANHAI-LOWCODE, CAP-SECURITY-CONTROL

讲稿：

将KCP2需求调研、KCP3高阶设计、分批建设、试运行验收串起来，强调每一阶段都有可交付文档和评审节点。

审核备注：待业务负责人审核后进入图片PPT渲染。

## P12 合作价值总结

- 核心观点：以平台化能力支撑后勤数智化长期演进。
- 页面类型：closing
- 关联需求：REQ-001, REQ-002, REQ-003, REQ-004, REQ-005
- 关联能力：CAP-DATA-ANALYTICS, CAP-LINGZHE-AGENT, CAP-PANSHI-IOT, CAP-CHENXING-VISUAL

讲稿：

收束到统一数据资产、智能感知场景、灵活架构扩展和持续生态共建，说明本项目既解决当前痛点，也沉淀长期运营能力。

审核备注：待业务负责人审核后进入图片PPT渲染。
"""


SMART_LOGISTICS_ORIGINAL_PROMPT_DIR = Path(
    os.environ.get("SOLUTION_FACTORY_REFERENCE_PROMPT_DIR", "")
)


def load_smart_logistics_original_prompts() -> str:
    sections = [
        "# 智慧后勤原始图片PPT提示词（12页）",
        "",
        "来源：`SOLUTION_FACTORY_REFERENCE_PROMPT_DIR/slide-01.md` 至 `slide-12.md`。",
        "",
        "用途：作为复杂原始提示词参考，让需求梳理和图片 PPT 制作阶段都能看到真实图片生成提示词的颗粒度。新任务可参考结构、全局口径、页面目标、图示结构、关键词、讲稿和视觉注意，但不得直接套用客户事实。",
        "",
    ]
    for index in range(1, 13):
        prompt_path = SMART_LOGISTICS_ORIGINAL_PROMPT_DIR / f"slide-{index:02d}.md"
        if not prompt_path.exists():
            sections.extend([f"## slide-{index:02d}.md", "", "原始提示词文件未找到。", ""])
            continue
        sections.extend(
            [
                f"## slide-{index:02d}.md",
                "",
                prompt_path.read_text(encoding="utf-8", errors="replace").strip(),
                "",
            ]
        )
    return "\n".join(sections).strip() + "\n"


def load_smart_logistics_prompt_page(page_no: int) -> str:
    prompt_path = SMART_LOGISTICS_ORIGINAL_PROMPT_DIR / f"slide-{page_no:02d}.md"
    if not prompt_path.exists():
        return f"# slide-{page_no:02d}.md\n\n原始提示词文件未找到。\n"
    raw_prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
    return build_chinese_prompt_reference(page_no, raw_prompt)


def build_chinese_prompt_reference(page_no: int, raw_prompt: str) -> str:
    """Keep the detailed reference structure, but expose it as a Chinese prompt."""
    chinese_lines: list[str] = []
    for raw_line in raw_prompt.splitlines():
        line = raw_line.rstrip()
        if not line:
            if chinese_lines and chinese_lines[-1] != "":
                chinese_lines.append("")
            continue
        if contains_chinese(line):
            chinese_lines.append(line)
        elif line.strip().startswith("#"):
            translated = translate_prompt_heading(line.strip())
            if translated:
                chinese_lines.append(translated)
        elif any(token in line for token in ("REQ", "CAP-", "existing", "configurable", "integration", "custom_dev", "unclear")):
            chinese_lines.append(translate_prompt_taxonomy(line.strip()))

    cleaned = "\n".join(chinese_lines).strip()
    return f"""# P{page_no:02d} 图片PPT生成提示词（中文整理版）

用途：作为当前页图片 PPT 的生成提示词。内容已从原始复杂提示词整理为中文口径，供第二步制作图片 PPT 使用。

## 基础要求

- 生成一页完整的 16:9 横版商务汇报图片，最终会作为整页图片放入 PPT。
- 幻灯片内所有可见文字必须使用简体中文。
- 标题、图示节点、表格标签、风险提示和待确认事项都必须清晰可读。
- 长段讲稿只作为生成参考，不要直接堆到页面上。
- 不要编造客户已有系统、接口状态、金额、比例、点位数量、人员信息或上线状态。

## 原始复杂提示词中文化参考

{cleaned or "原始复杂提示词中没有可直接复用的中文内容，请依据当前页脚本和任务风格生成。"}
"""


def contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def translate_prompt_heading(line: str) -> str:
    mapping = {
        "Global source of truth:": "## 全局事实依据",
        "Page-specific source of truth:": "## 当前页事实依据",
        "Primary request:": "## 主要生成请求",
        "Strict text rules:": "## 文字规则",
        "Visual rules:": "## 视觉规则",
    }
    return mapping.get(line, "")


def translate_prompt_taxonomy(line: str) -> str:
    return (
        line.replace("existing", "现有能力")
        .replace("configurable", "可配置能力")
        .replace("integration", "需集成")
        .replace("custom_dev", "需定制开发")
        .replace("unclear", "信息不清")
    )


def split_smart_logistics_script_pages() -> list[dict[str, object]]:
    matches = list(re.finditer(r"^## P(?P<page_no>\d{2}) (?P<title>.+)$", SMART_LOGISTICS_SCRIPT_MD, flags=re.MULTILINE))
    pages: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        page_no = int(match.group("page_no"))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(SMART_LOGISTICS_SCRIPT_MD)
        content = SMART_LOGISTICS_SCRIPT_MD[match.start() : end].strip() + "\n"
        pages.append(
            {
                "page_no": page_no,
                "page_id": f"p{page_no:02d}",
                "title": match.group("title").strip(),
                "content": content,
            }
        )
    return pages


def build_page_prompt_from_script(page_no: int, title: str, script: str, style_prompt: str = "") -> str:
    style_section = localize_prompt_terms(style_prompt.strip() or "沿用当前任务选择的解决方案风格。")
    script_section = localize_prompt_terms(script.strip())
    page_truth = localize_prompt_terms(extract_script_section(script, "Page-specific source of truth", ("页面设计 Brief", "讲稿", "审核备注")))
    if not page_truth:
        page_truth = "本页缺少 Page-specific source of truth，不能作为高质量图片生成输入；请先回到第一步补写当前页设计真值。"
    return f"""# P{page_no:02d} 图片PPT生成提示词

用途：根据当前任务的第 {page_no} 页页面脚本，生成这一页图片 PPT 的详细提示词。只影响本页，不改其他页面。

## 当前页标题

{title}

## 当前任务风格要求

{style_section}

## 当前页设计真值（必须优先执行）

下面这一段是本页图片生成的最高优先级说明。必须逐项落实页面目标、版式、图示节点、关键词、上屏文字、视觉注意、事实边界和禁止事项；不得只按通用风格生成。

{page_truth}

## 当前页脚本

{script_section}

## 生成要求

- 生成一页完整的 16:9 横版商务汇报图片，画面应达到正式汇报草稿水准。
- 使用简体中文，页面要像政企解决方案汇报，不要像营销海报。
- 以“当前页设计真值”为画面执行依据，以页面脚本里的“核心观点、来源依据、图示结构、页面设计 Brief、讲稿、审核备注”为事实边界。
- 如果“当前页设计真值”缺少页面目标、版式要求、图示结构、必须出现的关键词、上屏文字、视觉注意、事实与能力边界或禁止事项，本页不得进入正式图片生成，应先回到第一步重生成或补写脚本。
- 必须优先执行“页面设计 Brief”：主体图示、画面模块、上屏文字、视觉布局、待确认表达和禁止画面都要落实到页面。
- 如果页面脚本没有“页面设计 Brief”，本页不得进入正式图片生成，应先回到第一步重生成或补写脚本。
- 若脚本里出现待确认事项，必须明确标注“待客户确认”，不能写成已完成。
- 每页必须有清晰标题、主体图示和少量支撑文字，不要做纯文字页。
- 图示优先使用流程节点、系统接口、数据流、能力矩阵、架构分层或闭环链路。
- 封面页按封面处理：突出项目/方案名称、汇报场景、提交人或团队、日期，不要画成流程页。
- 目录页按目录处理：列出后续章节结构，不要画成普通内容页。
- 每页左上角保留敢为云 Logo 位；真实素材未上传时可用“敢为云”文字占位。
- 不要编造客户已有系统名称、接口状态、金额、比例、人员信息、点位数量或上线状态。
- 如果本页脚本仍然来自样例，请只参考结构和表达方式，不得套用样例客户事实。
"""


def extract_script_section(script: str, heading: str, stop_headings: tuple[str, ...]) -> str:
    start = re.search(re.escape(heading) + r"\s*[：:]", script)
    if not start:
        return ""
    tail = script[start.end() :]
    stops = []
    for stop_heading in stop_headings:
        stop = re.search(r"\n\s*" + re.escape(stop_heading) + r"\s*[：:]", tail)
        if stop:
            stops.append(stop.start())
    if stops:
        tail = tail[: min(stops)]
    return tail.strip()


def localize_prompt_terms(text: str) -> str:
    replacements = {
        "existing": "现有能力",
        "configurable": "可配置能力",
        "integration": "需集成",
        "custom_dev": "需定制开发",
        "unclear": "信息不清",
        "background": "背景介绍页",
        "architecture": "架构页",
        "requirement_analysis": "需求拆解页",
        "business_flow": "业务流程页",
        "data_flow": "数据流页",
        "capability_matrix": "能力矩阵页",
        "value_metrics": "价值指标页",
        "risk_control": "风险控制页",
        "implementation_roadmap": "实施路径页",
        "closing": "总结页",
        " ribbon ": " 条带 ",
        "API": "接口",
        "RPA": "流程自动化",
        "REQ-001": "需求一：一站式后勤保障",
        "REQ-002": "需求二：全域资源管理",
        "REQ-003": "需求三：智能客服体系",
        "REQ-004": "需求四：统一后勤服务管理",
        "REQ-005": "需求五：第三责任区安全管理",
        "CAP-DATA-ANALYTICS": "数据分析能力",
        "CAP-LINGZHE-AGENT": "灵哲智能体能力",
        "CAP-HANHAI-LOWCODE": "瀚海低代码能力",
        "CAP-PANSHI-IOT": "磐石物联能力",
        "CAP-CHENXING-VISUAL": "晨星可视化能力",
        "CAP-SERVICE-WORKORDER": "服务工单能力",
        "CAP-SECURITY-CONTROL": "安全管控能力",
        "CAP-KNOWLEDGE-BASE": "知识库能力",
    }
    localized = text
    for source, target in replacements.items():
        localized = localized.replace(source, target)
    return localized


def build_requirement_reminders(status: object) -> str:
    title = getattr(status, "title", "")
    requester_name = getattr(status, "requester_name", "")
    pages = getattr(status, "pages", None)
    scenario = getattr(status, "scenario", "")
    audience = getattr(status, "audience", "")
    user_instruction = getattr(status, "user_instruction", "")
    return f"""# 需求梳理提醒

## 本任务基本信息

- 提交人：{requester_name}
- 标题：{title}
- 建议页数：{pages or '待根据资料判断'}
- 使用场景：{scenario or '未填写'}
- 受众对象：{audience or '未填写'}

## 只做这些事

1. 先把上传资料里的事实、需求、能力边界和待确认项梳理清楚。
2. 明确哪些内容属于现有能力、可配置、需集成、需定制开发、信息不清。
3. 标出不能编造的内容：客户已有系统、接口状态、金额、比例、点位数量、组织名称、上线状态。
4. 给第二步制作图片 PPT 留出可执行输入：页面主题、核心观点、来源依据、待确认问题。
5. 参考“智慧后勤逐页脚本样例”的颗粒度，但不要把样例里的客户事实直接套进当前项目。

## 不在这里展开

- 不在需求梳理提醒里写完整逐页图片生成提示词。
- 不在这里堆完整视觉规则全文。
- 不把待确认事项写成已确认事实。
- 不直接进入最终 PPT 交付判断。

## 用户补充说明

{user_instruction or '未填写'}
"""
