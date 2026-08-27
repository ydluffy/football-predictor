import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_URL = "https://www.lottery.gov.cn/jc/zqsgkj/";

function parseArgs(argv) {
  const out = {
    url: DEFAULT_URL,
    startDate: "",
    endDate: "",
    output: path.join(ROOT, "data", "external", "lottery_gov_zqsgkj_results_rendered.txt"),
    screenshot: "",
    channel: "chrome",
    timeout: 60000,
    headful: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--url") out.url = argv[++i];
    else if (arg === "--start-date") out.startDate = argv[++i];
    else if (arg === "--end-date") out.endDate = argv[++i];
    else if (arg === "--output") out.output = path.resolve(argv[++i]);
    else if (arg === "--screenshot") out.screenshot = path.resolve(argv[++i]);
    else if (arg === "--channel") out.channel = argv[++i];
    else if (arg === "--timeout") out.timeout = Number(argv[++i]);
    else if (arg === "--headful") out.headful = true;
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return out;
}

function requireLocalPlaywright() {
  const pnpmDir = path.join(ROOT, "node_modules", ".pnpm");
  const pnpmCandidates = fs.existsSync(pnpmDir)
    ? fs
        .readdirSync(pnpmDir)
        .filter((name) => name.startsWith("playwright@"))
        .map((name) => path.join(pnpmDir, name, "node_modules", "playwright"))
    : [];
  const require = createRequire(import.meta.url);
  const candidates = [
    ...pnpmCandidates,
    path.join(ROOT, "node_modules", ".pnpm", "playwright@1.61.0", "node_modules", "playwright"),
    path.join(ROOT, "node_modules", ".pnpm", "playwright@1.61.1", "node_modules", "playwright"),
    path.join(ROOT, "node_modules", "playwright"),
    "playwright",
  ];
  let lastError;
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(`Cannot load Playwright: ${lastError?.message || ""}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.startDate || !args.endDate) {
    throw new Error("--start-date and --end-date are required");
  }
  const { chromium } = requireLocalPlaywright();
  const launchOptions = { headless: !args.headful };
  if (args.channel) launchOptions.channel = args.channel;
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    viewport: { width: 1440, height: 1200 },
  });
  page.setDefaultTimeout(args.timeout);
  await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: args.timeout });
  try {
    await page.waitForLoadState("networkidle", { timeout: 30000 });
  } catch {}
  await page.waitForSelector("#start_date", { timeout: args.timeout });
  await page.evaluate(
    ({ startDate, endDate }) => {
      const start = document.querySelector("#start_date");
      const end = document.querySelector("#end_date");
      if (start) {
        start.value = startDate;
        start.dispatchEvent(new Event("input", { bubbles: true }));
        start.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (end) {
        end.value = endDate;
        end.dispatchEvent(new Event("input", { bubbles: true }));
        end.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (typeof window.click_submit === "function") {
        window.click_submit();
      } else {
        const btn = Array.from(document.querySelectorAll("a,button")).find((el) =>
          (el.textContent || "").includes("开始查询")
        );
        btn?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      }
    },
    { startDate: args.startDate, endDate: args.endDate }
  );
  await page.waitForTimeout(5000);
  const text = await page.locator("body").innerText({ timeout: args.timeout });
  fs.mkdirSync(path.dirname(args.output), { recursive: true });
  fs.writeFileSync(args.output, text, "utf8");
  if (args.screenshot) {
    fs.mkdirSync(path.dirname(args.screenshot), { recursive: true });
    await page.screenshot({ path: args.screenshot, fullPage: true });
  }
  await browser.close();
  console.log(JSON.stringify({ ok: true, output: args.output, chars: text.length }, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
