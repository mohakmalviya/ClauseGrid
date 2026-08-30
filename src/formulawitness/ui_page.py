"""Presentation layer for the ClauseGrid review workbench."""

_PAGE_BEFORE_SCRIPT = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#101c2c">
<title>ClauseGrid · Policy assurance workbench</title>
<style>
:root {
  --canvas: #f3f0e8;
  --paper: #fffdf8;
  --paper-strong: #ffffff;
  --ink: #101a2b;
  --ink-soft: #586273;
  --rail: #101c2c;
  --rail-soft: #192a40;
  --line: #d7d1c5;
  --line-strong: #b9b1a3;
  --action: #3157e6;
  --action-dark: #2343b9;
  --signal: #d9f36a;
  --signal-ink: #293408;
  --pass: #08765f;
  --pass-soft: #e4f4ee;
  --fail: #b73e42;
  --fail-soft: #fbe8e7;
  --warn: #9b6107;
  --warn-soft: #fff1d5;
  --radius: 16px;
  --radius-small: 10px;
  --shadow: 0 20px 55px rgba(16, 28, 44, .10);
  --header-height: 76px;
  --text-xs: 12px;
  --text-sm: 13px;
  --text-ui: 14px;
  --text-nav: 15px;
  --text-body: 16px;
  --text-lead: 17px;
  --workbench-pad: clamp(22px, 2.4vw, 38px);
  --workbench-columns: minmax(0, 1fr) minmax(0, 1fr);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  overflow-x: hidden;
  background-color: var(--canvas);
  background-image:
    linear-gradient(rgba(16, 28, 44, .028) 1px, transparent 1px),
    linear-gradient(90deg, rgba(16, 28, 44, .028) 1px, transparent 1px);
  background-size: 28px 28px;
  color: var(--ink);
  font-family: "Segoe UI Variable", "Aptos", "Segoe UI", sans-serif;
  font-size: var(--text-body);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

[hidden], .hidden { display: none !important; }
button, select, input { font: inherit; }
button, a, select, input, summary { -webkit-tap-highlight-color: transparent; }
button:focus-visible, a:focus-visible, select:focus-visible, input:focus-visible,
summary:focus-visible, [tabindex]:focus-visible {
  outline: 3px solid rgba(49, 87, 230, .34);
  outline-offset: 3px;
}
.skip-link {
  position: fixed;
  z-index: 1000;
  top: 8px;
  left: 10px;
  transform: translateY(-150%);
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--signal);
  color: var(--signal-ink);
  font-weight: 800;
  text-decoration: none;
}
.skip-link:focus { transform: translateY(0); }

.appbar {
  position: sticky;
  z-index: 40;
  top: 0;
  height: var(--header-height);
  border-bottom: 1px solid rgba(255, 255, 255, .11);
  background: var(--rail);
  color: #fff;
}
.appbar-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: clamp(14px, 2vw, 28px);
  width: 100%;
  height: 100%;
  padding: 0 clamp(16px, 2vw, 30px);
}
.brand-wrap { display: flex; align-items: center; gap: 11px; min-width: 0; }
.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid rgba(255, 255, 255, .22);
  border-radius: 10px;
  background: var(--signal);
  color: var(--rail);
  font-family: Georgia, serif;
  font-size: 20px;
  font-weight: 900;
}
.brand-copy { display: grid; gap: 1px; }
.brand { font-size: 19px; font-weight: 820; letter-spacing: -.35px; }
.brand-subtitle {
  color: #aebed1;
  font-family: Consolas, monospace;
  font-size: var(--text-xs);
  letter-spacing: .11em;
  text-transform: uppercase;
}
.appbar-actions { display: flex; align-items: center; gap: 12px; }
.appbar-nav { display: flex; flex: 1 1 auto; align-items: center; justify-content: center; gap: 4px; }
.appbar-nav a {
  padding: 8px 10px;
  border-radius: 8px;
  color: #c9d4e1;
  font-size: var(--text-nav);
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}
.appbar-nav a:hover { background: var(--rail-soft); color: #fff; }
#start, #auditWorkspace, #howItWorks, #policyPackSection, #evidenceSection {
  scroll-margin-top: calc(var(--header-height) + 18px);
}
.header-pack {
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  column-gap: 8px;
  min-width: 210px;
  max-width: 270px;
  padding: 7px 10px;
  border-left: 1px solid rgba(255,255,255,.16);
}
.header-pack-label { color: #aebdcb; font-family: Consolas, monospace; font-size: var(--text-xs); font-weight: 850; letter-spacing: .07em; text-transform: uppercase; }
.header-pack b { overflow: hidden; color: #fff; font-size: var(--text-sm); text-overflow: ellipsis; white-space: nowrap; }
.header-pack-meta { grid-column: 1 / -1; margin-top: 2px; color: var(--signal); font-family: Consolas, monospace; font-size: var(--text-xs); }
.mobile-pack-copy { display: none; }
.tour-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 14px;
  border: 1px solid rgba(217, 243, 106, .54);
  border-radius: 9px;
  background: transparent;
  color: var(--signal);
  box-shadow: none;
  font-size: var(--text-ui);
  font-weight: 800;
  cursor: pointer;
}
.tour-trigger::before { content: "?"; font-family: Georgia, serif; font-size: 16px; }
.tour-trigger:hover { background: rgba(217, 243, 106, .09); }

.app-shell { display: block; width: 100%; }

.workspace {
  min-width: 0;
  width: 100%;
  padding: clamp(18px, 2.2vw, 34px);
}
.workspace-inner { width: 100%; max-width: none; margin: 0; }
.eyebrow, .section-kicker {
  display: block;
  color: var(--action);
  font-family: Consolas, monospace;
  font-size: var(--text-xs);
  font-weight: 850;
  letter-spacing: .09em;
  text-transform: uppercase;
}
.opening {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(300px, .7fr);
  gap: clamp(26px, 4vw, 64px);
  align-items: center;
  min-height: 214px;
  padding: clamp(26px, 3vw, 44px);
  border: 1px solid #26384f;
  border-radius: var(--radius);
  background: var(--rail);
  color: #fff;
}
.opening .eyebrow { color: var(--signal); }
.opening h1 {
  max-width: 800px;
  margin: 10px 0 12px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(34px, 3.4vw, 55px);
  font-weight: 700;
  letter-spacing: -1.7px;
  line-height: 1.01;
}
.opening p { max-width: 780px; margin: 0; color: #d1dae4; font-size: var(--text-lead); line-height: 1.58; }
.opening-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; margin-top: 18px; }
.opening-actions button { min-height: 42px; padding: 0 15px; }
.opening-quick { background: var(--signal); color: var(--signal-ink); }
.opening-quick:hover:not(:disabled) { background: #c8e653; }
.opening-tour { border: 1px solid rgba(255,255,255,.24); background: transparent; color: #fff; }
.opening-tour:hover:not(:disabled) { background: rgba(255,255,255,.08); }
.proof-list { display: grid; gap: 1px; border: 1px solid rgba(255,255,255,.12); }
.proof-item {
  display: grid;
  grid-template-columns: 36px 1fr;
  align-items: center;
  min-height: 54px;
  padding: 8px 13px;
  background: rgba(255, 255, 255, .045);
}
.proof-item i {
  display: grid;
  place-items: center;
  width: 25px;
  height: 25px;
  border-radius: 50%;
  background: var(--signal);
  color: var(--signal-ink);
  font-style: normal;
  font-size: var(--text-ui);
  font-weight: 900;
}
.proof-item b { display: block; font-size: var(--text-ui); }
.proof-item span { display: block; margin-top: 2px; color: #b9c6d3; font-size: var(--text-sm); }
.trust-chain {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin: 12px 0 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255, 253, 248, .9);
}
.trust-chain span {
  position: relative;
  padding: 12px 34px 12px 14px;
  color: var(--ink-soft);
  font-size: var(--text-sm);
  font-weight: 750;
  text-align: center;
}
.trust-chain span:not(:last-child) { border-right: 1px solid var(--line); }
.trust-chain span:not(:last-child)::after {
  content: "→";
  position: absolute;
  right: 10px;
  color: var(--action);
}

.surface-primary, .panel {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper);
}
.audit-workbench {
  overflow: hidden;
  box-shadow: var(--shadow);
  scroll-margin-top: calc(var(--header-height) + 18px);
}
.workbench-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 26px;
  padding: 24px var(--workbench-pad) 18px;
  border-bottom: 1px solid var(--line);
}
.workbench-head h2 { margin: 5px 0 0; font-family: Georgia, serif; font-size: clamp(25px, 2.3vw, 36px); }
.workbench-head p { max-width: 620px; margin: 0; color: var(--ink-soft); font-size: var(--text-body); line-height: 1.55; }
.runtime-ready {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
  color: var(--pass);
  font-family: Consolas, monospace;
  font-size: var(--text-xs);
  font-weight: 850;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.runtime-ready::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #35c9a7; box-shadow: 0 0 0 4px #dff5ef; }
.runtime-ready.unavailable { color: var(--fail); }
.runtime-ready.unavailable::before { background: var(--fail); box-shadow: 0 0 0 4px var(--fail-soft); }
.mode-switch {
  display: grid;
  grid-template-columns: var(--workbench-columns);
  gap: 0;
  margin: 0;
  padding: 0;
  border-bottom: 1px solid var(--line);
  background: #f6f3ed;
}
.mode-tab {
  position: relative;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 78px;
  padding: 13px var(--workbench-pad);
  border: 0;
  border-bottom: 3px solid transparent;
  border-radius: 0;
  background: transparent;
  color: var(--ink-soft);
  box-shadow: none;
  text-align: left;
  cursor: pointer;
}
.mode-tab + .mode-tab { border-left: 1px solid var(--line); }
.mode-tab.active { border-bottom-color: var(--action); background: var(--paper); color: var(--ink); }
.mode-tab:hover:not(:disabled) { background: #ece8df; transform: none; }
.mode-tab.active:hover:not(:disabled) { background: var(--paper); color: var(--ink); }
.mode-index {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  font-family: Consolas, monospace;
  font-size: var(--text-xs);
  font-weight: 850;
}
.mode-tab.active .mode-index { border-color: var(--action); background: var(--action); color: #fff; }
.mode-title { display: block; font-size: var(--text-body); font-weight: 850; }
.mode-description { display: block; margin-top: 3px; font-size: var(--text-sm); font-weight: 550; }
.mode-badge {
  padding: 5px 7px;
  border: 1px solid currentColor;
  border-radius: 99px;
  color: var(--pass);
  font-family: Consolas, monospace;
  font-size: var(--text-xs);
  font-weight: 850;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.mode-tab:not(.active) .mode-badge { color: #788494; }
.mode-pane { min-height: 0; }
.workbench-grid { display: grid; grid-template-columns: var(--workbench-columns); }
.input-stage, .run-stage { min-width: 0; padding: var(--workbench-pad); }
.input-stage { border-right: 1px solid var(--line); }
.stage-label {
  display: flex;
  align-items: center;
  gap: 8px;
  width: max-content;
  margin-bottom: 18px;
  color: var(--ink);
  font-family: Consolas, monospace;
  font-size: var(--text-xs);
  font-weight: 850;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.stage-label::before { content: ""; width: 18px; height: 2px; background: var(--action); }
.pack-snapshot {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  margin-bottom: 22px;
  padding: 14px 16px;
  border-left: 4px solid var(--pass);
  background: #edf6f1;
}
.pack-snapshot span { display: block; color: var(--pass); font-size: var(--text-xs); font-weight: 850; letter-spacing: .07em; text-transform: uppercase; }
.pack-snapshot b { display: block; margin-top: 4px; font-size: var(--text-body); }
.pack-rule-count { color: var(--pass); font-family: Consolas, monospace; font-size: var(--text-xs); font-weight: 800; text-align: right; }
label {
  display: block;
  margin-bottom: 8px;
  color: #465164;
  font-size: var(--text-xs);
  font-weight: 850;
  letter-spacing: .07em;
  text-transform: uppercase;
}
select, input {
  width: 100%;
  min-height: 48px;
  padding: 11px 13px;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-small);
  background: #fff;
  color: var(--ink);
  outline: none;
}
select:focus, input:focus { border-color: var(--action); box-shadow: 0 0 0 4px rgba(49, 87, 230, .09); }
.field-note { margin: 9px 0 0; color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.5; }
.run-stage { display: flex; flex-direction: column; min-height: 0; background: #f8f6f1; }
.run-stage h3 { margin: 0; font-family: Georgia, serif; font-size: 22px; }
.run-stage > p { margin: 8px 0 18px; color: var(--ink-soft); font-size: var(--text-body); line-height: 1.55; }
.run-checks { display: grid; gap: 9px; margin-bottom: 20px; }
.run-check {
  display: grid;
  grid-template-columns: 22px 1fr;
  align-items: start;
  color: #3e4a5b;
  font-size: var(--text-sm);
  line-height: 1.45;
}
.run-check i { color: var(--pass); font-style: normal; font-weight: 900; }
button {
  min-height: 48px;
  border: 0;
  border-radius: var(--radius-small);
  padding: 0 18px;
  background: var(--action);
  color: #fff;
  font-weight: 800;
  cursor: pointer;
  transition: background-color 160ms ease, transform 160ms ease, opacity 160ms ease;
}
button:hover:not(:disabled) { background: var(--action-dark); transform: translateY(-1px); }
button.secondary { border: 1px solid var(--line); background: #ece8df; color: var(--ink); }
button.secondary:hover:not(:disabled) { background: #e3ded3; }
button:disabled { cursor: not-allowed; opacity: .48; }
.run-stage .primary-run { width: 100%; margin-top: 0; }
.actions { display: flex; gap: 9px; margin-top: 15px; }
.actions #audit { flex: 1; }
.run-note { min-height: 34px; margin-top: 11px; color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.45; }
.investigation-controls {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: minmax(280px, 340px) minmax(0, 764px);
  gap: 16px;
  align-items: center;
  justify-content: center;
  padding: 20px var(--workbench-pad);
  border-top: 1px solid var(--line);
  background: #f8f6f1;
}
.investigation-controls .actions, .investigation-controls .run-status { margin: 0; }
.investigation-controls .actions { align-self: center; }
.verify-result {
  min-height: 152px;
  margin: 0 var(--workbench-pad) 28px;
  padding: 20px;
  border: 1px solid var(--line);
  border-left: 4px solid var(--line-strong);
  border-radius: 12px;
  background: #fff;
}
#verificationResult:focus-visible, #results:focus-visible { outline: none; box-shadow: inset 0 0 0 3px rgba(49, 87, 230, .24); }
.result-empty { display: grid; place-items: center; min-height: 108px; text-align: center; }
.result-empty div { max-width: 440px; }
.result-empty b { display: block; margin-bottom: 6px; font-size: var(--text-body); }
.result-empty span { color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.5; }
.verify-summary { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.verify-details { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
.verify-details div { min-width: 0; padding: 10px; background: #f2f0ea; color: var(--ink-soft); font-size: var(--text-xs); }
.verify-details b { display: block; overflow: hidden; margin-top: 4px; color: var(--ink); font-size: var(--text-ui); text-overflow: ellipsis; white-space: nowrap; }
.verify-result .patch { margin: 14px 0; }

.source-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin: 0 0 17px;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #ece8df;
}
.source-tabs.single-tab { grid-template-columns: 1fr; }
.source-tab { min-height: 48px; padding: 8px 11px; background: transparent; color: var(--ink-soft); box-shadow: none; font-size: var(--text-ui); line-height: 1.3; white-space: normal; }
.source-tab:hover:not(:disabled) { background: rgba(255, 255, 255, .52); transform: none; }
.source-tab.active { background: #fff; color: var(--ink); }
.upload-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.file-box { min-width: 0; padding: 12px; border: 1px dashed var(--line-strong); background: #fff; }
.file-box input[type=file] { min-height: 44px; padding: 8px; font-size: var(--text-xs); }
.consent { display: flex; align-items: flex-start; gap: 9px; margin-top: 11px; padding: 11px; border-left: 3px solid var(--warn); background: var(--warn-soft); color: #5f4a27; font-size: var(--text-sm); line-height: 1.45; text-transform: none; letter-spacing: 0; }
.consent input { width: auto; min-height: auto; margin: 2px 0 0; accent-color: var(--action); }
.profile-note { margin: 9px 0 0; color: #5f6876; font-size: var(--text-xs); line-height: 1.5; }
.upload-manifest { margin-top: 10px; padding: 10px 12px; border-left: 3px solid var(--pass); background: var(--pass-soft); color: #315b54; font-size: var(--text-xs); line-height: 1.5; }
code { font-family: Consolas, monospace; font-size: var(--text-xs); word-break: break-all; }
.runtime-label { margin: 0 0 16px; padding: 9px 11px; border-left: 3px solid var(--action); background: #eef1fa; color: #3a4962; }
.run-status { margin-top: 13px; padding: 13px; border: 1px solid var(--line); border-radius: var(--radius-small); background: #fff; }
.status-line { display: flex; align-items: flex-start; gap: 9px; line-height: 1.45; }
.status-dot { flex: 0 0 auto; width: 8px; height: 8px; margin-top: 6px; border-radius: 50%; background: #9aa4b1; }
.status-dot.live { background: #35c9a7; box-shadow: 0 0 0 4px #dff5ef; animation: pulse 1.6s infinite; }
.progress-track { height: 4px; margin-top: 10px; overflow: hidden; background: #e1ded7; }
.progress-bar { width: 0; height: 100%; background: var(--action); transition: width .45s ease; }
.status-meta { min-height: 18px; margin-top: 7px; color: #66717f; font-family: Consolas, monospace; font-size: var(--text-xs); }
@keyframes pulse { 50% { opacity: .45; } }

.workflow-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  border-top: 1px solid var(--line);
  background: #f2efe8;
}
.step {
  position: relative;
  min-width: 0;
  padding: 14px 10px 14px 30px;
  border-right: 1px solid var(--line);
  color: #626d7b;
  font-family: Consolas, monospace;
  font-size: var(--text-xs);
  font-weight: 800;
  text-align: center;
  text-transform: uppercase;
}
.step:last-child { border-right: 0; }
.step::before { content: ""; position: absolute; top: 18px; left: 16px; width: 7px; height: 7px; border-radius: 50%; background: #adb4bd; }
.step.on { color: var(--action); background: #fff; }
.step.on::before { background: var(--action); }

#results {
  display: grid;
  gap: 16px;
  width: min(100%, 1120px);
  margin: clamp(24px, 3vw, 40px) auto 0;
  scroll-margin-top: calc(var(--header-height) + 18px);
}
.results-grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
.result-sheet, #results > .panel, .results-grid .panel {
  padding: var(--workbench-pad);
  background: var(--paper);
}
.decision-panel { position: static; order: -1; }
.outcome-panel { border-left: 5px solid var(--warn); }
.outcome-panel.outcome-REPAIR { border-left-color: var(--action); }
.outcome-panel.outcome-NO_CHANGE { border-left-color: var(--pass); }
.outcome-panel.outcome-REPAIR_REJECTED { border-left-color: var(--fail); }
.outcome-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.outcome-head h2 { max-width: 760px; margin: 5px 0 0; font-family: Georgia, serif; font-size: clamp(24px, 2.4vw, 34px); letter-spacing: -.35px; line-height: 1.15; }
.outcome-label { color: var(--ink-soft); font-size: var(--text-xs); font-weight: 850; letter-spacing: .11em; text-transform: uppercase; }
.outcome-body { max-width: 760px; margin: 18px 0 0; color: var(--ink-soft); font-size: var(--text-lead); line-height: 1.65; }
.outcome-foot { margin: 16px 0 0; padding: 12px 14px; border-left: 3px solid var(--line-strong); background: #f2f0ea; color: var(--ink-soft); font-size: var(--text-sm); }
.status { display: inline-flex; align-items: center; min-height: 30px; padding: 6px 10px; border-radius: 999px; font-size: var(--text-xs); font-weight: 850; white-space: nowrap; }
.PASS, .EXACT, .NO_CHANGE, .SURVIVED { background: var(--pass-soft); color: var(--pass); }
.FAIL, .AMBIGUOUS, .CONFLICT, .BROKEN, .REPAIR_REJECTED { background: var(--fail-soft); color: var(--fail); }
.REPAIR { background: #e8edfd; color: var(--action-dark); }
.ABSTAIN, .INCONCLUSIVE, .SAFETY_LIMIT_REACHED, .HUMAN_REVIEW { background: var(--warn-soft); color: var(--warn); }
.result-detail { overflow: hidden; }
.result-detail summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; cursor: pointer; color: var(--ink); font-family: Georgia, serif; font-size: 19px; font-weight: 800; line-height: 1.3; list-style: none; }
.result-detail summary::-webkit-details-marker { display: none; }
.result-detail summary::after { content: "+"; flex: 0 0 auto; color: var(--action); font-family: "Segoe UI", sans-serif; font-size: 20px; }
.result-detail[open] summary::after { content: "−"; }
.result-detail > div { margin-top: 18px; }
.citation-panel #citations { max-height: none; overflow: visible; padding: 0; }
.quote { margin: 10px 0; padding: 12px 14px; border-left: 3px solid var(--action); background: #f1f3f8; color: #39465a; font-size: var(--text-ui); line-height: 1.55; }
.patch { min-width: 0; margin: 15px 0; padding: 16px; border: 1px solid var(--line); background: #fff; }
.formula-label { display: block; margin: 13px 0 5px; color: #626d7b; font-size: var(--text-xs); font-weight: 850; text-transform: uppercase; }
.before, .after { padding: 11px; background: #f4f2ed; font-family: Consolas, monospace; font-size: var(--text-sm); overflow-wrap: anywhere; word-break: break-word; }
.before { border-left: 3px solid var(--fail); color: #8e2931; }
.after { border-left: 3px solid var(--pass); color: #0b6843; }
.outcome-panel .patch { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin: 22px 0 0; padding: 0; overflow: hidden; border-radius: 12px; background: var(--line); }
.outcome-panel .patch > b { grid-column: 1 / -1; padding: 13px 14px; background: #f2f0ea; font-size: var(--text-sm); }
.outcome-panel .patch > .formula-label { margin: 0; padding: 10px 14px 5px; background: #fff; }
.outcome-panel .patch > .formula-label:first-of-type { grid-column: 1; grid-row: 2; }
.outcome-panel .patch > .formula-label:last-of-type { grid-column: 2; grid-row: 2; }
.outcome-panel .patch > .before { grid-column: 1; grid-row: 3; }
.outcome-panel .patch > .after { grid-column: 2; grid-row: 3; }
.outcome-panel .patch > p { grid-column: 1 / -1; margin: 0; padding: 13px 14px; background: #fff; color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.55; }
.approval { border-color: #dfbd7f; background: #fff9ed !important; }
.downloads a { display: inline-block; margin: 6px 6px 0 0; padding: 9px 11px; border: 1px solid #aebbd0; border-radius: 8px; color: var(--action-dark); background: #f7f8fc; font-size: var(--text-sm); font-weight: 750; text-decoration: none; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
.danger { color: var(--fail) !important; }
.small { color: var(--ink-soft); font-size: var(--text-sm); }

.support-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: repeat(4, auto); column-gap: 14px; row-gap: 0; align-items: stretch; margin: 0 0 18px; }
.support-card { display: grid; grid-row: span 4; grid-template-rows: subgrid; min-width: 0; align-self: stretch; padding: clamp(20px, 2.2vw, 30px); border: 1px solid var(--line); border-radius: var(--radius); background: rgba(255, 253, 248, .94); }
.support-card h2 { margin: 6px 0 11px; font-family: Georgia, serif; font-size: clamp(23px, 2vw, 31px); line-height: 1.12; text-wrap: balance; }
.support-card > p { margin: 0; color: var(--ink-soft); font-size: var(--text-body); line-height: 1.65; }
.support-card > :is(.difference-flow, .agent-pair) { align-self: stretch; margin-top: 20px; }
.difference-flow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; border: 1px solid var(--line); background: var(--line); }
.difference-flow div { min-height: 0; padding: 14px; background: #fff; }
.difference-flow b { display: block; margin-bottom: 6px; font-size: var(--text-ui); }
.difference-flow span { color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.45; }
.agent-pair { display: grid; grid-template-columns: 1fr auto 1fr; align-items: stretch; gap: 10px; }
.agent-node { min-height: 0; padding: 15px; border-top: 3px solid var(--action); background: #fff; }
.agent-node:last-child { border-top-color: var(--pass); }
.agent-node b { display: block; font-size: var(--text-ui); }
.agent-node span { display: block; margin-top: 6px; color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.45; }
.agent-arrow { align-self: center; color: var(--action); font-weight: 900; }
.support-details { margin-top: 14px; padding: 0; overflow: hidden; }
.support-details > summary {
  padding: 20px clamp(20px, 2.2vw, 30px);
  cursor: pointer;
  color: var(--ink);
  font-family: Georgia, serif;
  font-size: 19px;
  font-weight: 800;
  list-style: none;
}
.support-details > summary::-webkit-details-marker { display: none; }
.support-details > summary::after { content: "+"; float: right; color: var(--action); font-family: "Segoe UI", sans-serif; }
.support-details[open] > summary::after { content: "−"; }
.details-body { padding: 0 clamp(20px, 2.2vw, 30px) 28px; }
.pack-head { display: flex; justify-content: space-between; gap: 22px; }
.pack-head h2 { margin: 5px 0 8px; font-family: Georgia, serif; font-size: 27px; }
.pack-head p { max-width: 780px; margin: 0; }
.zero-badge { flex: 0 0 auto; height: fit-content; padding: 7px 10px; border: 1px solid var(--pass); border-radius: 99px; color: var(--pass); font-size: var(--text-xs); font-weight: 850; }
.pack-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin: 20px 0 14px; border: 1px solid var(--line); background: var(--line); }
.pack-metric { padding: 14px; background: #fff; }
.pack-metric span, .hash-item span { display: block; color: #626d7b; font-size: var(--text-xs); font-weight: 850; letter-spacing: .07em; text-transform: uppercase; }
.pack-metric b { display: block; margin-top: 6px; font-size: 16px; }
.hash-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.hash-item { min-width: 0; padding: 12px; background: #f1efe9; }
.hash-item code { display: block; overflow: hidden; margin-top: 5px; text-overflow: ellipsis; white-space: nowrap; }
.lifecycle { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; margin-top: 14px; border: 1px solid var(--line); background: var(--line); }
.lifecycle-step { padding: 13px; background: #fff; color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.45; }
.lifecycle-step b { display: block; margin-bottom: 5px; color: var(--action); }
.governance-warning { margin-top: 14px; padding: 13px 15px; border-left: 4px solid var(--warn); background: var(--warn-soft); color: #674a19; font-size: var(--text-sm); line-height: 1.55; }
.evidence-head { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }
.evidence-head h2 { margin: 5px 0; font-family: Georgia, serif; }
.evidence-head p { margin: 4px 0 12px; }
.benchmark-badge { max-width: 340px; padding: 8px 10px; background: #edf0f7; color: var(--ink); font-size: var(--text-xs); font-weight: 800; text-align: right; }
table { width: 100%; border-collapse: collapse; font-size: var(--text-ui); }
th { padding: 11px 9px; border-bottom: 1px solid var(--line); color: #596575; font-size: var(--text-xs); letter-spacing: .06em; text-align: left; text-transform: uppercase; }
td { padding: 12px 9px; border-bottom: 1px solid #e9e5dc; vertical-align: top; }
.score-table td:nth-child(n+2), .score-table th:nth-child(n+2) { text-align: right; }
.disclosure { margin-top: 13px; padding: 11px 13px; border-left: 3px solid #7c8795; background: #f1efe9; color: var(--ink-soft); font-size: var(--text-sm); line-height: 1.5; }

.tour-layer { position: fixed; z-index: 100; inset: 0; overflow: hidden; }
.tour-backdrop { position: absolute; inset: 0; background: transparent; }
.tour-spotlight {
  position: fixed;
  z-index: 101;
  border: 3px solid var(--signal);
  border-radius: 12px;
  box-shadow: 0 0 0 9999px rgba(7, 15, 26, .68), 0 0 0 7px rgba(217, 243, 106, .15);
  pointer-events: none;
  transition: top 180ms ease, left 180ms ease, width 180ms ease, height 180ms ease;
}
.tour-dialog {
  position: fixed;
  z-index: 102;
  width: min(390px, calc(100vw - 28px));
  max-height: calc(100dvh - 28px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, .18);
  border-radius: 14px;
  background: var(--rail);
  color: #fff;
  box-shadow: 0 24px 70px rgba(0,0,0,.34);
}
.tour-dialog-head { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.tour-count { color: var(--signal); font-family: Consolas, monospace; font-size: var(--text-xs); font-weight: 850; letter-spacing: .1em; text-transform: uppercase; }
.tour-close { min-width: 32px; min-height: 32px; padding: 0; border: 1px solid rgba(255,255,255,.16); background: transparent; color: #fff; font-size: 18px; }
.tour-dialog h2 { margin: 14px 0 8px; font-family: Georgia, serif; font-size: 24px; }
#tourTitle:focus-visible { outline: none; }
.tour-dialog p { min-height: 54px; margin: 0; color: #d6dee7; font-size: var(--text-ui); line-height: 1.55; }
.tour-progress { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 4px; margin: 17px 0; }
.tour-progress i { height: 3px; background: #34465b; }
.tour-progress i.on { background: var(--signal); }
.tour-actions { display: flex; align-items: center; gap: 8px; }
.tour-actions button { min-height: 40px; padding: 0 14px; }
.tour-skip { margin-right: auto; background: transparent; color: #aebdcb; }
.tour-skip:hover:not(:disabled) { background: rgba(255,255,255,.07); }
.tour-back { border: 1px solid rgba(255,255,255,.18); background: transparent; }
.tour-next { background: var(--signal); color: var(--signal-ink); }
.tour-next:hover:not(:disabled) { background: #c8e653; }

@media (max-width: 1280px) {
  :root { --header-height: 116px; }
  .appbar-inner {
    flex-wrap: wrap;
    align-content: center;
    gap: 4px 10px;
    padding: 7px 12px;
  }
  .appbar-nav {
    order: 3;
    flex: 0 0 100%;
    justify-content: flex-start;
    gap: 2px;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .appbar-nav::-webkit-scrollbar { display: none; }
  .appbar-nav a { flex: 0 0 auto; padding: 8px 10px; font-size: var(--text-nav); }
  .appbar-actions { margin-left: auto; }
  .header-pack {
    grid-template-columns: minmax(0, 1fr);
    min-width: 170px;
    max-width: 200px;
    padding-block: 5px;
  }
  .header-pack-label { display: none; }
  .header-pack-meta { grid-column: 1; }
}
@media (max-width: 1100px) {
  .opening { grid-template-columns: minmax(0, 1fr) 310px; }
  .workbench-grid, .support-grid { grid-template-columns: 1fr; }
  .support-grid { grid-template-rows: none; row-gap: 14px; }
  .support-card { display: block; grid-row: auto; }
  .input-stage { border-right: 0; border-bottom: 1px solid var(--line); }
}
@media (max-width: 900px) {
  .workspace { padding: 16px; }
  .opening { grid-template-columns: 1fr; min-height: auto; }
  .proof-list { grid-template-columns: repeat(3, 1fr); }
  .proof-item { grid-template-columns: 30px 1fr; }
  .mode-tab { grid-template-columns: 34px 1fr; }
  .mode-badge { display: none; }
  .difference-flow { grid-template-columns: 1fr; }
  .difference-flow div { min-height: 68px; }
  .pack-grid { grid-template-columns: 1fr 1fr; }
  .hash-grid { grid-template-columns: 1fr; }
  .lifecycle { grid-template-columns: 1fr 1fr; }
  .investigation-controls { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .header-pack { min-width: 150px; max-width: 165px; }
  .header-pack b { display: none; }
  .workbench-head { display: grid; align-items: start; }
  .runtime-ready { margin-top: 4px; }
}
@media (max-width: 640px) {
  :root { --header-height: 108px; }
  body { background-size: 22px 22px; }
  .brand-subtitle { display: none; }
  .brand-mark { width: 34px; height: 34px; }
  .tour-trigger { min-height: 40px; padding: 0 10px; font-size: var(--text-ui); }
  .workspace { padding: 10px; }
  .opening { gap: 20px; padding: 24px 19px; border-radius: 13px; }
  .opening h1 { font-size: clamp(31px, 10vw, 42px); letter-spacing: -1.2px; }
  .proof-list { grid-template-columns: 1fr; }
  .trust-chain { grid-template-columns: 1fr 1fr; }
  .trust-chain span:nth-child(2) { border-right: 0; }
  .trust-chain span:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .trust-chain span:nth-child(2)::after { display: none; }
  .workbench-head { display: grid; padding: 21px 17px 16px; }
  .mode-switch { grid-template-columns: 1fr; padding: 0; }
  .mode-pane { min-height: 0; }
  .mode-tab { min-height: 70px; padding: 12px 17px 12px 13px; border-bottom-width: 0; border-left: 4px solid transparent; }
  .mode-tab + .mode-tab { border-left: 4px solid transparent; border-top: 1px solid var(--line); }
  .mode-tab.active { border-left-color: var(--action); }
  .input-stage, .run-stage { padding: 21px 17px; }
  .investigation-controls { padding: 17px; }
  .verify-result { margin: 0 17px 20px; padding: 15px; }
  #results { gap: 10px; margin-top: 24px; }
  .result-sheet, #results > .panel, .results-grid .panel { padding: 20px 17px; }
  .outcome-panel .patch { grid-template-columns: 1fr; }
  #results .outcome-panel .patch > :is(b, .formula-label, .before, .after, p) { grid-column: 1; grid-row: auto; }
  .verify-details, .upload-grid, .grid { grid-template-columns: 1fr; }
  .workflow-strip { grid-template-columns: 1fr; }
  .step { padding: 10px 10px 10px 32px; border-right: 0; border-bottom: 1px solid var(--line); text-align: left; }
  .step::before { top: 13px; }
  .step:last-child { border-bottom: 0; }
  .support-grid { gap: 10px; margin: 0 0 10px; }
  .support-card { padding: 20px 17px; }
  .agent-pair { grid-template-columns: 1fr; }
  .agent-arrow { transform: rotate(90deg); text-align: center; }
  .pack-head, .evidence-head { display: grid; }
  .pack-grid, .lifecycle { grid-template-columns: 1fr; }
  .actions { flex-wrap: wrap; }
  .actions button { width: 100%; }
  .outcome-head { display: grid; }
  .outcome-head .status { justify-self: start; }
  .tour-dialog {
    inset: auto 0 0 0 !important;
    width: 100%;
    max-height: min(72dvh, calc(100dvh - 14px));
    padding: 20px 17px calc(18px + env(safe-area-inset-bottom));
    border-right: 0;
    border-bottom: 0;
    border-left: 0;
    border-radius: 16px 16px 0 0;
  }
}
@media (max-width: 480px) {
  .brand-copy { display: none; }
  .header-pack { min-width: 112px; max-width: 124px; border-left: 0; }
  .header-pack-meta { margin: 0; }
  .desktop-pack-copy { display: none; }
  .mobile-pack-copy { display: inline; }
  .tour-trigger { width: 44px; padding: 0; }
  .tour-trigger-label { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
</head>
<body>
<a class="skip-link" href="#auditWorkspace">Skip to the workbench</a>
<header class="appbar">
  <div class="appbar-inner">
    <div class="brand-wrap">
      <div class="brand-mark" aria-hidden="true">C</div>
      <div class="brand-copy"><span class="brand">ClauseGrid</span><span class="brand-subtitle">Policy assurance workbench</span></div>
    </div>
    <nav class="appbar-nav" aria-label="Primary navigation">
      <a href="#start">Start</a>
      <a href="#auditWorkspace">Run a check</a>
      <a href="#howItWorks">Why ClauseGrid</a>
      <a href="#policyPackSection">Policy Pack</a>
      <a href="#evidenceSection">Evidence</a>
    </nav>
    <div class="appbar-actions">
      <div class="header-pack" aria-label="Active Policy Pack">
        <span class="header-pack-label">Active Policy Pack</span>
        <b id="headerPackVersion">Loading…</b>
        <span class="header-pack-meta"><span id="headerRuleCount">—</span><span class="desktop-pack-copy"> approved rules · 0 AI calls</span><span class="mobile-pack-copy"> rules · 0 AI</span></span>
      </div>
      <button type="button" class="tour-trigger" id="startTour" aria-label="Guided tour"><span class="tour-trigger-label">Guided tour</span></button>
    </div>
  </div>
</header>
<div class="app-shell" id="appShell">
  <main class="workspace" id="mainContent">
    <div class="workspace-inner">
      <section class="opening" id="start" data-tour="welcome" aria-labelledby="openingTitle">
        <div>
          <span class="eyebrow">Policy locked spreadsheet assurance</span>
          <h1 id="openingTitle">Prove every spreadsheet follows the approved policy</h1>
          <p>ClauseGrid checks workbook formulas against rules that qualified people already approved and shows the exact evidence behind every result. It does not ask an AI model to redefine the policy on every recurring audit.</p>
          <div class="opening-actions"><button type="button" class="opening-quick" id="quickAudit" disabled>Run the M10 quick check</button><button type="button" class="opening-tour" id="openingTour">Show me around</button></div>
        </div>
        <aside class="proof-list" aria-label="ClauseGrid assurances">
          <div class="proof-item"><i>✓</i><div><b>Source file unchanged</b><span>All checks run on controlled copies</span></div></div>
          <div class="proof-item"><i id="heroCheckCount">—</i><div><b>Approved checks</b><span>Boundaries and regressions are retained</span></div></div>
          <div class="proof-item"><i>0</i><div><b>AI calls for recurring audits</b><span>Deterministic code owns pass or fail</span></div></div>
        </aside>
      </section>
      <div class="trust-chain" aria-label="Assurance chain"><span>exact policy clause</span><span>human approved examples</span><span>frozen executable pack</span><span>repeatable evidence</span></div>

      <section class="support-grid" id="howItWorks">
        <article class="support-card">
          <span class="section-kicker">Why not just use Claude</span>
          <h2>AI can investigate ClauseGrid preserves the approved answer</h2>
          <p>Claude or another model can read a policy and suggest a formula That is useful ClauseGrid adds the control a chat does not keep by itself qualified people approve concrete examples once and deterministic code repeats those checks the same way every time</p>
          <div class="difference-flow"><div><b>AI proposes</b><span>Find clauses and draft possible interpretations</span></div><div><b>People approve</b><span>Policy and controls owners decide concrete expected behavior</span></div><div><b>Code verifies</b><span>The frozen pack owns recurring pass or fail with no model call</span></div></div>
        </article>
        <article class="support-card">
          <span class="section-kicker">Agent engineering</span>
          <h2>Two agent roles challenge unfamiliar evidence before approval</h2>
          <p>Agents are optional and cannot silently change policy meaning They investigate new workbooks run experiments and challenge proposed repairs Approved tests still control the final pass or fail decision</p>
          <div class="agent-pair"><div class="agent-node"><b>Audit manager</b><span>Reads evidence runs experiments and proposes an exact formula change</span></div><div class="agent-arrow">→</div><div class="agent-node"><b>Fresh context falsifier</b><span>Searches for counterexamples and blocks unsupported proposals</span></div></div>
        </article>
      </section>

      <section class="surface-primary audit-workbench" id="auditWorkspace" data-tour="workspace" aria-labelledby="workspaceTitle">
        <div class="workbench-head">
          <div><span class="section-kicker">Live controlled audit</span><h2 id="workspaceTitle">Choose the kind of check you need</h2></div>
          <span class="runtime-ready" id="runtimeState">Connecting</span>
        </div>
        <div class="mode-switch" id="modeSwitch" data-tour="mode" role="tablist" aria-label="Audit mode">
          <button type="button" class="mode-tab active" id="modeRecurring" role="tab" aria-selected="true" aria-controls="recurringPane">
            <span class="mode-index">01</span><span><span class="mode-title">Verify a known workbook</span><span class="mode-description">Replay approved rules on a controlled template</span></span><span class="mode-badge">0 AI calls</span>
          </button>
          <button type="button" class="mode-tab" id="modeInvestigation" role="tab" aria-selected="false" aria-controls="investigationPane">
            <span class="mode-index">02</span><span><span class="mode-title">Investigate new evidence</span><span class="mode-description">Use agents for unfamiliar workbooks or diagnosis</span></span><span class="mode-badge">AI assisted</span>
          </button>
        </div>

        <section class="mode-pane" id="recurringPane" role="tabpanel" aria-labelledby="modeRecurring">
          <div class="workbench-grid">
            <div class="input-stage" data-tour="pack">
              <span class="stage-label">Approved control</span>
              <div class="pack-snapshot" id="packAnchor">
                <div><span>Frozen Policy Pack</span><b id="inlinePackVersion">Loading approved version…</b></div>
                <div class="pack-rule-count"><span id="inlineRuleCount">—</span> rules<br>hash locked</div>
              </div>
              <label for="verifyCase">Controlled workbook version</label>
              <select id="verifyCase"></select>
              <p class="field-note">Choose M10 for the flagship demo. It contains a subtle waiver scope error that one approved regression check catches.</p>
            </div>
            <div class="run-stage" data-tour="run">
              <span class="stage-label">Deterministic verification</span>
              <h3>Replay the same approved meaning</h3>
              <p>ClauseGrid calculates the expected result with its independent rule engine, executes the workbook separately, then compares both.</p>
              <div class="run-checks">
                <div class="run-check"><i>✓</i><span>Runs generated boundary and retained regression cases</span></div>
                <div class="run-check"><i>✓</i><span>Never sends the workbook to a model</span></div>
                <div class="run-check"><i>✓</i><span>Never edits the source workbook</span></div>
              </div>
              <button class="primary-run" id="verifyPack">Run approved checks</button>
              <div class="run-note" id="verifyMessage" role="status" aria-live="polite">Ready to replay the approved suite.</div>
            </div>
          </div>
          <div class="verify-result" id="verificationResult" data-tour="result" role="region" aria-label="Deterministic verification evidence" tabindex="-1">
            <div class="result-empty"><div><b>Your evidence will appear here</b><span>Run the approved checks to see the verdict expected and actual values affected rules and reproducible hashes</span></div></div>
          </div>
        </section>

        <section class="mode-pane hidden" id="investigationPane" role="tabpanel" aria-labelledby="modeInvestigation">
          <div class="workbench-grid">
            <div class="input-stage" id="sourceChooser" data-tour="input">
              <span class="stage-label">Evidence source</span>
              <div class="runtime-label"><label>Optional server side AI runtime</label><code id="runtime">Loading configuration…</code></div>
              <div class="source-tabs" role="tablist" aria-label="Audit input">
                <button type="button" class="source-tab active" id="benchmarkTab" role="tab" aria-selected="true" aria-controls="benchmarkSource">Controlled benchmark</button>
                <button type="button" class="source-tab" id="uploadTab" role="tab" aria-selected="false" aria-controls="uploadSource">Upload workbook and policy</button>
              </div>
              <div id="benchmarkSource" role="tabpanel" aria-labelledby="benchmarkTab"><label for="case">Synthetic benchmark workbook</label><select id="case"></select><p class="field-note">Use the controlled benchmark to see the complete investigation flow without uploading company data.</p></div>
              <div id="uploadSource" class="hidden" role="tabpanel" aria-labelledby="uploadTab">
                <div class="upload-grid">
                  <div class="file-box"><label for="workbookFile">Compatible xlsx workbook</label><input id="workbookFile" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"></div>
                  <div class="file-box"><label for="policyFile">Matching policy pdf</label><input id="policyFile" type="file" accept=".pdf,application/pdf"></div>
                </div>
                <label class="consent"><input id="uploadConsent" type="checkbox"><span>I confirm these files contain public synthetic or approved data Selected cells formulas and policy passages may be sent to <b id="consentProvider">the managed AI service</b> and retained in the evidence trace</span></label>
                <p class="profile-note">Supported profile calculation focused xlsx only No macros external links drawings comments embedded objects Power Query defined names shared or array formulas conditional formatting data validation worksheet extensions cross sheet formula chains or functions outside the supported arithmetic and lookup set Temporary input copies expire after 30 minutes</p>
                <div id="uploadManifest" class="upload-manifest hidden"></div>
              </div>
            </div>
            <div class="run-stage" id="investigationRun">
              <span class="stage-label">Agent investigation</span>
              <h3>Find evidence test a theory then challenge it</h3>
              <p>The manager reads policy evidence and runs workbook experiments A fresh context falsifier searches for counterexamples before any repair can reach human review</p>
              <div class="run-checks">
                <div class="run-check"><i>1</i><span>Manager investigates and proposes an exact change</span></div>
                <div class="run-check"><i>2</i><span>Independent falsifier tries to break the proposal</span></div>
                <div class="run-check"><i>3</i><span>Uncertainty fails closed to human review</span></div>
              </div>
            </div>
            <div class="investigation-controls" data-tour="run-ai">
              <div class="actions"><button id="audit">Run AI investigation</button><button class="secondary" id="reset">Reset</button></div>
              <div class="run-status">
                <div class="status-line"><span class="status-dot" id="statusDot"></span><div id="message" role="status" aria-live="polite">M10 demonstrates a subtle waiver scope failure An AI investigation can take several minutes</div></div>
                <div class="progress-track" role="progressbar" aria-label="AI investigation progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="progress-bar" id="progressBar"></div></div>
                <div class="status-meta" id="progressMeta">Ready · waiting for a case</div>
              </div>
            </div>
          </div>
        </section>

        <div class="workflow-strip hidden" id="auditFlow" data-tour="trail" aria-label="Investigation evidence trail">
          <div class="step on">1 · Inputs</div><div class="step" id="s2">2 · Evidence</div><div class="step" id="s3">3 · Experiments</div><div class="step" id="s4">4 · Falsification</div><div class="step" id="s5">5 · Review</div>
        </div>
      </section>

      <section id="results" class="hidden" tabindex="-1">
        <div class="results-grid"><div class="panel decision-panel outcome-panel" id="outcomePanel"><div class="outcome-head"><div><span class="outcome-label">AI investigation result</span><h2 id="outcomeTitle">Investigation result</h2></div><span id="outcomeBadge" class="status ABSTAIN">Review</span></div><div id="diagnosis"></div><p id="outcomeFoot" class="outcome-foot"></p></div></div>
        <details class="panel result-detail citation-panel" open><summary>Policy evidence</summary><div id="citations"></div></details>
        <details class="panel result-detail"><summary>Reproducible sandbox experiments</summary><div style="overflow:auto"><table><thead><tr><th>ID</th><th>Actor</th><th>Purpose</th><th>Observed result</th></tr></thead><tbody id="experiments"></tbody></table></div></details>
        <details class="panel result-detail"><summary>Independent falsifier verdict</summary><div id="falsifier"></div></details>
        <div class="panel approval hidden" id="approvalPanel"><h2>Private human approval</h2><p>This applies only to the exact copied workbook repair above It does not approve or change Policy Pack meaning Review the citations experiments falsifier result and proposal hash before authorizing a copy</p><div class="grid"><div><label for="reviewer">Reviewer label</label><input id="reviewer" value="hackathon-reviewer"></div><div><label>Source SHA 256</label><code id="sourceHash"></code><label style="margin-top:12px">Proposal hash</label><code id="proposalHash"></code></div></div><div class="actions"><button id="approve">Approve exact repair proposal</button></div><div id="approvalMessage" class="small" role="status" aria-live="polite"></div><div id="downloads" class="downloads"></div></div>
      </section>

      <details class="surface-primary support-details" id="policyPackSection">
        <summary>Inspect the active controlled Policy Pack</summary>
        <div class="details-body">
          <div class="pack-head"><div><span class="section-kicker">Approved meaning that can be replayed</span><h2>One frozen release binds rules tests mappings and engines</h2><p>The public deployment exposes one synthetic supplier rebate pack so the complete verification mechanism is testable Its governance view is read only Real version changes require authenticated reviewers durable pack history and an audit registry</p></div><span class="zero-badge">Recurring audit · 0 AI calls</span></div>
          <div class="pack-grid"><div class="pack-metric"><span>Policy version</span><b id="packVersion">Loading…</b></div><div class="pack-metric"><span>Approved rules</span><b id="packRules">—</b></div><div class="pack-metric"><span>Generated tests</span><b id="packGenerated">—</b></div><div class="pack-metric"><span>Regression tests</span><b id="packRegressions">—</b></div></div>
          <div class="hash-grid"><div class="hash-item"><span>Policy Pack hash</span><code id="packHash">—</code></div><div class="hash-item"><span>Test suite hash</span><code id="suiteHash">—</code></div><div class="hash-item"><span>Workbook mapping hash</span><code id="mappingHash">—</code></div></div>
          <div class="lifecycle" aria-label="Required production policy change lifecycle"><div class="lifecycle-step"><b>1 · Review real behavior</b>Save the smallest real edge case</div><div class="lifecycle-step"><b>2 · Publish an immutable pack</b>Classify and compare the exact behavior</div><div class="lifecycle-step"><b>3 · Audit without an LLM</b>Replay the frozen rules and tests</div><div class="lifecycle-step"><b>4 · Keep every defect class</b>Retain every reviewed regression</div><div class="lifecycle-step"><b>5 · Supersede safely</b>Publish a successor and find affected audits</div></div>
          <div class="governance-warning" id="packWarning">Approval means an authorized interpretation not proof that the policy can never be wrong Production correction requires durable version and audit history The public demo is read only</div>
        </div>
      </details>

      <details class="surface-primary support-details" id="evidenceSection">
        <summary>View frozen engineering evidence and baseline comparison</summary>
        <div class="details-body">
          <div class="evidence-head"><div><span class="section-kicker">Measured deterministic layer</span><h2>Legacy deterministic regression evidence</h2><p>This frozen scorecard validates the deterministic workbook layer It is not model agent performance</p></div><div class="benchmark-badge" id="benchmarkBadge">Loading benchmark…</div></div>
          <div style="overflow:auto"><table class="score-table"><thead><tr><th>Metric</th><th>Legacy baseline</th><th>Legacy advanced</th><th>Change</th></tr></thead><tbody id="scorecard"></tbody></table></div><div class="disclosure" id="measurementDisclosure"></div>
        </div>
      </details>
    </div>
  </main>
</div>

<div class="tour-layer hidden" id="tourLayer" aria-hidden="true">
  <div class="tour-backdrop"></div>
  <div class="tour-spotlight" id="tourSpotlight" aria-hidden="true"></div>
  <section class="tour-dialog" id="tourDialog" role="dialog" aria-modal="true" aria-labelledby="tourTitle" aria-describedby="tourBody" tabindex="-1">
    <div class="tour-dialog-head"><span class="tour-count" id="tourCount">Step 1 of 7</span><button type="button" class="tour-close" id="tourClose" aria-label="Close guided tour">×</button></div>
    <h2 id="tourTitle" tabindex="-1">Welcome to ClauseGrid</h2>
    <p id="tourBody"></p>
    <div class="tour-progress" id="tourProgress" aria-hidden="true"></div>
    <div class="tour-actions"><button type="button" class="tour-skip" id="tourSkip">Skip tour</button><button type="button" class="tour-back" id="tourBack">Back</button><button type="button" class="tour-next" id="tourNext">Next</button></div>
  </section>
</div>
"""


_PAGE_AFTER_SCRIPT = r"""
<script>
const TOUR_STORAGE_KEY='clausegrid.guidedTour.v1';
let workspaceMode='recurring';
let tourIndex=0;
let tourTarget=null;
let tourReturnFocus=null;
let tourResizeObserver=null;
let tourStartMode='recurring';
let tourActive=false;
let tourTimer=null;
let tourMobileAdjustedIndex=-1;

const TOUR_STEPS=[
  {target:'[data-tour="welcome"]',title:'Start with the promise',body:'ClauseGrid checks spreadsheet formulas against approved policy meaning and leaves the source file unchanged'},
  {target:'[data-tour="mode"]',title:'Choose one of two clear paths',body:'Use recurring verification for a known workbook or switch to AI assisted investigation for unfamiliar evidence'},
  {target:'[data-tour="pack"]',title:'The approved pack defines correct behavior',body:'The frozen pack binds the cited rules examples tests workbook mapping and deterministic engines to one version',mode:'recurring'},
  {target:'[data-tour="run"]',title:'Replay every approved check',body:'This recurring audit runs deterministic code with zero model calls and never modifies the original workbook',mode:'recurring'},
  {target:'[data-tour="result"]',title:'Read the verdict and exact difference',body:'The result shows which approved check failed the expected and actual cell values the affected rules and reproducible evidence hashes',mode:'recurring'},
  {target:'[data-tour="input"]',title:'AI is optional and separated',body:'For a new workbook choose the controlled benchmark or upload an authorized workbook with its matching policy',mode:'investigation'},
  {target:'[data-tour="trail"]',title:'Follow the complete evidence trail',body:'The investigation records evidence experiments falsification and human review so the result can be inspected instead of merely trusted',mode:'investigation'}
];

function setWorkspaceMode(mode,options={}){
  workspaceMode=mode==='investigation'?'investigation':'recurring';
  const investigating=workspaceMode==='investigation';
  $('recurringPane').classList.toggle('hidden',investigating);
  $('investigationPane').classList.toggle('hidden',!investigating);
  $('modeRecurring').classList.toggle('active',!investigating);
  $('modeInvestigation').classList.toggle('active',investigating);
  $('modeRecurring').setAttribute('aria-selected',String(!investigating));
  $('modeInvestigation').setAttribute('aria-selected',String(investigating));
  $('modeRecurring').tabIndex=investigating?-1:0;
  $('modeInvestigation').tabIndex=investigating?0:-1;
  $('auditFlow').classList.toggle('hidden',!investigating);
  const hasAgentResult=$('results').dataset.ready==='true';
  $('results').classList.toggle('hidden',!investigating||!hasAgentResult);
  if(options.focus)$((investigating?'modeInvestigation':'modeRecurring')).focus();
}

const originalSetInputMode=setInputMode;
setInputMode=function(mode){
  originalSetInputMode(mode);
  const custom=inputMode==='upload';
  $('benchmarkTab').tabIndex=custom?-1:0;
  $('uploadTab').tabIndex=custom?0:-1;
};

const originalRenderPack=renderPack;
renderPack=function(pack){
  originalRenderPack(pack);
  const version=`${pack.policy_id} · v${pack.version}`;
  $('inlinePackVersion').textContent=version;
  $('inlineRuleCount').textContent=String(pack.rule_count);
  $('headerPackVersion').textContent=version;
  $('headerRuleCount').textContent=String(pack.rule_count);
  $('heroCheckCount').textContent=String(pack.generated_test_count+pack.regression_test_count);
};

const originalRenderVerification=renderVerification;
renderVerification=function(data){
  originalRenderVerification(data);
  $('verificationResult').style.borderLeftColor=data.verification.decision==='FAIL'?'var(--fail)':data.verification.decision==='INCONCLUSIVE'?'var(--warn)':'var(--pass)';
};

const originalRender=render;
render=function(data){
  setWorkspaceMode('investigation');
  originalRender(data);
  $('results').dataset.ready='true';
  $('results').classList.remove('hidden');
};

function tourDisabledByQuery(){return new URLSearchParams(location.search).get('tour')==='off'}
function tourStored(){try{return localStorage.getItem(TOUR_STORAGE_KEY)!==null}catch{return false}}
function storeTour(state){try{localStorage.setItem(TOUR_STORAGE_KEY,state)}catch{}}
function visibleTarget(selector){const element=document.querySelector(selector);if(!element)return null;const style=getComputedStyle(element);if(style.display==='none'||style.visibility==='hidden')return null;return element}
function tourFocusables(){return [...$('tourDialog').querySelectorAll('button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])')]}

function positionTour(){
  if(!tourTarget||$('tourLayer').classList.contains('hidden'))return;
  const rect=tourTarget.getBoundingClientRect();
  const pad=8;
  const top=Math.max(8,rect.top-pad);
  const left=Math.max(8,rect.left-pad);
  const right=Math.min(innerWidth-8,rect.right+pad);
  const bottom=Math.min(innerHeight-8,rect.bottom+pad);
  Object.assign($('tourSpotlight').style,{top:`${top}px`,left:`${left}px`,width:`${Math.max(40,right-left)}px`,height:`${Math.max(40,bottom-top)}px`});
  const dialog=$('tourDialog');
  if(innerWidth<=640){
    const sheetTop=innerHeight-dialog.offsetHeight-16;
    if(tourMobileAdjustedIndex!==tourIndex&&rect.bottom>sheetTop){
      tourMobileAdjustedIndex=tourIndex;
      window.scrollBy({top:rect.bottom-sheetTop+18,behavior:'auto'});
      requestAnimationFrame(positionTour);
    }
    return;
  }
  const width=Math.min(390,innerWidth-28);
  const height=dialog.offsetHeight||300;
  const spaceBelow=innerHeight-bottom;
  const spaceAbove=top;
  const spaceRight=innerWidth-right;
  const spaceLeft=left;
  let proposedTop;
  let proposedLeft;
  if(spaceBelow>=height+24){proposedTop=bottom+14;proposedLeft=Math.min(Math.max(14,left),innerWidth-width-14)}
  else if(spaceAbove>=height+24){proposedTop=top-height-14;proposedLeft=Math.min(Math.max(14,left),innerWidth-width-14)}
  else if(spaceRight>=width+24){proposedTop=Math.min(Math.max(14,top+(bottom-top-height)/2),innerHeight-height-14);proposedLeft=right+14}
  else if(spaceLeft>=width+24){proposedTop=Math.min(Math.max(14,top+(bottom-top-height)/2),innerHeight-height-14);proposedLeft=left-width-14}
  else{proposedTop=Math.max(14,Math.min(innerHeight-height-14,bottom+14));proposedLeft=Math.min(Math.max(14,left),innerWidth-width-14)}
  Object.assign(dialog.style,{top:`${proposedTop}px`,left:`${proposedLeft}px`,right:'auto',bottom:'auto'});
}

function renderTourStep(direction=1){
  let step=TOUR_STEPS[tourIndex];
  if(!step)return finishTour('completed');
  if(step.mode)setWorkspaceMode(step.mode);
  tourTarget=visibleTarget(step.target);
  if(!tourTarget){
    const next=tourIndex+direction;
    if(next<0)return;
    if(next>=TOUR_STEPS.length)return finishTour('completed');
    tourIndex=next;
    return renderTourStep(direction);
  }
  $('tourCount').textContent=`Step ${tourIndex+1} of ${TOUR_STEPS.length}`;
  tourMobileAdjustedIndex=-1;
  $('tourTitle').textContent=step.title;
  $('tourBody').textContent=step.body;
  $('tourBack').disabled=tourIndex===0;
  $('tourNext').textContent=tourIndex===TOUR_STEPS.length-1?'Finish':'Next';
  $('tourProgress').replaceChildren();
  for(let index=0;index<TOUR_STEPS.length;index++){const item=document.createElement('i');item.classList.toggle('on',index<=tourIndex);$('tourProgress').append(item)}
  tourTarget.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center',inline:'nearest'});
  if(tourResizeObserver)tourResizeObserver.disconnect();
  tourResizeObserver=new ResizeObserver(()=>positionTour());
  tourResizeObserver.observe(tourTarget);
  requestAnimationFrame(()=>requestAnimationFrame(()=>{positionTour();$('tourTitle').focus()}));
}

function startGuidedTour(){
  if(tourTimer!==null){clearTimeout(tourTimer);tourTimer=null}
  if(tourActive)return;
  tourActive=true;
  tourReturnFocus=document.activeElement;
  tourStartMode=workspaceMode;
  tourIndex=0;
  setWorkspaceMode('recurring');
  $('tourLayer').classList.remove('hidden');
  $('tourLayer').setAttribute('aria-hidden','false');
  $('appShell').inert=true;
  document.querySelector('.appbar').inert=true;
  document.querySelector('.skip-link').inert=true;
  document.body.style.overflow='hidden';
  renderTourStep();
}

function finishTour(state){
  if(!tourActive)return;
  tourActive=false;
  storeTour(state);
  $('tourLayer').classList.add('hidden');
  $('tourLayer').setAttribute('aria-hidden','true');
  $('appShell').inert=false;
  document.querySelector('.appbar').inert=false;
  document.querySelector('.skip-link').inert=false;
  document.body.style.overflow='';
  if(tourResizeObserver)tourResizeObserver.disconnect();
  tourResizeObserver=null;
  tourTarget=null;
  setWorkspaceMode(tourStartMode);
  const focusableReturn=tourReturnFocus instanceof HTMLElement&&tourReturnFocus.isConnected&&tourReturnFocus.matches('button,a[href],input,select,[tabindex]:not([tabindex="-1"])');
  (focusableReturn?tourReturnFocus:$('startTour')).focus();
}

function scheduleAutoTour(){
  if(tourDisabledByQuery()||tourStored())return;
  tourTimer=window.setTimeout(()=>{tourTimer=null;startGuidedTour()},450);
}

function moveTabFocus(event,tabs,activate){
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  const available=tabs.filter(tab=>!tab.disabled&&!tab.classList.contains('hidden'));
  if(!available.length)return;
  event.preventDefault();
  const current=Math.max(0,available.indexOf(document.activeElement));
  const next=event.key==='Home'?0:event.key==='End'?available.length-1:event.key==='ArrowRight'?(current+1)%available.length:(current-1+available.length)%available.length;
  activate(available[next]);
  available[next].focus();
}

$('modeRecurring').onclick=()=>setWorkspaceMode('recurring',{focus:true});
$('modeInvestigation').onclick=()=>setWorkspaceMode('investigation',{focus:true});
$('modeSwitch').addEventListener('keydown',event=>moveTabFocus(event,[$('modeRecurring'),$('modeInvestigation')],tab=>setWorkspaceMode(tab===$('modeInvestigation')?'investigation':'recurring')));
$('benchmarkTab').tabIndex=0;
$('uploadTab').tabIndex=-1;
$('benchmarkTab').parentElement.addEventListener('keydown',event=>moveTabFocus(event,[$('benchmarkTab'),$('uploadTab')],tab=>setInputMode(tab===$('uploadTab')?'upload':'benchmark')));
$('startTour').onclick=startGuidedTour;
$('openingTour').onclick=startGuidedTour;
$('quickAudit').onclick=async()=>{
  setWorkspaceMode('recurring');
  $('verifyCase').value='M10';
  $('quickAudit').disabled=true;
  $('quickAudit').textContent='Checking M10…';
  $('auditWorkspace').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
  try{await $('verifyPack').onclick();$('verificationResult').scrollIntoView({behavior:'smooth',block:'center'})}
  finally{$('quickAudit').disabled=false;$('quickAudit').textContent='Run the M10 quick check'}
};
const legacyAuditClick=$('audit').onclick;
$('audit').onclick=async event=>{
  setWorkspaceMode('investigation');
  $('modeRecurring').disabled=true;
  $('modeInvestigation').disabled=true;
  try{return await legacyAuditClick.call($('audit'),event)}
  finally{$('modeRecurring').disabled=false;$('modeInvestigation').disabled=false;setWorkspaceMode('investigation')}
};
$('tourClose').onclick=()=>finishTour('dismissed');
$('tourSkip').onclick=()=>finishTour('skipped');
$('tourBack').onclick=()=>{if(tourIndex>0){tourIndex-=1;renderTourStep(-1)}};
$('tourNext').onclick=()=>{if(tourIndex<TOUR_STEPS.length-1){tourIndex+=1;renderTourStep(1)}else finishTour('completed')};
window.addEventListener('resize',positionTour);
window.addEventListener('scroll',positionTour,true);
document.addEventListener('keydown',event=>{
  if($('tourLayer').classList.contains('hidden'))return;
  if(event.key==='Escape'){event.preventDefault();finishTour('dismissed');return}
  if(event.key==='ArrowRight'){event.preventDefault();$('tourNext').click();return}
  if(event.key==='ArrowLeft'){event.preventDefault();$('tourBack').click();return}
  if(event.key!=='Tab')return;
  const focusable=tourFocusables();
  if(!focusable.length)return;
  const first=focusable[0],last=focusable[focusable.length-1];
  if(!focusable.includes(document.activeElement)){event.preventDefault();(event.shiftKey?last:first).focus()}
  else if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
});

setWorkspaceMode('recurring');
init().then(()=>{
  $('runtime').textContent='Managed private AI runtime';
  $('runtimeState').textContent='Runtime ready';
  $('quickAudit').disabled=false;
  TOUR_STEPS.find(step=>step.target==='[data-tour="input"]').body=runtimeConfig.uploads_enabled?'Choose the controlled benchmark or upload an authorized workbook with its matching policy':'Choose the controlled benchmark Public file uploads are disabled on this deployment';
  scheduleAutoTour();
}).catch(error=>{
  $('runtimeState').textContent='Runtime unavailable';
  $('runtimeState').classList.add('unavailable');
  $('message').textContent=error.message;
  $('message').className='danger';
  $('verifyMessage').textContent=error.message;
  $('verifyMessage').className='danger';
});
</script>
</body>
</html>"""


def build_html(legacy_script: str) -> str:
    """Combine the existing behavior with the redesigned workbench presentation."""

    return (
        _PAGE_BEFORE_SCRIPT + "\n<script>\n" + legacy_script + "\n</script>\n" + _PAGE_AFTER_SCRIPT
    )
