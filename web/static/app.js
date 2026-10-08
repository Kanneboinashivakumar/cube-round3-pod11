const AGENTS = [
  ["receiving", "Receiving Manager", "Validates supplier delivery against the purchase order: identity, count, variant, damage and components.", "⇩"],
  ["prep", "Prep Manager", "Checks FBA preparation and captures proof for downstream fee review.", "◇"],
  ["pack", "Pack Manager", "Checks merchant-fulfilled orders before the parcel is sealed.", "▣"],
  ["returns", "Returns Manager", "Inspects returned inventory after the physical return reaches the warehouse.", "↶"],
  ["recovery", "Recovery Manager", "Compares a received fee or charge with the upstream evidence passport.", "$"],
];
const EVENT_INFO = {
  UNIT_CREATED: ["Unit created", "Creates a passport before the physical receipt arrives."],
  PRODUCT_RECEIVED: ["Product received", "Starts the unit passport and receiving inspection."],
  FULFILMENT_ROUTE_IDENTIFIED: ["Route identified", "Routes the unit to either Prep (FBA) or Pack (merchant fulfilled)."],
  RETURN_INITIATED: ["Return initiated", "Records the return request without running physical inspection."],
  RETURN_RECEIVED: ["Return physically received", "Starts Returns only after the item is back at the warehouse."],
  CHARGE_RECEIVED: ["Fee or charge received", "Starts Recovery with the saved upstream evidence."],
};
const pageNames = {overview:"Dashboard",workflows:"Unit passports",exceptions:"Exceptions",agents:"Agent mesh",evidence:"Evidence ledger",receiving:"Receiving",events:"Business events",detail:"Unit passport"};
let workflows = [];
let agentHealth = {};
let selectedPage = "overview";
let selectedWorkflow = null;
let eventType = "PRODUCT_RECEIVED";
let allEvidence = [];

const el = (selector, root=document) => root.querySelector(selector);
const esc = value => String(value ?? "—").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const timeLabel = value => value ? new Date(value).toLocaleString([], {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}) : "—";
const statusClass = value => ({NEEDS_REVIEW:"review",CLAIM_RECOMMENDED:"exception",INCOMPLETE:"review"}[String(value||"").toUpperCase()] || String(value || "pending").toLowerCase().replace(/[^a-z_]/g, "_"));
const fmtOutcome = wf => wf.final_outcome?.outcome || wf.status || "PENDING";

async function api(path, options={}) {
  const response = await fetch(path, {headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
  return data;
}

async function refresh() {
  try { workflows = await api("/workflows"); } catch { workflows = []; }
  try { const health = await api("/health"); agentHealth = health.agents || {}; el("#health-caption").textContent = health.status === "ok" ? "5 connected agents" : "Some agents need attention"; } catch { agentHealth = {}; el("#health-caption").textContent = "Health check unavailable"; }
  el("#workflow-count").textContent = workflows.length;
  el("#exception-count").textContent = workflows.filter(w => ["EXCEPTION","NEEDS_REVIEW","CLAIM_RECOMMENDED","INCOMPLETE"].includes(fmtOutcome(w))).length;
  el("#last-updated").textContent = "just now";
  if (selectedPage === "evidence") await loadEvidence();
  render();
}

function pageTitle(title, subtitle, action="") {
  return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-actions">${action}</div></div>`;
}
function metric(title, value, foot, icon, flavor="") {
  return `<article class="metric-card"><div class="metric-head">${title}<span class="metric-icon">${icon}</span></div><div class="metric-value">${value}</div><div class="metric-foot ${flavor}">${foot}</div></article>`;
}
function statusPill(value) { return `<span class="status-pill ${statusClass(value)}">${esc(String(value||"PENDING").replaceAll("_"," "))}</span>`; }
function stageDots(wf) {
  return `<div class="agent-strip" title="${esc((wf.stage_results||[]).map(s=>`${s.stage}: ${s.state}`).join(" · "))}">${(wf.stage_results||[]).map(s=>`<span class="stage-dot ${statusClass(s.state)}" aria-label="${esc(s.stage)}: ${esc(s.state)}" title="${esc(s.stage)}: ${esc(s.state)}">${({receiving:"R",prep:"P",pack:"K",returns:"↶",recovery:"$"})[s.stage]||"·"}</span>`).join("")}</div>`;
}
function workflowRows(list=workflows) {
  if (!list.length) return `<tr><td colspan="5"><div class="empty-state"><div class="empty-symbol">⌁</div><strong>No unit passports yet</strong><p>Start with a Product received event. As new events arrive, this table becomes the shared record for every agent.</p><button class="button-secondary" data-go="events">Create first event</button></div></td></tr>`;
  return list.map(wf=>`<tr data-id="${esc(wf.workflow_id)}"><td><span class="unit-main">${esc(wf.subject_id)}</span><span class="unit-sub">${esc(wf.workflow_id)}</span></td><td>${esc(wf.context?.route?.toUpperCase()||"—")}</td><td>${statusPill(fmtOutcome(wf))}</td><td>${stageDots(wf)}</td><td>${timeLabel(wf.timestamps?.updated_at)}</td></tr>`).join("");
}
function workflowTable(title="Recent unit passports", list=workflows) {
  return `<section class="panel"><div class="panel-head"><div><h3>${title}</h3><p>One traceable passport per unit, updated as business events arrive.</p></div><button class="section-link" data-go="workflows">View all →</button></div><div class="table-wrap"><table class="workflow-table"><thead><tr><th>Unit / workflow</th><th>Fulfilment</th><th>Outcome</th><th>Journey</th><th>Updated</th></tr></thead><tbody>${workflowRows(list)}</tbody></table></div></section>`;
}
function meshRows() {
  return AGENTS.map(([id,name,desc,icon])=>{
    const state = agentHealth[id]?.status || "unknown";
    return `<div class="mesh-row"><span class="mesh-mark">${icon}</span><span class="mesh-info"><strong>${name}</strong><small>${id[0].toUpperCase()+id.slice(1)} stage</small></span><span class="mesh-state ${state==="ok"?"":"degraded"}">${state==="ok"?"Ready":esc(state)}</span></div>`;
  }).join("");
}
function eventForm(compact=false) {
  const product = eventType === "PRODUCT_RECEIVED";
  const routeField = product || eventType === "FULFILMENT_ROUTE_IDENTIFIED" ? `<div class="field"><label for="fulfilment-route">Fulfilment route</label><select id="fulfilment-route" name="route"><option value="fba">FBA · Prep</option><option value="mfn">Merchant fulfilled · Pack</option>${product?'<option value="unknown">Not known yet</option>':""}</select></div>` : "";
  const eventFields = product ? `<div class="field"><label for="po-number">Purchase order</label><input id="po-number" name="po_number" placeholder="PO-7000" /></div>
      <div class="field"><label for="sku">Expected SKU</label><input id="sku" name="sku" placeholder="SKU-001" /></div><div class="field"><label for="qty-expected">Expected quantity</label><input id="qty-expected" name="quantity" type="number" min="0" placeholder="24" /></div>
      <div class="field"><label for="cartons-expected">Expected cartons</label><input id="cartons-expected" name="cartons" type="number" min="0" placeholder="1" /></div><div class="field"><label for="units-per-carton">Units per carton</label><input id="units-per-carton" name="units_per_carton" type="number" min="0" placeholder="12" /></div>
      <div class="field"><label for="variant">Expected variant</label><input id="variant" name="variant" placeholder="Blue · Large" /></div>`
      : eventType === "CHARGE_RECEIVED" ? `<div class="field"><label for="fee-type">Charge type</label><input id="fee-type" name="fee_type" placeholder="Inbound defect fee" /></div><div class="field"><label for="fee-amount">Amount (USD)</label><input id="fee-amount" name="amount_usd" type="number" min="0" step="0.01" placeholder="2.00" /></div>` : "";
  const photoFields = product ? `<div class="field"><label for="components">Expected components</label><input id="components" name="components" placeholder="Bottle; lid; straw" /></div><div class="field"><label for="receipt-photos">Receiving photos</label><input id="receipt-photos" name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple /></div>` : "";
  const heading = compact ? (product ? "Start a unit passport" : `Record ${EVENT_INFO[eventType][0].toLowerCase()}`) : "Record a business event";
  return `<section class="panel event-panel"><div class="panel-head"><div><h3>${heading}</h3><p>${product?"Begin the journey with the inbound receipt.":"Advance an existing unit when its next real-world event happens."}</p></div></div>
    <div class="event-tabs">${Object.keys(EVENT_INFO).map(type=>`<button class="event-tab ${eventType===type?"active":""}" data-event="${type}">${EVENT_INFO[type][0]}</button>`).join("")}</div>
    <form class="form-pad" id="event-form"><div class="form-grid">
      <div class="field"><label for="org-id">Organization</label><input id="org-id" name="org_id" value="org_demo_alpha" required /></div>
      <div class="field"><label for="unit-id">Unit / line ID</label><input id="unit-id" name="unit_id" placeholder="UNIT-0001" required /></div>
      ${routeField}${eventFields}${photoFields}
      <div class="field full"><label for="event-note">${product?"Receiving note":"Event reference / note"}</label><input id="event-note" name="note" placeholder="Optional context for the agent" /></div>
    </div><div class="form-note"><span>ⓘ</span><div>${product?"The workflow will run Receiving, then the route-specific agent. Returns and Recovery wait for their own events.":"This event adds to the existing passport. A duplicate event ID is ignored to protect the audit trail."}</div></div><button class="button-primary form-submit" type="submit"><span class="plus">+</span>${eventType==="PRODUCT_RECEIVED"?"Create unit passport":"Apply event"}</button></form></section>`;
}
function flowSteps() {
  const steps=[["R","Receiving"],["P / K","Prep or Pack"],["↶","Physical return"],["$","Fee event"]];
  return `<div class="flow-steps">${steps.map(([icon,name],i)=>`${i?`<span class="flow-arrow">→</span>`:""}<div class="flow-step"><div class="flow-node ${i===0?"active":""}">${icon}</div><small>${name}</small></div>`).join("")}</div>`;
}
function flowPanel() {
  return `<section class="panel flow-panel"><h3>Event-driven journey</h3><p>Only the agents relevant to each event and route are invoked.</p>${flowSteps()}</section>`;
}
function activityPanel() {
  const transitions=workflows.flatMap(w=> (w.transitions||[]).map(t=>({...t,subject:w.subject_id}))).sort((a,b)=>String(b.at).localeCompare(String(a.at))).slice(0,4);
  const body=transitions.length?transitions.map(t=>`<div class="activity-row"><span class="activity-bullet">⌁</span><span><strong>${esc((t.detail||t.event||"Workflow updated").replaceAll("_"," "))}</strong><small>${esc(t.subject||t.stage||"System event")}</small></span><time>${timeLabel(t.at)}</time></div>`).join(""):`<div class="activity-empty">Business events and agent decisions will appear here.</div>`;
  return `<section class="panel activity-panel"><h3>Latest activity</h3><p>Recent changes across unit passports.</p>${body}</section>`;
}
function dashboard() {
  const active=workflows.filter(w=>["IN_PROGRESS","RECOVERY_REQUIRED","BLOCKED","FAILED"].includes(w.status)).length;
  const exceptions=workflows.filter(w=>["EXCEPTION","NEEDS_REVIEW","CLAIM_RECOMMENDED","INCOMPLETE"].includes(fmtOutcome(w))).length;
  const receiving=workflows.filter(w=>(w.stage_results||[]).some(s=>s.stage==="receiving"&&s.state==="completed")).length;
  const fba=workflows.filter(w=>w.context?.route==="fba").length;
  return `${pageTitle("Operations Dashboard","One shared view of inbound inventory, agent work and the evidence behind every decision.",`<span class="date-chip">◷ &nbsp;Live operations</span><button class="button-primary" data-go="events"><span class="plus">+</span> New event</button>`)}
    <div class="overview-banner"><div class="banner-copy"><span class="banner-icon">⎔</span><div><strong>One unit. One traceable journey.</strong><p>Business events activate only the relevant agents. Every decision is attached to a shared unit passport.</p></div></div><div class="banner-meta"><div class="meta-item">FLOW VERSION<strong>Cube Flow v1</strong></div><div class="meta-item">AGENT NETWORK<strong>5 specialists</strong></div><button class="text-link" data-go="agents">View mesh →</button></div></div>
    <div class="section-header"><div><h2>Inbound &amp; orchestration</h2><p>Current work across the warehouse lifecycle</p></div><button class="section-link" data-go="workflows">All passports →</button></div>
    <div class="metric-grid">${metric("Unit passports",workflows.length,`${receiving} with receiving evidence`,"▤")}${metric("Active workflows",active,"Awaiting the next stage or review","◷",active?"attention":"")}${metric("Exceptions &amp; review",exceptions,"UNCERTAIN is never auto-passed","△",exceptions?"attention":"")}${metric("FBA routed",fba,`${workflows.length-fba} merchant / unknown route`,"⇢")}</div>
    <div class="data-layout"><div>${workflowTable()}</div><div class="right-stack">${eventForm(true)}<section class="panel mesh-panel"><div class="panel-head"><div><h3>Agent network</h3><p>Orchestrator-managed specialists</p></div><button class="section-link" data-go="agents">Details →</button></div><div class="mesh-list">${meshRows()}</div></section></div></div>
    <div class="lower-grid">${flowPanel()}${activityPanel()}</div>`;
}
function detailPage(wf) {
  const evidence=wf._evidence||{};
  const records=(wf.evidence_references||[]).map(id=>evidence[id]).filter(Boolean);
  const stages=(wf.stage_results||[]).map(sr=>{
    const record=evidence[sr.record_id];
    const photos=(record?.inputs||[]).filter(input=>input.kind==="image").map(input=>`<a class="photo-thumb" href="/captures?ref=${encodeURIComponent(input.ref)}" target="_blank" rel="noreferrer" title="SHA-256 ${esc(input.sha256||"unavailable")}"><img src="/captures?ref=${encodeURIComponent(input.ref)}" alt="Receiving evidence photograph" loading="lazy"/><span>${esc(input.ref.split("/").pop())}</span></a>`).join("");
    return `<article class="evidence-card"><div class="evidence-card-head"><strong>${esc(sr.stage[0].toUpperCase()+sr.stage.slice(1))} · ${esc(sr.record_id||sr.state)}</strong>${statusPill(sr.verdict||sr.state)}</div>${photos?`<div class="photo-gallery">${photos}</div>`:""}<div class="check-grid">${(record?.checks||[]).map(c=>`<div class="check-item"><strong><span class="stage-dot ${statusClass(c.verdict)}">${c.verdict==="PASS"?"✓":c.verdict==="FAIL"?"!":"?"}</span>${esc(c.check_key.replaceAll("_"," "))}</strong><p>${esc(c.detail||c.reason||`${c.expected??"Expected"} · ${c.observed??"Not observed"}`)}</p></div>`).join("")||`<div class="check-item"><strong>${esc(sr.skipped_reason||sr.error?.message||"No evidence recorded yet")}</strong></div>`}</div></article>`;
  }).join("");
  return `${pageTitle(wf.subject_id,`${wf.workflow_id} · ${wf.context?.route?.toUpperCase()||"route not set"}`,`<button class="button-secondary" data-go="workflows">← All passports</button>`)}
    <div class="detail-grid"><section class="panel detail-panel"><div class="detail-title"><div><h2>Unit passport</h2><p>Evidence chain for ${esc(wf.subject_id)} · ${esc(wf.org_id)}</p></div>${statusPill(fmtOutcome(wf))}</div>
      <div class="detail-section"><h3>Lifecycle context</h3><div class="kv-grid"><div class="kv"><label>FULFILMENT</label><strong>${esc(wf.context?.route?.toUpperCase()||"Unknown")}</strong></div><div class="kv"><label>RETURN RECEIVED</label><strong>${wf.context?.returned?"Yes":"Not yet"}</strong></div><div class="kv"><label>CHARGE RECEIVED</label><strong>${wf.context?.has_charge?"Yes":"Not yet"}</strong></div><div class="kv"><label>CREATED</label><strong>${timeLabel(wf.timestamps?.created_at)}</strong></div><div class="kv"><label>UPDATED</label><strong>${timeLabel(wf.timestamps?.updated_at)}</strong></div><div class="kv"><label>FINAL OUTCOME</label><strong>${esc(fmtOutcome(wf).replaceAll("_"," "))}</strong></div></div></div>
      <div class="detail-section"><h3>Agent evidence</h3>${stages||"<p>No stage records yet.</p>"}</div></section>
      <div class="right-stack"><section class="panel detail-panel"><h3 style="font:700 12px Manrope;margin:0 0 15px">Passport timeline</h3><div class="timeline">${(wf.transitions||[]).slice().reverse().map(t=>`<div class="timeline-item"><strong>${esc((t.event||"Update").replaceAll("_"," "))}</strong><p>${esc(t.detail||t.stage||"")} · ${timeLabel(t.at)}</p></div>`).join("")||"<p>No events yet.</p>"}</div></section>${eventForm(true)}</div></div>`;
}
function workflowsPage() {
  return `${pageTitle("Unit passports","A durable record of each unit’s event history, agent decisions, overrides and evidence.",`<button class="button-primary" data-go="events"><span class="plus">+</span> Record event</button>`)}${workflowTable("All unit passports")}`;
}
function exceptionsPage() {
  const list=workflows.filter(w=>["EXCEPTION","NEEDS_REVIEW","CLAIM_RECOMMENDED","INCOMPLETE"].includes(fmtOutcome(w))||w.status==="BLOCKED");
  return `${pageTitle("Exceptions & review","Human attention is preserved as an explicit outcome. Uncertain evidence is never silently promoted to pass.")}
    <div class="overview-banner"><div class="banner-copy"><span class="banner-icon">△</span><div><strong>${list.length} passport${list.length===1?"":"s"} require attention</strong><p>Open a passport to review per-check evidence, missing inputs and the event timeline.</p></div></div></div>${workflowTable("Needs attention",list)}`;
}
function agentsPage() {
  return `${pageTitle("Agent mesh","Five independently versioned specialists connect through one orchestrator-owned contract and state store.",`<button class="button-secondary" id="refresh-agents">⟳ Refresh health</button>`)}<p class="page-intro">Each agent receives the shared Agent Input, sees prior evidence when relevant, and returns a validated evidence record. The orchestrator decides what runs next and records every failure or uncertain result.</p><div class="agent-grid">${AGENTS.map(([id,name,desc,icon])=>`<article class="panel agent-card"><div class="agent-top"><span class="agent-icon">${icon}</span><span class="mesh-state ${(agentHealth[id]?.status||"unknown")==="ok"?"":"degraded"}">${esc(agentHealth[id]?.status||"unknown")}</span></div><h3>${name}</h3><p>${desc}</p><div class="agent-meta"><span>Stage · ${id}</span><span>${esc(agentHealth[id]?.mode||"in-process")}</span></div></article>`).join("")}</div><div class="lower-grid"><section class="panel flow-panel"><h3>Conditional routing</h3><p>FBA takes Prep; MFN takes Pack. They are mutually exclusive. Returns and Recovery wait for their own events.</p>${flowSteps()}</section><section class="panel activity-panel"><h3>Orchestration guarantees</h3><p>Evidence-first behaviour shared across the pod.</p><div class="activity-row"><span class="activity-bullet">✓</span><span><strong>UNCERTAIN remains visible</strong><small>Not inferred as PASS</small></span></div><div class="activity-row"><span class="activity-bullet">↺</span><span><strong>Errors are persisted</strong><small>Retry policy and pending evidence</small></span></div><div class="activity-row"><span class="activity-bullet">▤</span><span><strong>Evidence is immutable</strong><small>Content-hash checked before storage</small></span></div></section></div>`;
}
async function loadEvidence() {
  const bundles=await Promise.all(workflows.map(w=>api(`/workflows/${encodeURIComponent(w.workflow_id)}/evidence`).catch(()=>null)));
  allEvidence=bundles.filter(Boolean).flatMap(b=>Object.values(b.evidence||{}));
}
function evidencePage() {
  const rows=allEvidence.slice().sort((a,b)=>String(b.produced_at).localeCompare(String(a.produced_at)));
  const body=rows.length?rows.map(e=>`<div class="panel ledger-row"><strong>${esc(e.record_id)}<small>${esc(e.subject?.subject_id)}</small></strong><small>${esc(e.stage)} · ${esc(e.agent_id)}</small>${statusPill(e.decision?.verdict)}<small>${timeLabel(e.produced_at)}</small></div>`).join(""):`<div class="panel empty-state"><div class="empty-symbol">▤</div><strong>No evidence has been recorded</strong><p>Records will appear when a unit event activates an agent.</p></div>`;
  return `${pageTitle("Evidence ledger","Immutable agent output with source references, confidence, checks, content hash and upstream links.")}${rows.length?`<div class="ledger-heading ledger-row"><span>RECORD</span><span>STAGE · AGENT</span><span>VERDICT</span><span>PRODUCED</span></div>`:""}<div class="ledger-list">${body}</div>`;
}
function receivingPage() {
  return `${pageTitle("Receiving Manager","Point-of-receipt inspection against the purchase order. Every result is supported by evidence or explicitly marked uncertain.",`<button class="button-primary" data-go="events"><span class="plus">+</span> New receipt</button>`)}<p class="page-intro">The Receiving Manager checks product identity, expected and observed quantities, carton count and units per carton, variant, visible carton and unit damage, and required components. When a photo or PO detail is missing, the check remains uncertain for review.</p><div class="data-layout"><div>${workflowTable("Recent receiving passports",workflows.filter(w=>(w.stage_results||[]).some(s=>s.stage==="receiving")))}</div><div>${eventForm(true)}<section class="panel flow-panel" style="margin-top:13px"><h3>Receiving evidence checklist</h3><p>Eight dimensions carried from the DockProof Receiving Manager.</p><div class="check-grid">${["SKU identity","Quantity","Carton count","Units per carton","Colour / variant","Carton condition","Product condition","Components"].map(x=>`<div class="check-item"><strong>${esc(x)}</strong><p>Expected and observed values with a linked source or uncertainty reason.</p></div>`).join("")}</div></section></div></div>`;
}
function eventsPage() {
  const events=workflows.flatMap(w=>(w.transitions||[]).filter(t=>t.event==="business_event_received"||t.event==="workflow_created").map(t=>({subject:w.subject_id,...t}))).sort((a,b)=>String(b.at).localeCompare(String(a.at)));
  return `${pageTitle("Business events","The warehouse state changes over time. Each event reopens only the newly eligible stage on its existing passport.")}
    <p class="page-intro">Create the first receipt event to establish a unit passport. Later, append a physical-return or fee event. All event handling is idempotent and recorded in the workflow timeline.</p>
    <div class="event-choice">${Object.entries(EVENT_INFO).map(([type,[title,desc]])=>`<button class="${eventType===type?"selected":""}" data-event="${type}"><strong>${title}</strong><small>${desc}</small></button>`).join("")}</div><div style="max-width:620px">${eventForm()}</div><section class="panel activity-panel" style="margin-top:14px"><h3>Event history</h3><p>Most recent event activity across passports.</p>${events.length?events.slice(0,12).map(t=>`<div class="activity-row"><span class="activity-bullet">⌁</span><span><strong>${esc((t.detail||t.event).replaceAll("_"," "))}</strong><small>${esc(t.subject)} · ${esc(t.stage||"")}</small></span><time>${timeLabel(t.at)}</time></div>`).join(""):`<div class="activity-empty">No business events recorded yet.</div>`}</section>`;
}
function render() {
  const content=el("#page-content");
  const current=selectedWorkflow?"detail":selectedPage;
  el("#crumb-current").textContent=pageNames[current]||"Dashboard";
  document.querySelectorAll(".nav-item").forEach(item=>item.classList.toggle("active",item.dataset.page===selectedPage));
  const pages={overview:dashboard,workflows:workflowsPage,exceptions:exceptionsPage,agents:agentsPage,evidence:evidencePage,receiving:receivingPage,events:eventsPage};
  if(selectedWorkflow) content.innerHTML=detailPage(selectedWorkflow);
  else content.innerHTML=(pages[selectedPage]||dashboard)();
  bindContent();
}
function toast(message, error=false) {
  const item=document.createElement("div"); item.className=`toast ${error?"error":""}`; item.textContent=message; el("#toast-region").append(item); setTimeout(()=>item.remove(),4200);
}
function setEvent(type) { if(!EVENT_INFO[type])return; eventType=type; selectedWorkflow=null; render(); }
function bindContent() {
  document.querySelectorAll("[data-go]").forEach(button=>button.addEventListener("click",()=>{selectedPage=button.dataset.go;selectedWorkflow=null;render()}));
  document.querySelectorAll("[data-event]").forEach(button=>button.addEventListener("click",()=>setEvent(button.dataset.event)));
  document.querySelectorAll("tr[data-id]").forEach(row=>row.addEventListener("click",()=>openWorkflow(row.dataset.id)));
  const form=el("#event-form");
  if(form)form.addEventListener("submit",async event=>{
    event.preventDefault();
    const button=el("button[type=submit]",form); button.disabled=true; button.textContent="Recording event…";
    const formData=new FormData(form); const get=k=>String(formData.get(k)||"").trim();
    const payload={event_type:eventType,org_id:get("org_id"),unit_id:get("unit_id"),event_id:`${eventType}:${get("org_id")}:${get("unit_id")}:${Date.now()}`};
    if(eventType==="PRODUCT_RECEIVED") {
      payload.route=get("route")||"unknown";
      payload.receiving={note:get("note")};
      if(get("po_number"))payload.receiving.po_number=get("po_number");
      if(get("sku"))payload.receiving.sku=get("sku");
      if(get("quantity"))payload.receiving.quantity=Number(get("quantity"));
      if(get("cartons"))payload.receiving.cartons=Number(get("cartons"));
      if(get("units_per_carton"))payload.receiving.units_per_carton=Number(get("units_per_carton"));
      if(get("variant"))payload.receiving.variant=get("variant");
      if(get("components"))payload.receiving.components=get("components").split(";").map(value=>value.trim()).filter(Boolean);
      const files=Array.from(el("#receipt-photos",form)?.files||[]);
      if(files.length>12){toast("Choose at most 12 images",true);button.disabled=false;button.innerHTML=`<span class="plus">+</span>Create unit passport`;return;}
      try { payload.receiving.photos=await Promise.all(files.map(async file=>{
        if(file.size>8*1024*1024)throw new Error(`${file.name} is over 8 MB`);
        if(!["image/jpeg","image/png","image/webp"].includes(file.type))throw new Error(`${file.name} is not a supported JPEG, PNG or WebP image`);
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(",")[1]);reader.onerror=()=>reject(new Error(`Could not read ${file.name}`));reader.readAsDataURL(file)});
        return {name:file.name,mime_type:file.type,data};
      })); } catch(error){toast(error.message,true);button.disabled=false;button.innerHTML=`<span class="plus">+</span>Create unit passport`;return;}
    } else if(eventType==="FULFILMENT_ROUTE_IDENTIFIED") payload.route=get("route");
    else if(eventType==="CHARGE_RECEIVED") payload.fee={type:get("fee_type"),amount_usd:get("amount_usd")?Number(get("amount_usd")):null,note:get("note")};
    else payload.note=get("note");
    try { const result=await api("/events",{method:"POST",body:JSON.stringify(payload)}); toast(`${EVENT_INFO[eventType][0]} recorded · ${result.workflow_id}`); workflows=await api("/workflows"); selectedWorkflow=await api(`/workflows/${encodeURIComponent(result.workflow_id)}/evidence`); selectedWorkflow=selectedWorkflow.workflow; selectedWorkflow._evidence=(await api(`/workflows/${encodeURIComponent(result.workflow_id)}/evidence`)).evidence; selectedPage="workflows"; await refresh(); }
    catch(error){toast(error.message,true);button.disabled=false;button.innerHTML=`<span class="plus">+</span>${eventType==="PRODUCT_RECEIVED"?"Create unit passport":"Apply event"}`;}
  });
  const refreshBtn=el("#refresh-agents"); if(refreshBtn)refreshBtn.addEventListener("click",refresh);
}
async function openWorkflow(id) {
  const bundle=await api(`/workflows/${encodeURIComponent(id)}/evidence`).catch(()=>null);
  if(!bundle){toast("Could not load that unit passport",true);return;}
  selectedWorkflow=bundle.workflow; selectedWorkflow._evidence=bundle.evidence||{}; render();
}
document.querySelectorAll(".nav-item").forEach(item=>item.addEventListener("click",()=>{selectedPage=item.dataset.page;selectedWorkflow=null;if(selectedPage==="evidence")loadEvidence().then(render);else render()}));
el("#theme-toggle").addEventListener("click",()=>{document.body.classList.toggle("dark");localStorage.setItem("cube-theme",document.body.classList.contains("dark")?"dark":"light")});
if(localStorage.getItem("cube-theme")==="dark")document.body.classList.add("dark");
el("#global-search").addEventListener("input",event=>{
  const q=event.target.value.toLowerCase().trim();
  if(!q){render();return;}
  selectedPage="workflows";selectedWorkflow=null;
  const filtered=workflows.filter(w=>[w.subject_id,w.workflow_id,w.org_id,w.context?.route].some(v=>String(v||"").toLowerCase().includes(q)));
  el("#crumb-current").textContent="Search results";
  el("#page-content").innerHTML=`${pageTitle(`Search results`,`Matching unit passports for “${esc(q)}”`)}${workflowTable("Matching passports",filtered)}`;
  bindContent();
});
document.addEventListener("keydown",event=>{
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k") { event.preventDefault(); el("#global-search").focus(); }
  if(event.key==="Escape"&&document.activeElement===el("#global-search")) { el("#global-search").value=""; el("#global-search").blur(); render(); }
});
refresh();
setInterval(refresh,30000);
