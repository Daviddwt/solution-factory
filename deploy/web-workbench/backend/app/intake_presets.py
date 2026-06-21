from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Literal

from fastapi import HTTPException

from .config import PRESETS_DIR

PresetKind = Literal["scenario", "audience"]


DEFAULT_INTAKE_PRESETS = {
    "scenario": [
        {
            "id": "customer-report",
            "name": "客户汇报",
            "summary": "面向客户侧正式汇报，强调价值、路径、风险边界和可落地性。",
            "prompt": """本任务用于客户汇报，请按“客户能快速听懂并愿意继续推进”的口径梳理内容。

表达重点：
- 优先讲清楚客户为什么要做、解决什么管理问题、带来什么业务价值。
- 每页都要有一句明确结论，避免只有技术模块堆叠。
- 建设目标要分层：当前要解决的问题、阶段性成果、后续可扩展方向。
- 方案路径要体现可落地：先做什么、再做什么、哪些事项需要客户确认。
- 风险和边界要主动写出来，但语气要稳，不要显得方案不成熟。

内容取舍：
- 技术内容服务于价值说明，不堆砌协议、组件、产品名。
- 对客户领导关心的投入产出、运营效率、管理可视化、风险可控要有表达。
- 涉及接口、数据、点位、金额、上线时间、已有系统状态时，没有材料依据必须标注“待客户确认”。

禁止：
- 不要把待确认事项写成已完成。
- 不要编造客户已有系统、合同金额、人员、比例、承诺周期。
- 不要写成内部技术评审文档。""",
        },
        {
            "id": "internal-review",
            "name": "内部评审",
            "summary": "面向内部方案评审，强调事实边界、风险、缺口和交付可行性。",
            "prompt": """本任务用于内部评审，请按“方便团队判断能不能做、怎么做、风险在哪里”的口径梳理内容。

表达重点：
- 先列事实依据，再列推断和待确认事项，三者要分开。
- 明确能力匹配：existing、configurable、integration、custom_dev、unclear。
- 明确交付边界：哪些能直接复用，哪些需要集成，哪些需要定制开发。
- 把风险、缺口、依赖、客户待补材料和内部下一步分工写清楚。

内容取舍：
- 可以直接暴露不确定性，不要为了页面好看弱化问题。
- 对技术路径、数据来源、接口方式、验收风险要比客户汇报更细。
- 页面脚本要方便后续转成任务清单或评审意见。

禁止：
- 不要用营销话术掩盖未确认内容。
- 不要把“可能可做”写成“已经具备”。
- 不要遗漏需要客户或内部负责人确认的事项。""",
        },
        {
            "id": "bid-prep",
            "name": "投标准备",
            "summary": "面向投标或售前材料准备，强调响应关系、差异化能力和可证明依据。",
            "prompt": """本任务用于投标准备，请按“需求响应清晰、能力证据充分、承诺边界可控”的口径梳理内容。

表达重点：
- 围绕招标/客户要求建立响应关系，最好能体现“需求点 -> 方案响应 -> 交付方式”。
- 突出能力覆盖、差异化亮点、实施路径、风险兜底和可证明材料。
- 对评分点、关键指标、验收方式、交付周期要谨慎表达。
- 页面结构要便于后续扩展成投标章节或方案附件。

内容取舍：
- 优先保留客户要求、响应策略、能力依据和实施保障。
- 对没有证据的资质、案例、参数、金额和周期，只能写“待补充/待确认”。
- 可以加入“建议补充材料”提示，帮助团队补齐投标证据链。

禁止：
- 不得编造资质、案例、金额、参数或承诺周期。
- 不得把未确认指标写成确定承诺。
- 不要写成泛泛的产品介绍。""",
        },
        {
            "id": "solution-workshop",
            "name": "方案预沟通",
            "summary": "面向早期沟通，强调问题澄清、方案方向和共创议题。",
            "prompt": """本任务用于方案预沟通，请按“帮助双方对齐问题和方向”的口径梳理内容。

表达重点：
- 把已知需求、合理假设、关键问题、可选方案路径分开写。
- 页面要引导客户共同确认：业务范围、数据来源、接口条件、优先场景、成功标准。
- 方案不要过早写成定稿，而要体现可讨论、可收敛、可分阶段推进。

内容取舍：
- 多写问题澄清和可选路径，少写绝对承诺。
- 对不确定内容用“待客户确认”“建议会前补充”“建议现场澄清”。
- 适合用路线图、问题清单、场景优先级矩阵、能力边界图。

禁止：
- 不要把假设写成事实。
- 不要在材料不足时强行给出唯一方案。
- 不要过度包装成最终投标/交付方案。""",
        },
    ],
    "audience": [
        {
            "id": "customer-leader",
            "name": "客户领导",
            "summary": "关注价值、治理、成效、风险和阶段路线。",
            "prompt": """受众是客户领导，请按“决策者快速判断价值和路径”的方式组织内容。

他们通常关心：
- 为什么现在要做，解决哪些管理痛点。
- 建成后能带来哪些管理价值、业务成效、风险控制和可视化能力。
- 投入后如何分阶段见效，是否可控、可扩展、可持续运营。
- 哪些事项需要领导拍板或协调资源。

表达方式：
- 每页先给结论，再用图示支撑。
- 少写底层技术细节，多用管理语言解释架构和流程。
- 复杂技术用“平台能力、数据闭环、流程闭环、治理机制”转译。
- 待确认事项要写得稳：不是问题暴露，而是下一步决策信息。

避免：
- 不要堆协议、数据库、接口参数。
- 不要把页面写成技术方案说明书。""",
        },
        {
            "id": "business-owner",
            "name": "业务负责人",
            "summary": "关注流程、职责、数据口径、使用场景和闭环效果。",
            "prompt": """受众是业务负责人，请按“业务怎么用、流程怎么变、责任怎么闭环”的方式组织内容。

他们通常关心：
- 哪些业务场景被覆盖，谁来用，什么时候用。
- 原来的流程有什么断点，新方案如何形成闭环。
- 数据口径、异常处理、工单流转、协同机制和运营指标如何设计。
- 一线人员、主管、管理者分别看到什么、操作什么、追踪什么。

表达方式：
- 多用流程图、角色泳道、场景闭环、指标看板示意。
- 技术能力要落到具体工作：少录入、少催办、可追踪、可复盘。
- 需要明确哪些数据或业务规则还要业务负责人确认。

避免：
- 不要只讲平台模块，不讲业务动作。
- 不要把业务规则写死，除非材料已有明确依据。""",
        },
        {
            "id": "technical-team",
            "name": "技术团队",
            "summary": "关注架构、接口、数据、部署、安全和集成边界。",
            "prompt": """受众是技术团队，请按“架构能评审、接口能讨论、边界能落地”的方式组织内容。

他们通常关心：
- 总体架构、系统边界、数据流、接口方式、部署形态和安全权限。
- 现有系统如何对接，数据从哪里来，失败和异常如何处理。
- 哪些能力是已有，哪些可配置，哪些需集成，哪些需定制开发。
- 运维监控、日志、权限、网络、安全、性能和扩展性风险。

表达方式：
- 页面可以更技术化，但必须保持结构清晰。
- 多用架构分层图、数据流图、接口清单、能力矩阵、部署拓扑。
- 对接口、协议、数据字段、账号权限等未确认内容，必须标注待确认。

避免：
- 不要泛泛讲“平台支撑”，要说明支撑方式。
- 不要把 RPA、API、定制开发混为一谈。
- 不要编造接口状态、部署环境、系统名称和安全要求。""",
        },
        {
            "id": "project-team",
            "name": "方案团队",
            "summary": "关注材料完整性、页面逻辑、卖点、证据和后续制作口径。",
            "prompt": """受众是方案团队，请按“方便继续加工、复用和交付”的方式组织内容。

他们通常关心：
- 页面逻辑是否顺，卖点是否明确，证据是否够。
- 哪些内容来自材料，哪些是推断，哪些需要补材料。
- 哪些页面适合架构图、流程图、矩阵、路线图或对比图。
- 图片 PPT 和后续可编辑化需要注意哪些版式和组件。

表达方式：
- 每页脚本要保留标题、核心观点、图示建议、讲稿和审核备注。
- 对素材缺口、客户待确认、内部待补证据要单独列出。
- 可以给出后续图片 PPT 表达建议，但不要替代第二步生成。

避免：
- 不要把页面写成最终文案而缺少制作提示。
- 不要遗漏证据来源和待补材料。""",
        },
    ],
}


def presets_path() -> Path:
    return PRESETS_DIR / "intake-presets.json"


def read_intake_presets() -> dict:
    path = presets_path()
    if not path.exists():
        write_intake_presets(deepcopy(DEFAULT_INTAKE_PRESETS))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = deepcopy(DEFAULT_INTAKE_PRESETS)
        write_intake_presets(data)
    return merge_with_defaults(data)


def write_intake_presets(data: dict) -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    presets_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_with_defaults(data: dict) -> dict:
    merged = deepcopy(DEFAULT_INTAKE_PRESETS)
    for kind in ("scenario", "audience"):
        by_id = {item["id"]: item for item in merged[kind]}
        for item in data.get(kind, []):
            item_id = item.get("id")
            if item_id in by_id:
                by_id[item_id].update({key: value for key, value in item.items() if key in {"name", "summary", "prompt"}})
        merged[kind] = list(by_id.values())
    return merged


def update_intake_prompt(kind: PresetKind, preset_id: str, prompt: str) -> dict:
    data = read_intake_presets()
    for item in data[kind]:
        if item["id"] == preset_id:
            item["prompt"] = prompt.strip()
            write_intake_presets(data)
            return item
    raise HTTPException(status_code=404, detail="Preset not found")
