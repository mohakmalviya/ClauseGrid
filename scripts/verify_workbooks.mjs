import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.resolve(process.argv[2] ?? ".");
const previewDir = path.resolve(process.argv[3] ?? "outputs/workbook-verification");
const repairedPath = process.argv[4] ? path.resolve(process.argv[4]) : null;
const formulaErrors = /#(?:REF!|DIV\/0!|VALUE!|NAME\?|N\/A|NUM!|NULL!)/;

async function findWorkbooks(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await findWorkbooks(target));
    else if (entry.isFile() && entry.name.toLowerCase().endsWith(".xlsx")) result.push(target);
  }
  return result;
}

async function importWorkbook(file) {
  return SpreadsheetFile.importXlsx(await FileBlob.load(file));
}

async function renderSheets(workbook, names, prefix) {
  for (const name of names) {
    const image = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
    const bytes = new Uint8Array(await image.arrayBuffer());
    await fs.writeFile(path.join(previewDir, `${prefix}-${name}.png`), bytes);
  }
}

await fs.mkdir(previewDir, { recursive: true });
const workbookFiles = await findWorkbooks(path.join(root, "workbooks"));
const results = [];
for (const file of workbookFiles.sort()) {
  const workbook = await importWorkbook(file);
  const sheetNames = workbook.worksheets.items.map((sheet) => sheet.name);
  if (!sheetNames.includes("RebateCalc")) throw new Error(`Missing RebateCalc: ${file}`);
  const calc = workbook.worksheets.getItem("RebateCalc");
  const formulas = calc.getRange("L6:T6").formulas.flat();
  const values = calc.getRange("L6:T6").values.flat();
  if (formulas.filter(Boolean).length !== 9) throw new Error(`Expected nine core formulas: ${file}`);
  if (formulaErrors.test(JSON.stringify(values))) throw new Error(`Formula error found in RebateCalc: ${file}`);
  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange();
    if (used && formulaErrors.test(JSON.stringify(used.values))) {
      throw new Error(`Formula error found in ${sheet.name}: ${file}`);
    }
  }
  results.push({
    file: path.relative(root, file).replaceAll("\\", "/"),
    sheets: sheetNames,
    coreFormulaCount: formulas.filter(Boolean).length,
    formulaErrors: 0,
  });
}

const pristinePath = path.join(root, "workbooks", "reference", "supplier_rebate_pristine.xlsx");
const pristine = await importWorkbook(pristinePath);
const summary = await pristine.inspect({ kind: "workbook,sheet,formula", sheetId: "RebateCalc", range: "A1:T10", maxChars: 5000 });
await fs.writeFile(path.join(previewDir, "pristine-inspect.ndjson"), summary.ndjson ?? String(summary));
await renderSheets(pristine, ["Cover", "RebateCalc", "Checks"], "pristine");

if (repairedPath) {
  const repaired = await importWorkbook(repairedPath);
  await renderSheets(repaired, ["Cover", "RebateCalc", "Checks", "Counterexamples", "FormulaWitness_Report"], "repaired");
}

const report = { schemaVersion: 1, workbookCount: results.length, status: "PASS", files: results };
await fs.writeFile(path.join(previewDir, "verification.json"), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ status: report.status, workbookCount: report.workbookCount, previewDir }, null, 2));
