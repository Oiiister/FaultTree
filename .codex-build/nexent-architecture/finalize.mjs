import path from "node:path";
import { pathToFileURL } from "node:url";

const workspaceDir = "/Users/oyster/Desktop/学习资料/项目/P03_服创/17届A15/FTP/FT_LightRAG_Flyfish-main";
const SKILL_DIR = "/Users/oyster/.codex/plugins/cache/openai-primary-runtime/presentations/26.1011.11113/skills/presentations";
const RUNTIME_PYTHON = "/Users/oyster/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const candidatePath = path.join(workspaceDir, ".codex-build", "nexent-architecture", "nexent-architecture-draft.pptx");
const finalPath = path.join(workspaceDir, "output", "Nexent-LightRAG故障树系统架构方案.pptx");
const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools", "artifact_tool_utils.mjs")).href);

const result = await finalizePresentation({
  workspaceDir,
  candidatePath,
  finalPath,
  explicitTotalSlideCount: 2,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  fontPolicy: { basis: "design", families: ["Aptos"] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(workspaceDir, ".codex-build", "nexent-architecture", "validation.json"),
});
console.log(JSON.stringify(result));
