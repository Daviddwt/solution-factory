import fs from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

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
if (!args["job-dir"]) {
  console.error("usage: node capture_html_slides.mjs --job-dir <job_dir>");
  process.exit(2);
}

const jobDir = path.resolve(args["job-dir"]);
const imageDir = path.join(jobDir, "work", "02_image_ppt");
const htmlDir = path.join(imageDir, "codex-html");
const htmlManifestPath = path.join(htmlDir, "manifest.json");
const assetsDir = path.join(imageDir, "assets");
const formalManifestPath = path.join(imageDir, "formal-image-manifest.json");
const nodeModules = args["node-modules"] || process.env.NODE_MODULES_PATH || "";
const chromePath = args.chrome || process.env.CHROME_BIN || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const require = createRequire(import.meta.url);
const sharp = require(path.join(nodeModules, "sharp"));

await fs.mkdir(assetsDir, { recursive: true });

const manifest = JSON.parse(await fs.readFile(htmlManifestPath, "utf8"));
const slides = Array.isArray(manifest.slides) ? manifest.slides : [];
if (!slides.length) throw new Error("Codex HTML manifest has no slides.");

const captured = [];
for (const slide of slides) {
  const slideNo = Number(slide.slide_no);
  if (!Number.isInteger(slideNo) || slideNo < 1) {
    throw new Error(`Invalid slide_no in Codex HTML manifest: ${slide.slide_no}`);
  }
  const htmlPath = path.isAbsolute(slide.html_path)
    ? slide.html_path
    : path.join(jobDir, slide.html_path);
  await fs.access(htmlPath);
  const outputPath = path.join(assetsDir, `slide-${String(slideNo).padStart(2, "0")}.png`);
  const result = spawnSync(
    chromePath,
    [
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      "--force-device-scale-factor=1",
      "--window-size=1600,900",
      `--screenshot=${outputPath}`,
      pathToFileURL(htmlPath).href,
    ],
    { encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(`Chrome screenshot failed for slide ${slideNo}: ${result.stderr || result.stdout}`);
  }
  const normalized = await sharp(outputPath)
    .resize({ width: 1600, height: 900, fit: "cover", position: "center" })
    .png()
    .toBuffer();
  await fs.writeFile(outputPath, normalized);
  captured.push({
    slide_no: slideNo,
    title: slide.title || `P${String(slideNo).padStart(2, "0")}`,
    image_path: rel(jobDir, outputPath),
    html_path: rel(jobDir, htmlPath),
    generation_mode: "codex_visual_html_render",
  });
}

const formalManifest = {
  stage: "image_ppt_generation",
  generation_mode: "codex_visual_html_render",
  slide_count: captured.length,
  slides: captured.sort((a, b) => a.slide_no - b.slide_no),
  generated_at: new Date().toISOString(),
};
await fs.writeFile(formalManifestPath, `${JSON.stringify(formalManifest, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ generated_count: captured.length, manifest: rel(jobDir, formalManifestPath) }));
