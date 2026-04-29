#!/usr/bin/env node
"use strict";

/**
 * EPUB Optimizer — Node.js CLI
 *
 * Converts EPUB images to e-ink-friendly baseline JPEG, applies grayscale,
 * resizes to fit the display, handles split/rotate modes, and patches XHTML/OPF/NCX.
 *
 * Usage:
 *   node optimize.js [options] <input.epub ...>
 *   node optimize.js [options] <directory>
 *
 * Options:
 *   -o, --output <dir>       Output directory (default: ./optimized)
 *   -q, --quality <n>        JPEG quality 1-100 (default: 85)
 *       --no-grayscale       Disable grayscale conversion
 *   -n  --normalize          Enhance contrast by stretching luminance
 *   -c  --contrast <n>       Contrast multiplier (e.g., 1.2 or 1.5)
 *   -W, --max-width <n>      Max image width in px (default: 480)
 *   -H, --max-height <n>     Max image height in px (default: 800)
 *       --overlap <n>        Overlap % for splits: 5|10|15|20|25 (default: 5)
 *       --rotation <cw|ccw>  Rotation direction for H-Split (default: cw)
 *       --suffix <str>       Suffix to append before .epub (default: -optimized)
 *   -v, --verbose            Print per-image details
 *       --help               Show this help
 */

const fs = require("fs");
const path = require("path");

// ── Dependency check ────────────────────────────────────────────────────────
let JSZip, sharp;
try {
  JSZip = require("jszip");
} catch (e) {
  die("jszip not found. Run: npm install");
}
try {
  sharp = require("sharp");
} catch (e) {
  die("sharp not found. Run: npm install");
}

// ── Argument parsing ─────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
if (argv.includes("--help") || argv.includes("-h")) {
  printHelp();
  process.exit(0);
}

const settings = {
  outputDir: "./optimized",
  quality: 85,
  grayscale: true,
  normalize: false,
  contrast: null,
  maxWidth: 480,
  maxHeight: 800,
  overlapPercent: 5,
  rotation: "cw", // 'cw' | 'ccw'
  imageState: 0, // 0=none, 1=h-split, 2=v-split
  suffix: "-optimized",
  verbose: false,
};

const inputs = [];
for (let i = 0; i < argv.length; i++) {
  const arg = argv[i];
  switch (arg) {
    case "-o":
    case "--output":
      settings.outputDir = argv[++i];
      break;
    case "-q":
    case "--quality":
      settings.quality = clamp(parseInt(argv[++i]), 1, 100);
      break;
    case "--no-grayscale":
      settings.grayscale = false;
      break;
    case "-n":
    case "--normalize":
      settings.normalize = true;
      break;
    case "-c":
    case "--contrast":
      settings.contrast = parseFloat(argv[++i]);
      break;
    case "-W":
    case "--max-width":
      settings.maxWidth = parseInt(argv[++i]);
      break;
    case "-H":
    case "--max-height":
      settings.maxHeight = parseInt(argv[++i]);
      break;
    case "--overlap":
      settings.overlapPercent = parseInt(argv[++i]);
      break;
    case "--rotation":
      settings.rotation = argv[++i];
      break;
    case "--split": {
      const val = argv[++i];
      if (val === "h-split") settings.imageState = 1;
      else if (val === "v-split") settings.imageState = 2;
      else if (val === "none") settings.imageState = 0;
      else {
        console.error(`Invalid --split value: ${val} (use none, h-split, or v-split)`);
        process.exit(1);
      }
      break;
    }
    case "--suffix":
      settings.suffix = argv[++i];
      break;
    case "-v":
    case "--verbose":
      settings.verbose = true;
      break;
    default:
      if (!arg.startsWith("-")) inputs.push(arg);
      else {
        console.error(`Unknown option: ${arg}`);
        process.exit(1);
      }
  }
}

if (inputs.length === 0) {
  printHelp();
  process.exit(1);
}

// ── Resolve input files ──────────────────────────────────────────────────────
const epubFiles = [];
for (const input of inputs) {
  if (!fs.existsSync(input)) {
    console.error(`Not found: ${input}`);
    continue;
  }
  const stat = fs.statSync(input);
  if (stat.isDirectory()) {
    fs.readdirSync(input)
      .filter((f) => f.toLowerCase().endsWith(".epub"))
      .forEach((f) => epubFiles.push(path.join(input, f)));
  } else if (input.toLowerCase().endsWith(".epub")) {
    epubFiles.push(input);
  } else {
    console.error(`Skipping non-EPUB file: ${input}`);
  }
}

if (epubFiles.length === 0) {
  die("No EPUB files found.");
}

// ── Ensure output directory ──────────────────────────────────────────────────
fs.mkdirSync(settings.outputDir, { recursive: true });

// ── Main ─────────────────────────────────────────────────────────────────────
(async () => {
  console.log(`\nEPUB Optimizer`);
  console.log(
    `Settings: quality=${settings.quality}% | grayscale=${settings.grayscale} | normalize=${settings.normalize} | contrast=${settings.contrast || "none"} | ${settings.maxWidth}×${settings.maxHeight} | split=${["none", "h-split", "v-split"][settings.imageState] || "none"} | overlap=${settings.overlapPercent}% | rotation=${settings.rotation}\n`,
  );

  let succeeded = 0,
    failed = 0;

  for (const inputPath of epubFiles) {
    const baseName = path.basename(inputPath, ".epub");
    const outName = baseName + settings.suffix + ".epub";
    const outPath = path.join(settings.outputDir, outName);
    console.log(`  📖 ${path.basename(inputPath)} → ${outName}`);

    try {
      const inputBuf = fs.readFileSync(inputPath);
      const outputBuf = await optimizeEpub(inputBuf, settings);
      fs.writeFileSync(outPath, outputBuf);
      const ratio = ((1 - outputBuf.length / inputBuf.length) * 100).toFixed(1);
      const sign = ratio >= 0 ? "-" : "+";
      console.log(
        `     ✓ ${formatBytes(inputBuf.length)} → ${formatBytes(outputBuf.length)} (${sign}${Math.abs(ratio)}%)\n`,
      );
      succeeded++;
    } catch (err) {
      console.error(`     ✗ Failed: ${err.message}\n`);
      failed++;
    }
  }

  console.log(`Done: ${succeeded} succeeded, ${failed} failed`);
  console.log(`Output: ${path.resolve(settings.outputDir)}\n`);
  process.exit(failed > 0 ? 1 : 0);
})();

// ── EPUB Optimizer ────────────────────────────────────────────────────────────

async function optimizeEpub(inputBuffer, cfg) {
  const { quality, grayscale, maxWidth, maxHeight, overlapPercent, rotation, verbose } = cfg;
  const isClockwise = rotation === "cw";

  const zip = await JSZip.loadAsync(inputBuffer);
  const out = new JSZip();

  // Map non-JPEG images to their .jpg equivalent filename
  const renamed = {};
  zip.forEach((p) => {
    if (p.toLowerCase().match(/\.(png|gif|webp|bmp|jpeg)$/))
      renamed[p] = p.replace(/\.(png|gif|webp|bmp|jpeg)$/i, ".jpg");
  });

  const entries = Object.entries(zip.files);
  const splitImages = {}; // path → { origName, origDir, parts[] }
  const xhtmlFiles = {}; // path → text content
  let opfPath = null,
    opfContent = null,
    mainIdentifier = null;

  // Mimetype must be STORE (uncompressed) and first per OCF spec
  if (zip.files["mimetype"]) {
    const mt = await zip.files["mimetype"].async("nodebuffer");
    out.file("mimetype", mt, { compression: "STORE", createFolders: false });
  }

  // Pre-scan OPF to identify cover image path for targeted contrast enhancement
  let coverZipPath = null;
  for (const [fp, fo] of entries) {
    if (!fo.dir && fp.toLowerCase().endsWith(".opf")) {
      const opfText = await safeReadText(fo);
      const opfDir = fp.includes("/") ? fp.substring(0, fp.lastIndexOf("/")) : "";
      coverZipPath = extractCoverImagePath(opfText, opfDir);
      break;
    }
  }

  // ── First pass: images ───────────────────────────────────────────────────
  for (const [filePath, fileObj] of entries) {
    if (fileObj.dir || filePath === "mimetype") continue;
    const low = filePath.toLowerCase();

    if (low.match(/\.(png|gif|webp|bmp|jpg|jpeg)$/)) {
      const data = await fileObj.async("nodebuffer");
      let result;
      try {
        const imageCfg = filePath === coverZipPath ? { ...cfg, isCover: true } : cfg;
        result = await processImage(data, cfg.imageState, filePath, imageCfg);
      } catch (err) {
        if (verbose) console.log(`       ⚠ Image error ${path.basename(filePath)}: ${err.message} — using original`);
        result = {
          parts: [{ data, suffix: "", width: 0, height: 0, size: data.length }],
          meta: {
            origSize: data.length,
            wasSplit: false,
            finalSize: data.length,
          },
        };
      }

      const { parts, meta } = result;
      if (verbose) {
        if (meta.wasSplit)
          console.log(
            `       ↔ ${path.basename(filePath)} → ${parts.length} parts (${formatBytes(meta.origSize)} → ${formatBytes(meta.finalSize)})`,
          );
        else
          console.log(
            `       → ${path.basename(filePath)} ${formatBytes(meta.origSize)} → ${formatBytes(meta.finalSize)}`,
          );
      }

      const baseName = filePath.replace(/\.[^.]+$/, "");

      if (parts.length === 1 && parts[0].suffix === "") {
        const newPath = renamed[filePath] || filePath.replace(/\.[^.]+$/, ".jpg");
        out.file(newPath, parts[0].data, {
          compression: "STORE",
          createFolders: false,
        });
      } else {
        const origName = path.basename(filePath);
        const origDir = filePath.includes("/") ? filePath.substring(0, filePath.lastIndexOf("/")) : "";
        splitImages[filePath] = { origName, origDir, parts: [] };
        for (const part of parts) {
          const partName = path.basename(baseName) + part.suffix + ".jpg";
          const partPath =
            (filePath.includes("/") ? filePath.substring(0, filePath.lastIndexOf("/") + 1) : "") + partName;
          out.file(partPath, part.data, {
            compression: "STORE",
            createFolders: false,
          });
          splitImages[filePath].parts.push({
            path: partPath,
            imgName: partName,
            id: path.basename(baseName) + part.suffix,
            suffix: part.suffix,
          });
        }
      }
    } else if (low.match(/\.(xhtml|html|htm)$/)) {
      xhtmlFiles[filePath] = await safeReadText(fileObj);
    } else if (low.endsWith(".opf")) {
      opfPath = filePath;
      opfContent = await safeReadText(fileObj);
    }
  }

  // ── Second pass: XHTML ───────────────────────────────────────────────────
  for (const [xhtmlPath, content] of Object.entries(xhtmlFiles)) {
    let t = content;

    // Rename image extensions in text
    for (const [o, n] of Object.entries(renamed)) t = t.split(path.basename(o)).join(path.basename(n));

    // Fix SVG covers and SVG-wrapped images (regex-based, no DOM)
    const r = fixSvgCover(t);
    if (r.fixed) t = r.c;
    const r2 = fixSvgWrappedImages(t);
    if (r2.fixed) t = r2.c;

    // Remove width/height from <img> tags
    t = t.replace(/(<img\b[^>]*?)\s+width="[^"]*"([^>]*>)/gi, "$1$2");
    t = t.replace(/(<img\b[^>]*?)\s+height="[^"]*"([^>]*>)/gi, "$1$2");

    // Handle split image references (insert additional <img> tags after original)
    for (const [fullPath, splitInfo] of Object.entries(splitImages)) {
      const { origName, parts } = splitInfo;
      const newName = origName.replace(/\.(png|gif|webp|bmp|jpeg)$/i, ".jpg");
      if (parts.length < 2) continue;

      // Replace src of original → part1
      const imgRegex = new RegExp(
        `(<img\\b[^>]*?\\bsrc=["'])([^"']*${escapeRegex(origName)}|[^"']*${escapeRegex(newName)})(["'][^>]*>)`,
        "gi",
      );
      t = t.replace(imgRegex, (match, pre, src, post) => {
        const newSrc = src.replace(origName, parts[0].imgName).replace(newName, parts[0].imgName);
        // Build subsequent part <img> tags
        const extras = parts
          .slice(1)
          .map((p) => {
            const partSrc = src.replace(origName, p.imgName).replace(newName, p.imgName);
            return `<div><img src="${partSrc}" alt="" style="max-width:100%;height:auto"/></div>`;
          })
          .join("");
        return pre + newSrc + post + extras;
      });
    }

    // Inject defensive CSS before </head>
    if (t.includes("</head>")) {
      const DEFENSIVE_STYLE =
        '<style type="text/css">img,svg{max-width:100%;height:auto}body{overflow-wrap:break-word}table{max-width:100%;table-layout:fixed}pre,code{white-space:pre-wrap;word-wrap:break-word}*{box-sizing:border-box}</style>';
      t = t.replace("</head>", DEFENSIVE_STYLE + "</head>");
    }

    out.file(xhtmlPath, t, {
      compression: "DEFLATE",
      compressionOptions: { level: 8 },
      createFolders: false,
    });
  }

  // ── OPF identifier extraction ────────────────────────────────────────────
  if (opfContent) mainIdentifier = extractIdentifier(opfContent);

  // ── Third pass: OPF ──────────────────────────────────────────────────────
  if (opfContent) {
    let t = opfContent;
    for (const [o, n] of Object.entries(renamed)) t = t.split(path.basename(o)).join(path.basename(n));
    const opfDir = opfPath.includes("/") ? opfPath.substring(0, opfPath.lastIndexOf("/")) : "";
    t = fixOPF(t, opfDir, splitImages);
    out.file(opfPath, t, {
      compression: "DEFLATE",
      compressionOptions: { level: 8 },
      createFolders: false,
    });
  }

  // ── Copy remaining files ──────────────────────────────────────────────────
  for (const [filePath, fileObj] of entries) {
    if (fileObj.dir || filePath === "mimetype") continue;
    const low = filePath.toLowerCase();
    if (low.match(/\.(png|gif|webp|bmp|jpg|jpeg)$/) || low.match(/\.(xhtml|html|htm)$/) || low.endsWith(".opf"))
      continue;

    let data = await fileObj.async("nodebuffer");

    if (low.endsWith(".css")) {
      let t = await safeReadText(fileObj);
      for (const [o, n] of Object.entries(renamed)) t = t.split(path.basename(o)).join(path.basename(n));
      data = Buffer.from(t, "utf8");
    } else if (low.endsWith(".ncx")) {
      let t = await safeReadText(fileObj);
      for (const [o, n] of Object.entries(renamed)) t = t.split(path.basename(o)).join(path.basename(n));
      t = syncNCXIdentifier(t, mainIdentifier);
      data = Buffer.from(t, "utf8");
    }

    out.file(filePath, data, {
      compression: "DEFLATE",
      compressionOptions: { level: 8 },
      createFolders: false,
    });
  }

  return out.generateAsync({
    type: "nodebuffer",
    mimeType: "application/epub+zip",
  });
}

// ── Image Processing (via sharp) ──────────────────────────────────────────────
//
// imageState 0 = Normal (scale to fit, no rotation/split)
// imageState 1 = H-Split (scale width→maxHeight, rotate 90°, split if needed)
// imageState 2 = V-Split (scale height→maxHeight, split if needed)
// imageState 3 = Rotate & Fit (rotate 90°, then scale to fit)
//
// Controlled via --split flag (none|h-split|v-split). Defaults to none (state 0).

function applyColorFilters(s, cfg) {
  if (cfg.isCover) {
    // Grayscale first, then normalize the luma range, then gamma-darken midtones so
    // light backgrounds (e.g. teal) get visually separated from white text on e-ink.
    return s.grayscale().normalize().gamma(2.2);
  }
  if (cfg.grayscale) s = s.grayscale();
  if (cfg.normalize) s = s.normalize(); // normalize after grayscale for predictable luma stretching
  if (cfg.contrast) {
    const a = cfg.contrast;
    const b = 128 - 128 * a; // Pivot around mid-gray
    s = s.linear(a, b);
  }
  return s;
}

async function processImage(data, imageState, filePath, cfg) {
  const { quality, grayscale, maxWidth, maxHeight, overlapPercent, rotation } = cfg;
  const isClockwise = rotation === "cw";
  const origSize = data.length;

  const meta = await sharp(data).metadata();
  const origW = meta.width,
    origH = meta.height;

  async function toJpeg(sharpInstance) {
    return sharpInstance
      .flatten({ background: { r: 255, g: 255, b: 255 } })
      .jpeg({ quality, mozjpeg: false })
      .toBuffer();
  }

  if (imageState === 1) {
    // H-Split: scale width to maxHeight, rotate, split if wide
    const scaledH = Math.round(origH * (maxHeight / origW));

    // Step 1: resize so width = maxHeight
    const resized = await sharp(data)
      .flatten({ background: "#ffffff" })
      .resize(maxHeight, scaledH, { fit: "fill" })
      .toBuffer();

    // Step 2: rotate (CW = 90°, CCW = 270°)
    const rotAngle = isClockwise ? 90 : 270;
    const rotated = await sharp(resized).rotate(rotAngle, { background: "#ffffff" }).toBuffer();

    const rotMeta = await sharp(rotated).metadata();
    const rotW = rotMeta.width,
      rotH = rotMeta.height;

    if (rotW <= maxWidth) {
      // No split needed
      let s = sharp(rotated);
      s = applyColorFilters(s, cfg);
      const buf = await s.jpeg({ quality }).toBuffer();
      return {
        parts: [
          {
            data: buf,
            suffix: "",
            width: rotW,
            height: rotH,
            size: buf.length,
          },
        ],
        meta: {
          origW,
          origH,
          origSize,
          wasSplit: false,
          finalW: rotW,
          finalH: rotH,
          finalSize: buf.length,
        },
      };
    }
    return splitBuffer(rotated, rotW, rotH, origW, origH, origSize, isClockwise, cfg);
  }

  if (imageState === 2) {
    // V-Split: scale height to maxHeight, split if wide
    const scaledW = Math.round(origW * (maxHeight / origH));

    const scaled = await sharp(data)
      .flatten({ background: "#ffffff" })
      .resize(scaledW, maxHeight, { fit: "fill" })
      .toBuffer();

    const scaledMeta = await sharp(scaled).metadata();
    const sW = scaledMeta.width,
      sH = scaledMeta.height;

    if (sW <= maxWidth) {
      let s = sharp(scaled);
      s = applyColorFilters(s, cfg);
      const buf = await s.jpeg({ quality }).toBuffer();
      return {
        parts: [{ data: buf, suffix: "", width: sW, height: sH, size: buf.length }],
        meta: {
          origW,
          origH,
          origSize,
          wasSplit: false,
          finalW: sW,
          finalH: sH,
          finalSize: buf.length,
        },
      };
    }
    return splitBuffer(scaled, sW, sH, origW, origH, origSize, false, cfg);
  }

  if (imageState === 3) {
    // Rotate & Fit: rotate 90°, scale to fit display
    const rotAngle = isClockwise ? 90 : 270;
    const rotated = await sharp(data)
      .flatten({ background: "#ffffff" })
      .rotate(rotAngle, { background: "#ffffff" })
      .toBuffer();

    const rotMeta = await sharp(rotated).metadata();
    const rotW = rotMeta.width,
      rotH = rotMeta.height;

    let s = sharp(rotated);
    if (rotW > maxWidth || rotH > maxHeight) s = s.resize(maxWidth, maxHeight, { fit: "inside" });
    s = applyColorFilters(s, cfg);
    const buf = await s.jpeg({ quality }).toBuffer();
    const finalMeta = await sharp(buf).metadata();
    return {
      parts: [
        {
          data: buf,
          suffix: "",
          width: finalMeta.width,
          height: finalMeta.height,
          size: buf.length,
        },
      ],
      meta: {
        origW,
        origH,
        origSize,
        wasSplit: false,
        finalW: finalMeta.width,
        finalH: finalMeta.height,
        finalSize: buf.length,
      },
    };
  }

  // State 0: Normal — scale to fit, convert to JPEG, optional grayscale
  let s = sharp(data).flatten({ background: "#ffffff" });
  if (origW > maxWidth || origH > maxHeight) s = s.resize(maxWidth, maxHeight, { fit: "inside" });
  s = applyColorFilters(s, cfg);
  const buf = await s.jpeg({ quality }).toBuffer();
  const finalMeta = await sharp(buf).metadata();
  return {
    parts: [
      {
        data: buf,
        suffix: "",
        width: finalMeta.width,
        height: finalMeta.height,
        size: buf.length,
      },
    ],
    meta: {
      origW,
      origH,
      origSize,
      wasSplit: false,
      finalW: finalMeta.width,
      finalH: finalMeta.height,
      finalSize: buf.length,
    },
  };
}

async function splitBuffer(inputBuf, cW, cH, origW, origH, origSize, isClockwise, cfg) {
  const { quality, grayscale, maxWidth, overlapPercent } = cfg;
  const minOverlapPx = Math.round(maxWidth * (overlapPercent / 100));
  const maxStep = maxWidth - minOverlapPx;
  let numParts = Math.ceil((cW - minOverlapPx) / maxStep);
  if (numParts < 2) numParts = 2;
  let step = Math.round((cW - maxWidth) / (numParts - 1));
  let overlapPx = maxWidth - step;
  if (overlapPx < minOverlapPx) {
    overlapPx = minOverlapPx;
    step = maxWidth - overlapPx;
  }

  const positions = [];
  for (let i = 0; i < numParts; i++) {
    let x = isClockwise ? cW - maxWidth - i * step : i * step;
    x = Math.max(0, Math.min(x, cW - maxWidth));
    positions.push(x);
  }
  if (isClockwise) {
    positions[0] = cW - maxWidth;
    positions[numParts - 1] = 0;
  } else {
    positions[0] = 0;
    positions[numParts - 1] = cW - maxWidth;
  }

  const parts = [];
  for (let i = 0; i < numParts; i++) {
    const x = positions[i];
    let s = sharp(inputBuf).extract({
      left: x,
      top: 0,
      width: maxWidth,
      height: cH,
    });
    s = applyColorFilters(s, cfg);
    const buf = await s.jpeg({ quality }).toBuffer();
    parts.push({
      data: buf,
      suffix: `_part${i + 1}`,
      width: maxWidth,
      height: cH,
      size: buf.length,
    });
  }

  const totalSize = parts.reduce((sum, p) => sum + p.size, 0);
  return {
    parts,
    meta: {
      origW,
      origH,
      origSize,
      wasSplit: true,
      splitCount: numParts,
      finalW: maxWidth,
      finalH: cH,
      finalSize: totalSize,
    },
  };
}

// ── EPUB Text Utilities ───────────────────────────────────────────────────────

async function safeReadText(fileObj) {
  const raw = await fileObj.async("nodebuffer");
  let offset = 0;
  if (raw.length >= 3 && raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf) offset = 3;
  try {
    return raw.subarray(offset).toString("utf8");
  } catch (e) {}
  return raw.subarray(offset).toString("latin1");
}

function xmlEscape(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function decodeHref(href) {
  try {
    return decodeURIComponent(href);
  } catch (e) {
    return href;
  }
}

function extractIdentifier(opfContent) {
  // Regex-only (no DOM parser needed in CLI)
  let mainIdentifier = null;
  const uniqueIdMatch = opfContent.match(/<(?:\w+:)?package[^>]*unique-identifier=["']([^"']+)["']/i);
  if (uniqueIdMatch) {
    const idRegex = new RegExp(`<dc:identifier[^>]*id=["']${uniqueIdMatch[1]}["'][^>]*>([^<]+)</dc:identifier>`, "i");
    const idMatch = opfContent.match(idRegex);
    if (idMatch) mainIdentifier = idMatch[1].trim();
  }
  if (!mainIdentifier) {
    const firstIdMatch = opfContent.match(/<dc:identifier[^>]*>([^<]+)</i);
    if (firstIdMatch) mainIdentifier = firstIdMatch[1].trim();
  }
  return mainIdentifier;
}

function syncNCXIdentifier(ncxText, mainIdentifier) {
  if (!mainIdentifier) return ncxText;
  return ncxText.replace(
    /<meta\s+name=["']dtb:uid["']\s+content=["'][^"']*["']\s*\/?>/gi,
    `<meta name="dtb:uid" content="${xmlEscape(mainIdentifier)}"/>`,
  );
}

function fixOPF(opfText, opfDir, splitImages = {}) {
  let t = opfText;

  // Fix wrong media-types for renamed images
  t = t.replace(
    /(<(?:\w+:)?item\b[^>]*href="[^"]+\.jpg"[^>]*)media-type="image\/(png|gif|webp|bmp)"/g,
    '$1media-type="image/jpeg"',
  );
  t = t.replace(
    /(<(?:\w+:)?item\b[^>]*)media-type="image\/(png|gif|webp|bmp)"([^>]*href="[^"]+\.jpg")/g,
    '$1media-type="image/jpeg"$3',
  );

  // Remove svg from properties
  t = t.replace(/(\bproperties="[^"]*)\bsvg\b([^"]*")/g, (m, pre, post) => {
    const cleaned = (pre + post)
      .replace(/\bsvg\b\s*/g, "")
      .replace(/\s+"/, '"')
      .replace(/"(\s+)"/, '""');
    return cleaned;
  });
  t = t.replace(/ properties="\s*"/g, "");

  // Handle split images: update original href → part1 href, add manifest entries for extra parts
  for (const [splitKey, splitInfo] of Object.entries(splitImages)) {
    const parts = splitInfo.parts || splitInfo;
    let origHref = opfDir && splitKey.startsWith(opfDir + "/") ? splitKey.substring(opfDir.length + 1) : splitKey;
    const origHrefJpg = origHref.replace(/\.(png|gif|webp|bmp|jpeg)$/i, ".jpg");
    const part1Href = origHrefJpg.replace(/\.jpg$/i, "_part1.jpg");
    const origImgRegex = new RegExp(`(href=["'])(${escapeRegex(origHref)}|${escapeRegex(origHrefJpg)})(["'])`, "gi");
    t = t.replace(origImgRegex, `$1${part1Href}$3`);
    let adds = "";
    for (let j = 1; j < parts.length; j++) {
      const p = parts[j];
      const href = opfDir && p.path.startsWith(opfDir + "/") ? p.path.substring(opfDir.length + 1) : p.path;
      adds += `<item id="img-${xmlEscape(p.id)}" href="${xmlEscape(href)}" media-type="image/jpeg"/>\n`;
    }
    if (adds && t.includes("</manifest>")) t = t.replace("</manifest>", adds + "</manifest>");
  }

  // Ensure cover meta tag
  const cm = ensureCoverMetaRegex(t);
  if (cm.fixed) t = cm.o;

  return t;
}

function extractCoverImagePath(opfText, opfDir) {
  let coverId = null,
    m;
  if ((m = opfText.match(/<(?:\w+:)?meta\s+name=["']cover["']\s+content=["']([^"']+)["']/i))) coverId = m[1];
  if (!coverId && (m = opfText.match(/<(?:\w+:)?meta\s+content=["']([^"']+)["']\s+name=["']cover["']/i)))
    coverId = m[1];
  if (
    !coverId &&
    (m = opfText.match(/<(?:\w+:)?item\b[^>]+id=["']([^"']+)["'][^>]+properties="[^"]*cover-image[^"]*"/i))
  )
    coverId = m[1];
  if (
    !coverId &&
    (m = opfText.match(/<(?:\w+:)?item\b[^>]+properties="[^"]*cover-image[^"]*"[^>]+id=["']([^"']+)["']/i))
  )
    coverId = m[1];
  if (!coverId && (m = opfText.match(/<(?:\w+:)?item\b[^>]*id=["']([^"']*cover[^"']*)["'][^>]*media-type="image\//i)))
    coverId = m[1];
  if (!coverId) return null;

  const eid = escapeRegex(coverId);
  const hm =
    opfText.match(new RegExp(`<(?:\\w+:)?item\\b[^>]+id=["']${eid}["'][^>]+href=["']([^"']+)["']`, "i")) ||
    opfText.match(new RegExp(`<(?:\\w+:)?item\\b[^>]+href=["']([^"']+)["'][^>]+id=["']${eid}["']`, "i"));
  if (!hm) return null;

  const href = decodeHref(hm[1]);
  return opfDir ? `${opfDir}/${href}` : href;
}

function ensureCoverMetaRegex(o) {
  let coverId = null,
    m;
  if (!coverId && (m = o.match(/<\w+:?item[^>]+id="([^"]+)"[^>]+properties="[^"]*cover-image[^"]*"/i))) coverId = m[1];
  if (!coverId && (m = o.match(/<\w+:?item[^>]+properties="[^"]*cover-image[^"]*"[^>]+id="([^"]+)"/i))) coverId = m[1];
  if (!coverId && (m = o.match(/<\w+:?item[^>]*id="([^"]+)"[^>]*href="[^"]*cover[^"]*"[^>]*media-type="image\//i)))
    coverId = m[1];
  if (!coverId && (m = o.match(/<\w+:?item[^>]*href="[^"]*cover[^"]*"[^>]*id="([^"]+)"[^>]*media-type="image\//i)))
    coverId = m[1];
  if (!coverId && (m = o.match(/<\w+:?item[^>]*id="([^"]*cover[^"]*)"[^>]*media-type="image\//i))) coverId = m[1];
  if (!coverId) return { o, fixed: false };
  const metaMatch = o.match(/<\w+:?meta\s+name=["']cover["']\s+content=["']([^"']+)["']/i);
  if (metaMatch) {
    if (metaMatch[1] === coverId) return { o, fixed: false };
    o = o.replace(
      /<\w+:?meta\s+name=["']cover["']\s+content=["'][^"']+["']\s*\/?>/gi,
      `<meta name="cover" content="${xmlEscape(coverId)}" />`,
    );
    return { o, fixed: true };
  }
  const idx = o.indexOf("</metadata>");
  if (idx !== -1)
    return {
      o:
        o.substring(0, idx) +
        `    <meta name="cover" content="${xmlEscape(coverId)}"/>\n  </metadata>` +
        o.substring(idx + 11),
      fixed: true,
    };
  return { o, fixed: false };
}

function fixSvgCover(content) {
  const hasSvg = content.includes("<svg") || content.includes("<svg:");
  if (!hasSvg || !content.includes("xlink:href")) return { c: content, fixed: false };
  if (
    !content.includes("calibre:cover") &&
    !content.includes('name="cover"') &&
    !content.includes("<title>Cover</title>")
  )
    return { c: content, fixed: false };
  const m = content.match(/xlink:href=["']([^"']+)["']/);
  if (!m) return { c: content, fixed: false };
  return {
    fixed: true,
    c: `<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
<head><meta content="text/html; charset=UTF-8" http-equiv="default-style"/><title>Cover</title></head>
<body><section epub:type="cover"><img style="max-width:100%;height:auto" alt="Cover" src="${m[1]}"/></section></body>
</html>`,
  };
}

function fixSvgWrappedImages(content) {
  const hasSvg = content.includes("<svg") || content.includes("<svg:");
  if (!hasSvg || !content.includes("xlink:href")) return { c: content, fixed: false, count: 0 };
  let fixedCount = 0;
  const result = content.replace(
    /<(?:svg:)?svg\b[^>]*>[\s\S]*?<(?:svg:)?image\b[^>]*xlink:href=["']([^"']+)["'][^>]*\/?>\s*<\/(?:svg:)?svg>/gi,
    (_, href) => {
      fixedCount++;
      return `<img style="max-width:100%;height:auto" src="${href}" alt=""/>`;
    },
  );
  return { c: result, fixed: fixedCount > 0, count: fixedCount };
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function formatBytes(b) {
  if (!b) return "0 B";
  const k = 1024,
    s = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(b) / Math.log(k));
  return (b / Math.pow(k, i)).toFixed(1) + " " + s[i];
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function die(msg) {
  console.error(`\nError: ${msg}\n`);
  process.exit(1);
}

function printHelp() {
  console.log(`
EPUB Optimizer — CLI

Usage:
  node optimize.js [options] <input.epub ...>
  node optimize.js [options] <directory>

Options:
  -o, --output <dir>       Output directory           (default: ./optimized)
  -q, --quality <n>        JPEG quality 1-100         (default: 85)
      --no-grayscale       Disable grayscale
  -n, --normalize          Enhance contrast by stretching luminance
      --contrast <n>       Contrast multiplier (e.g., 1.2 or 1.5)
  -W, --max-width <n>      Max image width px         (default: 480)
  -H, --max-height <n>     Max image height px        (default: 800)
      --split <mode>       Split mode: none, h-split, v-split (default: none)
      --overlap <n>        Overlap % for image splits (default: 5)
      --rotation <cw|ccw>  Rotation for H-Split mode  (default: cw)
      --suffix <str>       Output filename suffix     (default: -optimized)
  -v, --verbose            Per-image details
      --help               Show this help

Examples:
  node optimize.js mybook.epub
  node optimize.js *.epub -o ~/calibre-library/optimized/
  node optimize.js ~/downloads/ -o ~/calibre-library/ --normalize --contrast 1.2
  node optimize.js book.epub -o . --suffix ""
`);
}
