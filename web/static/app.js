const CHECK_LABELS = {
  identity_match: "SKU identity", quantity: "Quantity", carton_count: "Carton count",
  units_per_carton: "Units per carton", variant: "Colour / variant",
  carton_damage: "Carton condition", unit_damage: "Product condition", components: "Components",
};
const ICONS = {
  dashboard: '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="10" width="8" height="11" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/>',
  inbound: '<path d="M12 3v12m-5-5 5 5 5-5"/><path d="M4 19h16"/>',
  box: '<path d="m3.5 7.5 8.5-4 8.5 4v9l-8.5 4-8.5-4z"/><path d="m3.8 7.6 8.2 4 8.2-4M12 11.6v8.7"/>',
  check: '<path d="m5 12 4 4L19 6"/><path d="M20 12v7H4V5h10"/>',
  alert: '<path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4m0 3h.01"/>',
  file: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6m-6 4h6"/>',
  catalog: '<path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="m4 12 8 4 8-4M4 17l8 4 8-4"/>',
  chart: '<path d="M4 20V10m5 10V4m6 16v-7m5 7V7"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.6a8 8 0 0 1-1.5.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.5-.9l-1.7.6-1.4-2.4 1.4-1.1a7 7 0 0 1 0-1.8l-1.4-1.1 1.4-2.4 1.7.6a8 8 0 0 1 1.5-.9l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.5.9l1.7-.6 1.4 2.4-1.4 1.1a7 7 0 0 1 0 1.7Z" transform="translate(-2 -1)"/>',
};
const el = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value ?? "—").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const safeNum = value => value === "" || value == null ? null : Number(value);
const timeLabel = value => value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";
const decisionClass = value => String(value || "UNCERTAIN").toLowerCase().replace(/[^a-z_]/g, "_");
const pageNames = { overview:"Overview", receipts:"Receipts", shipments:"Shipments", inspections:"Inspections", review:"Review queue", evidence:"Evidence", catalog:"Product catalogue", evaluation:"Quality lab", settings:"Settings", import:"Import manifest", new:"New receipt" };
let records = [];
let workflows = [];
let health = {};
let selectedPage = "overview";
let selectedRecord = null;
let selectedWorkflow = null;
let searchTerm = "";
let activeFilter = "ALL";

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
  return data;
}

function icon(name) { return `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`; }
function workflowFor(record) { return workflows.find(item => item.org_id === record.org_id && item.subject_id === record.unit_id) || null; }
function decisionForWorkflow(workflow) {
  const outcome = workflow?.final_outcome?.outcome || workflow?.status || "PENDING";
  if (["CLEAN", "PASS"].includes(outcome)) return "PASS";
  if (["EXCEPTION", "CLAIM_RECOMMENDED", "FAIL"].includes(outcome)) return "EXCEPTION";
  if (["NEEDS_REVIEW", "INCOMPLETE", "UNCERTAIN", "PENDING", "BLOCKED", "FAILED"].includes(outcome)) return "UNCERTAIN";
  return outcome;
}
function effectiveDecision(record) {
  const workflow = workflowFor(record);
  return workflow ? decisionForWorkflow(workflow) : record.decision || "PENDING";
}
function decisions() { return records.map(record => effectiveDecision(record)); }
function fmtDecision(value) {
  const normalized = String(value || "PENDING").replaceAll("_", " ");
  return `<span class="status-pill ${decisionClass(value)}">${esc(normalized)}</span>`;
}
function pageTitle(title, subtitle, action = "") {
  return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-actions">${action}</div></div>`;
}
function metricLine(label, value, note, tone = "") {
  return `<div class="summary-metric ${tone}"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`;
}
function filteredRecords(source = records) {
  let result = source;
  if (activeFilter !== "ALL") result = result.filter(record => effectiveDecision(record) === activeFilter);
  if (searchTerm) {
    const q = searchTerm.toLowerCase();
    result = result.filter(record => [record.unit_id, record.record_id, record.po_number, record.supplier, record.sku, record.asin, record.product_title].some(value => String(value || "").toLowerCase().includes(q)));
  }
  return result;
}
function recordTable(title, source = records, options = {}) {
  const rows = filteredRecords(source);
  return `<section class="panel table-panel"><div class="panel-head"><div><h2>${esc(title)}</h2><p>${rows.length} records · sample data from receiving_sample.csv</p></div>${options.action || ""}</div>
    <div class="table-wrap"><table class="record-table"><thead><tr><th>Unit / PO</th><th>Supplier</th><th>Product</th><th>Expected / received</th><th>Condition</th><th>Decision</th></tr></thead><tbody>
    ${rows.length ? rows.map(record => `<tr tabindex="0" role="button" data-record="${esc(record.record_id)}"><td><strong>${esc(record.unit_id)}</strong><small>${esc(record.po_number)} · line ${esc(record.po_line)}</small></td><td>${esc(record.supplier)}</td><td><strong>${esc(record.sku)}</strong><small>${esc(record.product_title)}</small></td><td><strong>${esc(record.qty_ordered)} / ${esc(record.qty_received)}</strong><small>${esc(record.cartons_received)} of ${esc(record.cartons_ordered)} cartons</small></td><td>${conditionLabel(record)}</td><td>${fmtDecision(effectiveDecision(record))}</td></tr>`).join("") : `<tr><td colspan="6"><div class="empty-state"><strong>No matching receipts</strong><p>Clear the filters or search a different PO, SKU, unit, or supplier.</p></div></td></tr>`}
    </tbody></table></div></section>`;
}
function conditionLabel(record) {
  const labels = [record.carton_damage, record.unit_damage].filter(value => value && value !== "none" && value !== "uncertain");
  const flags = String(record.quality_flags || "").split(";").map(value => value.trim()).filter(Boolean);
  const items = [...new Set([...labels, ...flags])];
  return items.length ? `<span class="condition-flag">${esc(items.map(value => value.replaceAll("_", " ")).join(" · "))}</span>` : `<span class="muted">No issue flagged</span>`;
}
function decisionStats(source = records) {
  const values = source.map(effectiveDecision);
  return { total: source.length, pass: values.filter(v => v === "PASS" || v === "CLEAN").length, exception: values.filter(v => ["EXCEPTION", "CLAIM_RECOMMENDED"].includes(v)).length, uncertain: values.filter(v => ["UNCERTAIN", "NEEDS_REVIEW", "INCOMPLETE", "PENDING"].includes(v)).length };
}
function dashboard() {
  const stats = decisionStats();
  const orchestrationStatus = health.status === "ok" ? "Ready" : health.status === "degraded" ? "Degraded" : "Checking";
  const orchestrationClass = health.status === "ok" ? "" : health.status === "degraded" ? "degraded" : "pending";
  const queue = records.filter(record => ["EXCEPTION", "UNCERTAIN"].includes(effectiveDecision(record))).slice(0, 5);
  return `${pageTitle("Receiving overview", "Verify every arrival against its purchase order, then keep the decision and evidence together.", `<button class="button-primary" data-action="new-receipt">Record receipt</button>`)}
    <div class="summary-strip">${metricLine("Sample receipts", stats.total, "Rows from the supplied dataset")}${metricLine("Pass", stats.pass, "No exception in fixture checks", "good")}${metricLine("Exceptions", stats.exception, "A failed receiving check", stats.exception ? "bad" : "")}${metricLine("Uncertain", stats.uncertain, "Needs evidence or review", stats.uncertain ? "warn" : "")}</div>
    <div class="dashboard-grid"><div class="main-column">${recordTable("Recent receipts", records.slice(0, 12), { action: `<button class="text-button" data-go="receipts">View all receipts</button>` })}${recordTable("Needs attention", queue, { action: `<button class="text-button" data-go="review">Open review queue</button>` })}</div>
      <aside class="side-column"><section class="panel coverage-panel"><div class="panel-head"><div><h2>Receiving inspection</h2><p>Eight checks · one decision</p></div></div><ol class="check-list">${Object.values(CHECK_LABELS).map((label, index) => `<li><span class="check-index">${String(index + 1).padStart(2, "0")}</span><span>${esc(label)}</span></li>`).join("")}</ol><p class="source-note">Evidence comes from the attached fixture or submitted photos. Fixture values are labeled and never presented as live image analysis.</p></section>
      <section class="panel orchestration-panel"><div class="panel-head"><div><h2>Orchestration</h2><p>Shared agent contract</p></div><span class="live-tag ${orchestrationClass}" role="status"><i></i> ${esc(orchestrationStatus)}</span></div><div class="orchestrator-flow"><span>Receipt</span><b>→</b><strong>Receiving Manager</strong><b>→</b><span>Evidence record</span></div><p class="source-note">One agent is active in this project. The flow contract is ready for other projects to add their own compatible agents.</p></section></aside></div>`;
}
function receiptsPage() {
  return `${pageTitle("Receipts", "Incoming product records and their receiving decisions.", `<button class="button-primary" data-action="new-receipt">Record receipt</button>`)}${filtersMarkup()}${recordTable("Receiving ledger")}`;
}
function inspectionsPage() {
  return `${pageTitle("Inspections", "Review the expected values, observed fixture data, and all eight decision checks.")}${filtersMarkup()}${recordTable("Inspection records")}`;
}
function reviewPage() {
  const source = records.filter(record => ["EXCEPTION", "UNCERTAIN"].includes(effectiveDecision(record)));
  return `${pageTitle("Review queue", "Failed checks and unresolved evidence stay visible until a reviewer can act.")}${filtersMarkup()}${recordTable("Requires attention", source)}`;
}
function filtersMarkup() {
  return `<div class="filter-bar"><label class="filter-search"><span>Search this list</span><input id="list-search" type="search" value="${esc(searchTerm)}" placeholder="PO, SKU, unit, supplier" /></label><label><span>Decision</span><select id="decision-filter"><option value="ALL">All decisions</option><option value="PASS">Pass</option><option value="EXCEPTION">Exception</option><option value="UNCERTAIN">Uncertain</option><option value="PENDING">Pending</option></select></label><button class="button-secondary" data-action="clear-filters">Clear filters</button></div>`;
}
function shipmentsPage() {
  const byPo = new Map();
  for (const row of records) {
    const item = byPo.get(row.po_number) || { po_number: row.po_number, supplier: row.supplier, units: 0, expected: 0, exceptions: 0, receipts: 0, date: row.captured_at };
    item.units += Number(row.qty_received || 0); item.expected += Number(row.qty_ordered || 0); item.receipts += 1;
    if (["EXCEPTION", "UNCERTAIN"].includes(effectiveDecision(row))) item.exceptions += 1;
    if (String(row.captured_at || "").localeCompare(item.date || "") > 0) item.date = row.captured_at;
    byPo.set(row.po_number, item);
  }
  const rows = [...byPo.values()].sort((a,b) => String(b.date).localeCompare(String(a.date)));
  return `${pageTitle("Shipments", "Purchase orders and inbound manifests represented in the supplied receiving records.", `<button class="button-secondary" data-action="import-manifest">Import manifest</button>`)}
    <section class="panel table-panel"><div class="panel-head"><div><h2>Purchase orders</h2><p>${rows.length} purchase orders · grouped from the receiving sample</p></div></div><div class="table-wrap"><table class="record-table"><thead><tr><th>Purchase order</th><th>Supplier</th><th>Receipt lines</th><th>Units expected / received</th><th>Needs attention</th><th>Latest capture</th></tr></thead><tbody>${rows.map(item => `<tr tabindex="0" role="button" data-po="${esc(item.po_number)}"><td><strong>${esc(item.po_number)}</strong></td><td>${esc(item.supplier)}</td><td>${item.receipts}</td><td><strong>${item.expected} / ${item.units}</strong></td><td>${item.exceptions}</td><td>${timeLabel(item.date)}</td></tr>`).join("")}</tbody></table></div></section>`;
}
function catalogPage() {
  const products = new Map();
  records.forEach(row => { if (!products.has(row.sku)) products.set(row.sku, row); });
  const items = [...products.values()].sort((a,b) => String(a.sku).localeCompare(String(b.sku)));
  return `${pageTitle("Product catalogue", "Purchase-order specifications and component expectations from the supplied records.")}
    <section class="panel table-panel"><div class="panel-head"><div><h2>Referenced products</h2><p>${items.length} unique SKUs · read from the receiving fixture</p></div></div><div class="table-wrap"><table class="record-table"><thead><tr><th>SKU / ASIN</th><th>Product</th><th>Colour / variant</th><th>Units per carton</th><th>Expected components</th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${esc(item.sku)}</strong><small>${esc(item.asin)}</small></td><td>${esc(item.product_title)}</td><td>${esc(item.spec_colour)} · ${esc(item.spec_variant)}</td><td>${esc(item.units_per_carton_ordered)}</td><td>${esc(item.spec_components || "—")}</td></tr>`).join("")}</tbody></table></div></section>`;
}
function importPage() {
  return `${pageTitle("Import manifest", "Add receiving rows from a CSV without changing the supplied sample dataset.", `<button class="button-secondary" data-go="shipments">Back to shipments</button>`)}
    <form id="import-form" class="panel receipt-form"><div class="form-heading"><h2>Choose a receiving CSV</h2><p>Existing org and unit pairs are skipped. New rows are stored as local import data.</p></div>
    <label>CSV manifest<input type="file" name="file" accept=".csv,text/csv" required /></label>
    <div class="manifest-format"><strong>Required columns</strong><code>unit_id, org_id, po_number, sku, qty_ordered, qty_received</code><span>Optional columns from receiving_sample.csv—cartons, units per carton, condition flags, variant, components, operator, and photo references—are retained.</span></div>
    <div class="form-actions"><button class="button-primary" type="submit">Import receiving records</button></div></form>`;
}
function evaluationPage() {
  const stats = decisionStats();
  const checkStats = Object.entries(CHECK_LABELS).map(([key, label]) => {
    const results = records.flatMap(row => row.checks || []).filter(check => check.key === key);
    return { label, pass: results.filter(check => check.verdict === "PASS").length, fail: results.filter(check => check.verdict === "FAIL").length, uncertain: results.filter(check => check.verdict === "UNCERTAIN").length };
  });
  return `${pageTitle("Quality lab", "A descriptive summary of the supplied sample—not a live model accuracy claim.")}
    <div class="summary-strip">${metricLine("Sample size", stats.total, "Receiving CSV rows")}${metricLine("Pass", stats.pass, `${stats.total ? Math.round(stats.pass / stats.total * 100) : 0}% of fixture rows`, "good")}${metricLine("Exception", stats.exception, "At least one failed check", "bad")}${metricLine("Uncertain", stats.uncertain, "Ambiguous or incomplete fixture data", "warn")}</div>
    <section class="panel table-panel"><div class="panel-head"><div><h2>Check distribution</h2><p>PASS / FAIL / UNCERTAIN assignments from the current fixture adapter</p></div></div><div class="table-wrap"><table class="record-table"><thead><tr><th>Receiving check</th><th>Pass</th><th>Fail</th><th>Uncertain</th><th>Sample rows</th></tr></thead><tbody>${checkStats.map(item => `<tr><td><strong>${esc(item.label)}</strong></td><td>${item.pass}</td><td>${item.fail}</td><td>${item.uncertain}</td><td>${item.pass + item.fail + item.uncertain}</td></tr>`).join("")}</tbody></table></div><p class="source-note">Fixture verdicts replay provided structured fields and quality flags. They do not measure vision-model performance or inspect the referenced photos.</p></section>`;
}
async function evidencePage() {
  const bundles = await Promise.all(workflows.map(workflow => api(`/workflows/${encodeURIComponent(workflow.workflow_id)}/evidence`).catch(() => null)));
  const rows = bundles.filter(Boolean).flatMap(bundle => Object.values(bundle.evidence || {}).map(item => ({ ...item, workflow_id: bundle.workflow?.workflow_id })));
  rows.sort((a,b) => String(b.produced_at).localeCompare(String(a.produced_at)));
  return `${pageTitle("Evidence", "Immutable records created when a receipt is processed by the Receiving Manager.")}
    ${rows.length ? `<section class="panel table-panel"><div class="panel-head"><div><h2>Evidence ledger</h2><p>${rows.length} records · evidence is stored by the orchestrator</p></div></div><div class="table-wrap"><table class="record-table"><thead><tr><th>Record</th><th>Unit / organization</th><th>Agent</th><th>Verdict</th><th>Created</th><th></th></tr></thead><tbody>${rows.map(item => `<tr><td><strong>${esc(item.record_id)}</strong><small>${esc(item.evidence_source || "Receiving inspection")}</small></td><td>${esc(item.subject?.subject_id)}<small>${esc(item.subject?.org_id)}</small></td><td>${esc(item.agent_id)}</td><td>${fmtDecision(item.decision?.verdict)}</td><td>${timeLabel(item.produced_at)}</td><td><button class="text-button" data-evidence="${esc(item.workflow_id)}">Open JSON</button></td></tr>`).join("")}</tbody></table></div></section>` : `<section class="panel empty-state"><strong>No sealed evidence yet</strong><p>Open a receipt and run its receiving inspection to create an evidence record.</p><button class="button-secondary" data-go="receipts">Open receiving ledger</button></section>`}`;
}
function settingsPage() {
  const receiving = health.agents?.receiving || {};
  const agentName = receiving.agent_id || "dockproof-receiving@1";
  return `${pageTitle("Settings", "Receiving Manager runtime and integration contract.")}
    <div class="settings-grid"><section class="panel settings-panel"><h2>Active receiving agent</h2><dl><div><dt>Agent</dt><dd>${esc(agentName)}</dd></div><div><dt>Connection</dt><dd>${esc(receiving.mode || "in-process")}</dd></div><div><dt>Health</dt><dd>${esc(receiving.status || health.status || "unknown")}</dd></div><div><dt>Flow</dt><dd>${esc(health.flow || "receiving-manager-v1")}</dd></div></dl></section>
    <section class="panel settings-panel"><h2>Shared agent contract</h2><p>Other projects can join this application by returning the shared structured evidence contract. Their stages are added to a project-specific flow only after the agent owner integrates them.</p><a class="button-secondary link-button" href="/docs/agent-api" target="_blank" rel="noreferrer">Open integration contract</a></section>
    <section class="panel settings-panel"><h2>Sample data</h2><dl><div><dt>Source</dt><dd>data/sample/receiving_sample.csv</dd></div><div><dt>Rows</dt><dd>${records.length}</dd></div><div><dt>Observation mode</dt><dd>CSV fixture; no photos analyzed</dd></div></dl></section></div>`;
}
function detailPage(record) {
  const wf = selectedWorkflow;
  const evidence = wf?._evidence || {};
  const receivingEvidence = Object.values(evidence).find(item => item.stage === "receiving") || null;
  const checkSource = receivingEvidence?.checks?.map(item => ({ ...item, key: item.check_key })) || record.checks || [];
  const checks = checkSource.map(item => `<article class="inspection-check"><div class="check-heading"><span class="check-label">${esc(CHECK_LABELS[item.key] || item.key.replaceAll("_", " "))}</span>${fmtDecision(item.verdict)}</div><div class="check-values"><div><small>EXPECTED</small><strong>${formatValue(item.expected)}</strong></div><div><small>OBSERVED</small><strong>${formatValue(item.observed)}</strong></div></div><p>${esc(item.detail || item.reason || "No supporting detail supplied.")}</p></article>`).join("");
  const canRun = !wf;
  const canOverride = Boolean(wf && receivingEvidence && ["EXCEPTION", "NEEDS_REVIEW", "CLAIM_RECOMMENDED", "INCOMPLETE"].includes(wf.final_outcome?.outcome));
  const damage = record.carton_damage && record.carton_damage !== "none" ? record.carton_damage : "No carton issue flagged";
  return `${pageTitle(record.unit_id, `${record.po_number} · ${record.supplier}`, `<button class="button-secondary" data-go="receipts">Back to receipts</button>`)}
    <div class="detail-summary"><section class="panel shipment-panel"><div class="panel-head"><div><h2>Purchase order line</h2><p>Receipt ${esc(record.record_id)} · captured ${timeLabel(record.captured_at)}</p></div>${fmtDecision(effectiveDecision(record))}</div><div class="product-summary"><div><small>PRODUCT</small><strong>${esc(record.product_title)}</strong><span>${esc(record.sku)} · ${esc(record.asin)}</span></div><div><small>EXPECTED / RECEIVED</small><strong>${esc(record.qty_ordered)} / ${esc(record.qty_received)} units</strong><span>${esc(record.cartons_received)} of ${esc(record.cartons_ordered)} cartons · ${esc(record.units_per_carton_counted)} units per carton</span></div><div><small>VARIANT</small><strong>${esc(record.spec_colour)} · ${esc(record.spec_variant)}</strong><span>${esc(record.spec_components || "No component list supplied")}</span></div><div><small>CONDITION</small><strong>${esc(damage)}</strong><span>${esc(record.unit_damage && record.unit_damage !== "none" ? record.unit_damage : "No product issue flagged")}</span></div></div><p class="source-note">${esc(record.evidence_source || "CSV fixture")} · photo references are fixture identifiers, not locally stored image files.</p>
    ${canRun ? `<button class="button-primary" data-action="run-inspection" data-record="${esc(record.record_id)}">Run receiving inspection</button>` : `<div class="evidence-link">Inspection run ${timeLabel(wf.timestamps?.updated_at)} · ${esc(receivingEvidence?.record_id || "evidence pending")}</div>`}</section>
    <section class="panel inspection-panel"><div class="panel-head"><div><h2>Eight receiving checks</h2><p>${wf ? "Orchestrator-recorded agent evidence" : "Structured results from the supplied CSV fixture"}</p></div></div><div class="inspection-grid">${checks}</div></section>
    ${canOverride ? `<section class="panel review-panel"><div class="panel-head"><div><h2>Reviewer decision</h2><p>Overrides preserve the original finding and require an audit reason.</p></div></div><form id="override-form" data-workflow="${esc(wf.workflow_id)}" data-record="${esc(receivingEvidence.record_id)}"><label>Decision<select name="new_verdict"><option value="PASS">Pass</option><option value="FAIL">Fail</option><option value="UNCERTAIN">Uncertain</option></select></label><label>Reason<textarea name="reason" required minlength="4" placeholder="Explain the evidence behind this decision"></textarea></label><label>Reviewer<input name="actor" value="receiving-reviewer" required /></label><button class="button-primary" type="submit">Record audited override</button></form></section>` : ""}
    ${wf?.overrides?.length ? `<section class="panel table-panel"><div class="panel-head"><div><h2>Override audit history</h2><p>The original agent decision remains sealed.</p></div></div><div class="audit-list">${wf.overrides.map(item => `<div class="audit-row"><strong>${esc(item.original_verdict)} → ${esc(item.new_verdict)}</strong><span>${esc(item.actor)} · ${timeLabel(item.at)}</span><p>${esc(item.reason)}</p><small>Supersedes ${esc(item.supersedes?.record_id)}</small></div>`).join("")}</div></section>` : ""}
    ${receivingEvidence ? `<section class="panel evidence-panel"><div class="panel-head"><div><h2>Evidence record</h2><p>${esc(receivingEvidence.record_id)} · ${esc(receivingEvidence.content_hash || "hash unavailable")}</p></div><div class="heading-actions"><button class="button-secondary" data-action="copy-evidence">Copy JSON</button><button class="button-secondary" data-action="download-evidence" data-record="${esc(receivingEvidence.record_id)}">Download JSON</button></div></div><pre id="evidence-json">${esc(JSON.stringify(receivingEvidence, null, 2))}</pre></section>` : ""}</div>`;
}
function formatValue(value) {
  if (value == null || value === "") return "Not supplied";
  if (typeof value === "object") return esc(JSON.stringify(value));
  return esc(String(value));
}
function newReceiptPage() {
  return `${pageTitle("Record a receipt", "Enter the purchase-order expectation and attach receiving photos before inspection.", `<button class="button-secondary" data-go="receipts">Cancel</button>`)}
    <form id="receipt-form" class="panel receipt-form"><div class="form-heading"><h2>Receipt details</h2><p>All fields stay with the unit's receiving evidence.</p></div><div class="form-grid">
      <label>Organization ID<input name="org_id" value="org_demo_alpha" required pattern="[A-Za-z0-9._-]+" /></label><label>Unit / line ID<input name="unit_id" placeholder="UNIT-0101" required pattern="[A-Za-z0-9._-]+" /></label>
      <label>Purchase order<input name="po_number" placeholder="PO-7000" required /></label><label>PO line<input name="po_line" type="number" min="1" placeholder="1" /></label>
      <label>Supplier<input name="supplier" placeholder="Supplier name" /></label><label>SKU<input name="sku" placeholder="SKU-001" required /></label>
      <label>ASIN<input name="asin" placeholder="B0…" /></label><label>Product title<input name="product_title" placeholder="Product name" /></label>
      <label>Expected quantity<input name="quantity" type="number" min="0" required /></label><label>Expected cartons<input name="cartons" type="number" min="0" /></label>
      <label>Units per carton<input name="units_per_carton" type="number" min="0" /></label><label>Colour / variant<input name="variant" placeholder="Blue · Large" /></label>
      <label class="wide-field">Expected components<input name="components" placeholder="Bottle; lid; straw" /></label><label class="wide-field">Receiving photos<input name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple /></label>
      <label class="wide-field">Receiving note<textarea name="note" placeholder="Optional context"></textarea></label>
    </div><p class="source-note">Photos are analyzed only when a live vision provider is configured. Without sufficient visual evidence, the agent returns UNCERTAIN.</p><div class="form-actions"><button class="button-primary" type="submit">Create receipt and inspect</button></div></form>`;
}
function emptyPage(title, text) { return `${pageTitle(title, text)}<section class="panel empty-state"><strong>No records yet</strong><p>Process a receipt to create the first orchestrated evidence record.</p><button class="button-secondary" data-go="receipts">Open receipts</button></section>`; }
function render() {
  const current = el("#page-content");
  const detail = Boolean(selectedRecord);
  const currentPage = detail ? "detail" : selectedPage;
  el("#crumb-current").textContent = detail ? selectedRecord.unit_id : pageNames[currentPage] || "Overview";
  document.querySelectorAll(".nav-item").forEach(item => {
    const active = item.dataset.page === (selectedPage === "new" ? "receipts" : selectedPage);
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  if (detail) current.innerHTML = detailPage(selectedRecord);
  else {
    const pages = { overview: dashboard, receipts: receiptsPage, shipments: shipmentsPage, inspections: inspectionsPage, review: reviewPage, catalog: catalogPage, evaluation: evaluationPage, settings: settingsPage, import: importPage, new: newReceiptPage };
    if (selectedPage === "evidence") { current.innerHTML = `<div class="loading-state">Loading evidence ledger…</div>`; evidencePage().then(html => { if (selectedPage === "evidence" && !selectedRecord) { current.innerHTML = html; bindContent(); } }); }
    else current.innerHTML = (pages[selectedPage] || dashboard)();
  }
  bindContent();
}
function bindContent() {
  document.querySelectorAll("[data-go]").forEach(button => button.addEventListener("click", () => { selectedPage = button.dataset.go; selectedRecord = null; selectedWorkflow = null; render(); }));
  document.querySelectorAll("[data-record]").forEach(row => {
    const open = () => openRecord(row.dataset.record);
    row.addEventListener("click", open);
    row.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
  });
  document.querySelectorAll("[data-po]").forEach(row => row.addEventListener("click", () => {
    searchTerm = row.dataset.po; selectedPage = "receipts"; activeFilter = "ALL"; render();
    const input = el("#list-search"); if (input) { input.value = searchTerm; input.dispatchEvent(new Event("input")); }
  }));
  const search = el("#list-search"); if (search) search.addEventListener("input", event => { searchTerm = event.target.value; const pos = event.target.selectionStart; render(); const next = el("#list-search"); if (next) { next.focus(); next.setSelectionRange(pos, pos); } });
  const select = el("#decision-filter"); if (select) { select.value = activeFilter; select.addEventListener("change", event => { activeFilter = event.target.value; render(); }); }
  document.querySelectorAll("[data-action='clear-filters']").forEach(button => button.addEventListener("click", () => { searchTerm = ""; activeFilter = "ALL"; render(); }));
  document.querySelectorAll("[data-action='import-manifest']").forEach(button => button.addEventListener("click", () => { selectedPage = "import"; selectedRecord = null; render(); }));
  const importForm = el("#import-form"); if (importForm && !importForm.dataset.bound) { importForm.dataset.bound = "true"; importForm.addEventListener("submit", importManifest); }
  document.querySelectorAll("[data-action='new-receipt']").forEach(button => button.addEventListener("click", () => { selectedPage = "new"; selectedRecord = null; selectedWorkflow = null; render(); }));
  const receiptForm = el("#receipt-form"); if (receiptForm) bindReceiptForm();
  document.querySelectorAll("[data-action='run-inspection']").forEach(button => button.addEventListener("click", () => runInspection(button.dataset.record)));
  const overrideForm = el("#override-form"); if (overrideForm) overrideForm.addEventListener("submit", submitOverride);
  document.querySelectorAll("[data-evidence]").forEach(button => button.addEventListener("click", () => openEvidence(button.dataset.evidence)));
  const copy = el("[data-action='copy-evidence']"); if (copy) copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(el("#evidence-json").textContent); toast("Evidence JSON copied"); } catch { toast("Clipboard access is unavailable", true); } });
  const download = el("[data-action='download-evidence']"); if (download) download.addEventListener("click", () => { const blob = new Blob([el("#evidence-json").textContent], { type: "application/json" }); const href = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = href; link.download = `${download.dataset.record || "receiving-evidence"}.json`; link.click(); URL.revokeObjectURL(href); });
}
async function importManifest(event) {
  event.preventDefault(); const form = event.currentTarget; const file = el("input[type='file']", form)?.files?.[0]; const button = el("button[type='submit']", form);
  if (!file) return;
  button.disabled = true; button.textContent = "Importing records…";
  try {
    const content = await file.text();
    const result = await api("/receiving/import", { method: "POST", body: JSON.stringify({ filename: file.name, csv: content }) });
    await loadData(); selectedPage = "receipts"; selectedRecord = null; render();
    toast(`${result.imported} record${result.imported === 1 ? "" : "s"} imported${result.skipped ? ` · ${result.skipped} duplicate rows skipped` : ""}`);
  } catch (error) { toast(error.message, true); button.disabled = false; button.textContent = "Import receiving records"; }
}
function bindReceiptForm() {
  const form = el("#receipt-form"); if (!form || form.dataset.bound) return;
  form.dataset.bound = "true";
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = el("button[type='submit']", form); button.disabled = true; button.textContent = "Creating receipt…";
    const data = new FormData(form); const get = key => String(data.get(key) || "").trim();
    const receiving = { po_number: get("po_number"), po_line: safeNum(get("po_line")), supplier: get("supplier"), sku: get("sku"), asin: get("asin"), product_title: get("product_title"), quantity: safeNum(get("quantity")), cartons: safeNum(get("cartons")), units_per_carton: safeNum(get("units_per_carton")), variant: get("variant"), components: get("components").split(";").map(value => value.trim()).filter(Boolean), note: get("note") };
    try {
      const files = [...(el("input[name='photos']", form)?.files || [])];
      if (files.length > 12) throw new Error("Choose at most 12 receiving photos.");
      receiving.photos = await Promise.all(files.map(async file => {
        if (file.size > 8 * 1024 * 1024) throw new Error(`${file.name} is over 8 MB.`);
        if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error(`${file.name} is not JPEG, PNG, or WebP.`);
        const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = () => reject(new Error(`Could not read ${file.name}.`)); reader.readAsDataURL(file); });
        return { name: file.name, mime_type: file.type, data: dataUrl };
      }));
      const result = await api("/events", { method: "POST", body: JSON.stringify({ project_id: "receiving", event_type: "PRODUCT_RECEIVED", org_id: get("org_id"), unit_id: get("unit_id"), event_id: `PRODUCT_RECEIVED:${get("org_id")}:${get("unit_id")}:${Date.now()}`, route: "unknown", receiving }) });
      await loadData(); await openRecordByUnit(get("unit_id"), get("org_id")); toast(`Receipt recorded · ${result.workflow_id}`);
    } catch (error) { toast(error.message, true); button.disabled = false; button.textContent = "Create receipt and inspect"; }
  });
}
async function openRecord(recordId) {
  const record = records.find(item => item.record_id === recordId);
  if (!record) return toast("That receipt is no longer in the sample list", true);
  await showRecord(record);
}
async function openRecordByUnit(unitId, orgId) {
  const record = records.find(item => item.unit_id === unitId && item.org_id === orgId);
  if (record) await showRecord(record);
  else { selectedPage = "receipts"; selectedRecord = null; render(); }
}
async function showRecord(record) {
  selectedRecord = record; selectedWorkflow = workflowFor(record);
  if (selectedWorkflow) {
    const bundle = await api(`/workflows/${encodeURIComponent(selectedWorkflow.workflow_id)}/evidence`).catch(() => null);
    if (bundle) { selectedWorkflow = bundle.workflow; selectedWorkflow._evidence = bundle.evidence || {}; }
  }
  render();
}
async function runInspection(recordId) {
  const record = records.find(item => item.record_id === recordId);
  if (!record) return;
  const button = el("[data-action='run-inspection']"); if (button) { button.disabled = true; button.textContent = "Running receiving checks…"; }
  try {
    const result = await api("/events", { method: "POST", body: JSON.stringify({ project_id: "receiving", event_type: "PRODUCT_RECEIVED", org_id: record.org_id, unit_id: record.unit_id, event_id: `PRODUCT_RECEIVED:${record.org_id}:${record.unit_id}`, route: "unknown", receiving: { note: "Inspection invoked from the supplied receiving sample." } }) });
    await loadData(); await showRecord(records.find(item => item.record_id === recordId)); toast(`Inspection recorded · ${result.workflow_id}`);
  } catch (error) { toast(error.message, true); if (button) { button.disabled = false; button.textContent = "Run receiving inspection"; } }
}
async function submitOverride(event) {
  event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const button = el("button[type='submit']", form); button.disabled = true; button.textContent = "Saving review…";
  try {
    await api(`/workflows/${encodeURIComponent(form.dataset.workflow)}/overrides`, { method: "POST", body: JSON.stringify({ record_id: form.dataset.record, new_verdict: data.get("new_verdict"), actor: data.get("actor"), reason: data.get("reason") }) });
    await loadData(); await showRecord(selectedRecord); toast("Reviewer decision saved with audit reason");
  } catch (error) { toast(error.message, true); button.disabled = false; button.textContent = "Record audited override"; }
}
async function openEvidence(workflowId) {
  const bundle = await api(`/workflows/${encodeURIComponent(workflowId)}/evidence`).catch(() => null);
  if (!bundle) return toast("Evidence record could not be loaded", true);
  const recordId = bundle.workflow?.subject_id;
  await openRecordByUnit(recordId, bundle.workflow?.org_id);
}
async function loadData() {
  try {
    const [receiptRows, workflowRows, currentHealth] = await Promise.all([api("/receiving"), api("/workflows"), api("/health?project_id=receiving")]);
    records = receiptRows; workflows = workflowRows.filter(item => item.context?.project_id === "receiving" || ["receiving-manager-v1", "cube-receiving-v1"].includes(item.flow_id)); health = currentHealth;
  }
  catch (error) { console.error(error); toast("Could not load receiving data. Refresh to retry.", true); }
  el("#receipt-count").textContent = records.length;
  const needsReview = records.filter(record => ["EXCEPTION", "UNCERTAIN"].includes(effectiveDecision(record))).length;
  el("#review-count").textContent = needsReview;
  const status = health.status === "ok" ? "Ready" : "Needs attention";
  el("#orchestrator-status").innerHTML = `<i class="${health.status === "ok" ? "" : "degraded"}"></i><span>${esc(status)}</span>`;
  el("#health-caption").textContent = `${health.agents ? Object.keys(health.agents).length : 0} receiving agent connected`;
  el("#last-updated").textContent = "just now";
  render();
}
function toast(message, error = false) { const item = document.createElement("div"); item.className = `toast ${error ? "error" : ""}`; item.textContent = message; el("#toast-region").append(item); setTimeout(() => item.remove(), 4500); }
document.querySelectorAll(".nav-item").forEach(item => item.addEventListener("click", () => { selectedPage = item.dataset.page; selectedRecord = null; selectedWorkflow = null; render(); }));
el("#global-search").addEventListener("input", event => { searchTerm = event.target.value.trim(); selectedPage = "receipts"; selectedRecord = null; render(); });
el("#global-search").addEventListener("keydown", event => { if (event.key === "Escape") { event.currentTarget.value = ""; searchTerm = ""; selectedPage = "overview"; render(); } });
document.addEventListener("keydown", event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); el("#global-search").focus(); } });
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-icon]").forEach(node => { node.innerHTML = icon(node.dataset.icon); });
});
loadData();
