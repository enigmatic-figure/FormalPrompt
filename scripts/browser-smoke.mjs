import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const canvasUrl = process.env.FORMALPROMPT_CANVAS_URL;
const chromePath = process.env.CHROME_PATH;
const debugPort = Number(process.env.CHROME_DEBUG_PORT || 59321);
if (!canvasUrl || !chromePath) {
  console.error("FORMALPROMPT_CANVAS_URL and CHROME_PATH are required");
  process.exit(2);
}

const profile = await mkdtemp(join(tmpdir(), "formalprompt-smoke-"));
const chrome = spawn(
  chromePath,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${profile}`,
    "--window-size=1440,1100",
    canvasUrl,
  ],
  { stdio: "ignore" },
);

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function retry(operation, timeout = 10000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      await sleep(100);
    }
  }
  throw lastError || new Error("Operation timed out");
}

let socket;
const pending = new Map();
let sequence = 0;

function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const response = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || "Browser evaluation failed");
  }
  return response.result.value;
}

async function waitFor(expression, timeout = 10000) {
  return retry(async () => {
    const value = await evaluate(expression);
    if (!value) throw new Error(`Condition not ready: ${expression}`);
    return value;
  }, timeout);
}

try {
  const pages = await retry(async () => {
    const response = await fetch(`http://127.0.0.1:${debugPort}/json/list`);
    if (!response.ok) throw new Error("Chrome debugger is not ready");
    const targets = await response.json();
    const page = targets.find((target) => target.type === "page" && target.url.startsWith("http"));
    if (!page) throw new Error("Canvas page is not ready");
    return page;
  });

  socket = new WebSocket(pages.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  });
  await command("Runtime.enable");
  await waitFor("document.querySelectorAll('[role=\"tab\"]').length === 4");
  await waitFor("document.querySelectorAll('.field-card').length === 3");

  const initial = await evaluate(`({
    title: document.querySelector('h1').textContent,
    tabs: document.querySelectorAll('[role="tab"]').length,
    visibleFields: document.querySelectorAll('.field-card').length,
    coverage: document.querySelector('.progress-copy').textContent,
    issues: document.querySelectorAll('.issue').length,
    status: document.querySelector('.status-pill').textContent,
    revision: Number(document.querySelector('.run-meta').textContent.match(/Revision (\\d+)/)[1])
  })`);

  if (initial.issues > 0) {
    await evaluate(`(() => {
      [...document.querySelectorAll('[role="tab"]')].find((node) => node.textContent === 'Delivery').click();
      const input = document.getElementById('field-delivery.mvp_evidence');
      input.value = 'Automated tests, lint, package inspection, authenticated API integration, and a real Chrome journey must pass; Carbonyl launch behavior must be covered and exercised on Linux CI.';
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })()`);
    await waitFor(`document.querySelector('.run-meta').textContent.includes('Revision ${initial.revision + 1}')`);
  }
  await waitFor("document.querySelectorAll('.issue').length === 0");

  await evaluate(`(() => {
    [...document.querySelectorAll('button')].find((node) => node.textContent === 'Approve specification').click();
    return true;
  })()`);
  await waitFor("document.querySelector('.status-pill').textContent.trim().toLowerCase() === 'approved'");
  await evaluate(`(() => {
    [...document.querySelectorAll('button')].find((node) => node.textContent === 'Compile handoff').click();
    return true;
  })()`);
  await waitFor("document.querySelector('.status-pill').textContent.trim().toLowerCase() === 'compiled'");

  const final = await evaluate(`({
    revision: document.querySelector('.run-meta').textContent.match(/Revision \\d+/)[0],
    issues: document.querySelectorAll('.issue').length,
    status: document.querySelector('.status-pill').textContent,
    hashCleared: location.hash === ''
  })`);
  console.log(JSON.stringify({ initial, final }));
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  const exited = new Promise((resolve) => chrome.once("exit", resolve));
  chrome.kill();
  await Promise.race([exited, sleep(3000)]);
  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      await rm(profile, { recursive: true, force: true });
      break;
    } catch (error) {
      if (error.code !== "EBUSY" || attempt === 9) throw error;
      await sleep(200);
    }
  }
}
