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

function rel(from, to) {
  return path.relative(from, to).replaceAll(path.sep, "/");
}

const args = parseArgs(process.argv);
if (!args.workspace) {
  console.error("usage: node assemble_image_deck.mjs --workspace <dir>");
  process.exit(2);
}

const workspace = path.resolve(args.workspace);
const manifestPath = path.join(workspace, "manifest.json");
const qaDir = path.join(workspace, "qa");
const outputDir = path.join(workspace, "output");
const nodeModules = args["node-modules"] || process.env.NODE_MODULES_PATH || "";
const require = createRequire(import.meta.url);
const sharp = require(path.join(nodeModules, "sharp"));
const PptxGenJS = require(path.join(nodeModules, "pptxgenjs"));

const W = 1600;
const H = 900;
const PPT_W = 13.333;
const PPT_H = 7.5;

await fs.mkdir(qaDir, { recursive: true });
await fs.mkdir(outputDir, { recursive: true });

const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
const finalPptx = path.isAbsolute(manifest.output_pptx)
  ? manifest.output_pptx
  : path.join(workspace, manifest.output_pptx || "output/image-draft.pptx");
const imageRecords = [];

for (const slide of manifest.slides) {
  const imagePath = path.isAbsolute(slide.image_path) ? slide.image_path : path.join(workspace, slide.image_path);
  await fs.access(imagePath);
  const originalMeta = await sharp(imagePath).metadata();
  const normalized = await sharp(imagePath)
    .resize({ width: W, height: H, fit: "contain", background: "#F4F8FB" })
    .png()
    .toBuffer();
  await fs.writeFile(imagePath, normalized);
  const finalMeta = await sharp(imagePath).metadata();
  imageRecords.push({
    page_id: slide.page_id,
    slide_no: slide.slide_no,
    title: slide.title,
    image_path: rel(workspace, imagePath),
    original_width: originalMeta.width,
    original_height: originalMeta.height,
    width: finalMeta.width,
    height: finalMeta.height,
  });
}

const thumbW = 320;
const thumbH = 180;
const labelH = 40;
const cols = Math.min(4, Math.max(1, imageRecords.length));
const rows = Math.ceil(imageRecords.length / cols);
const composites = [];

for (let i = 0; i < imageRecords.length; i += 1) {
  const rec = imageRecords[i];
  const left = (i % cols) * thumbW;
  const top = Math.floor(i / cols) * (thumbH + labelH);
  const thumb = await sharp(path.join(workspace, rec.image_path))
    .resize({ width: thumbW, height: thumbH, fit: "cover" })
    .png()
    .toBuffer();
  const label = String(rec.title || "").replace(/[<&>]/g, "").slice(0, 18);
  const labelSvg = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${thumbW}" height="${labelH}">
    <rect width="${thumbW}" height="${labelH}" fill="#EAF2F8"/>
    <text x="10" y="25" font-family="PingFang SC, Microsoft YaHei, Arial, sans-serif" font-size="15" fill="#153F73">P${String(rec.slide_no || i + 1).padStart(2, "0")} ${label}</text>
  </svg>`);
  composites.push({ input: thumb, left, top });
  composites.push({ input: labelSvg, left, top: top + thumbH });
}

const contactSheetPath = path.join(qaDir, "contact-sheet.png");
await sharp({
  create: {
    width: cols * thumbW,
    height: rows * (thumbH + labelH),
    channels: 3,
    background: "#F4F8FB",
  },
})
  .composite(composites)
  .png()
  .toFile(contactSheetPath);

const pptx = new PptxGenJS();
pptx.author = "解决方案部 AI PPT 生产线";
pptx.company = "解决方案部";
pptx.subject = "图片版 PPT 草稿";
pptx.title = manifest.title || manifest.project_id || "图片版 PPT 草稿";
pptx.lang = "zh-CN";
pptx.defineLayout({ name: "CUSTOM_16_9", width: PPT_W, height: PPT_H });
pptx.layout = "CUSTOM_16_9";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};

for (const rec of imageRecords) {
  const slide = pptx.addSlide();
  slide.background = { color: "FFFFFF" };
  slide.addImage({
    path: path.join(workspace, rec.image_path),
    x: 0,
    y: 0,
    w: PPT_W,
    h: PPT_H,
  });
}

await pptx.writeFile({ fileName: finalPptx });

manifest.output_pptx = rel(workspace, finalPptx);
manifest.qa = {
  contact_sheet: rel(workspace, contactSheetPath),
  slide_size: { width: W, height: H },
  image_records: imageRecords,
};
manifest.assembled_at = new Date().toISOString();
await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

console.log(JSON.stringify({ output_pptx: manifest.output_pptx, contact_sheet: manifest.qa.contact_sheet }));
