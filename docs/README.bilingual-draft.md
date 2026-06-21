# Solution Factory

[中文](#中文) | [English](#english)

## 中文

Solution Factory 是面向解决方案、售前、产品和交付团队的 AI PPT 脚本生产台。它把客户资料、公司知识库、汇报口径和 PPT 风格要求整理成可审阅的逐页 PPT 脚本与逐页图片生产提示词。

### 给 Codex 的安装指令

不要手动下载、解压和分步安装。把下面这句话复制给 Codex：

```text
请给我的 Codex 安装以下地址的插件：https://github.com/Daviddwt/solution-factory
请自行读取注意事项、下载最新分享包、安装插件、打开网页工作台并完成验证。
```

### 当前生产边界

```text
客户资料 + 公司知识库 + 汇报口径 + PPT风格要求
-> 需求梳理
-> 能力匹配
-> 实现路径
-> 逐页 PPT 脚本
-> 逐页图片生产提示词
-> Markdown / ZIP 交付包
```

当前版本不默认生成最终图片 PPT，也不默认生成可编辑 PPTX。图片 PPT 与可编辑 PPTX 是后续独立流程。

### 使用建议

- 先上传客户需求、会议纪要、现有系统说明、接口信息和业务流程材料。
- 再上传公司产品 FRS、产品手册、案例材料和公司介绍。
- 如果要匹配指定 PPT 风格，请上传参考 PPT/PDF/截图。
- 没有材料依据的内容应标记为“待确认”。
- 非现有产品能力应标记为 `integration`、`custom_dev` 或 `unclear`。

### 公司服务器

如果你使用公司统一部署的服务器网页，请从内部公告或企业微信获取地址。公开 GitHub 文档不会暴露公司内网 IP。

## English

Solution Factory is an AI-assisted PPT script workbench for solution, presales, product, and delivery teams. It turns customer materials, company knowledge, presentation intent, and style references into reviewable page-level PPT scripts and image-production prompts.

### Codex Installation Prompt

Do not download, unzip, or install the package manually. Copy this prompt to Codex:

```text
Please install the Codex plugin from this URL: https://github.com/Daviddwt/solution-factory
Read the notes, download the latest release package, install the plugin, open the web workbench, and verify it works.
```

### Current Capability Boundary

```text
customer materials + company knowledge + presentation intent + PPT style references
-> requirement decomposition
-> capability matching
-> implementation path
-> page-level PPT scripts
-> page-level image-production prompts
-> Markdown / ZIP handoff package
```

This version does not automatically generate final image PPT files or editable PPTX files. Image PPT generation and editable PPT reconstruction are downstream workflows.

### Usage Tips

- Upload customer requirements, meeting notes, existing system descriptions, interface details, and business process materials first.
- Then upload company product FRS files, product manuals, case materials, and company profile materials.
- If a specific PPT style is required, upload reference PPT/PDF/screenshots.
- Mark content without evidence as "to be confirmed".
- Requirements outside existing product capabilities should be labeled as `integration`, `custom_dev`, or `unclear`.

### Company Server

If your company provides a shared server version, get the URL from the internal announcement. Public GitHub documentation should not expose internal network addresses.
