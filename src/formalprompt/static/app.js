const app = document.querySelector("#app");
const announcer = document.querySelector("#announcer");
let session = null;
let validation = { ready: false, issues: [] };
let activeTab = 0;
let busy = false;
let selectedWorkflowNode = null;
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
  const proposal = result.response.next_document;
  const preview = element("textarea", {
    className: "control proposal-preview",
    readonly: "readonly",
    "aria-label": "Proposed replacement canvas JSON",
  });
  preview.value = JSON.stringify(proposal, null, 2);
  panel.append(element("details", { className: "proposal-inspection" }, [
    element("summary", { text: proposalChangeSummary(session.document, proposal) }),
    element("p", {
      className: "description",
      text: "Inspect the complete replacement before applying it. Confirmed facts are enforced by the broker.",
    }),
    preview,
  ]));
  const apply = element("button", { className: "button compact", text: "Apply proposed canvas", disabled: busy });
  apply.addEventListener("click", () => applyProposal(result.request_id));
  panel.append(apply);
}

function proposalChangeSummary(current, proposal) {
  const currentFields = new Map(current.tabs.flatMap((tab) => tab.sections)
    .flatMap((section) => section.fields).map((field) => [field.id, JSON.stringify(field)]));
  const proposedFields = new Map(proposal.tabs.flatMap((tab) => tab.sections)
    .flatMap((section) => section.fields).map((field) => [field.id, JSON.stringify(field)]));
  const currentArtifacts = new Map((current.initialization?.artifacts || [])
    .map((artifact) => [artifact.id, JSON.stringify(artifact)]));
  const proposedArtifacts = new Map((proposal.initialization?.artifacts || [])
    .map((artifact) => [artifact.id, JSON.stringify(artifact)]));
  const fieldChanges = mapChangeCount(currentFields, proposedFields);
  const artifactChanges = mapChangeCount(currentArtifacts, proposedArtifacts);
  const currentNodes = current.workflow?.nodes.length || 0;
  const proposedNodes = proposal.workflow?.nodes.length || 0;
  return `Inspect proposal · ${fieldChanges} field changes · ${artifactChanges} artifact changes · ${currentNodes}→${proposedNodes} nodes`;
}

function mapChangeCount(left, right) {
  const keys = new Set([...left.keys(), ...right.keys()]);
  return [...keys].filter((key) => left.get(key) !== right.get(key)).length;
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
    if (session.document.workflow) {
      activeTab = session.document.tabs.length + ((session.document.initialization?.artifacts || []).length ? 1 : 0);
    } else {
      activeTab = (session.document.initialization?.artifacts || []).length ? session.document.tabs.length : 0;
    }
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
  const workflow = session.document.workflow;
  const workflowIndex = tabs.length + (artifacts.length ? 1 : 0);
  const tabCount = workflowIndex + (workflow ? 1 : 0);
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
  if (workflow) {
    const button = element("button", {
      className: "tab",
      role: "tab",
      id: "tab-workflow",
      "aria-selected": workflowIndex === activeTab,
      "aria-controls": "panel-workflow",
      tabindex: workflowIndex === activeTab ? 0 : -1,
      text: `Workflow · ${workflow.nodes.length}`,
    });
    button.addEventListener("click", () => { activeTab = workflowIndex; render(); });
    button.addEventListener("keydown", (event) => moveTab(event, workflowIndex));
    tabList.append(button);
  }
  workspace.append(tabList);
  if (activeTab === tabs.length && artifacts.length) {
    workspace.append(renderInitialization(artifacts));
    return workspace;
  }
  if (activeTab === workflowIndex && workflow) {
    workspace.append(renderWorkflow(workflow));
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
  const count = session.document.tabs.length
    + ((session.document.initialization?.artifacts || []).length ? 1 : 0)
    + (session.document.workflow ? 1 : 0);
  if (event.key === "Home") activeTab = 0;
  else if (event.key === "End") activeTab = count - 1;
  else activeTab = (index + (event.key === "ArrowRight" ? 1 : -1) + count) % count;
  render();
  document.querySelectorAll('[role="tab"]')[activeTab]?.focus();
}

function renderWorkflow(graph) {
  const panel = element("div", {
    className: "tab-panel workflow-panel",
    role: "tabpanel",
    id: "panel-workflow",
    "aria-labelledby": "tab-workflow",
  });
  const kind = element("select", { className: "control graph-kind", "aria-label": "Node type" });
  for (const value of ["input", "artifact", "agent", "operation", "review", "gate", "join"]) {
    kind.append(element("option", { value, text: value.replace("-", " ") }));
  }
  const add = element("button", { className: "button compact", text: "Add node", disabled: busy });
  add.addEventListener("click", () => addWorkflowNode(graph, kind.value));
  const arrange = element("button", { className: "button compact", text: "Arrange DAG", disabled: busy });
  arrange.addEventListener("click", () => arrangeWorkflow(graph));
  panel.append(
    element("div", { className: "graph-heading" }, [
      element("div", {}, [
        element("h2", { text: graph.title }),
        element("p", { className: "tab-intro", text: graph.description || "Approved execution blueprint" }),
      ]),
      element("div", { className: "graph-toolbar" }, [kind, add, arrange]),
    ]),
  );

  const surface = element("div", { className: "graph-surface", tabindex: 0 });
  const width = Math.max(1500, ...graph.nodes.map((node) => node.position.x + 300));
  const height = Math.max(720, ...graph.nodes.map((node) => node.position.y + 240));
  surface.style.width = `${width}px`;
  surface.style.height = `${height}px`;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "graph-edges");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("aria-hidden", "true");
  const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]));
  for (const edge of graph.edges) {
    const source = nodeMap.get(edge.source_node);
    const target = nodeMap.get(edge.target_node);
    if (!source || !target) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const x1 = source.position.x + 230;
    const y1 = source.position.y + 64;
    const x2 = target.position.x;
    const y2 = target.position.y + 64;
    const bend = Math.max(50, Math.abs(x2 - x1) * 0.45);
    path.setAttribute("d", `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`);
    path.setAttribute("class", `graph-edge edge-${edge.data_type}`);
    path.setAttribute("data-edge", edge.id);
    svg.append(path);
  }
  surface.append(svg);
  for (const node of graph.nodes) surface.append(renderWorkflowNode(graph, node));
  const viewport = element("div", { className: "graph-viewport", "aria-label": "Workflow node graph" }, [surface]);
  const inspector = renderWorkflowInspector(graph, nodeMap.get(selectedWorkflowNode));
  panel.append(element("div", { className: "graph-layout" }, [viewport, inspector]));
  return panel;
}

function renderWorkflowNode(graph, node) {
  const card = element("article", {
    className: `graph-node node-${node.kind}${node.id === selectedWorkflowNode ? " selected" : ""}`,
    tabindex: 0,
    "data-node": node.id,
    "data-provenance": node.provenance,
    "aria-label": `${node.kind} node ${node.title}`,
  });
  card.style.left = `${node.position.x}px`;
  card.style.top = `${node.position.y}px`;
  card.append(
    element("div", { className: "node-title" }, [
      makeBadge(node.kind),
      element("strong", { text: node.title }),
    ]),
    node.description ? element("p", { text: node.description }) : null,
    element("p", { className: "node-meta", text: `${node.provenance.replace("-", " ")} · ${node.review_status.replace("-", " ")}` }),
  );
  const inputs = element("div", { className: "node-ports inputs" });
  for (const port of node.input_ports) inputs.append(element("span", { className: `node-port port-${port.data_type}`, title: port.label }));
  const outputs = element("div", { className: "node-ports outputs" });
  for (const port of node.output_ports) outputs.append(element("span", { className: `node-port port-${port.data_type}`, title: port.label }));
  card.append(inputs, outputs);
  card.addEventListener("click", () => { selectedWorkflowNode = node.id; render(); });
  card.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const delta = event.shiftKey ? 50 : 10;
    const moved = structuredClone(graph);
    const target = moved.nodes.find((candidate) => candidate.id === node.id);
    if (event.key === "ArrowLeft") target.position.x = Math.max(0, target.position.x - delta);
    if (event.key === "ArrowRight") target.position.x += delta;
    if (event.key === "ArrowUp") target.position.y = Math.max(0, target.position.y - delta);
    if (event.key === "ArrowDown") target.position.y += delta;
    saveWorkflow(moved, `${node.title} moved`);
  });
  card.addEventListener("pointerdown", (event) => beginNodeDrag(event, graph, node, card));
  return card;
}

function beginNodeDrag(event, graph, node, card) {
  if (event.button !== 0) return;
  selectedWorkflowNode = node.id;
  const startX = event.clientX;
  const startY = event.clientY;
  const origin = { ...node.position };
  let moved = false;
  card.setPointerCapture(event.pointerId);
  const move = (current) => {
    const x = Math.max(0, origin.x + current.clientX - startX);
    const y = Math.max(0, origin.y + current.clientY - startY);
    moved ||= Math.abs(x - origin.x) + Math.abs(y - origin.y) > 4;
    card.style.left = `${x}px`;
    card.style.top = `${y}px`;
  };
  const finish = (current) => {
    card.removeEventListener("pointermove", move);
    card.removeEventListener("pointerup", finish);
    card.removeEventListener("pointercancel", finish);
    if (!moved) return;
    const updated = structuredClone(graph);
    const target = updated.nodes.find((candidate) => candidate.id === node.id);
    target.position.x = Math.max(0, Math.round(origin.x + current.clientX - startX));
    target.position.y = Math.max(0, Math.round(origin.y + current.clientY - startY));
    saveWorkflow(updated, `${node.title} moved`);
  };
  card.addEventListener("pointermove", move);
  card.addEventListener("pointerup", finish);
  card.addEventListener("pointercancel", finish);
}

function renderWorkflowInspector(graph, selected) {
  const inspector = element("aside", { className: "graph-inspector", "aria-label": "Workflow node inspector" });
  if (!selected) {
    inspector.append(
      element("h2", { text: "Workflow resources" }),
      element("p", { className: "description", text: "Select a node to inspect its exact declaration. Drag nodes or use arrow keys to change layout." }),
    );
    for (const resource of graph.resources) {
      inspector.append(element("div", { className: "resource-row" }, [
        makeBadge(resource.kind),
        element("span", { text: resource.title }),
        element("code", { text: resource.reference }),
      ]));
    }
    return inspector;
  }
  inspector.append(
    element("h2", { text: selected.title }),
    element("p", { className: "description", text: "The declaration below is canonical workflow state. Node ID and kind are immutable in this editor." }),
  );
  const declaration = element("textarea", { className: "control node-json", "aria-label": `${selected.title} declaration` });
  declaration.value = JSON.stringify(selected, null, 2);
  const save = element("button", { className: "button primary", text: "Save node declaration", disabled: busy });
  save.addEventListener("click", () => {
    try {
      const candidate = JSON.parse(declaration.value);
      if (candidate.id !== selected.id || candidate.kind !== selected.kind) throw new Error("Node ID and kind cannot be changed here");
      const updated = structuredClone(graph);
      updated.nodes[updated.nodes.findIndex((node) => node.id === selected.id)] = candidate;
      saveWorkflow(updated, `${selected.title} declaration saved`, [selected.id]);
    } catch (error) {
      announce(error.message, true);
    }
  });
  const targets = element("select", { className: "control", "aria-label": "Connection target" });
  for (const node of graph.nodes.filter((node) => node.id !== selected.id)) {
    targets.append(element("option", { value: node.id, text: node.title }));
  }
  const connect = element("button", { className: "button", text: "Connect compatible ports", disabled: busy || !targets.children.length });
  connect.addEventListener("click", () => connectWorkflowNodes(graph, selected.id, targets.value));
  const isBoundary = graph.entry_nodes.includes(selected.id) || graph.completion_nodes.includes(selected.id);
  const remove = element("button", {
    className: "button danger",
    text: isBoundary ? "Boundary node cannot be deleted" : "Delete node",
    disabled: busy || graph.nodes.length === 1 || isBoundary,
  });
  remove.addEventListener("click", () => deleteWorkflowNode(graph, selected.id));
  inspector.append(declaration, save, element("hr"), targets, connect, remove);
  const edges = graph.edges.filter((edge) => edge.source_node === selected.id || edge.target_node === selected.id);
  if (edges.length) inspector.append(element("h3", { text: "Connections" }));
  for (const edge of edges) {
    const drop = element("button", { className: "edge-delete", text: "Remove", disabled: busy });
    drop.addEventListener("click", () => {
      const updated = structuredClone(graph);
      updated.edges = updated.edges.filter((candidate) => candidate.id !== edge.id);
      saveWorkflow(updated, `Connection ${edge.id} removed`);
    });
    inspector.append(element("div", { className: "edge-row" }, [
      element("code", { text: `${edge.source_node} → ${edge.target_node}` }), drop,
    ]));
  }
  return inspector;
}

function connectWorkflowNodes(graph, sourceId, targetId) {
  const source = graph.nodes.find((node) => node.id === sourceId);
  const target = graph.nodes.find((node) => node.id === targetId);
  const pair = source.output_ports.flatMap((output) => target.input_ports.map((input) => [output, input]))
    .find(([output, input]) => {
      if (output.data_type !== input.data_type) return false;
      return input.multiple || !graph.edges.some(
        (edge) => edge.target_node === targetId && edge.target_port === input.id,
      );
    });
  if (!pair) { announce("These nodes have no compatible open port types", true); return; }
  const [output, input] = pair;
  const updated = structuredClone(graph);
  const base = `${sourceId}-${targetId}-${output.data_type}`.replace(/[^A-Za-z0-9_.-]/g, "-");
  let id = base;
  let suffix = 2;
  while (updated.edges.some((edge) => edge.id === id)) id = `${base}-${suffix++}`;
  updated.edges.push({ id, source_node: sourceId, source_port: output.id, target_node: targetId, target_port: input.id, data_type: output.data_type, label: "" });
  saveWorkflow(updated, `Connected ${source.title} to ${target.title}`);
}

function deleteWorkflowNode(graph, nodeId) {
  const updated = structuredClone(graph);
  updated.nodes = updated.nodes.filter((node) => node.id !== nodeId);
  updated.edges = updated.edges.filter((edge) => edge.source_node !== nodeId && edge.target_node !== nodeId);
  updated.entry_nodes = updated.entry_nodes.filter((id) => id !== nodeId);
  updated.completion_nodes = updated.completion_nodes.filter((id) => id !== nodeId);
  selectedWorkflowNode = null;
  saveWorkflow(updated, `Node ${nodeId} deleted`);
}

function addWorkflowNode(graph, kind) {
  const updated = structuredClone(graph);
  let index = updated.nodes.length + 1;
  let id = `${kind}-${index}`;
  while (updated.nodes.some((node) => node.id === id)) id = `${kind}-${++index}`;
  const position = { x: 80 + (index % 4) * 260, y: 100 + Math.floor(index / 4) * 190 };
  const controlIn = [{ id: "in", label: "Input", data_type: "control", required: true, multiple: false }];
  const controlOut = [{ id: "out", label: "Output", data_type: "control", required: false, multiple: false }];
  const common = { id, kind, title: `${kind[0].toUpperCase()}${kind.slice(1)} ${index}`, description: "", position, input_ports: controlIn, output_ports: controlOut, provenance: "unresolved", review_status: "needs-input", importance: "normal", rationale: "Added by the user; complete and save the declaration to confirm it." };
  const prompt = updated.resources.find((resource) => resource.kind === "prompt")?.id || "select.prompt";
  let node;
  if (kind === "input") node = { ...common, input_ports: [], resource_ids: [] };
  else if (kind === "artifact") node = { ...common, resource_id: updated.resources[0]?.id || "select.resource", mode: "read" };
  else if (kind === "agent") node = { ...common, model: "select-model", prompt_resource: prompt, agent_definition_resource: null, context_resources: [], skill_resources: [], tool_resources: [], write_scope: [], acceptance_criteria: ["Define observable completion"], timeout_seconds: 3600, token_budget: null };
  else if (kind === "operation") node = { ...common, operation: "research", instruction_resource: prompt, resource_ids: [], write_scope: [], acceptance_criteria: ["Define observable completion"], timeout_seconds: 3600 };
  else if (kind === "review") node = { ...common, model: "select-review-model", prompt_resource: prompt, subject_resources: [], required_evidence: ["Define required evidence"], independent: true, independent_from: [], remediation: { maximum_rounds: 3, repair_template_resource: updated.resources.find((resource) => ["template", "prompt"].includes(resource.kind))?.id || "select.repair-template", exhaustion: "request-user-decision" } };
  else if (kind === "gate") node = { ...common, gate: "user-approval", criteria: ["Define approval condition"], required_evidence: [] };
  else node = { ...common, strategy: "all", remaining_inputs: null, input_ports: [
    { id: "branch-a", label: "Branch A", data_type: "control", required: true, multiple: false },
    { id: "branch-b", label: "Branch B", data_type: "control", required: true, multiple: false },
  ] };
  updated.nodes.push(node);
  selectedWorkflowNode = id;
  saveWorkflow(updated, `${node.title} added`);
}

function arrangeWorkflow(graph) {
  const updated = structuredClone(graph);
  const indegree = new Map(updated.nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(updated.nodes.map((node) => [node.id, []]));
  for (const edge of updated.edges) {
    if (!indegree.has(edge.target_node) || !outgoing.has(edge.source_node)) continue;
    indegree.set(edge.target_node, indegree.get(edge.target_node) + 1);
    outgoing.get(edge.source_node).push(edge.target_node);
  }
  const queue = [...updated.nodes.filter((node) => indegree.get(node.id) === 0).map((node) => ({ id: node.id, level: 0 }))];
  const levels = new Map();
  while (queue.length) {
    const current = queue.shift();
    levels.set(current.id, Math.max(levels.get(current.id) || 0, current.level));
    for (const target of outgoing.get(current.id)) {
      indegree.set(target, indegree.get(target) - 1);
      if (indegree.get(target) === 0) queue.push({ id: target, level: current.level + 1 });
    }
  }
  const rows = new Map();
  for (const node of updated.nodes) {
    const level = levels.get(node.id) || 0;
    const row = rows.get(level) || 0;
    node.position = { x: 50 + level * 280, y: 70 + row * 180 };
    rows.set(level, row + 1);
  }
  saveWorkflow(updated, "Workflow arranged by dependency level");
}

async function saveWorkflow(workflow, message, confirmedNodeIds = []) {
  if (busy) return;
  setBusy(true, "Saving workflow…");
  let failed = false;
  let outcome = message;
  try {
    session = await api("/api/workflow", {
      method: "PUT",
      body: JSON.stringify({
        workflow,
        expected_revision: session.state.revision,
        confirmed_node_ids: confirmedNodeIds,
      }),
    });
    await refreshValidation();
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
