import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = "/Users/oyster/Desktop/学习资料/项目/P03_服创/17届A15/FTP/FT_LightRAG_Flyfish-main";
const BUILD = path.join(ROOT, ".codex-build", "nexent-architecture");
const OUT = path.join(ROOT, "output");
const FONT = "PingFang SC";
const W = 1280;
const H = 720;

const C = {
  bg: "#F4F6FB",
  navy: "#27345C",
  text: "#26324A",
  muted: "#64748B",
  line: "#B7C2D3",
  blue: "#5B7CFA",
  blueSoft: "#E8EDFF",
  teal: "#1E9A9A",
  tealSoft: "#E1F5F3",
  purple: "#7E64C5",
  purpleSoft: "#F0EAFF",
  orange: "#C47A22",
  orangeSoft: "#FFF0D7",
  green: "#2F8F5B",
  greenSoft: "#E4F5EA",
  white: "#FFFFFF",
};

function addText(slide, text, position, style = {}, opts = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name: opts.name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize: style.fontSize ?? 18,
    color: style.color ?? C.text,
    bold: style.bold ?? false,
    fontFamily: FONT,
    ...style,
  };
  shape.text.alignment = style.alignment ?? opts.align ?? "left";
  shape.text.verticalAlignment = style.verticalAlignment ?? "middle";
  shape.text.insets = style.insets ?? { left: 0, right: 0, top: 0, bottom: 0 };
  return shape;
}

function box(slide, text, position, fill, line = fill, style = {}, opts = {}) {
  const shape = slide.shapes.add({
    geometry: opts.geometry ?? "roundRect",
    name: opts.name,
    position,
    fill,
    line: { style: "solid", fill: line, width: opts.lineWidth ?? 1.2 },
    borderRadius: opts.radius ?? 14,
  });
  shape.text = text;
  shape.text.style = {
    fontSize: style.fontSize ?? 16,
    color: style.color ?? C.text,
    bold: style.bold ?? false,
    fontFamily: FONT,
    alignment: style.alignment ?? "center",
    ...style,
  };
  shape.text.alignment = style.alignment ?? "center";
  shape.text.verticalAlignment = style.verticalAlignment ?? "middle";
  shape.text.insets = style.insets ?? { left: 10, right: 10, top: 6, bottom: 6 };
  return shape;
}

function line(slide, x1, y1, x2, y2, color = C.line, width = 1.5, dashed = false) {
  const left = Math.min(x1, x2);
  const top = Math.min(y1, y2);
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);
  return slide.shapes.add({
    geometry: "connector",
    kind: "straight",
    position: { left, top, width: Math.max(w, 0.01), height: h },
    line: { style: dashed ? "dashed" : "solid", fill: color, width },
  });
}

function arrow(slide, from, to, color = C.line, kind = "straight", opts = {}) {
  return slide.shapes.connect(from, to, {
    kind,
    fromSide: opts.fromSide ?? "right",
    toSide: opts.toSide ?? "left",
    line: { style: opts.dashed ? "dashed" : "solid", fill: color, width: opts.width ?? 2 },
    tail: { type: "triangle", width: "sm", length: "sm" },
  });
}

function titleBlock(slide, title, subtitle, page) {
  addText(slide, title, { left: 56, top: 32, width: 850, height: 38 }, { fontSize: 28, bold: true, color: C.navy });
  addText(slide, subtitle, { left: 58, top: 75, width: 900, height: 25 }, { fontSize: 15, color: C.muted });
  addText(slide, page, { left: 1180, top: 42, width: 44, height: 20 }, { fontSize: 13, color: C.muted, alignment: "right" });
  line(slide, 56, 112, 1224, 112, "#D6DDE8", 1);
}

function addLayerLabel(slide, text, x, y, w, color) {
  addText(slide, text, { left: x, top: y, width: w, height: 24 }, { fontSize: 13, bold: true, color, alignment: "left" });
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

const presentation = Presentation.create({ slideSize: { width: W, height: H } });
presentation.view.hideGridlines();

// Slide 1: horizontal architecture
{
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  titleBlock(slide, "Nexent × LightRAG 故障树系统架构", "以 Agent 编排串起知识检索、故障树生成与专家审核", "01");

  addLayerLabel(slide, "输入", 56, 142, 110, C.muted);
  addLayerLabel(slide, "智能体编排", 206, 142, 300, C.blue);
  addLayerLabel(slide, "工具接口", 522, 142, 80, C.purple);
  addLayerLabel(slide, "领域服务", 620, 142, 270, C.teal);
  addLayerLabel(slide, "知识与业务数据", 912, 142, 220, C.orange);
  addLayerLabel(slide, "输出", 1150, 142, 100, C.green);

  const input = box(slide, "设备文档\n+ 顶事件", { left: 56, top: 214, width: 122, height: 130 }, C.white, "#CBD5E1", { fontSize: 20, bold: true, color: C.navy });

  const nexent = slide.shapes.add({
    geometry: "roundRect",
    name: "nexent-layer",
    position: { left: 206, top: 184, width: 294, height: 194 },
    fill: C.blueSoft,
    line: { style: "solid", fill: "#B8C6FF", width: 1.5 },
    borderRadius: 18,
  });
  addText(slide, "Nexent Agent 编排层", { left: 222, top: 198, width: 260, height: 28 }, { fontSize: 20, bold: true, color: C.blue, alignment: "center" });
  const agent1 = box(slide, "文档分析", { left: 222, top: 240, width: 116, height: 42 }, C.white, "#C8D3FF", { fontSize: 14, bold: true, color: C.blue });
  const agent2 = box(slide, "检索 / 抽取", { left: 350, top: 240, width: 134, height: 42 }, C.white, "#C8D3FF", { fontSize: 14, bold: true, color: C.blue });
  const agent3 = box(slide, "校验 / 修复", { left: 222, top: 294, width: 116, height: 42 }, C.white, "#C8D3FF", { fontSize: 14, bold: true, color: C.blue });
  const agent4 = box(slide, "生成 / 审核", { left: 350, top: 294, width: 134, height: 42 }, C.white, "#C8D3FF", { fontSize: 14, bold: true, color: C.blue });
  line(slide, 338, 261, 350, 261, C.blue, 1.5);
  line(slide, 280, 282, 280, 294, C.blue, 1.5);
  line(slide, 412, 282, 412, 294, C.blue, 1.5);
  addText(slide, "低置信度返工 · 专家确认 · 评测迭代", { left: 222, top: 348, width: 260, height: 20 }, { fontSize: 12, color: C.muted, alignment: "center" });

  const gateway = box(slide, "MCP\n/ API", { left: 522, top: 235, width: 74, height: 92 }, C.purpleSoft, "#CBBDF0", { fontSize: 17, bold: true, color: C.purple });

  const service = slide.shapes.add({
    geometry: "roundRect",
    name: "service-layer",
    position: { left: 620, top: 184, width: 270, height: 194 },
    fill: C.tealSoft,
    line: { style: "solid", fill: "#A6DED8", width: 1.5 },
    borderRadius: 18,
  });
  addText(slide, "LightRAG + 故障树服务", { left: 636, top: 198, width: 238, height: 28 }, { fontSize: 19, bold: true, color: C.teal, alignment: "center" });
  const s1 = box(slide, "解析 / 分块", { left: 636, top: 240, width: 110, height: 42 }, C.white, "#B4E3DF", { fontSize: 13, bold: true, color: C.teal });
  const s2 = box(slide, "混合检索", { left: 760, top: 240, width: 110, height: 42 }, C.white, "#B4E3DF", { fontSize: 13, bold: true, color: C.teal });
  const s3 = box(slide, "事件 / 关系抽取", { left: 636, top: 294, width: 110, height: 42 }, C.white, "#B4E3DF", { fontSize: 13, bold: true, color: C.teal });
  const s4 = box(slide, "投影 / 规则校验", { left: 760, top: 294, width: 110, height: 42 }, C.white, "#B4E3DF", { fontSize: 13, bold: true, color: C.teal });
  line(slide, 746, 261, 760, 261, C.teal, 1.5);
  line(slide, 691, 282, 691, 294, C.teal, 1.5);
  line(slide, 815, 282, 815, 294, C.teal, 1.5);
  addText(slide, "保留现有 LightRAG 内核，补足领域服务边界", { left: 636, top: 348, width: 238, height: 20 }, { fontSize: 12, color: C.muted, alignment: "center" });

  const docStore = box(slide, "原始文档\n对象存储", { left: 912, top: 198, width: 100, height: 68 }, C.orangeSoft, "#F0C989", { fontSize: 13, bold: true, color: C.orange });
  const vecStore = box(slide, "向量索引\n语义检索", { left: 1022, top: 198, width: 100, height: 68 }, C.orangeSoft, "#F0C989", { fontSize: 13, bold: true, color: C.orange });
  const graphStore = box(slide, "知识图谱\n事件 / 因果", { left: 912, top: 286, width: 100, height: 68 }, C.orangeSoft, "#F0C989", { fontSize: 13, bold: true, color: C.orange });
  const dbStore = box(slide, "业务数据库\n草稿 / 版本 / 审核", { left: 1022, top: 286, width: 100, height: 68 }, C.orangeSoft, "#F0C989", { fontSize: 12, bold: true, color: C.orange });

  const output = box(slide, "故障树\n草稿", { left: 1150, top: 214, width: 80, height: 58 }, C.greenSoft, "#AEDCC0", { fontSize: 16, bold: true, color: C.green });
  const evidence = box(slide, "证据链\n+ 校验结果", { left: 1150, top: 284, width: 80, height: 58 }, C.greenSoft, "#AEDCC0", { fontSize: 14, bold: true, color: C.green });

  arrow(slide, input, nexent, C.line, "straight", { fromSide: "right", toSide: "left" });
  arrow(slide, nexent, gateway, C.purple, "straight", { fromSide: "right", toSide: "left" });
  arrow(slide, gateway, service, C.purple, "straight", { fromSide: "right", toSide: "left" });
  arrow(slide, service, docStore, C.orange, "elbow", { fromSide: "right", toSide: "left" });
  arrow(slide, service, vecStore, C.orange, "elbow", { fromSide: "right", toSide: "left" });
  arrow(slide, service, graphStore, C.orange, "elbow", { fromSide: "right", toSide: "left" });
  arrow(slide, service, dbStore, C.orange, "elbow", { fromSide: "right", toSide: "left" });
  arrow(slide, docStore, output, C.green, "elbow", { fromSide: "right", toSide: "left" });
  arrow(slide, graphStore, evidence, C.green, "elbow", { fromSide: "right", toSide: "left" });
  arrow(slide, dbStore, evidence, C.green, "elbow", { fromSide: "right", toSide: "left" });

  const skill = box(slide, "SKILL：抽取规范 · 故障树建模 · 校验规则 · 评测规范", { left: 206, top: 428, width: 684, height: 54 }, C.white, "#CBD5E1", { fontSize: 16, bold: true, color: C.purple });
  addText(slide, "贯穿 Agent 决策与领域服务调用", { left: 224, top: 488, width: 648, height: 20 }, { fontSize: 12, color: C.muted, alignment: "center" });
  arrow(slide, skill, nexent, C.purple, "straight", { fromSide: "top", toSide: "bottom", dashed: true, width: 1.5 });
  arrow(slide, skill, service, C.purple, "straight", { fromSide: "top", toSide: "bottom", dashed: true, width: 1.5 });

  const feedback = line(slide, 1228, 344, 1228, 528, C.green, 1.5, true);
  const feedback2 = line(slide, 1228, 528, 360, 528, C.green, 1.5, true);
  addText(slide, "人工审核与评测反馈回流 Agent", { left: 824, top: 506, width: 300, height: 22 }, { fontSize: 13, color: C.green, alignment: "right" });
  arrow(slide, evidence, skill, C.green, "elbow", { fromSide: "bottom", toSide: "right", dashed: true, width: 1.5 });
  addText(slide, "保留内核，重构边界", { left: 56, top: 616, width: 300, height: 28 }, { fontSize: 18, bold: true, color: C.navy });
  addText(slide, "Nexent 负责编排与治理，LightRAG 负责检索与知识处理，故障树服务负责领域逻辑", { left: 56, top: 649, width: 1000, height: 24 }, { fontSize: 15, color: C.muted });
  slide.speakerNotes.text = [
    "本页用于说明重构后的目标架构。核心原则是保留已有 LightRAG 与故障树领域能力，由 Nexent 负责 Agent 编排、工具调用、审核和评测。",
    "依据：docs/Nexent重构初步方案.md；项目现有 FastAPI、LightRAG、React/Vue 故障树编辑器和校验器。",
  ];
}

// Slide 2: explanation page
{
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  titleBlock(slide, "架构图的核心逻辑", "一条主链路，三个边界，形成可审核的故障树生成闭环", "02");

  const leftX = 64;
  const leftW = 650;
  const rowY = [166, 274, 382];
  const colors = [C.blue, C.teal, C.orange];
  const soft = [C.blueSoft, C.tealSoft, C.orangeSoft];
  const headings = ["Nexent 负责协作", "LightRAG 负责知识处理", "数据层负责沉淀"]; 
  const bodies = [
    "把文档分析、检索抽取、校验修复、故障树生成和专家审核编排成一条可回退的任务流。",
    "复用现有文档解析、混合检索、知识图谱、故障树投影和规则校验能力。",
    "统一保存原文证据、事件关系、故障树草稿、审核记录和评测样本，支持追溯与迭代。",
  ];
  for (let i = 0; i < 3; i++) {
    const n = box(slide, String(i + 1), { left: leftX, top: rowY[i], width: 46, height: 46 }, soft[i], colors[i], { fontSize: 22, bold: true, color: colors[i] }, { radius: 23 });
    addText(slide, headings[i], { left: leftX + 66, top: rowY[i] - 2, width: 330, height: 30 }, { fontSize: 21, bold: true, color: C.navy });
    addText(slide, bodies[i], { left: leftX + 66, top: rowY[i] + 34, width: 560, height: 54 }, { fontSize: 16, color: C.muted, verticalAlignment: "top" });
    if (i < 2) line(slide, leftX + 23, rowY[i] + 58, leftX + 23, rowY[i + 1] - 12, "#D6DDE8", 1.5);
  }

  // Right-side loop diagram
  addLayerLabel(slide, "任务闭环", 828, 152, 180, C.navy);
  const loopBox = slide.shapes.add({
    geometry: "roundRect",
    position: { left: 808, top: 182, width: 410, height: 286 },
    fill: C.white,
    line: { style: "solid", fill: "#D6DDE8", width: 1.2 },
    borderRadius: 18,
  });
  const nodes = [
    ["输入", "文档\n顶事件", 842, 224, C.blueSoft, C.blue],
    ["检索", "证据\n召回", 1010, 224, C.tealSoft, C.teal],
    ["抽取", "事件\n关系", 1010, 348, C.purpleSoft, C.purple],
    ["校验", "结构\n规则", 842, 348, C.orangeSoft, C.orange],
  ];
  const loopShapes = [];
  for (const [label, sub, x, y, fill, color] of nodes) {
    const sh = box(slide, `${label}\n${sub}`, { left: x, top: y, width: 106, height: 66 }, fill, color, { fontSize: 15, bold: true, color });
    loopShapes.push(sh);
  }
  arrow(slide, loopShapes[0], loopShapes[1], C.line, "straight", { fromSide: "right", toSide: "left", width: 1.5 });
  arrow(slide, loopShapes[1], loopShapes[2], C.line, "straight", { fromSide: "bottom", toSide: "top", width: 1.5 });
  arrow(slide, loopShapes[2], loopShapes[3], C.line, "straight", { fromSide: "left", toSide: "right", width: 1.5 });
  arrow(slide, loopShapes[3], loopShapes[0], C.line, "straight", { fromSide: "top", toSide: "bottom", width: 1.5 });
  addText(slide, "生成故障树草稿", { left: 908, top: 292, width: 205, height: 28 }, { fontSize: 16, bold: true, color: C.navy, alignment: "center" });
  addText(slide, "专家审核 → 版本入库 → 评测迭代", { left: 858, top: 436, width: 310, height: 22 }, { fontSize: 13, color: C.green, alignment: "center" });

  const conclusion = box(slide, "重构原则：保留 LightRAG 内核，Nexent 增强协作与治理能力", { left: 64, top: 574, width: 1154, height: 66 }, C.navy, C.navy, { fontSize: 22, bold: true, color: C.white });
  slide.speakerNotes.text = [
    "本页用于向指导老师解释架构图中的职责边界。重点说明：Nexent 解决 Agent 协作与治理问题，LightRAG 与故障树服务继续承担已有领域能力，数据层保证证据和版本可追溯。",
    "依据：docs/Nexent重构初步方案.md。",
  ];
}

await fs.mkdir(BUILD, { recursive: true });
await fs.mkdir(OUT, { recursive: true });
for (const [idx, slide] of presentation.slides.items.entries()) {
  await writeBlob(path.join(BUILD, `slide-${String(idx + 1).padStart(2, "0")}.png`), await presentation.export({ slide, format: "png", scale: 1.5 }));
}
await writeBlob(path.join(BUILD, "deck-montage.webp"), await presentation.export({ format: "webp", montage: true }));
const draft = path.join(BUILD, "nexent-architecture-draft.pptx");
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(draft);
console.log(JSON.stringify({ draft, slides: presentation.slides.items.length }));
