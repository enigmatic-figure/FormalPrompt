const app = document.querySelector("#app");
const announcer = document.querySelector("#announcer");
let session = null;
let validation = { ready: false, issues: [] };
let activeTab = 0;
let busy = false;
const fieldAssistance = new Map();
let lastReview = null;
let lastComposition = null;

function element(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("data-")) node.setAttribute(key, value);
    else if (key === "checked" || key === "selected" || key === "disabled") node[key] = Boolean(value);
    else if (value !== undefined && value !== null) node.setAttribute(key, String(value));
  }
  for (const child of children) {
    if (child) node.append(child);
  }
  return node;
}

function getToken() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const supplied = fragment.get("token");
  if (supplied) {
    sessionStorage.setItem("formalprompt-token", supplied);
    history.replaceState(null, "", `${location.pathname}${location.search}`);
  }
  return supplied || sessionStorage.getItem("formalprompt-token");
}

const token = getToken();

async function api(path, options = {}) {
  if (!token) throw new Error("No run token was provided. Open the complete URL printed by the CLI.");
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    const error = new Error(typeof detail === "string" ? detail : detail?.message || "Request failed");
    error.payload = payload;
    throw error;
  }
  return payload;
}

function allFields() {
  return session.document.tabs.flatMap((tab) => tab.sections.flatMap((section) => section.fields));
}

function makeBadge(text, extra = "") {
  return element("span", { className: `badge ${extra}`.trim(), text });
}

function renderField(field) {
  const card = element("article", {
    className: "field-card",
    "data-provenance": field.provenance,
    "data-review": field.review_status,
  });
  const title = element("label", {
    className: "field-label",
    for: `field-${field.id}`,
    text: field.label,
  });
  if (field.required) title.append(element("span", { className: "required", text: " · required" }));
  const badges = element("div", { className: "badges" }, [
    makeBadge(field.provenance.replace("-", " "), field.provenance),
    makeBadge(field.review_status.replace("-", " "), field.review_status),
    field.importance !== "normal" ? makeBadge(field.importance, field.importance) : null,
  ]);
  card.append(element("div", { className: "field-topline" }, [title, badges]));
  if (field.description) card.append(element("p", { className: "description", text: field.description }));
  if (field.rationale) card.append(element("p", { className: "rationale", text: `Agent rationale: ${field.rationale}` }));
  card.append(makeControl(field));
  if (field.assistance.enabled) card.append(renderAssistance(field));
  return card;
}

function renderAssistance(field) {
  const question = element("input", {
    className: "control assistance-input",
    type: "text",
    placeholder: "Ask for options, tradeoffs, or a sharper formulation",
    "aria-label": `Question about ${field.label}`,
  });
  const ask = element("button", { className: "button compact", text: "Ask facilitator", disabled: busy });
  ask.addEventListener("click", () => requestFieldAssistance(field, question.value));
  const body = element("div", { className: "assistance-body" }, [
    field.assistance.prompt ? element("p", { className: "description", text: field.assistance.prompt }) : null,
    element("div", { className: "assistance-query" }, [question, ask]),
  ]);
  const result = fieldAssistance.get(field.id);
  if (result) body.append(renderAssistantResult(field, result));
  return element("details", { className: "assistance" }, [
    element("summary", { text: "Agent assistance" }),
    body,
  ]);
}

function renderAssistantResult(field, result) {
  if (result.status === "pending") {
    return element("p", { className: "assistant-result", text: `Request ${result.request_id} is queued for an external facilitator.` });
  }
  const response = result.response;
  const panel = element("div", { className: "assistant-result" }, [
    element("p", { text: response.summary || "The facilitator returned suggestions." }),
  ]);
  for (const suggestion of response.suggestions || []) {
    const apply = element("button", { className: "button compact", text: `Apply suggestion: ${suggestion.label}` });
    apply.setAttribute("aria-label", `Apply suggestion ${suggestion.label} to ${field.label}`);
    apply.addEventListener("click", () => saveField(field, suggestion.value));
    panel.append(element("div", { className: "suggestion" }, [
      element("p", { text: suggestion.implications || suggestion.label }), apply,
    ]));
  }
  for (const followup of response.questions || []) panel.append(element("p", { className: "followup", text: `Follow-up: ${followup}` }));
  appendProposalAction(panel, result);
  return panel;
}

function appendProposalAction(panel, result) {
  if (result.status !== "completed" || !result.response?.next_document) return;
  const apply = element("button", { className: "button compact", text: "Apply proposed canvas", disabled: busy });
  apply.addEventListener("click", () => applyProposal(result.request_id));
  panel.append(apply);
}

async function applyProposal(requestId) {
  setBusy(true, "Applying proposed canvas…");
  let outcome = "";
  let failed = false;
  try {
    session = await api("/api/proposals/apply", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, expected_revision: session.state.revision }),
    });
    lastReview = null;
    lastComposition = null;
    activeTab = (session.document.initialization?.artifacts || []).length ? session.document.tabs.length : 0;
    await refreshValidation();
    outcome = "Proposed canvas applied for user review";
  } catch (error) {
    outcome = error.message;
    failed = true;
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

async function requestFieldAssistance(field, question) {
  const text = question.trim();
  if (!text) { announce("Enter a question for the facilitator", true); return; }
  setBusy(true, `Asking about ${field.label}…`);
  let outcome = "";
  let failed = false;
  try {
    const result = await api("/api/assistance", {
      method: "POST",
      body: JSON.stringify({ field_id: field.id, question: text }),
    });
    fieldAssistance.set(field.id, result);
    outcome = result.status === "pending" ? "Facilitator request queued" : "Facilitator response received";
  } catch (error) {
    outcome = error.message;
    failed = true;
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

function makeControl(field) {
  const id = `field-${field.id}`;
  let control;
  if (field.type === "textarea") {
    control = element("textarea", { id, className: "control", placeholder: field.placeholder });
    control.value = field.value ?? "";
  } else if (field.type === "select" || field.type === "multiselect") {
    control = element("select", {
      id,
      className: field.type === "multiselect" ? "control multiselect" : "control",
      multiple: field.type === "multiselect" ? "multiple" : null,
    });
    if (field.type === "select" && !field.required) {
      control.append(element("option", { value: "", text: "Not specified" }));
    }
    const selected = new Set(Array.isArray(field.value) ? field.value : [field.value]);
    for (const option of field.options) {
      const node = element("option", { value: option.value, text: option.label });
      node.selected = selected.has(option.value);
      if (option.implications) node.title = option.implications;
      control.append(node);
    }
  } else if (field.type === "checkbox") {
    control = element("input", { id, type: "checkbox", checked: field.value, className: "checkbox" });
    const row = element("div", { className: "checkbox-row" }, [control, element("span", { text: field.value ? "Enabled" : "Disabled" })]);
    control.addEventListener("change", () => saveField(field, control.checked));
    return row;
  } else {
    control = element("input", {
      id,
      type: field.type === "number" ? "number" : "text",
      className: "control",
      placeholder: field.placeholder,
    });
    control.value = field.value ?? "";
    if (field.validation.minimum !== null) control.min = field.validation.minimum;
    if (field.validation.maximum !== null) control.max = field.validation.maximum;
    if (field.validation.min_length !== null) control.minLength = field.validation.min_length;
    if (field.validation.max_length !== null) control.maxLength = field.validation.max_length;
    if (field.validation.pattern) control.pattern = field.validation.pattern;
  }
  control.addEventListener("change", () => saveField(field, readControlValue(field, control)));
  return control;
}

function readControlValue(field, control) {
  if (field.type === "number") return control.value === "" ? null : Number(control.value);
  if (field.type === "multiselect") return [...control.selectedOptions].map((option) => option.value);
  return control.value;
}

async function saveField(field, value) {
  if (busy) return;
  setBusy(true, `Saving ${field.label}…`);
  let outcome = "";
  let failed = false;
  try {
    session = await api(`/api/fields/${encodeURIComponent(field.id)}`, {
      method: "PATCH",
      body: JSON.stringify({ value, expected_revision: session.state.revision }),
    });
    await refreshValidation();
    outcome = `${field.label} saved`;
  } catch (error) {
    outcome = error.message;
    failed = true;
    await load();
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

async function refreshValidation() {
  validation = await api("/api/validation");
}

function render() {
  app.replaceChildren();
  app.setAttribute("aria-busy", String(busy));
  const shell = element("div", { className: "app-shell" });
  shell.append(renderHeader());
  const layout = element("div", { className: "layout" });
  layout.append(renderWorkspace(), renderSidebar());
  shell.append(layout);
  app.append(shell);
}

function renderHeader() {
  const metadata = session.document.metadata;
  return element("header", { className: "masthead" }, [
    element("div", {}, [
      element("p", { className: "eyebrow", text: "Agent Canvas · Specification" }),
      element("h1", { text: metadata.title }),
      metadata.description ? element("p", { className: "subtitle", text: metadata.description }) : null,
    ]),
    element("div", { className: "run-meta" }, [
      element("span", { text: `Revision ${session.state.revision}` }),
      element("span", { className: "status-pill", text: session.state.status.replace("-", " ") }),
    ]),
  ]);
}

function renderWorkspace() {
  const workspace = element("section", { className: "workspace", id: "workspace", "aria-label": "Specification fields" });
  const tabs = session.document.tabs;
  const artifacts = session.document.initialization?.artifacts || [];
  const tabCount = tabs.length + (artifacts.length ? 1 : 0);
  if (activeTab >= tabCount) activeTab = 0;
  const tabList = element("div", { className: "tab-list", role: "tablist", "aria-label": "Specification sections" });
  tabs.forEach((tab, index) => {
    const button = element("button", {
      className: "tab",
      role: "tab",
      id: `tab-${tab.id}`,
      "aria-selected": index === activeTab,
      "aria-controls": `panel-${tab.id}`,
      tabindex: index === activeTab ? 0 : -1,
      text: tab.label,
    });
    button.addEventListener("click", () => { activeTab = index; render(); });
    button.addEventListener("keydown", (event) => moveTab(event, index));
    tabList.append(button);
  });
  if (artifacts.length) {
    const index = tabs.length;
    const button = element("button", {
      className: "tab",
      role: "tab",
      id: "tab-initialization",
      "aria-selected": index === activeTab,
      "aria-controls": "panel-initialization",
      tabindex: index === activeTab ? 0 : -1,
      text: `Initialization · ${artifacts.length}`,
    });
    button.addEventListener("click", () => { activeTab = index; render(); });
    button.addEventListener("keydown", (event) => moveTab(event, index));
    tabList.append(button);
  }
  workspace.append(tabList);
  if (activeTab === tabs.length && artifacts.length) {
    workspace.append(renderInitialization(artifacts));
    return workspace;
  }
  const current = tabs[activeTab];
  const panel = element("div", {
    className: "tab-panel",
    role: "tabpanel",
    id: `panel-${current.id}`,
    "aria-labelledby": `tab-${current.id}`,
  });
  if (current.description) panel.append(element("p", { className: "tab-intro", text: current.description }));
  for (const section of current.sections) panel.append(renderSection(section));
  workspace.append(panel);
  return workspace;
}

function moveTab(event, index) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const count = session.document.tabs.length + ((session.document.initialization?.artifacts || []).length ? 1 : 0);
  if (event.key === "Home") activeTab = 0;
  else if (event.key === "End") activeTab = count - 1;
  else activeTab = (index + (event.key === "ArrowRight" ? 1 : -1) + count) % count;
  render();
  document.querySelectorAll('[role="tab"]')[activeTab]?.focus();
}

function renderInitialization(artifacts) {
  const panel = element("div", {
    className: "tab-panel",
    role: "tabpanel",
    id: "panel-initialization",
    "aria-labelledby": "tab-initialization",
  });
  panel.append(element("p", { className: "tab-intro", text: "These files remain staged inside the run bundle. Edit them here before approving the specification." }));
  for (const artifact of artifacts) {
    const content = element("textarea", {
      className: "control artifact-content",
      "aria-label": `${artifact.title} content`,
    });
    content.value = artifact.content;
    content.addEventListener("change", () => saveArtifact(artifact, content.value));
    panel.append(element("article", {
      className: "field-card artifact-card",
      "data-provenance": artifact.provenance,
      "data-review": artifact.review_status,
    }, [
      element("div", { className: "field-topline" }, [
        element("h2", { className: "field-label", text: artifact.title }),
        element("div", { className: "badges" }, [
          makeBadge(artifact.kind.replaceAll("-", " ")),
          makeBadge(artifact.provenance.replace("-", " "), artifact.provenance),
          makeBadge(artifact.review_status.replace("-", " "), artifact.review_status),
        ]),
      ]),
      artifact.description ? element("p", { className: "description", text: artifact.description }) : null,
      element("p", { className: "artifact-path", text: `Staged path: initialization/${artifact.path}` }),
      artifact.rationale ? element("p", { className: "rationale", text: `Composer rationale: ${artifact.rationale}` }) : null,
      content,
    ]));
  }
  return panel;
}

async function saveArtifact(artifact, content) {
  if (busy) return;
  setBusy(true, `Saving ${artifact.title}…`);
  let outcome = "";
  let failed = false;
  try {
    session = await api(`/api/artifacts/${encodeURIComponent(artifact.id)}`, {
      method: "PATCH",
      body: JSON.stringify({ content, expected_revision: session.state.revision }),
    });
    await refreshValidation();
    outcome = `${artifact.title} saved`;
  } catch (error) {
    outcome = error.message;
    failed = true;
    await load();
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

function renderSection(section) {
  const heading = element("div", { className: "section-heading" }, [
    element("h2", { text: section.title }),
    section.description ? element("p", { text: section.description }) : null,
  ]);
  const fields = element("div", { className: "fields" });
  section.fields.forEach((field) => fields.append(renderField(field)));
  return element("section", { className: "section" }, [heading, fields]);
}

function renderSidebar() {
  const sidebar = element("aside", { className: "sidebar", "aria-label": "Review status and actions" });
  const fields = allFields();
  const settled = fields.filter((field) => field.value !== null && field.value !== "" && field.review_status !== "conflict" && field.provenance !== "unresolved").length;
  const percent = fields.length ? Math.round((settled / fields.length) * 100) : 0;
  const progressValue = element("div", { className: "progress-value" });
  progressValue.style.width = `${percent}%`;
  sidebar.append(element("section", { className: "side-card" }, [
    element("h2", { text: "Specification coverage" }),
    element("div", { className: "progress-track", role: "progressbar", "aria-valuenow": percent, "aria-valuemin": 0, "aria-valuemax": 100 }, [progressValue]),
    element("p", { className: "progress-copy", text: `${settled} of ${fields.length} fields settled · ${percent}%` }),
  ]));
  sidebar.append(renderIssues());
  sidebar.append(renderReview());
  sidebar.append(renderActions());
  return sidebar;
}

function renderIssues() {
  const card = element("section", { className: "side-card" }, [element("h2", { text: `Validation · ${validation.issues.length}` })]);
  if (!validation.issues.length) {
    card.append(element("p", { className: "no-issues", text: "No blocking issues detected." }));
    return card;
  }
  const list = element("ul", { className: "issue-list" });
  validation.issues.forEach((issue) => list.append(element("li", { className: "issue", text: issue.message })));
  card.append(list);
  return card;
}

function renderReview() {
  const facilitator = element("button", { className: "button", text: "Facilitator review", disabled: busy });
  facilitator.addEventListener("click", () => requestReview("facilitator"));
  const critic = element("button", { className: "button", text: "Adversarial review", disabled: busy });
  critic.addEventListener("click", () => requestReview("critic"));
  const compose = element("button", { className: "button", text: "Compose initialization", disabled: busy });
  compose.addEventListener("click", requestComposition);
  const card = element("section", { className: "side-card" }, [
    element("h2", { text: "Independent review" }),
    element("div", { className: "actions" }, [facilitator, critic, compose]),
  ]);
  const reviewState = session.state.independent_review;
  if (session.document.completion.require_independent_review) {
    card.append(element("p", {
      className: reviewState?.status === "passed" ? "no-issues" : "followup",
      text: reviewState?.status === "passed"
        ? `Required review passed for revision ${reviewState.revision}.`
        : "A passing critic review is required before approval.",
    }));
  }
  if (lastReview) {
    if (lastReview.status === "pending") {
      card.append(element("p", { className: "assistant-result", text: `Review ${lastReview.request_id} is queued.` }));
    } else {
      const response = lastReview.response;
      card.append(element("p", { className: "assistant-result", text: response.summary }));
      for (const question of response.questions || []) card.append(element("p", { className: "followup", text: question }));
      appendProposalAction(card, lastReview);
    }
  }
  if (lastComposition) {
    if (lastComposition.status === "pending") {
      card.append(element("p", { className: "assistant-result", text: `Composition ${lastComposition.request_id} is queued.` }));
    } else {
      card.append(element("p", { className: "assistant-result", text: lastComposition.response.summary }));
      for (const question of lastComposition.response.questions || []) card.append(element("p", { className: "followup", text: question }));
      appendProposalAction(card, lastComposition);
    }
  }
  return card;
}

async function requestReview(role) {
  setBusy(true, `Requesting ${role} review…`);
  let outcome = "";
  let failed = false;
  try {
    lastReview = await api("/api/review", {
      method: "POST",
      body: JSON.stringify({
        role,
        focus: role === "critic" ? "Find ambiguity, contradictions, hidden assumptions, and unverifiable acceptance criteria." : "Check completeness and ask only consequential follow-up questions.",
      }),
    });
    session = await api("/api/session");
    await refreshValidation();
    outcome = lastReview.status === "pending" ? "Review queued" : "Review received";
  } catch (error) {
    outcome = error.message;
    failed = true;
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

async function requestComposition() {
  setBusy(true, "Composing initialization package…");
  let outcome = "";
  let failed = false;
  try {
    lastComposition = await api("/api/compose", {
      method: "POST",
      body: JSON.stringify({
        focus: "If consequential ambiguity remains, propose a focused next canvas. Otherwise add a minimal, role-scoped initialization artifact package and identify the primary handoff.",
      }),
    });
    outcome = lastComposition.status === "pending" ? "Composition queued" : "Composition received";
  } catch (error) {
    outcome = error.message;
    failed = true;
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

function renderActions() {
  const identity = element("input", { className: "control identity", type: "text", value: "Local user", "aria-label": "Approver name" });
  identity.value = session.state.approval?.approved_by || "Local user";
  const validate = element("button", { className: "button", text: "Re-run validation", disabled: busy });
  validate.addEventListener("click", async () => { await refreshValidation(); render(); announce("Validation refreshed"); });
  const approve = element("button", { className: "button primary", text: session.state.approval ? "Approved" : "Approve specification", disabled: busy || !validation.ready || Boolean(session.state.approval) });
  approve.addEventListener("click", () => approveDocument(identity.value));
  const compile = element("button", { className: "button", text: session.state.status === "compiled" ? "Artifacts compiled" : "Compile handoff", disabled: busy || !session.state.approval || session.state.status === "compiled" });
  compile.addEventListener("click", compileDocument);
  return element("section", { className: "side-card" }, [
    element("h2", { text: "Finalize" }), identity,
    element("div", { className: "actions" }, [validate, approve, compile]),
    element("p", { className: "message", id: "action-message", text: "Edits are autosaved. Approval is invalidated by any later change." }),
  ]);
}

async function approveDocument(approvedBy) {
  setBusy(true, "Approving specification…");
  let outcome = "";
  let failed = false;
  try {
    session = await api("/api/approve", { method: "POST", body: JSON.stringify({ approved_by: approvedBy || "Local user", expected_revision: session.state.revision }) });
    outcome = "Specification approved";
  } catch (error) {
    outcome = error.message;
    failed = true;
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

async function compileDocument() {
  setBusy(true, "Compiling handoff artifacts…");
  let outcome = "";
  let failed = false;
  try {
    const result = await api("/api/compile", { method: "POST", body: JSON.stringify({ expected_revision: session.state.revision }) });
    session.state.status = result.status;
    outcome = `Handoff compiled at ${result.handoff}`;
  } catch (error) {
    outcome = error.message;
    failed = true;
  } finally {
    setBusy(false);
    render();
    announce(outcome, failed);
  }
}

function setBusy(value, message = "") {
  busy = value;
  app.setAttribute("aria-busy", String(value));
  if (message) announce(message);
}

function announce(message, error = false) {
  announcer.textContent = message;
  const visible = document.querySelector("#action-message");
  if (visible) {
    visible.textContent = message;
    visible.className = `message ${error ? "error" : "success"}`;
  }
}

async function load() {
  try {
    session = await api("/api/session");
    await refreshValidation();
    render();
  } catch (error) {
    app.replaceChildren(element("section", { className: "fatal" }, [
      element("h1", { text: "Canvas unavailable" }),
      element("p", { text: error.message }),
    ]));
    app.setAttribute("aria-busy", "false");
  }
}

load();
