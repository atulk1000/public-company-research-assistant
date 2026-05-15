import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import fsSync from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();
const chromeCandidates = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
];
const chromePath = chromeCandidates.find((candidate) => {
  try {
    fsSync.statSync(candidate);
    return true;
  } catch {
    return false;
  }
});

if (!chromePath) {
  throw new Error("No Chrome or Edge executable found in the expected Windows install paths.");
}

const outputDir = path.join(repoRoot, "docs", "screenshots");
const profileDir = path.join(repoRoot, ".tmp", "chrome-demo-profile");
const remoteDebuggingPort = 9223;
const appUrl = process.env.STREAMLIT_URL || "http://localhost:8501";

const scenarios = [
  {
    name: "sql_only",
    question: "Which loaded company had the highest operating margin in the latest reported quarter?",
    tabText: "Metrics",
    waitFor: "Rows Returned",
  },
  {
    name: "rag_citations",
    question: "What themes dominate Alphabet latest management commentary around AI?",
    tabText: "Documents",
    waitFor: "Retrieved Evidence",
  },
  {
    name: "hybrid_analysis",
    question: "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters.",
    tabText: "Documents",
    waitFor: "Retrieved Evidence",
  },
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForJson(url, attempts = 60) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return await response.json();
      }
    } catch {
      // Browser is still starting.
    }
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function connectCdp(webSocketDebuggerUrl) {
  const socket = new WebSocket(webSocketDebuggerUrl);
  let nextId = 1;
  const pending = new Map();

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (!payload.id || !pending.has(payload.id)) {
      return;
    }
    const { resolve, reject } = pending.get(payload.id);
    pending.delete(payload.id);
    if (payload.error) {
      reject(new Error(payload.error.message));
    } else {
      resolve(payload.result);
    }
  });

  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  return {
    send(method, params = {}) {
      const id = nextId;
      nextId += 1;
      const promise = new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
      socket.send(JSON.stringify({ id, method, params }));
      return promise;
    },
    close() {
      socket.close();
    },
  };
}

async function evaluate(client, expression, awaitPromise = false) {
  const result = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || "Runtime.evaluate failed");
  }
  return result.result?.value;
}

async function waitForText(client, text, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const found = await evaluate(
      client,
      `document.body && document.body.innerText.includes(${JSON.stringify(text)})`
    );
    if (found) {
      return;
    }
    await sleep(1500);
  }
  throw new Error(`Timed out waiting for page text: ${text}`);
}

async function setQuestion(client, question) {
  const escapedQuestion = JSON.stringify(question);
  await evaluate(
    client,
    `(() => {
      const textarea = document.querySelector("textarea");
      if (!textarea) return false;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
      setter.call(textarea, ${escapedQuestion});
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      textarea.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    })()`
  );
}

async function clickButtonByText(client, text) {
  const clicked = await evaluate(
    client,
    `(() => {
      const button = Array.from(document.querySelectorAll("button"))
        .find((candidate) => candidate.innerText.trim().includes(${JSON.stringify(text)}));
      if (!button) return false;
      button.click();
      return true;
    })()`
  );
  if (!clicked) {
    throw new Error(`Could not find button containing text: ${text}`);
  }
}

async function clickTabByText(client, text) {
  await evaluate(
    client,
    `(() => {
      const tab = Array.from(document.querySelectorAll("button, [role='tab']"))
        .find((candidate) => candidate.innerText.trim() === ${JSON.stringify(text)});
      if (tab) tab.click();
      return Boolean(tab);
    })()`
  );
}

async function capture(client, outputPath) {
  const screenshot = await client.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
    fromSurface: true,
  });
  await fs.writeFile(outputPath, Buffer.from(screenshot.data, "base64"));
}

await fs.mkdir(outputDir, { recursive: true });
await fs.rm(profileDir, { recursive: true, force: true });
await fs.mkdir(profileDir, { recursive: true });

const browser = spawn(chromePath, [
  "--headless=new",
  "--disable-gpu",
  "--disable-dev-shm-usage",
  "--no-sandbox",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${remoteDebuggingPort}`,
  `--user-data-dir=${profileDir}`,
  "--window-size=1440,1400",
  appUrl,
]);

try {
  const targets = await waitForJson(`http://localhost:${remoteDebuggingPort}/json/list`);
  const pageTarget = targets.find((target) => target.type === "page") || targets[0];
  const client = await connectCdp(pageTarget.webSocketDebuggerUrl);

  await client.send("Page.enable");
  await client.send("Runtime.enable");

  for (const [index, scenario] of scenarios.entries()) {
    const url = new URL(appUrl);
    url.searchParams.set("demo_question", scenario.question);
    url.searchParams.set("demo_live", "false");
    url.searchParams.set("demo_run", `${scenario.name}-${Date.now()}-${index}`);

    await client.send("Page.navigate", { url: url.toString() });
    await waitForText(client, "Public Company Research Assistant");
    await waitForText(client, "Analysis Plan");
    await waitForText(client, "Answer");
    await sleep(2500);
    await clickTabByText(client, scenario.tabText);
    await waitForText(client, scenario.waitFor);
    await sleep(1000);
    await capture(client, path.join(outputDir, `${scenario.name}.png`));
    console.log(`Captured ${scenario.name}.png`);
  }

  client.close();
} finally {
  browser.kill();
}
