import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const OUTPUT_DIR = path.resolve(process.argv[2] ?? "outputs/formulawitness-benchmark");

const formulas = {
  L6: "=MAX(0,E6-F6-G6)",
  M6: "=MAX(0,C6-MAX(B6,D6)+1)",
  N6: "=IF(L6<100000,0,IF(L6<250000,0.02,IF(L6<500000,0.03,0.04)))",
  O6: "=L6*N6",
  P6: '=IF(AND(J6>=1,K6<>"Y"),0,IF(AND(H6<0.95,I6>0.02),0.6,IF(OR(H6<0.95,I6>0.02),0.75,1)))',
  Q6: "=IF(M6<90,0.5,1)",
  R6: "=O6*P6*Q6",
  S6: "=ROUND(MIN(R6,20000),2)",
  T6: '=IF(AND(J6>=1,K6<>"Y"),"EXCLUDED_CRITICAL",IF(S6=0,"NO_REBATE","PAYABLE"))',
};

const mutants = {
  M01: { L6: "=MAX(0,E6-G6)" },
  M02: { L6: "=MAX(0,E6-F6)" },
  M03: { N6: "=IF(L6<=100000,0,IF(L6<250000,0.02,IF(L6<500000,0.03,0.04)))" },
  M04: { N6: "=IF(L6<100000,0,IF(L6<=250000,0.02,IF(L6<500000,0.03,0.04)))" },
  M05: { N6: "=IF(L6<100000,0,IF(L6<250000,0.02,IF(L6<=500000,0.03,0.04)))" },
  M06: { P6: '=IF(AND(J6>=1,K6<>"Y"),0,IF(AND(H6<=0.95,I6>0.02),0.6,IF(OR(H6<=0.95,I6>0.02),0.75,1)))' },
  M07: { P6: '=IF(AND(J6>=1,K6<>"Y"),0,IF(AND(H6<0.95,I6>=0.02),0.6,IF(OR(H6<0.95,I6>=0.02),0.75,1)))' },
  M08: { P6: '=IF(AND(J6>1,K6<>"Y"),0,IF(AND(H6<0.95,I6>0.02),0.6,IF(OR(H6<0.95,I6>0.02),0.75,1)))' },
  M09: { P6: '=IF(AND(J6>=1,K6<>"Y"),0,IF(AND(H6<0.95,I6>0.02),0.5,IF(OR(H6<0.95,I6>0.02),0.75,1)))' },
  M10: { P6: '=IF(K6="Y",1,IF(AND(J6>=1,K6<>"Y"),0,IF(AND(H6<0.95,I6>0.02),0.6,IF(OR(H6<0.95,I6>0.02),0.75,1))))' },
  M11: { Q6: "=IF(M6<=90,0.5,1)" },
  M12: { S6: "=ROUND(MIN(O6,20000)*P6*Q6,2)" },
  H01: {
    N6: "=IF(L6<100000,0,IF(L6<250000,0.02,IF(L6<500000,0.03,0.035)))",
    P6: '=IF(K6="Y",1,IF(AND(J6>=1,K6<>"Y"),0,IF(AND(H6<0.95,I6>0.02),0.6,IF(OR(H6<0.95,I6>0.02),0.75,1))))',
    S6: "=ROUND(MIN(O6,20000)*P6*Q6,2)",
  },
};

const defaults = {
  supplierId: "SUP-1042",
  periodStart: new Date("2026-01-01T00:00:00Z"),
  periodEnd: new Date("2026-03-31T00:00:00Z"),
  contractStart: new Date("2025-01-01T00:00:00Z"),
  grossInvoices: 250000,
  returnsCredits: 0,
  passThrough: 0,
  onTimeRate: 0.98,
  defectRate: 0.01,
  criticalIncidents: 0,
  criticalWaiver: "N",
};

const cases = [
  { id: "pristine", patch: {}, input: defaults, kind: "reference" },
  ...Object.entries(mutants).map(([id, patch]) => ({ id, patch, input: defaults, kind: id === "H01" ? "hard" : "mutant" })),
  { id: "C01", patch: {}, input: { ...defaults, grossInvoices: 180000 }, kind: "control" },
  { id: "C02", patch: {}, input: { ...defaults, grossInvoices: 250000, onTimeRate: 0.95, defectRate: 0.02, contractStart: new Date("2026-01-01T00:00:00Z") }, kind: "control" },
  { id: "C03", patch: {}, input: { ...defaults, grossInvoices: 250000, onTimeRate: 0.94, defectRate: 0.01, criticalIncidents: 1, criticalWaiver: "Y" }, kind: "control" },
];

function styleWorkbook(workbook, input) {
  const cover = workbook.worksheets.add("Cover");
  const calc = workbook.worksheets.add("RebateCalc");
  const checks = workbook.worksheets.add("Checks");

  cover.showGridLines = false;
  cover.getRange("A1:H2").merge();
  cover.getRange("A1").values = [["Supplier Rebate & SLA Settlement"]];
  cover.getRange("A1:H2").format = { fill: "#12233F", font: { bold: true, color: "#FFFFFF", size: 22 }, verticalAlignment: "center", horizontalAlignment: "left" };
  cover.getRange("A4:B10").values = [
    ["Workbook", "Quarterly controlled calculator"],
    ["Policy", "SR-SLA-2026.1"],
    ["Effective", "2026-01-01"],
    ["Owner", "Procurement Operations"],
    ["Currency", "USD"],
    ["Data", "Synthetic only"],
    ["Status", "See Checks sheet"],
  ];
  cover.getRange("A4:A10").format = { fill: "#EAF1FB", font: { bold: true, color: "#12233F" } };
  cover.getRange("A4:B10").format.borders = { preset: "outside", style: "thin", color: "#B8C4D6" };
  cover.getRange("A12:H14").merge();
  cover.getRange("A12").values = [["Use RebateCalc to review one settlement at a time. Blue-font cells are editable inputs; black-font cells are formulas. Do not add macros, external links, or network refreshes."]];
  cover.getRange("A12:H14").format = { fill: "#F7F9FC", font: { color: "#334155" }, wrapText: true, verticalAlignment: "center" };
  cover.getRange("A:H").format.columnWidth = 15;
  cover.getRange("A:A").format.columnWidth = 20;
  cover.getRange("B:B").format.columnWidth = 34;

  calc.showGridLines = false;
  calc.freezePanes.freezeRows(5);
  calc.getRange("A1:T2").merge();
  calc.getRange("A1").values = [["Quarterly Supplier Rebate Calculator"]];
  calc.getRange("A1:T2").format = { fill: "#12233F", font: { bold: true, color: "#FFFFFF", size: 18 }, verticalAlignment: "center", horizontalAlignment: "left" };
  calc.getRange("A3:T3").merge();
  calc.getRange("A3").values = [["Inputs A:K | Controlled calculations L:T | Policy SR-SLA-2026.1"]];
  calc.getRange("A3:T3").format = { fill: "#DCE9F9", font: { color: "#234E83", italic: true } };
  calc.getRange("A5:T5").values = [[
    "Supplier ID", "Period start", "Period end", "Contract start", "Gross eligible invoices", "Returns & credits", "Pass-through charges", "On-time rate", "Defect rate", "Critical incidents", "Critical waiver", "Eligible spend", "Active days", "Tier rate", "Gross rebate", "SLA multiplier", "Tenure multiplier", "Adjusted rebate", "Final rebate", "Decision code",
  ]];
  calc.getRange("A5:T5").format = { fill: "#244A78", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center", horizontalAlignment: "center", borders: { preset: "inside", style: "thin", color: "#7890AE" } };
  calc.getRange("A5:T5").format.rowHeight = 44;
  calc.getRange("A6:K6").values = [[
    input.supplierId, input.periodStart, input.periodEnd, input.contractStart, input.grossInvoices, input.returnsCredits, input.passThrough, input.onTimeRate, input.defectRate, input.criticalIncidents, input.criticalWaiver,
  ]];
  calc.getRange("A6:K6").format = { fill: "#FFF8DD", font: { color: "#0000FF" } };
  calc.getRange("L6:T6").formulas = [[formulas.L6, formulas.M6, formulas.N6, formulas.O6, formulas.P6, formulas.Q6, formulas.R6, formulas.S6, formulas.T6]];
  calc.getRange("L6:T6").format = { fill: "#F3F6FA", font: { color: "#000000" } };
  calc.getRange("A6:T6").format.borders = { preset: "outside", style: "thin", color: "#AAB6C7" };
  calc.getRange("B6:D6").format.numberFormat = "yyyy-mm-dd";
  calc.getRange("E6:G6").format.numberFormat = "$#,##0.00;[Red]($#,##0.00);-";
  calc.getRange("H6:I6").format.numberFormat = "0.0%;[Red](0.0%);-";
  calc.getRange("J6").format.numberFormat = "0";
  calc.getRange("L6").format.numberFormat = "$#,##0.00;[Red]($#,##0.00);-";
  calc.getRange("M6").format.numberFormat = "0";
  calc.getRange("N6").format.numberFormat = "0.0%";
  calc.getRange("O6").format.numberFormat = "$#,##0.00;[Red]($#,##0.00);-";
  calc.getRange("P6:Q6").format.numberFormat = "0.00x";
  calc.getRange("R6:S6").format.numberFormat = "$#,##0.00;[Red]($#,##0.00);-";
  calc.getRange("A8:K10").merge();
  calc.getRange("A8").values = [["Control note: Settlement formulas implement policy rules RB-101 through RB-303. Formula changes require cited evidence, discriminating counterexamples, a minimal diff, and reviewer approval. The original workbook is immutable."]];
  calc.getRange("A8:K10").format = { fill: "#F7F9FC", font: { color: "#475569" }, wrapText: true, verticalAlignment: "center" };
  calc.getRange("A:T").format.columnWidth = 14;
  calc.getRange("A:A").format.columnWidth = 15;
  calc.getRange("E:G").format.columnWidth = 18;
  calc.getRange("T:T").format.columnWidth = 22;

  checks.showGridLines = false;
  checks.getRange("A1:F2").merge();
  checks.getRange("A1").values = [["Model Controls"]];
  checks.getRange("A1:F2").format = { fill: "#12233F", font: { bold: true, color: "#FFFFFF", size: 18 }, verticalAlignment: "center" };
  checks.getRange("A4:F4").values = [["Check", "Actual", "Expected", "Difference", "Status", "Where to fix"]];
  checks.getRange("A4:F4").format = { fill: "#244A78", font: { bold: true, color: "#FFFFFF" } };
  checks.getRange("A5:F8").values = [
    ["Period order", null, null, null, null, "RebateCalc!B6:C6"],
    ["Non-negative deductions", null, null, null, null, "RebateCalc!F6:G6"],
    ["Rate bounds", null, null, null, null, "RebateCalc!H6:I6"],
    ["Waiver code", null, null, null, null, "RebateCalc!K6"],
  ];
  checks.getRange("B5:B8").formulas = [
    ["=RebateCalc!C6-RebateCalc!B6"],
    ["=MIN(RebateCalc!F6,RebateCalc!G6)"],
    ["=MIN(RebateCalc!H6,RebateCalc!I6,1-RebateCalc!H6,1-RebateCalc!I6)"],
    ['=IF(OR(RebateCalc!K6="Y",RebateCalc!K6="N"),1,0)'],
  ];
  checks.getRange("C5:C8").values = [[">=0"], [">=0"], [">=0"], ["1"]];
  checks.getRange("D5:E8").formulas = [
    ["=MIN(0,B5)", '=IF(D5=0,"OK","FAIL")'],
    ["=MIN(0,B6)", '=IF(D6=0,"OK","FAIL")'],
    ["=MIN(0,B7)", '=IF(D7=0,"OK","FAIL")'],
    ["=B8-1", '=IF(D8=0,"OK","FAIL")'],
  ];
  checks.getRange("A10:D10").merge();
  checks.getRange("A10").values = [["MODEL STATUS"]];
  checks.getRange("E10:F10").merge();
  checks.getRange("E10").formulas = [['=IF(COUNTIF(E5:E8,"FAIL")=0,"PASS","FAIL")']];
  checks.getRange("A10:D10").format = { fill: "#DCE9F9", font: { bold: true, color: "#12233F" } };
  checks.getRange("E10:F10").format = { fill: "#DFF4E5", font: { bold: true, color: "#176B38" }, horizontalAlignment: "center" };
  checks.getRange("A:F").format.columnWidth = 22;
  checks.getRange("A:A").format.columnWidth = 28;
  checks.getRange("F:F").format.columnWidth = 25;
  return { workbook, calc };
}

async function writeCase(spec) {
  const workbook = Workbook.create();
  const { calc } = styleWorkbook(workbook, spec.input);
  for (const [cell, formula] of Object.entries(spec.patch)) {
    calc.getRange(cell).formulas = [[formula]];
  }
  const directory = path.join(OUTPUT_DIR, spec.kind);
  await fs.mkdir(directory, { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const filename = spec.id === "pristine" ? "supplier_rebate_pristine.xlsx" : `${spec.id}_supplier_rebate.xlsx`;
  await output.save(path.join(directory, filename));
  return { id: spec.id, kind: spec.kind, file: path.join(spec.kind, filename).replaceAll("\\", "/"), changedCells: Object.keys(spec.patch) };
}

await fs.mkdir(OUTPUT_DIR, { recursive: true });
const manifest = [];
for (const spec of cases) {
  manifest.push(await writeCase(spec));
}
await fs.writeFile(path.join(OUTPUT_DIR, "build-manifest.json"), JSON.stringify({ schemaVersion: 1, formulaCells: Object.keys(formulas), cases: manifest }, null, 2));
console.log(JSON.stringify({ outputDir: OUTPUT_DIR, workbookCount: manifest.length, manifest }, null, 2));
