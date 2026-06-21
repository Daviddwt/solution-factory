import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

const args = parseArgs(process.argv);
if (!args["job-dir"]) {
  console.error("usage: node render_formal_images.mjs --job-dir <job_dir>");
  process.exit(2);
}

const jobDir = path.resolve(args["job-dir"]);
const nodeModules = args["node-modules"] || process.env.NODE_MODULES_PATH || "";
const require = createRequire(import.meta.url);
const sharp = require(path.join(nodeModules, "sharp"));

const W = 1600;
const H = 900;
const imageDir = path.join(jobDir, "work", "02_image_ppt");
const assetsDir = path.join(imageDir, "assets");
await fs.mkdir(assetsDir, { recursive: true });

const status = JSON.parse(await fs.readFile(path.join(jobDir, "status.json"), "utf8"));
const pages = JSON.parse(await fs.readFile(path.join(jobDir, "work", "01_requirements", "page-index.json"), "utf8"));

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clean(value) {
  return String(value ?? "")
    .replace(/\r/g, "")
    .replace(/\*\*/g, "")
    .replace(/[`#]/g, "")
    .trim();
}

function extractBetween(text, startLabels, endLabels) {
  const starts = Array.isArray(startLabels) ? startLabels : [startLabels];
  let start = -1;
  let startLength = 0;
  for (const label of starts) {
    const index = text.indexOf(label);
    if (index !== -1 && (start === -1 || index < start)) {
      start = index;
      startLength = label.length;
    }
  }
  if (start === -1) return "";
  const tail = text.slice(start + startLength);
  let end = tail.length;
  for (const label of endLabels) {
    const index = tail.indexOf(label);
    if (index !== -1 && index < end) end = index;
  }
  return clean(tail.slice(0, end));
}

function extractBullets(text, limit = 12) {
  return text
    .split("\n")
    .map((line) => clean(line.replace(/^[-•]\s*/, "")))
    .filter((line) => line && !line.includes("```"))
    .filter((line) => !/^(页面目标|版式要求|图示结构|必须出现的关键词|上屏文字|讲稿要点|视觉注意|事实与能力边界|禁止事项)[：:]/.test(line))
    .slice(0, limit);
}

function extractLabel(text, label) {
  const match = text.match(new RegExp(`${label}[：:]\\s*([^\\n]+)`));
  return clean(match?.[1] || "");
}

function splitFragments(text, limit = 8) {
  return clean(text)
    .replace(/[“”"]/g, "")
    .split(/[；;。]/)
    .map((item) => clean(item.replace(/^第[一二三四五六七八九十]+层/, "").replace(/^(第一层|第二层|第三层|第四层|第五层)[：:]/, "")))
    .filter(Boolean)
    .filter((item) => !/^(页面目标|版式要求|图示结构|必须出现的关键词|上屏文字|讲稿要点|视觉注意|事实与能力边界|禁止事项)$/.test(item))
    .slice(0, limit);
}

function extractQuotedItems(text, limit = 16) {
  const items = [];
  const re = /[“"]([^”"]{2,40})[”"]/g;
  let match;
  while ((match = re.exec(text || "")) && items.length < limit) {
    items.push(clean(match[1]));
  }
  return items.filter((item, index, arr) => item && arr.indexOf(item) === index);
}

function splitListItems(text, limit = 18) {
  return clean(text)
    .replace(/[“”"]/g, "")
    .replace(/第[一二三四五六七八九十]+层/g, "")
    .split(/[；;。:：、,，]/)
    .map((item) => clean(item.replace(/^(图示结构|主体图示|上屏文字|必须出现的关键词|底部三张卡片为|四个辐射节点分别写)/, "")))
    .filter((item) => item && item.length <= 26)
    .filter((item, index, arr) => arr.indexOf(item) === index)
    .slice(0, limit);
}

function classifyPage(page, script) {
  const title = page.title || "";
  const type = extractLabel(script, "页面类型");
  const basis = `${title} ${type}`;
  if (page.page_no === 1 || /封面/.test(title) || /建设方案$/.test(title)) return "cover";
  if (page.page_no === 2 || /目录|议程/.test(basis)) return "agenda";
  if (/建设定位|项目背景|背景|目标|总结|价值/.test(basis)) return "overview";
  if (/需求全景|六类|场景能力|能力地图|全景/.test(basis)) return "capability";
  if (/IOC|指挥中心|一屏|大屏|看板|态势|状态感知|运行|监控|趋势|热力图/.test(basis)) return "dashboard";
  if (/实施|步骤|推广|分期|验收|下一步|路线/.test(basis)) return "roadmap";
  if (/规则|分级|痛点|需求|矩阵|风险/.test(basis)) return "matrix";
  if (/权限|审计|分工|职责|边界|审批|确认|复用|安全/.test(basis)) return "governance";
  if (/音视频|协同指挥|跨部门|通知|推送/.test(basis)) return "collaboration";
  if (/总体架构|技术架构|架构图|架构|底座|平台|物联|接入|集成|物模型|设备/.test(basis)) return "architecture";
  if (/流程|路径|闭环|联动|派单|工单|审批|确认/.test(basis)) return "flow";
  if (/痛点|需求|边界|矩阵|分工|职责|安全|权限|风险/.test(basis)) return "matrix";
  return "overview";
}

function getBrief(page, script, prompt) {
  const truth = extractBetween(script, "Page-specific source of truth", ["页面设计 Brief", "讲稿", "审核备注"]);
  const design = extractBetween(script, "页面设计 Brief", ["讲稿", "审核备注"]);
  const source = extractBetween(script, "来源依据", ["图示结构", "页面设计 Brief"]);
  const onSlideLabel = extractLabel(`${truth}\n${design}\n${prompt}`, "上屏文字");
  const keywordsLabel = extractLabel(`${truth}\n${design}\n${prompt}`, "必须出现的关键词");
  const diagramLabel = extractLabel(`${truth}\n${design}`, "图示结构") || extractLabel(`${truth}\n${design}`, "主体图示");
  const modules = [
    ...splitFragments(diagramLabel, 6),
    ...splitFragments(onSlideLabel, 4),
    ...splitFragments(keywordsLabel, 4),
    ...extractBullets(design, 5),
  ]
    .filter((item, index, arr) => arr.indexOf(item) === index)
    .slice(0, 8);
  const sourceBullets = extractBullets(source, 4);
  const goal = extractLabel(`${truth}\n${design}`, "页面目标") || extractLabel(`${truth}\n${design}`, "核心观点");
  const diagram = diagramLabel;
  const boundary = extractLabel(`${truth}\n${design}`, "事实与能力边界") || "材料不足处标注待客户确认";
  const layout = extractLabel(`${truth}\n${design}`, "版式要求");
  const visual = extractLabel(`${truth}\n${design}`, "视觉注意");
  const nodes = [
    ...extractQuotedItems(`${diagramLabel}\n${onSlideLabel}\n${keywordsLabel}`, 18),
    ...splitListItems(`${diagramLabel}\n${onSlideLabel}\n${keywordsLabel}`, 18),
  ].filter((item, index, arr) => item && arr.indexOf(item) === index);
  return {
    title: clean(page.title),
    type: classifyPage(page, script),
    goal: goal || modules[0] || "围绕当前材料形成可审阅页面结论",
    diagram: diagram || "分层图示",
    layout,
    visual,
    modules: nodes.length ? nodes.slice(0, 10) : modules.length ? modules : sourceBullets.length ? sourceBullets : ["业务目标", "能力边界", "实施路径"],
    nodes,
    onSlide: splitFragments(onSlideLabel, 6),
    keywords: splitFragments(keywordsLabel, 8),
    sourceBullets,
    boundary,
  };
}

function wrapText(text, maxChars, maxLines = 4) {
  const source = clean(text);
  const chunks = [];
  let line = "";
  for (const char of source) {
    const charWidth = /[A-Za-z0-9]/.test(char) ? 0.55 : 1;
    const lineWidth = Array.from(line).reduce((sum, item) => sum + (/[A-Za-z0-9]/.test(item) ? 0.55 : 1), 0);
    if (lineWidth + charWidth > maxChars && line) {
      chunks.push(line);
      line = char;
      if (chunks.length >= maxLines) break;
    } else {
      line += char;
    }
  }
  if (line && chunks.length < maxLines) chunks.push(line);
  if (chunks.length === maxLines && source.length > chunks.join("").length) {
    chunks[maxLines - 1] = `${chunks[maxLines - 1].slice(0, Math.max(0, chunks[maxLines - 1].length - 1))}…`;
  }
  return chunks;
}

function textBlock(text, x, y, widthChars, options = {}) {
  const size = options.size || 28;
  const color = options.color || "#203246";
  const weight = options.weight || 500;
  const lineHeight = options.lineHeight || Math.round(size * 1.45);
  const maxLines = options.maxLines || 4;
  const lines = wrapText(text, widthChars, maxLines);
  return `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${color}" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${lines
    .map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${esc(line)}</tspan>`)
    .join("")}</text>`;
}

function card(x, y, w, h, fill = "#FFFFFF", stroke = "#CFE0EE") {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`;
}

function decorBackground() {
  const lines = [];
  for (let x = 48; x < W; x += 128) {
    lines.push(`<path d="M${x} 116 L${x + 42} 116 L${x + 42} 150" stroke="#D8E8F2" stroke-width="2" fill="none" opacity="0.7"/>`);
  }
  for (let y = 150; y < 780; y += 96) {
    lines.push(`<circle cx="1500" cy="${y}" r="4" fill="#9CC8E2" opacity="0.45"/>`);
  }
  return `<defs>
    <linearGradient id="pageBg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#F7FBFD"/>
      <stop offset="0.62" stop-color="#EEF6FB"/>
      <stop offset="1" stop-color="#F9FBFD"/>
    </linearGradient>
    <linearGradient id="blueBar" x1="0" x2="1">
      <stop offset="0" stop-color="#0D477A"/>
      <stop offset="0.62" stop-color="#155F9F"/>
      <stop offset="1" stop-color="#0B3A68"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="12" stdDeviation="12" flood-color="#0B3354" flood-opacity="0.12"/>
    </filter>
    <marker id="arrowBlue" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#1E7DC1"/></marker>
  </defs>
  <rect width="${W}" height="${H}" fill="url(#pageBg)"/>
  <g opacity="0.38">${lines.join("")}</g>
  <path d="M1120 104 C1280 150 1390 230 1490 390 C1560 504 1570 660 1514 785" stroke="#D8E8F2" stroke-width="34" fill="none" opacity="0.38"/>`;
}

function icon(type, x, y, size = 38, color = "#1666A5") {
  const s = size;
  const stroke = `stroke="${color}" stroke-width="${Math.max(3, size / 12)}" stroke-linecap="round" stroke-linejoin="round" fill="none"`;
  const fill = `fill="${color}"`;
  if (type === "database") {
    return `<g transform="translate(${x} ${y})"><ellipse cx="${s / 2}" cy="${s * 0.22}" rx="${s * 0.36}" ry="${s * 0.16}" ${stroke}/><path d="M${s * 0.14} ${s * 0.22} v${s * 0.48} c0 ${s * 0.09} ${s * 0.16} ${s * 0.16} ${s * 0.36} ${s * 0.16} s${s * 0.36}-${s * 0.07} ${s * 0.36}-${s * 0.16} v-${s * 0.48}" ${stroke}/><path d="M${s * 0.14} ${s * 0.46} c0 ${s * 0.09} ${s * 0.16} ${s * 0.16} ${s * 0.36} ${s * 0.16} s${s * 0.36}-${s * 0.07} ${s * 0.36}-${s * 0.16}" ${stroke}/></g>`;
  }
  if (type === "building") {
    return `<g transform="translate(${x} ${y})"><path d="M${s * 0.16} ${s * 0.82} v-${s * 0.5} l${s * 0.28}-${s * 0.16} l${s * 0.28} ${s * 0.16} v${s * 0.5}" ${stroke}/><path d="M${s * 0.72} ${s * 0.82} v-${s * 0.38} h${s * 0.16} v${s * 0.38}" ${stroke}/><path d="M${s * 0.28} ${s * 0.44} h${s * 0.1} M${s * 0.52} ${s * 0.44} h${s * 0.1} M${s * 0.28} ${s * 0.6} h${s * 0.1} M${s * 0.52} ${s * 0.6} h${s * 0.1}" ${stroke}/></g>`;
  }
  if (type === "shield") {
    return `<g transform="translate(${x} ${y})"><path d="M${s / 2} ${s * 0.1} l${s * 0.34} ${s * 0.14} v${s * 0.28} c0 ${s * 0.22}-${s * 0.14} ${s * 0.34}-${s * 0.34} ${s * 0.45} c-${s * 0.2}-${s * 0.11}-${s * 0.34}-${s * 0.23}-${s * 0.34}-${s * 0.45} v-${s * 0.28} z" ${stroke}/><path d="M${s * 0.32} ${s * 0.47} l${s * 0.13} ${s * 0.13} l${s * 0.24}-${s * 0.27}" ${stroke}/></g>`;
  }
  if (type === "flow") {
    return `<g transform="translate(${x} ${y})"><circle cx="${s * 0.22}" cy="${s * 0.28}" r="${s * 0.13}" ${stroke}/><circle cx="${s * 0.76}" cy="${s * 0.28}" r="${s * 0.13}" ${stroke}/><circle cx="${s * 0.49}" cy="${s * 0.74}" r="${s * 0.13}" ${stroke}/><path d="M${s * 0.35} ${s * 0.28} h${s * 0.28} M${s * 0.29} ${s * 0.39} l${s * 0.13} ${s * 0.22} M${s * 0.68} ${s * 0.39} l-${s * 0.13} ${s * 0.22}" ${stroke}/></g>`;
  }
  if (type === "warning") {
    return `<g transform="translate(${x} ${y})"><path d="M${s / 2} ${s * 0.12} L${s * 0.9} ${s * 0.84} H${s * 0.1} Z" fill="#FFF1DE" stroke="${color}" stroke-width="${Math.max(3, size / 13)}"/><path d="M${s / 2} ${s * 0.34} v${s * 0.24}" ${stroke}/><circle cx="${s / 2}" cy="${s * 0.7}" r="${s * 0.035}" ${fill}/></g>`;
  }
  if (type === "screen") {
    return `<g transform="translate(${x} ${y})"><rect x="${s * 0.12}" y="${s * 0.16}" width="${s * 0.76}" height="${s * 0.5}" rx="${s * 0.06}" ${stroke}/><path d="M${s * 0.36} ${s * 0.82} h${s * 0.28} M${s * 0.5} ${s * 0.66} v${s * 0.16}" ${stroke}/></g>`;
  }
  return `<g transform="translate(${x} ${y})"><circle cx="${s / 2}" cy="${s / 2}" r="${s * 0.34}" ${stroke}/><path d="M${s * 0.32} ${s * 0.52} l${s * 0.13} ${s * 0.13} l${s * 0.25}-${s * 0.31}" ${stroke}/></g>`;
}

function iconFor(text) {
  if (/数据|台账|库|底座|沉淀|档案/.test(text)) return "database";
  if (/公寓|楼|园区|校区|宿舍|空间|A20/.test(text)) return "building";
  if (/安全|消防|报警|风险|权限|边界|防控/.test(text)) return "shield";
  if (/流程|工单|派单|联动|闭环|协同|响应|处置/.test(text)) return "flow";
  if (/大屏|看板|可视|展示|态势|监控|视频/.test(text)) return "screen";
  if (/待确认|不足|风险|问题|难|慢|弱/.test(text)) return "warning";
  return "check";
}

function pill(x, y, text, color = "#0F61A4", fill = "#E8F3FA") {
  return `<rect x="${x}" y="${y}" width="${Math.min(250, Math.max(112, clean(text).length * 21 + 34))}" height="38" rx="19" fill="${fill}" stroke="#C9DCEA"/>
  <circle cx="${x + 22}" cy="${y + 19}" r="5" fill="${color}"/>
  <text x="${x + 38}" y="${y + 25}" font-size="18" font-weight="700" fill="#23445F" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(clean(text).slice(0, 10))}</text>`;
}

function metricCard(x, y, w, label, value, accent = "#1E7DC1") {
  return `<rect x="${x}" y="${y}" width="${w}" height="88" rx="16" fill="#FFFFFF" stroke="#C9DCEA" filter="url(#shadow)"/>
    <rect x="${x}" y="${y}" width="8" height="88" rx="4" fill="${accent}"/>
    <text x="${x + 24}" y="${y + 32}" font-size="17" font-weight="700" fill="#667D90" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(label)}</text>
    ${textBlock(value, x + 24, y + 65, Math.max(8, Math.floor(w / 25)), { size: 22, weight: 900, color: "#132A40", maxLines: 1 })}`;
}

function moduleTile(x, y, w, h, title, note = "", index = 0) {
  const color = index % 3 === 0 ? "#1267B1" : index % 3 === 1 ? "#21A582" : "#E7962E";
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="16" fill="#FFFFFF" stroke="#C8DDEA" filter="url(#shadow)"/>
  <rect x="${x}" y="${y}" width="${w}" height="44" rx="16" fill="#F0F7FC"/>
  <circle cx="${x + 32}" cy="${y + 22}" r="16" fill="${color}"/>
  ${icon(iconFor(title), x + 14, y + 6, 36, "#FFFFFF")}
  ${textBlock(title, x + 62, y + 30, Math.floor((w - 80) / 22), { size: 22, weight: 900, color: "#17344D", maxLines: 1 })}
  ${textBlock(note || "按材料确认后进入细化设计", x + 24, y + 80, Math.floor((w - 48) / 19), { size: 18, weight: 600, color: "#5C7284", maxLines: 3, lineHeight: 27 })}`;
}

function confirmationPanel(x, y, w, h, brief) {
  const items = [
    brief.boundary || "材料不足处标注待客户确认",
    "现有系统、接口、设备点位、权限、报价和上线节奏必须复核",
    "不得把参考案例事实直接套入本项目",
  ];
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="18" fill="#FFF8EF" stroke="#F0C58E" stroke-width="2"/>
  ${icon("warning", x + 24, y + 22, 46, "#D87916")}
  <text x="${x + 84}" y="${y + 52}" font-size="24" font-weight="900" fill="#8B4E12" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">待确认边界</text>
  ${items
    .map((item, index) => `${textBlock(`- ${item}`, x + 34, y + 104 + index * 58, Math.floor((w - 68) / 18), { size: 18, weight: 700, color: "#654A2B", maxLines: 2, lineHeight: 26 })}`)
    .join("")}`;
}

function shell(page, brief, body) {
  const pageNo = String(page.page_no).padStart(2, "0");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  ${decorBackground()}
  <rect x="0" y="0" width="${W}" height="86" fill="url(#blueBar)"/>
  <rect x="0" y="86" width="${W}" height="4" fill="#2A9AD6"/>
  <rect x="52" y="24" width="112" height="38" rx="8" fill="#EAF5FF" opacity="0.95"/>
  <text x="70" y="51" font-size="24" font-weight="900" fill="#0B4A7E" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">敢为云</text>
  <text x="190" y="55" font-size="30" font-weight="900" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">第${pageNo}页 | ${esc(brief.title)}</text>
  <rect x="1320" y="24" width="188" height="38" rx="19" fill="#EAF5FF" opacity="0.16"/>
  <text x="1350" y="51" font-size="21" font-weight="700" fill="#D8EAF8" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(status.scenario || "方案汇报")}</text>
  ${body}
  <rect x="58" y="826" width="1375" height="30" rx="10" fill="#E8F1F8" stroke="#D3E5F0"/>
  <text x="78" y="847" font-size="17" fill="#5B7084" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">审阅提示：涉及现有系统、接口、设备点位、数据权限、上线时间、报价金额和无人装备调度权限时，必须以材料为准或标注待客户确认。</text>
  <text x="1482" y="847" font-size="18" font-weight="700" fill="#6B7D8E" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">P${pageNo}</text>
  </svg>`;
}

function richCover(page, brief) {
  const chips = [
    status.audience || "客户领导",
    status.scenario || "客户汇报",
    "方案边界待确认",
    status.page_count ? `${status.page_count}页` : "逐页审阅",
  ];
  const body = `
    <rect x="58" y="122" width="1484" height="650" rx="28" fill="#FFFFFF" stroke="#C9DDEA" stroke-width="2" filter="url(#shadow)"/>
    <rect x="98" y="162" width="552" height="470" rx="22" fill="#E9F5FE" stroke="#C8DDEA"/>
    <path d="M210 520 L210 308 L320 246 L430 308 L430 520 Z" fill="#FFFFFF" stroke="#2369A3" stroke-width="4"/>
    <path d="M438 520 L438 304 L548 246 L658 304 L658 520 Z" fill="#F7FBFF" stroke="#2A9AD6" stroke-width="4"/>
    <path d="M384 378 L428 422 L520 324" fill="none" stroke="#128260" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="150" y="660" width="450" height="46" rx="23" fill="#0F61A4"/>
    <text x="185" y="690" font-size="22" font-weight="800" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">校园安全数字底座 · 方案汇报</text>
    ${textBlock(brief.title, 730, 250, 25, { size: 46, weight: 900, color: "#10263D", maxLines: 2, lineHeight: 64 })}
    ${textBlock(brief.goal, 734, 382, 34, { size: 27, weight: 700, color: "#36546E", maxLines: 2 })}
    ${chips.map((chip, index) => pill(734 + (index % 2) * 280, 468 + Math.floor(index / 2) * 56, chip, index === 2 ? "#D87916" : "#1267B1", index === 2 ? "#FFF4E6" : "#E8F3FA")).join("")}
    ${metaChip(734, 610, "提交人", status.requester_name || "待确认")}
    ${metaChip(1028, 610, "审阅口径", "先确认事实，再生成图片")}
    <rect x="734" y="718" width="604" height="46" rx="12" fill="#0F61A4"/>
    <text x="760" y="748" font-size="23" font-weight="900" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">待确认：范围、接口、数据、报价和上线节奏</text>`;
  return shell(page, brief, body);
}

function richAgenda(page, brief, pages) {
  const items = pages.slice(2, 12);
  const list = items
    .map((item, index) => {
      const col = index % 2;
      const row = Math.floor(index / 2);
      const x = 142 + col * 675;
      const y = 242 + row * 92;
      return `<rect x="${x}" y="${y}" width="606" height="68" rx="16" fill="${index % 2 ? "#F6FAFD" : "#EAF4FC"}" stroke="#CFE0EE"/>
      <rect x="${x + 18}" y="${y + 18}" width="60" height="32" rx="16" fill="#1267B1"/>
      <text x="${x + 32}" y="${y + 40}" font-size="18" font-weight="900" fill="#FFFFFF" font-family="Arial">P${String(item.page_no).padStart(2, "0")}</text>
      ${textBlock(item.title, x + 96, y + 43, 20, { size: 23, weight: 900, maxLines: 1 })}
      <text x="${x + 450}" y="${y + 42}" font-size="17" fill="#688197" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(classifyPage(item, ""))}</text>`;
    })
    .join("");
  const body = `
    ${card(100, 132, 1400, 645, "#FFFFFF", "#C9DDEA")}
    ${textBlock("本方案按“背景与目标、总体架构、关键场景、实施路径、待确认事项”组织，先形成共识，再进入细化设计。", 144, 170, 55, { size: 28, weight: 900, color: "#22415F", maxLines: 2 })}
    ${metricCard(145, 122, 250, "汇报逻辑", "先结论后证据", "#1267B1")}
    ${metricCard(430, 122, 250, "页面状态", "逐页可审阅", "#21A582")}
    ${metricCard(715, 122, 250, "边界管理", "待确认标注", "#D87916")}
    ${list}`;
  return shell(page, brief, body);
}

function metaChip(x, y, label, value, fill = "#F0F7FC", color = "#173A59") {
  return `<rect x="${x}" y="${y}" width="260" height="72" rx="12" fill="${fill}" stroke="#D2E3EF"/>
  <text x="${x + 22}" y="${y + 28}" font-size="17" font-weight="700" fill="#5D7184" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(label)}</text>
  ${textBlock(value, x + 22, y + 57, 12, { size: 22, weight: 800, color, maxLines: 1 })}`;
}

function matrix(page, brief) {
  const items = brief.modules.slice(0, 6);
  while (items.length < 6) items.push(["业务目标", "能力边界", "客户确认", "实施路径", "数据基础", "风险控制"][items.length]);
  const cells = items
    .map((item, index) => {
      const col = index % 3;
      const row = Math.floor(index / 3);
      const x = 102 + col * 360;
      const y = 308 + row * 164;
      return `${moduleTile(x, y, 318, 124, item, index < 3 ? "问题和需求边界需先形成共识" : "进入方案能力和执行路径表达", index)}`;
    })
    .join("");
  const body = `
    ${textBlock(brief.goal, 104, 140, 44, { size: 32, weight: 900, color: "#10263D", maxLines: 2 })}
    ${textBlock(`主体图示：${brief.diagram}`, 104, 226, 44, { size: 22, weight: 700, color: "#526B80", maxLines: 1 })}
    <rect x="100" y="268" width="1028" height="382" rx="22" fill="#EAF5FC" stroke="#C9DDEA"/>
    <text x="128" y="300" font-size="22" font-weight="900" fill="#18486D" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">问题-能力-边界矩阵</text>
    ${cells}
    ${confirmationPanel(1165, 268, 310, 382, brief)}
    <rect x="100" y="686" width="1375" height="90" rx="18" fill="#FFFFFF" stroke="#C9DDEA"/>
    ${textBlock(`汇报表达：${(brief.onSlide[0] || "先讲清问题，再说明方案路径和可落地边界")}`, 132, 724, 58, { size: 24, weight: 900, color: "#17344D", maxLines: 2 })}`;
  return shell(page, brief, body);
}

function flow(page, brief) {
  const items = brief.modules.slice(0, 6);
  while (items.length < 6) items.push(["触发", "研判", "派发", "处置", "复盘", "沉淀"][items.length]);
  const nodes = items
    .map((item, index) => {
      const x = 112 + index * 232;
      const y = index % 2 === 0 ? 368 : 470;
      const arrow = index < items.length - 1 ? `<path d="M${x + 172} ${y + 48} C${x + 204} ${y + 48}, ${x + 198} ${index % 2 === 0 ? y + 100 : y - 60}, ${x + 228} ${index % 2 === 0 ? y + 100 : y - 60}" stroke="#278BD2" stroke-width="5" fill="none" marker-end="url(#arrowBlue)"/>` : "";
      return `${card(x, y, 184, 96, "#FFFFFF", "#BED8EA")}
      <circle cx="${x + 34}" cy="${y + 36}" r="22" fill="${index % 2 ? "#21A582" : "#1267B1"}"/>
      <text x="${x + 24}" y="${y + 44}" font-size="22" font-weight="900" fill="#FFFFFF" font-family="Arial">${index + 1}</text>
      ${textBlock(item, x + 68, y + 39, 7, { size: 20, weight: 900, maxLines: 2, lineHeight: 27 })}
      ${arrow}`;
    })
    .join("");
  const body = `
    ${textBlock(brief.goal, 112, 142, 52, { size: 32, weight: 900, color: "#10263D", maxLines: 2 })}
    <rect x="112" y="248" width="1366" height="82" rx="20" fill="#EAF5FC" stroke="#CFE2EF"/>
    ${icon("flow", 142, 268, 42, "#1267B1")}
    ${textBlock(`闭环主线：${brief.diagram}`, 205, 298, 50, { size: 25, weight: 900, color: "#26516F", maxLines: 1 })}
    <rect x="112" y="356" width="1366" height="246" rx="26" fill="#F7FBFE" stroke="#CFE0EE"/>
    ${nodes}
    ${moduleTile(122, 642, 310, 112, "事实摘录", brief.sourceBullets[0] || "从上传材料中抽取当前任务事实", 0)}
    ${moduleTile(456, 642, 310, 112, "协同留痕", "每个动作保留责任、时间和状态", 1)}
    ${moduleTile(790, 642, 310, 112, "复盘沉淀", "形成趋势分析和优化依据", 2)}
    ${moduleTile(1124, 642, 310, 112, "待确认项", "材料不足处不做确定性表达", 3)}`;
  return shell(page, brief, body);
}

function architecture(page, brief) {
  const layers = brief.modules.slice(0, 5);
  while (layers.length < 5) layers.push(["应用展示与工作台", "事件流程与联动", "平台能力服务", "数据治理底座", "设备接入与感知"][layers.length]);
  const layerLabel = (item, index) => {
    if (/边缘感知|消防主机|视频监控|门禁|用电|水浸/.test(item)) return "边缘感知层";
    if (/二级物联|设备管理|数据服务|接入管理/.test(item)) return "二级物联层";
    if (/应用展示|大屏|桌面端|移动端|领导视角|值班视角/.test(item)) return "应用展示层";
    if (/IOC|态势感知|事件管理|联动指挥/.test(item)) return "IOC大脑层";
    if (/数据|台账|物模型|空间/.test(item)) return "数据层";
    return ["应用层", "流程层", "平台层", "数据层", "感知层"][index];
  };
  const blocks = layers
    .map((item, index) => {
      const y = 180 + index * 96;
      const fill = index === 2 ? "#DDF0FC" : "#FFFFFF";
      const label = layerLabel(item, index);
      const fragments = splitFragments(item, 4);
      const chips = (fragments.length ? fragments : [item]).slice(0, 4).map((frag, i) => pill(522 + i * 178, y + 22, frag, index === 2 ? "#FFFFFF" : "#1267B1", index === 2 ? "#CFE9FA" : "#F0F7FC")).join("");
      return `${card(220, y, 1000, 74, fill, "#C8DDEA")}
      <rect x="220" y="${y}" width="260" height="74" rx="14" fill="${index === 2 ? "#0F61A4" : "#E8F3FA"}"/>
      ${icon(iconFor(item), 242, y + 15, 42, index === 2 ? "#FFFFFF" : "#1267B1")}
      <text x="304" y="${y + 47}" font-size="23" font-weight="900" fill="${index === 2 ? "#FFFFFF" : "#16456C"}" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(label)}</text>
      ${chips}`;
    })
    .join("");
  const body = `
    ${textBlock(brief.goal, 112, 134, 50, { size: 30, weight: 900, color: "#10263D", maxLines: 2 })}
    <rect x="174" y="164" width="1090" height="532" rx="24" fill="#F7FBFE" stroke="#7CBCE6" stroke-width="3" stroke-dasharray="10 10"/>
    <path d="M1276 210 L1276 640" stroke="#1E7DC1" stroke-width="6" marker-end="url(#arrowBlue)"/>
    ${blocks}
    <rect x="1288" y="184" width="196" height="492" rx="20" fill="#FFFFFF" stroke="#C9DDEA" filter="url(#shadow)"/>
    <text x="1322" y="226" font-size="23" font-weight="900" fill="#17344D" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">支撑机制</text>
    ${["权限边界", "数据治理", "流程留痕", "安全策略", "运营复盘"].map((item, i) => `${icon(iconFor(item), 1316, 260 + i * 72, 34, i === 1 ? "#21A582" : "#1267B1")}<text x="1362" y="${285 + i * 72}" font-size="20" font-weight="800" fill="#284B66" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${item}</text>`).join("")}
    <rect x="190" y="716" width="1060" height="74" rx="16" fill="#FFF8EF" stroke="#F0C58E" stroke-width="2"/>
    ${icon("warning", 220, 730, 40, "#D87916")}
    <text x="276" y="757" font-size="22" font-weight="900" fill="#8B4E12" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">待确认边界</text>
    <text x="422" y="757" font-size="19" font-weight="700" fill="#654A2B" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">架构层级、接口状态、控制权限和设备接入方式需由客户确认</text>`;
  return shell(page, brief, body);
}

function roadmap(page, brief) {
  const items = brief.modules.slice(0, 6);
  while (items.length < 6) items.push(["资料确认", "方案深化", "样板实施", "联调验收", "运营复盘", "推广复制"][items.length]);
  const steps = items
    .map((item, index) => {
      const x = 120 + index * 222;
      const color = index < 2 ? "#1267B1" : index < 4 ? "#21A582" : "#D87916";
      return `<circle cx="${x + 58}" cy="386" r="42" fill="${color}"/>
      <text x="${x + 41}" y="398" font-size="30" font-weight="900" fill="#FFFFFF" font-family="Arial">${index + 1}</text>
      ${index < items.length - 1 ? `<path d="M${x + 104} 386 L${x + 196} 386" stroke="#9ECBE8" stroke-width="6" marker-end="url(#arrowBlue)"/>` : ""}
      <rect x="${x}" y="470" width="166" height="118" rx="16" fill="#FFFFFF" stroke="#C9DDEA"/>
      ${textBlock(item, x + 18, 512, 7, { size: 21, weight: 900, maxLines: 3 })}`;
    })
    .join("");
  const body = `
    ${textBlock(brief.goal, 118, 142, 52, { size: 32, weight: 900, color: "#10263D", maxLines: 2 })}
    <rect x="118" y="312" width="1345" height="148" rx="28" fill="#EAF5FC" stroke="#CFE2EF"/>
    ${steps}
    ${moduleTile(132, 640, 390, 112, "交付前置", "先完成事实、边界、责任和材料版本确认", 0)}
    ${moduleTile(600, 640, 390, 112, "实施控制", "分阶段推进，避免承诺未确认接口和上线时间", 1)}
    ${moduleTile(1068, 640, 390, 112, "验收闭环", "把问题、过程、结果沉淀为后续复用资料", 2)}`;
  return shell(page, brief, body);
}

function richOverview(page, brief) {
  const left = brief.modules.slice(0, 3);
  const right = brief.modules.slice(3, 6);
  while (left.length < 3) left.push(["目标", "能力", "边界"][left.length]);
  while (right.length < 3) right.push(["路径", "待确认", "风险控制"][right.length]);
  const center = /A20|单栋|样板/.test(`${brief.title} ${brief.diagram}`) ? "A20单栋样板" : brief.diagram;
  const leftCards = left.map((item, i) => `${moduleTile(110, 250 + i * 132, 420, 106, item, brief.sourceBullets[i] || "从材料中提炼本页表达重点", i)}<path d="M530 ${303 + i * 132} L682 ${442}" stroke="#9ECBE8" stroke-width="4" fill="none"/>`).join("");
  const rightCards = right.map((item, i) => `${moduleTile(1068, 250 + i * 132, 420, 106, item, brief.sourceBullets[i + 3] || "用于支撑客户汇报的可视化表达", i + 3)}<path d="M1068 ${303 + i * 132} L918 ${442}" stroke="#9ECBE8" stroke-width="4" fill="none"/>`).join("");
  const body = `
    ${textBlock(brief.goal, 112, 138, 52, { size: 32, weight: 900, color: "#10263D", maxLines: 2 })}
    ${leftCards}
    <circle cx="800" cy="442" r="118" fill="#DDF0FC" stroke="#2A8ACB" stroke-width="6"/>
    <circle cx="800" cy="442" r="78" fill="#FFFFFF" stroke="#C9DDEA"/>
    ${icon(iconFor(center), 764, 358, 72, "#1267B1")}
    ${textBlock(center, 706, 470, 8, { size: 26, weight: 900, color: "#0F4C86", maxLines: 2 })}
    ${rightCards}`;
  return shell(page, brief, body);
}

function slideTitle(brief, x = 82, y = 132, chars = 58) {
  return textBlock(brief.goal, x, y, chars, { size: 27, weight: 900, color: "#122D46", maxLines: 2, lineHeight: 38 });
}

function titleBand(x, y, w, label, color = "#0F61A4") {
  return `<rect x="${x}" y="${y}" width="${w}" height="42" rx="10" fill="${color}"/>
  <text x="${x + 18}" y="${y + 28}" font-size="20" font-weight="900" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(label)}</text>`;
}

function smallTag(x, y, text, color = "#1267B1", w = 132) {
  return `<rect x="${x}" y="${y}" width="${w}" height="28" rx="14" fill="#EEF7FD" stroke="#BFD9EA"/>
  <circle cx="${x + 18}" cy="${y + 14}" r="5" fill="${color}"/>
  <text x="${x + 31}" y="${y + 20}" font-size="15" font-weight="800" fill="#254A64" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(clean(text).slice(0, 8))}</text>`;
}

function densePanel(x, y, w, h, title, items, options = {}) {
  const color = options.color || "#1267B1";
  const body = items.map((item) => clean(item).replace(/^[:：]+/, "")).filter(Boolean).slice(0, options.limit || 5).map((item, index) => {
    const yy = y + 76 + index * 38;
    return `<circle cx="${x + 30}" cy="${yy - 7}" r="11" fill="${index % 2 ? "#21A582" : color}"/>
      <text x="${x + 26}" y="${yy - 2}" font-size="13" font-weight="900" fill="#FFFFFF" font-family="Arial">${index + 1}</text>
      ${textBlock(item, x + 52, yy, Math.floor((w - 70) / 17), { size: 17, weight: 800, color: "#203B52", maxLines: 1 })}`;
  }).join("");
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="#FFFFFF" stroke="#C7DBE8" filter="url(#shadow)"/>
    <rect x="${x}" y="${y}" width="${w}" height="48" rx="14" fill="#EAF5FC"/>
    ${icon(iconFor(title), x + 16, y + 11, 30, color)}
    <text x="${x + 58}" y="${y + 31}" font-size="21" font-weight="900" fill="#17344D" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(title.slice(0, 16))}</text>
    ${body}`;
}

function bottomEvidence(brief, x = 82, y = 742, w = 1436) {
  const text = brief.boundary || brief.sourceBullets[0] || "材料不足处必须标注待客户确认";
  return `<rect x="${x}" y="${y}" width="${w}" height="60" rx="14" fill="#FFF8EF" stroke="#F0C58E"/>
  ${icon("warning", x + 18, y + 12, 36, "#D87916")}
  <text x="${x + 68}" y="${y + 37}" font-size="20" font-weight="900" fill="#8B4E12" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">待确认边界</text>
  ${textBlock(text, x + 206, y + 37, Math.floor((w - 230) / 17), { size: 17, weight: 700, color: "#674B2A", maxLines: 1 })}`;
}

function cover(page, brief) {
  const body = `
    <rect x="70" y="122" width="1460" height="678" rx="22" fill="#FFFFFF" stroke="#C5DBEA" filter="url(#shadow)"/>
    <rect x="106" y="164" width="520" height="438" rx="18" fill="#EAF5FC" stroke="#C0D9EA"/>
    <path d="M218 492 L218 300 L320 242 L422 300 L422 492 Z" fill="#FFFFFF" stroke="#1C68A3" stroke-width="4"/>
    <path d="M438 492 L438 296 L540 242 L642 296 L642 492 Z" fill="#F8FCFF" stroke="#2398D2" stroke-width="4"/>
    <path d="M390 372 L430 412 L524 310" fill="none" stroke="#138260" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="142" y="640" width="438" height="44" rx="10" fill="#0F61A4"/>
    <text x="176" y="669" font-size="22" font-weight="900" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">校园安消一体化 · 图片版汇报稿</text>
    ${textBlock(brief.title, 704, 242, 25, { size: 43, weight: 900, color: "#10263D", maxLines: 2, lineHeight: 60 })}
    ${textBlock(brief.goal, 708, 362, 33, { size: 25, weight: 800, color: "#36546E", maxLines: 2, lineHeight: 36 })}
    ${densePanel(704, 464, 330, 164, "汇报口径", [status.scenario || "客户汇报", status.audience || "客户领导", "逐页审阅后使用"], { limit: 3 })}
    ${densePanel(1066, 464, 330, 164, "边界提示", ["范围待确认", "接口待确认", "报价不上屏"], { color: "#D87916", limit: 3 })}
    ${titleBand(704, 684, 692, "先确认事实，再进入图片版汇报", "#0F61A4")}`;
  return shell(page, brief, body);
}

function agenda(page, brief, pages) {
  const items = pages.slice(2, 14);
  const list = items.map((item, index) => {
    const col = index % 3;
    const row = Math.floor(index / 3);
    const x = 96 + col * 474;
    const y = 238 + row * 112;
    return `<rect x="${x}" y="${y}" width="430" height="84" rx="12" fill="${row % 2 ? "#F8FBFD" : "#EAF5FC"}" stroke="#C6DDEA"/>
      <rect x="${x + 16}" y="${y + 18}" width="60" height="30" rx="15" fill="#1267B1"/>
      <text x="${x + 29}" y="${y + 39}" font-size="17" font-weight="900" fill="#FFFFFF" font-family="Arial">P${String(item.page_no).padStart(2, "0")}</text>
      ${textBlock(item.title, x + 92, y + 39, 15, { size: 19, weight: 900, color: "#17344D", maxLines: 2, lineHeight: 27 })}`;
  }).join("");
  const body = `
    ${slideTitle({ ...brief, goal: "先给客户领导建立整体路线图，再进入架构、场景、实施和待确认事项。" })}
    ${metricCard(92, 166, 300, "汇报主线", "背景-架构-场景-实施", "#1267B1")}
    ${metricCard(424, 166, 300, "审阅方式", "逐页确认事实和边界", "#21A582")}
    ${metricCard(756, 166, 300, "输出目标", "可拿去讨论的图片版 PPT", "#D87916")}
    ${list}`;
  return shell(page, brief, body);
}

function overview(page, brief) {
  const core = /A20|单栋|样板/.test(`${brief.title} ${brief.diagram}`) ? "A20单栋样板" : clean(brief.diagram).slice(0, 12) || "方案中心";
  const nodes = (brief.nodes.length ? brief.nodes : brief.modules).filter(Boolean);
  const primary = nodes.filter((item) => /可运行|可验收|可汇报|可复制|真实场景|证据链|领导|复用|样板|覆盖|标准化/.test(item)).slice(0, 4);
  while (primary.length < 4) primary.push(["可运行", "可验收", "可汇报", "可复制"][primary.length]);
  const packSeed = nodes.filter((item) => /成果包|技术|业务|管理|标准化/.test(item)).join(" ");
  const packs = /技术|业务|管理/.test(packSeed)
    ? ["技术成果包", "业务成果包", "管理成果包"]
    : nodes.filter((item) => /成果包|标准化/.test(item)).slice(0, 3);
  while (packs.length < 3) packs.push(["技术成果包", "业务成果包", "管理成果包"][packs.length]);
  const positions = [[160, 248], [1052, 248], [160, 478], [1052, 478]];
  const notes = ["真实链路跑通", "验收材料完整", "领导汇报可展示", "后续楼栋可复用"];
  const cards = primary.map((item, index) => {
    const [x, y] = positions[index];
    return `${densePanel(x, y, 350, 142, item, [notes[index], index < 2 ? "先做深做透" : "再复制推广"], { limit: 2, color: index % 2 ? "#21A582" : "#1267B1" })}
      <path d="${index % 2 ? `M1052 ${y + 70} L918 446` : `M510 ${y + 70} L682 446`}" stroke="#8EC8EA" stroke-width="4" fill="none"/>`;
  }).join("");
  const packCards = packs.map((item, index) => {
    const x = 278 + index * 350;
    return `<rect x="${x}" y="640" width="300" height="96" rx="14" fill="#FFFFFF" stroke="#BED7E8" filter="url(#shadow)"/>
      <rect x="${x}" y="640" width="300" height="36" rx="14" fill="${index === 0 ? "#0F61A4" : index === 1 ? "#21A582" : "#D87916"}"/>
      <text x="${x + 24}" y="665" font-size="19" font-weight="900" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${esc(item.slice(0, 12))}</text>
      ${textBlock(["配置模板 / 接入规范", "流程口径 / 验收清单", "复用方法 / 管理台账"][index], x + 24, 708, 13, { size: 18, weight: 800, color: "#284B66", maxLines: 1 })}`;
  }).join("");
  const body = `
    ${slideTitle(brief)}
    <circle cx="800" cy="448" r="132" fill="#DBF0FC" stroke="#1D84C7" stroke-width="6"/>
    <circle cx="800" cy="448" r="78" fill="#FFFFFF" stroke="#BED7E8"/>
    ${icon(iconFor(core), 764, 372, 72, "#1267B1")}
    ${textBlock(core, 714, 486, 8, { size: 28, weight: 900, color: "#0F4C86", maxLines: 2 })}
    ${cards}
    <rect x="238" y="616" width="1124" height="146" rx="18" fill="#F7FBFE" stroke="#C6DDEA"/>
    ${titleBand(258, 638, 230, "复制成果包", "#0F61A4")}
    ${packCards}`;
  return shell(page, brief, body);
}

function richArchitecture(page, brief) {
  let layers = [];
  const text = `${brief.diagram} ${brief.nodes.join(" ")}`;
  if (/边缘感知|二级物联|IOC|应用展示/.test(text)) {
    layers = [
      { label: "应用展示层", items: ["IOC大屏", "桌面端", "WeLink移动端", "领导视角", "值班视角"] },
      { label: "IOC大脑层", items: ["态势感知", "运行监测", "事件管理", "联动指挥", "决策支持"] },
      { label: "二级物联层", items: ["设备管理", "数据服务", "接入管理", "应用支撑", "系统管理"] },
      { label: "边缘感知层", items: ["消防主机", "视频监控", "门禁", "用电", "水浸", "动环"] },
    ];
  } else {
    const items = brief.nodes.length ? brief.nodes : brief.modules;
    layers = [
      { label: "应用层", items: items.slice(0, 5) },
      { label: "平台层", items: items.slice(2, 7) },
      { label: "数据层", items: items.slice(4, 9) },
      { label: "接入层", items: items.slice(1, 6) },
    ];
  }
  const blocks = layers.map((layer, index) => {
    const y = 220 + index * 112;
    const active = index === 1;
    const chips = layer.items.slice(0, 6).map((item, i) => {
      const x = 430 + i * 132;
      return smallTag(x, y + 34, item, active ? "#FFFFFF" : "#1267B1", 116);
    }).join("");
    return `<rect x="230" y="${y}" width="940" height="82" rx="12" fill="${active ? "#D8EEFA" : "#FFFFFF"}" stroke="#BDD7E8"/>
      <rect x="230" y="${y}" width="172" height="82" rx="12" fill="${active ? "#0F61A4" : "#E8F3FA"}"/>
      ${icon(iconFor(layer.label), 250, y + 22, 38, active ? "#FFFFFF" : "#1267B1")}
      <text x="302" y="${y + 52}" font-size="22" font-weight="900" fill="${active ? "#FFFFFF" : "#17486D"}" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${layer.label}</text>
      ${chips}`;
  }).join("");
  const body = `
    ${slideTitle(brief)}
    <rect x="182" y="190" width="1040" height="496" rx="20" fill="#F8FCFE" stroke="#69B7E3" stroke-width="3" stroke-dasharray="10 10"/>
    <text x="104" y="410" font-size="22" font-weight="900" fill="#1267B1" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif" transform="rotate(-90 104 410)">数据上行</text>
    <path d="M150 632 L150 248" stroke="#1E7DC1" stroke-width="6" marker-end="url(#arrowBlue)"/>
    <text x="1246" y="410" font-size="22" font-weight="900" fill="#D87916" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif" transform="rotate(90 1246 410)">指令下行</text>
    <path d="M1268 248 L1268 632" stroke="#D87916" stroke-width="6" marker-end="url(#arrowBlue)"/>
    ${blocks}
    ${densePanel(1268, 204, 230, 394, "支撑机制", ["权限边界", "数据治理", "流程留痕", "安全策略", "运营复盘"], { limit: 5 })}
    ${bottomEvidence(brief, 184, 710, 1114)}`;
  return shell(page, brief, body);
}

function richFlow(page, brief) {
  const items = (brief.nodes.length ? brief.nodes : brief.modules).slice(0, 6);
  while (items.length < 6) items.push(["触发", "定位", "研判", "派发", "处置", "复盘"][items.length]);
  const nodes = items.map((item, index) => {
    const x = 118 + index * 225;
    const y = index % 2 === 0 ? 340 : 466;
    return `<rect x="${x}" y="${y}" width="178" height="92" rx="12" fill="#FFFFFF" stroke="#AFCFE4" stroke-width="2"/>
      <circle cx="${x + 30}" cy="${y + 34}" r="22" fill="${index % 2 ? "#21A582" : "#1267B1"}"/>
      <text x="${x + 22}" y="${y + 42}" font-size="22" font-weight="900" fill="#FFFFFF" font-family="Arial">${index + 1}</text>
      ${textBlock(item, x + 64, y + 37, 7, { size: 18, weight: 900, color: "#17344D", maxLines: 2, lineHeight: 25 })}
      ${index < 5 ? `<path d="M${x + 178} ${y + 46} C${x + 210} ${y + 46}, ${x + 204} ${index % 2 === 0 ? 512 : 386}, ${x + 222} ${index % 2 === 0 ? 512 : 386}" stroke="#1E7DC1" stroke-width="5" fill="none" marker-end="url(#arrowBlue)"/>` : ""}`;
  }).join("");
  const body = `
    ${slideTitle(brief)}
    <rect x="92" y="218" width="1416" height="76" rx="14" fill="#EAF5FC" stroke="#BED7E8"/>
    ${icon("flow", 126, 236, 42, "#1267B1")}
    ${textBlock(`闭环主线：${brief.onSlide[0] || brief.diagram}`, 190, 264, 58, { size: 23, weight: 900, color: "#214A67", maxLines: 1 })}
    <rect x="92" y="318" width="1416" height="284" rx="20" fill="#F8FCFE" stroke="#C6DDEA"/>
    ${nodes}
    ${densePanel(112, 642, 310, 112, "事实摘录", [brief.sourceBullets[0] || "以材料事实为准", "不编造系统状态"], { limit: 2 })}
    ${densePanel(456, 642, 310, 112, "协同留痕", ["责任、时间、状态留痕", "跨部门同步"], { limit: 2, color: "#21A582" })}
    ${densePanel(800, 642, 310, 112, "复盘沉淀", ["趋势分析", "优化依据"], { limit: 2, color: "#D87916" })}
    ${densePanel(1144, 642, 310, 112, "待确认项", ["接口状态", "控制权限"], { limit: 2, color: "#D87916" })}`;
  return shell(page, brief, body);
}

function richMatrix(page, brief) {
  const items = (brief.nodes.length ? brief.nodes : brief.modules).slice(0, 8);
  while (items.length < 8) items.push(["业务目标", "能力边界", "客户确认", "实施路径", "数据基础", "风险控制", "协同机制", "复盘优化"][items.length]);
  const cells = items.slice(0, 6).map((item, index) => {
    const x = 104 + (index % 3) * 340;
    const y = 288 + Math.floor(index / 3) * 154;
    return moduleTile(x, y, 306, 114, item, index < 3 ? "当前问题和边界" : "方案能力落点", index);
  }).join("");
  const body = `
    ${slideTitle(brief)}
    <rect x="92" y="246" width="1052" height="356" rx="18" fill="#EAF5FC" stroke="#BDD7E8"/>
    ${titleBand(112, 260, 236, "问题-能力-边界矩阵", "#0F61A4")}
    ${cells}
    ${densePanel(1170, 246, 318, 356, "客户确认", [brief.boundary, "现有系统状态", "接口和权限", "报价和上线节奏"], { limit: 4, color: "#D87916" })}
    ${densePanel(104, 634, 430, 116, "上屏结论", brief.onSlide.length ? brief.onSlide : ["先讲问题", "再讲路径", "最后讲边界"], { limit: 3 })}
    ${densePanel(584, 634, 430, 116, "来源依据", brief.sourceBullets.length ? brief.sourceBullets : ["上传材料", "客户补充信息"], { limit: 3, color: "#21A582" })}
    ${densePanel(1064, 634, 430, 116, "禁止表达", ["不写已完成对接", "不写无来源金额", "不套用参考案例事实"], { limit: 3, color: "#D87916" })}`;
  return shell(page, brief, body);
}

function richCapabilityMap(page, brief) {
  const items = (brief.nodes.length ? brief.nodes : brief.modules).slice(0, 8);
  while (items.length < 8) items.push(["消防报警", "视频联动", "门禁管理", "工单闭环", "IOC展示", "数据台账", "移动通知", "复盘分析"][items.length]);
  const tiles = items.slice(0, 8).map((item, index) => {
    const x = 112 + (index % 4) * 260;
    const y = 286 + Math.floor(index / 4) * 142;
    const color = index % 3 === 0 ? "#1267B1" : index % 3 === 1 ? "#21A582" : "#D87916";
    return `<rect x="${x}" y="${y}" width="226" height="110" rx="16" fill="#FFFFFF" stroke="#C5DBEA" filter="url(#shadow)"/>
      <rect x="${x}" y="${y}" width="226" height="34" rx="16" fill="#EFF7FC"/>
      ${icon(iconFor(item), x + 16, y + 16, 40, color)}
      ${textBlock(item, x + 66, y + 48, 7, { size: 19, weight: 900, color: "#17344D", maxLines: 2, lineHeight: 25 })}
      <text x="${x + 66}" y="${y + 88}" font-size="15" font-weight="800" fill="#6B7D8E" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">能力边界待确认</text>`;
  }).join("");
  const body = `
    ${slideTitle(brief)}
    <rect x="92" y="226" width="1104" height="400" rx="22" fill="#EAF5FC" stroke="#BDD7E8"/>
    ${titleBand(112, 246, 260, "能力覆盖地图", "#0F61A4")}
    ${tiles}
    ${densePanel(1230, 226, 280, 184, "先做样板", ["A20单栋先跑通", "场景闭环可验收", "证据链可汇报"], { limit: 3, color: "#1267B1" })}
    ${densePanel(1230, 442, 280, 184, "再做推广", ["能力可复制", "标准可沉淀", "边界先确认"], { limit: 3, color: "#21A582" })}
    ${bottomEvidence(brief, 92, 674, 1418)}`;
  return shell(page, brief, body);
}

function richDashboard(page, brief) {
  const items = (brief.nodes.length ? brief.nodes : brief.modules).slice(0, 10);
  while (items.length < 10) items.push(["态势总览", "事件列表", "设备状态", "报警趋势", "视频联动", "工单进度", "值班确认", "权限审计", "热力分析", "复盘报告"][items.length]);
  const kpis = items.slice(0, 4).map((item, index) => metricCard(104 + index * 350, 202, 310, item, ["可视", "可查", "可控", "可追溯"][index], index === 0 ? "#1267B1" : index === 1 ? "#21A582" : "#D87916")).join("");
  const leftRows = items.slice(4, 8).map((item, index) => {
    const y = 380 + index * 58;
    return `<rect x="124" y="${y}" width="560" height="42" rx="10" fill="${index % 2 ? "#FFFFFF" : "#F2F8FC"}" stroke="#D3E5F0"/>
      ${icon(iconFor(item), 142, y + 8, 26, index % 2 ? "#21A582" : "#1267B1")}
      ${textBlock(item, 182, y + 28, 18, { size: 17, weight: 900, color: "#213E56", maxLines: 1 })}
      <rect x="548" y="${y + 12}" width="${70 + index * 28}" height="12" rx="6" fill="${index % 2 ? "#21A582" : "#1267B1"}" opacity="0.75"/>`;
  }).join("");
  const rightCards = items.slice(6, 10).map((item, index) => densePanel(1042, 360 + index * 88, 390, 70, item, [index % 2 ? "待确认后展示" : "来自当前材料"], { limit: 1, color: index % 2 ? "#D87916" : "#1267B1" })).join("");
  const body = `
    ${slideTitle(brief)}
    ${kpis}
    <rect x="104" y="332" width="920" height="312" rx="22" fill="#FFFFFF" stroke="#C5DBEA" filter="url(#shadow)"/>
    <rect x="104" y="332" width="920" height="54" rx="22" fill="#0F61A4"/>
    <text x="136" y="367" font-size="23" font-weight="900" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">一屏统筹视图</text>
    ${leftRows}
    <rect x="728" y="404" width="238" height="158" rx="16" fill="#EAF5FC" stroke="#BED7E8"/>
    <path d="M754 530 C800 462 846 504 894 438 C918 470 936 492 950 450" fill="none" stroke="#1267B1" stroke-width="7" stroke-linecap="round"/>
    <text x="760" y="596" font-size="18" font-weight="900" fill="#36546E" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">趋势只表达方向，不写无来源百分比</text>
    ${rightCards}
    ${bottomEvidence(brief, 104, 692, 1328)}`;
  return shell(page, brief, body);
}

function richGovernance(page, brief) {
  const items = (brief.nodes.length ? brief.nodes : brief.modules).slice(0, 9);
  while (items.length < 9) items.push(["责任主体", "权限边界", "审批口径", "接口状态", "数据范围", "安全审计", "报价口径", "上线节奏", "复盘机制"][items.length]);
  const columns = [
    { title: "客户确认", color: "#D87916", items: items.slice(0, 3) },
    { title: "方案边界", color: "#1267B1", items: items.slice(3, 6) },
    { title: "交付留痕", color: "#21A582", items: items.slice(6, 9) },
  ].map((col, index) => {
    const x = 112 + index * 482;
    const rows = col.items.map((item, row) => `<rect x="${x + 24}" y="${316 + row * 94}" width="390" height="68" rx="12" fill="#FFFFFF" stroke="#C8DDEA"/>
      <circle cx="${x + 52}" cy="${350 + row * 94}" r="15" fill="${col.color}"/>
      <text x="${x + 47}" y="${356 + row * 94}" font-size="16" font-weight="900" fill="#FFFFFF" font-family="Arial">${row + 1}</text>
      ${textBlock(item, x + 82, 356 + row * 94, 13, { size: 19, weight: 900, color: "#203B52", maxLines: 1 })}`).join("");
    return `<rect x="${x}" y="240" width="438" height="380" rx="20" fill="#F8FCFE" stroke="#C5DBEA" filter="url(#shadow)"/>
      <rect x="${x}" y="240" width="438" height="58" rx="20" fill="${col.color}"/>
      <text x="${x + 28}" y="278" font-size="24" font-weight="900" fill="#FFFFFF" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">${col.title}</text>
      ${rows}`;
  }).join("");
  const body = `
    ${slideTitle(brief)}
    ${columns}
    <rect x="112" y="668" width="1390" height="92" rx="18" fill="#FFF8EF" stroke="#F0C58E"/>
    ${icon("warning", 140, 688, 48, "#D87916")}
    <text x="206" y="718" font-size="24" font-weight="900" fill="#8B4E12" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">不可替客户下结论</text>
    ${textBlock(brief.boundary || "涉及系统、接口、点位、金额、上线时间均需待客户确认。", 418, 718, 48, { size: 20, weight: 800, color: "#674B2A", maxLines: 1 })}`;
  return shell(page, brief, body);
}

function richCollaboration(page, brief) {
  const items = (brief.nodes.length ? brief.nodes : brief.modules).slice(0, 9);
  while (items.length < 9) items.push(["值班人员", "保卫处", "后勤部门", "事件确认", "视频会商", "工单流转", "移动通知", "处置记录", "复盘台账"][items.length]);
  const actors = [
    { title: items[0], x: 120, color: "#1267B1" },
    { title: items[1], x: 620, color: "#21A582" },
    { title: items[2], x: 1120, color: "#D87916" },
  ].map((actor, index) => `<rect x="${actor.x}" y="250" width="360" height="354" rx="22" fill="#FFFFFF" stroke="#C5DBEA" filter="url(#shadow)"/>
    <rect x="${actor.x}" y="250" width="360" height="58" rx="22" fill="#EFF7FC"/>
    ${icon(iconFor(actor.title), actor.x + 26, 264, 42, actor.color)}
    ${textBlock(actor.title, actor.x + 88, 288, 12, { size: 23, weight: 900, color: "#17344D", maxLines: 1 })}
    ${densePanel(actor.x + 28, 336, 304, 176, index === 0 ? "接收与研判" : index === 1 ? "协同与处置" : "复核与沉淀", items.slice(3 + index * 2, 6 + index * 2), { limit: 3, color: actor.color })}
    <rect x="${actor.x + 28}" y="536" width="304" height="38" rx="19" fill="#EAF5FC"/>
    <text x="${actor.x + 54}" y="562" font-size="18" font-weight="900" fill="#36546E" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif">责任、时间、状态留痕</text>`).join("");
  const body = `
    ${slideTitle(brief)}
    <path d="M480 428 L620 428 M980 428 L1120 428" stroke="#8EC8EA" stroke-width="7" marker-end="url(#arrowBlue)"/>
    <circle cx="800" cy="428" r="104" fill="#DDF0FC" stroke="#1E7DC1" stroke-width="6"/>
    ${icon("screen", 756, 374, 88, "#1267B1")}
    ${textBlock("同屏研判", 744, 486, 6, { size: 27, weight: 900, color: "#0F4C86", maxLines: 1 })}
    ${actors}
    ${bottomEvidence(brief, 120, 666, 1360)}`;
  return shell(page, brief, body);
}

function richRoadmap(page, brief) {
  const items = (brief.nodes.length ? brief.nodes : brief.modules).slice(0, 6);
  while (items.length < 6) items.push(["资料确认", "方案深化", "样板实施", "联调验收", "运营复盘", "推广复制"][items.length]);
  const steps = items.map((item, index) => {
    const x = 120 + index * 225;
    const color = index < 2 ? "#1267B1" : index < 4 ? "#21A582" : "#D87916";
    return `<circle cx="${x + 54}" cy="350" r="36" fill="${color}"/>
      <text x="${x + 42}" y="362" font-size="28" font-weight="900" fill="#FFFFFF" font-family="Arial">${index + 1}</text>
      ${index < 5 ? `<path d="M${x + 92} 350 L${x + 190} 350" stroke="#9ECBE8" stroke-width="6" marker-end="url(#arrowBlue)"/>` : ""}
      <rect x="${x}" y="420" width="166" height="104" rx="12" fill="#FFFFFF" stroke="#C6DDEA"/>
      ${textBlock(item, x + 18, 458, 7, { size: 19, weight: 900, maxLines: 3, lineHeight: 26 })}`;
  }).join("");
  const body = `
    ${slideTitle(brief)}
    <rect x="92" y="294" width="1416" height="262" rx="20" fill="#EAF5FC" stroke="#BED7E8"/>
    ${steps}
    ${densePanel(112, 620, 390, 128, "交付前置", ["确认事实", "确认边界", "确认责任"], { limit: 3 })}
    ${densePanel(604, 620, 390, 128, "实施控制", ["分阶段推进", "接口待确认", "不承诺未核实周期"], { limit: 3, color: "#21A582" })}
    ${densePanel(1096, 620, 390, 128, "验收闭环", ["证据链", "复盘报告", "后续复制口径"], { limit: 3, color: "#D87916" })}`;
  return shell(page, brief, body);
}

function renderSvg(page, brief, allPages) {
  if (brief.type === "cover") return cover(page, brief);
  if (brief.type === "agenda") return agenda(page, brief, allPages);
  if (brief.type === "architecture") return richArchitecture(page, brief);
  if (brief.type === "capability") return richCapabilityMap(page, brief);
  if (brief.type === "dashboard") return richDashboard(page, brief);
  if (brief.type === "governance") return richGovernance(page, brief);
  if (brief.type === "collaboration") return richCollaboration(page, brief);
  if (brief.type === "flow") return richFlow(page, brief);
  if (brief.type === "matrix") return richMatrix(page, brief);
  if (brief.type === "roadmap") return richRoadmap(page, brief);
  return overview(page, brief);
}

const slides = [];
for (const page of pages) {
  const scriptPath = path.join(jobDir, page.script_path);
  const promptPath = path.join(jobDir, page.prompt_path);
  const script = await fs.readFile(scriptPath, "utf8");
  const prompt = await fs.readFile(promptPath, "utf8");
  const brief = getBrief(page, script, prompt);
  const svg = renderSvg(page, brief, pages);
  const outPath = path.join(assetsDir, `slide-${String(page.page_no).padStart(2, "0")}.png`);
  await sharp(Buffer.from(svg))
    .resize({ width: W, height: H, fit: "contain", background: "#F3F8FC" })
    .png()
    .toFile(outPath);
  slides.push({
    slide_no: page.page_no,
    page_id: `P${String(page.page_no).padStart(2, "0")}`,
    title: page.title,
    image_path: path.relative(imageDir, outPath).replaceAll(path.sep, "/"),
    generation_mode: "codex_formal_png_renderer",
    renderer_template: brief.type,
  });
}

const manifest = {
  project_id: status.job_id,
  title: status.title,
  requester_name: status.requester_name,
  stage: "image_ppt_generation",
  generation_mode: "codex_formal_png_renderer",
  slide_count: slides.length,
  slide_size: { width: W, height: H },
  slides,
  generated_at: new Date().toISOString(),
};

await fs.writeFile(path.join(imageDir, "formal-image-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ generated_count: slides.length, manifest: "work/02_image_ppt/formal-image-manifest.json" }));
