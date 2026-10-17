import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = process.env.AYA_PRESENTATION_ROOT || path.dirname(fileURLToPath(import.meta.url));
const packages = process.env.AYA_NODE_MODULES;
const skill = process.env.AYA_PRESENTATION_SKILL;
const python = process.env.AYA_RUNTIME_PYTHON;
if (!packages || !skill || !python) throw new Error("Set AYA_NODE_MODULES, AYA_PRESENTATION_SKILL, and AYA_RUNTIME_PYTHON.");
process.env.RUNTIME_NODE_MODULES = packages;
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(packages, "@oai/artifact-tool/dist/artifact_tool.mjs")).href);
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, "container_tools/artifact_tool_utils.mjs")).href);
const manifest = JSON.parse(await fs.readFile(path.join(root, "demo-manifest.json"), "utf8"));
const comparison = JSON.parse(await fs.readFile(path.resolve(root, manifest.comparison), "utf8"));
const build = path.resolve(root, "../.state/presentation-build");
const previews = path.join(root, "preview");
await fs.mkdir(build, { recursive: true });
await fs.mkdir(previews, { recursive: true });
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const tableOwners = [];
const c = { bg: "#F6F4ED", ink: "#182221", muted: "#59635E", accent: "#0B6B50" };

function text(s, content, x, y, width, height, size = 28, bold = false, color = c.ink) {
  const shape = s.shapes.add({ geometry: "textbox", position: { left: x, top: y, width, height }, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = content;
  shape.text.style = { typeface: "Arial", fontSize: size, bold, color, insets: 0, autoFit: "none", verticalAlignment: "top" };
  return shape;
}
function slide(title, notes, dark = false) {
  const s = deck.slides.add();
  s.background.fill = dark ? c.ink : c.bg;
  if (title) text(s, title, 72, 52, 1136, 100, 44, true, dark ? c.bg : c.ink);
  s.speakerNotes.text = notes;
  return s;
}
function table(s, values, widths, top = 180, height = 360, fontSize = 26) {
  tableOwners.push(deck.slides.items.indexOf(s) + 1);
  const t = s.tables.add({ rows: values.length, columns: values[0].length, left: 72, top, width: 1136, height, columnWidths: widths, values });
  t.styleOptions = { headerRow: true, bandedRows: false };
  t.cells.block({ row: 0, column: 0, rowCount: values.length, columnCount: values[0].length }).assign({ fill: c.bg, textStyle: { typeface: "Arial", fontSize, color: c.ink }, margins: { left: 16, right: 16, top: 14, bottom: 14 }, anchor: "center" });
  t.borders.assign({ style: "solid", fill: "#CED3CB", width: 1 });
  t.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: values[0].length }).assign({ fill: c.ink, textStyle: { typeface: "Arial", fontSize, bold: true, color: "#FFFFFF" } });
}
async function screenshot(s, name, position, alt) {
  const bytes = await fs.readFile(path.join(root, "assets", name));
  s.images.add({ blob: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), contentType: "image/png", alt, fit: "contain", position });
}

// Main presentation: six slides explain the target product. Five appendices preserve measured evidence.
{
  const s = slide(null, "AYA has two peer workflows: reverse engineering and agent improvement. The measured example ports Fireworks SQL tool behavior to Crusoe, then runs Sakana MASS RHI and a separate verified-answer SFT integration test. Sources: https://github.com/Ali-Maq/aya and https://github.com/Ali-Maq/mass/pull/1", true);
  text(s, "AYA", 72, 105, 1100, 155, 130, true, c.bg);
  text(s, "Recover software.\nImprove the agents that build it.", 80, 330, 1110, 170, 48, false, c.bg);
  text(s, "Crusoe · Hermes · OpenShell · REA · MASS", 80, 610, 1100, 45, 27, false, "#BCD2C7");
}
{
  const s = slide("A feature request becomes a reviewable change", "Product workflow. A user supplies a target repository, reference software and a precise behavior contract. Hermes investigates the reference with REA, implements the bounded component inside OpenShell and returns an accepted GitHub change. The working example ports selected Fireworks SQL-tool behavior to Crusoe; this is source/runtime analysis, not binary decompilation. Measured results and limitations are preserved in the evidence appendix.");
  text(s, "YOUR REPOSITORY + A REFERENCE", 72, 175, 1136, 40, 23, true, c.accent);
  text(s, "Recover the behavior", 72, 260, 550, 65, 41, true);
  text(s, "Investigate what it does, including edge cases.\nDefine what must work in your product.", 72, 340, 1120, 105, 30);
  text(s, "Inspect  →  build  →  test  →  review", 72, 500, 1136, 75, 42, true, c.accent);
  text(s, "Hermes + REA · OpenShell execution · Crusoe models · GitHub delivery", 72, 635, 1136, 50, 23, false, c.muted);
}
{
  const s = slide("Target outcome: useful software with evidence", "These are target outcomes, not measured economic or recursive-improvement results. Independent acceptance tests define useful behavior. A cost-aware selection policy should select the least expensive passing workflow using provider prices when available, while reporting total experiment cost. The current prototype records calls, tokens and latency rather than complete dollar cost. Controlled rollout, adoption and willingness-to-pay measurement are future extensions. Actual experiment results are in the appendix.");
  const rows = [["01", "A feature that passes independent tests"], ["02", "The least expensive workflow that meets the bar"], ["03", "The full cost of each experiment is visible"], ["04", "A limited rollout checks whether people want it"]];
  rows.forEach(([n,label],i)=>{text(s,n,72,185+i*100,90,65,36,true,c.accent);text(s,label,180,185+i*100,1015,75,32);});
  text(s, "TARGET · These are product goals, not claimed measured results.", 72, 635, 1136, 55, 23, true, c.muted);
}
{
  const s = slide("Improve the process, then test the next version", "MASS alternates workflow search with training, then repeats with updated weights. AYA ran one actual upstream RHI proposal-and-comparison round, selected verified final answers and completed a Crusoe supervised training job. This is final-answer distillation, not the paper's full trajectory-training recipe. The new checkpoint still requires deployment and independent evaluation; no recursive tuned-model gain was demonstrated. Exact outcomes are in the evidence appendix.");
  text(s, "Search a workflow  →  measure quality + effort", 72, 195, 1136, 75, 39, true, c.accent);
  text(s, "Keep verified examples  →  train a student", 72, 310, 1136, 75, 39, true);
  text(s, "Evaluate the next version  →  repeat", 72, 425, 1136, 75, 39, true);
  text(s, "Keep the simpler approach when extra agent work does not help.", 72, 555, 1136, 65, 29);
  text(s, "CURRENT GATE · The trained checkpoint needs serving and evaluation.", 72, 640, 1136, 45, 22, false, c.muted);
}
{
  const s = slide("Spend less to learn what customers value", "Target architecture and future economics, not measured revenue or willingness-to-pay results. Two connected loops recover useful software and improve the process used to build it. Specs, tests, traces, decisions and outcomes are durable organization knowledge, portable across models. A future controlled rollout measures adoption and willingness to pay and feeds the next feature objective. Current evaluation did not establish accuracy improvement; serving and evaluating the trained checkpoint remain required. Actual numbers are preserved in the appendix.");
  text(s, "FEATURE LOOP", 72, 175, 300, 40, 22, true, c.accent);
  text(s, "Recover a feature  →  test its behavior  →  ship", 72, 225, 1136, 65, 35, true);
  text(s, "LEARNING LOOP", 72, 330, 300, 40, 22, true, c.accent);
  text(s, "Learn a workflow  →  measure effort + quality  →  reuse", 72, 380, 1136, 65, 33, true);
  text(s, "Keep specs, tests, traces and decisions when models change.", 72, 490, 1136, 60, 28);
  text(s, "FUTURE · Roll out gradually → learn what people use and pay for → choose the next feature", 72, 570, 1136, 75, 26, false, c.accent);
  text(s, "Target, not a measured economic result. Token activity is not customer value.", 72, 665, 1136, 35, 20, false, c.muted);
}
{
  const s = slide("Two workflows, one evidence trail", `Open the actual app at http://localhost:3021/app/factory. Reverse engineering is the default tab; Agent improvement is http://localhost:3021/app/factory?tab=improve. This screenshot records a real run and is not a new execution. Inspect the exact GitHub PR, native tool activity, Langfuse trace, retained workflow and provider training receipt. Sources: ${manifest.factory.pull_request}; ${manifest.sql_feature.pull_request}; ${manifest.mass.pull_request}.`);
  await screenshot(s, manifest.factory.screenshot || "factory-dual-workflows.png", { left:72,top:160,width:1136,height:490 }, "Actual AYA interface with reverse engineering and agent improvement peer tabs");
  text(s, "github.com/Ali-Maq/aya", 72, 660, 1136, 35, 23, false, c.accent);
}

// Evidence appendix: measured results remain explicit and separate from the target story.
{
  const s = slide("Evidence · Recovered SQL behavior", "A target GitHub repository, reviewed behavior contract, and pinned reference define the job. Native Hermes investigates selected unchanged upstream SQL functions through REA process capture, implements the bounded component, and repairs failed independent checks inside OpenShell. This source/runtime example is not binary decompilation and does not reproduce Fireworks RL training. First candidate 117/118; accepted and fresh-seed 118/118. Target tests 54; real Crusoe questions 4/4. Source: https://github.com/Ali-Maq/crusoe-developer-hub/pull/2 and aya/demo/evidence/492e2ca7851347f5.");
  text(s, "117 / 118", 72, 195, 520, 110, 76, true, c.muted);
  text(s, "First submitted component", 72, 325, 530, 65, 29);
  text(s, "118 / 118", 700, 195, 510, 110, 76, true, c.accent);
  text(s, "Accepted + fresh-seed checks", 700, 325, 510, 90, 29);
  text(s, "An empty SQL operation failed the contract.\nThe gate required a repair before GitHub delivery.", 72, 480, 1120, 115, 33);
  text(s, "54 target tests passed · GitHub PR and CI · 4 real Crusoe questions", 72, 630, 1136, 48, 24, false, c.muted);
}
{
  const p = manifest.public_sql;
  if (!p?.results || p.results.length < 3) throw new Error("MASS comparison slide requires all three measured development results.");
  const s = slide("Evidence · MASS did not beat the bare model", `Actual public Spider development results and measured whole-episode usage. ${JSON.stringify(p, null, 2)}. The baseline uses one Crusoe completion. Native v0 and v1 each use one child. The actual upstream MASS RHI proposes and compares workflows; v0/v1 tie so the controller retains v0. The bare reference performed better. This is not a claim of improved model accuracy. Keep this public 12/6 experiment separate from the historical fixture experiment with 36 checks per split. Source: https://github.com/Ali-Maq/mass/pull/1 and the run's sanitized receipts.`);
  table(s, [["Public SQL workflow", "Development", "Calls", "Tokens", "Seconds"], ...p.results.map(r=>[r.name, r.development, String(r.calls), r.tokens.toLocaleString("en-US"), String(r.elapsed_seconds)])], [346, 230, 130, 230, 200], 170, 325, 25);
  text(s, "Retained v0: 3 / 6 held-out questions passed", 72, 540, 1136, 85, 39, true, c.ink);
  text(s, "Baseline held-out performance was not evaluated. No accuracy gain is established.", 72, 635, 1136, 55, 23, false, c.muted);
}
{
  const tr = manifest.public_sql.training;
  if (!tr || tr.status !== "succeeded") throw new Error("Training slide requires the actual succeeded receipt.");
  const s = slide("Evidence · Verified answers trained a 9B student", `The public Spider development selection chose12 verified direct-baseline answers:10training,2fixedvalidation,0heldout. Actual Crusoe job ${tr.id} succeeded. Student ${tr.model}; checkpoint ${tr.fine_tuned_model}; trained tokens ${tr.trained_tokens}. 10 training + 2 validation examples, 1 epoch, no heldout training rows. This is assistant-only supervised distillation of verified final SQL outputs, not a MASS winning-teacher training round because no workflow beat the bare reference. Dedicated serving and tuned inference evaluation remain separate gates. Source: https://console.crusoecloud.com/foundry/fine-tuning/jobs/${tr.id}/overview and aya/.state/mass/${manifest.public_sql.run_id}/training/receipt.json.`);
  text(s, "Training succeeded", 72, 185, 1110, 90, 58, true, c.accent);
  text(s, "Qwen3.5-9B", 72, 315, 500, 75, 43, true);
  text(s, "10 training examples\n2 validation examples · 1 epoch", 72, 420, 600, 135, 31);
  text(s, "26,624", 800, 320, 380, 100, 69, true);
  text(s, "trained tokens", 800, 430, 380, 60, 29);
  text(s, "SFT integration test. No winning MASS teacher or tuned-quality gain.\nDeployment and independent tuned-model evaluation are still required.", 72, 600, 1136, 88, 23, false, c.muted);
}

// Comparison limits and implementation boundaries.
{
  const b = comparison.one_shot, a = comparison.aya_completed_run;
  const s = slide("Appendix · One SQL component comparison", `Same model, reviewed contract, evaluator and seeds. Unequal budget and tool access. One task and one baseline sample. No Claude Code or Codex baseline ran. This measures the component contract, not the NL 36-check benchmark. ${JSON.stringify(comparison,null,2)}`);
  table(s, [["SQL component", "Contract-only one shot", "AYA accepted"], ["Independent checks", `${b.development.passed} / ${b.development.total}`, "118 / 118"], ["Fresh-seed checks", `${b.fresh_seed.passed} / ${b.fresh_seed.total}`, "118 / 118"], ["Model calls", "1", String(a.planning_and_native_model_calls)], ["Cumulative tokens", b.usage.total_tokens.toLocaleString("en-US"), a.planning_and_native_usage.total_tokens.toLocaleString("en-US")]], [410,363,363], 170, 400, 26);
  text(s, "Unequal budgets. This does not isolate REA's effect or establish superiority.", 72, 615, 1136, 65, 25, false, c.muted);
}
{
  const s = slide("Appendix · Boundaries and review links", "The controller retains credentials and current Spider reference SQL. The public benchmark uses public_db_executor.py; the earlier fixture uses the digest-bound accepted repository component. Both execute generated SQL in restricted containers. Native Hermes uses fresh workspaces in one shared OpenShell worker, with no per-job filesystem isolation. The public v0 trace read an unrelated earlier fixture file from a sibling workspace; no current Spider reference SQL was observed. Landlock is unavailable on Docker Desktop. These are execution controls, not a formal security proof. Relevant sources: aya/DEMO.md, aya/aya_factory/sql_eval.py, aya/aya_factory/sql_benchmark.py.");
  text(s, "Current Spider reference SQL stays controller-side.\nSQL runs in a separate restricted executor.\nNative workspaces share one worker filesystem.", 72, 175, 1120, 190, 32);
  const links = [["Factory",manifest.factory.pull_request],["Recovered SQL component",manifest.sql_feature.pull_request],["MASS integration",manifest.mass.pull_request]];
  links.forEach((item,i)=>{const y=405+i*76;text(s,item[0],72,y,335,50,26,true);text(s,item[1],410,y,798,50,24,false,c.accent);});
  text(s, "No cross-run filesystem isolation. Native Landlock is unavailable on this host.",72,650,1136,42,22,false,c.muted);
}

const version = process.env.AYA_DECK_VERSION || "dual-sql-mass-v1";
const candidatePath = path.join(build, `candidate-${version}.pptx`);
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
for (const [i,s] of deck.slides.items.entries()) {
  const png = await deck.export({ slide:s,format:"png",scale:1 });
  await fs.writeFile(path.join(previews,`slide-${String(i+1).padStart(2,"0")}.png`),new Uint8Array(await png.arrayBuffer()));
}
const finalPath = process.env.AYA_FINAL_PPTX || path.join(root,"AYA-MASS-demo.pptx");
await finalizePresentation({workspaceDir:path.resolve(root,"../.."),candidatePath,finalPath,pythonExecutable:python,integrityValidatorPath:path.join(skill,"container_tools/inspect_presentation_package_integrity.py"),layoutValidatorPath:path.join(skill,"container_tools/inspect_presentation_layout_geometry.py"),layoutArgs:["--expected-slide-size-emu","12192000,6858000","--validate-bullet-geometry","--validate-heading-fit",...tableOwners.flatMap(n=>["--require-native-table-slide",String(n)])],explicitTotalSlideCount:11,requiredNativeTableOwnerSlides:tableOwners,fontPolicy:{basis:"design",families:["Arial"]},verifyArtifactToolImport:true,receiptPath:path.join(build,`${version}-validation.json`)});
console.log(finalPath);
