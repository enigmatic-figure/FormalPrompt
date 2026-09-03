import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const canvasUrl = process.env.FORMALPROMPT_CANVAS_URL;
const chromePath = process.env.CHROME_PATH;
const debugPort = Number(process.env.CHROME_DEBUG_PORT || 59322);
if (!canvasUrl || !chromePath) process.exit(2);

const profile = await mkdtemp(join(tmpdir(), "formalprompt-workflow-smoke-"));
const chrome = spawn(chromePath, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--remote-debugging-port=" + debugPort,
  "--user-data-dir=" + profile,
  "--window-size=1600,1100",
  canvasUrl,
], { stdio: "ignore" });

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
    if (!value) throw new Error("Condition not ready: " + expression);
    return value;
  }, timeout);
}

try {
  const page = await retry(async () => {
    const response = await fetch("http://127.0.0.1:" + debugPort + "/json/list");
    if (!response.ok) throw new Error("Chrome debugger is not ready");
    const targets = await response.json();
    const found = targets.find((target) => target.type === "page" && target.url.startsWith("http"));
    if (!found) throw new Error("Canvas page is not ready");
    return found;
  });

  socket = new WebSocket(page.webSocketDebuggerUrl);
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
  await waitFor("document.querySelectorAll('[role=tab]').length === 3");
  await evaluate("([...document.querySelectorAll('[role=tab]')].find((node) => node.textContent.startsWith('Workflow'))).click()");
  await waitFor("document.querySelectorAll('.graph-node').length === 6");

  const initial = await evaluate("({ nodes: document.querySelectorAll('.graph-node').length, edges: document.querySelectorAll('.graph-edge').length, title: document.querySelector('.graph-heading h2').textContent, revision: Number(document.querySelector('.run-meta').textContent.match(/Revision (\\d+)/)[1]) })");
  await evaluate("document.querySelector('[data-node=implement]').click()");
  await waitFor("document.querySelector('.node-json') !== null");
  await evaluate("(() => { const area = document.querySelector('.node-json'); const node = JSON.parse(area.value); node.title = 'Implement verified project'; area.value = JSON.stringify(node, null, 2); [...document.querySelectorAll('.graph-inspector button')].find((button) => button.textContent === 'Save node declaration').click(); return true; })()");
  await waitFor(
    "document.querySelector('.run-meta').textContent.includes('Revision "
      + (initial.revision + 1)
      + "')",
  );
  await waitFor("document.querySelector('[data-node=implement]').textContent.includes('Implement verified project')");

  const final = await evaluate("({ nodes: document.querySelectorAll('.graph-node').length, edges: document.querySelectorAll('.graph-edge').length, selectedTitle: document.querySelector('[data-node=implement] strong').textContent, inspector: document.querySelector('.graph-inspector h2').textContent, revision: Number(document.querySelector('.run-meta').textContent.match(/Revision (\\d+)/)[1]), hashCleared: location.hash === '' })");
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
