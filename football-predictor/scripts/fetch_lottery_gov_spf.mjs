import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_URL = "https://www.lottery.gov.cn/jc/jsq/zqspf/";

function parseArgs(argv) {
  const out = {
    url: DEFAULT_URL,
    output: path.join(ROOT, "data", "external", "lottery_gov_zqspf_rendered.txt"),
    screenshot: "",
    linksOutput: "",
    channel: "chrome",
    timeout: 60000,
    waitText: "世界杯",
    expandAll: false,
    headful: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--url") out.url = argv[++i];
    else if (arg === "--output") out.output = path.resolve(argv[++i]);
    else if (arg === "--screenshot") out.screenshot = path.resolve(argv[++i]);
    else if (arg === "--links-output") out.linksOutput = path.resolve(argv[++i]);
    else if (arg === "--channel") out.channel = argv[++i];
    else if (arg === "--timeout") out.timeout = Number(argv[++i]);
    else if (arg === "--wait-text") out.waitText = argv[++i];
    else if (arg === "--no-wait-text") out.waitText = "";
    else if (arg === "--expand-all") out.expandAll = true;
    else if (arg === "--headful") out.headful = true;
    else if (arg === "--help") {
      console.log(`Usage: node scripts/fetch_lottery_gov_spf.mjs [options]

Options:
  --url URL              Page URL. Default: ${DEFAULT_URL}
  --output PATH          Rendered page text output.
  --screenshot PATH      Optional screenshot output for debugging.
  --links-output PATH    Optional JSON file containing page links.
  --channel NAME         Browser channel: chrome, msedge, or empty for bundled chromium.
  --timeout MS           Navigation/render timeout. Default: 60000.
  --wait-text TEXT       Text that indicates the rendered table is ready.
  --no-wait-text         Do not wait for any specific text.
  --expand-all           Click visible "+" expand controls before saving text.
  --headful              Show browser window.`);
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
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
  const candidates = [
    ...pnpmCandidates,
    path.join(ROOT, "node_modules", ".pnpm", "playwright@1.61.0", "node_modules", "playwright"),
    path.join(ROOT, "node_modules", ".pnpm", "playwright@1.61.1", "node_modules", "playwright"),
    path.join(ROOT, "node_modules", "playwright"),
    "playwright",
  ];
  const require = createRequire(import.meta.url);
  let lastError;
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(
    `Cannot load Playwright. Install it locally with "pnpm add -D playwright" or "npm install -D playwright". Last error: ${lastError?.message || ""}`
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { chromium } = requireLocalPlaywright();
  const launchOptions = {
    headless: !args.headful,
  };
  if (args.channel) {
    launchOptions.channel = args.channel;
  }

  let browser;
  try {
    browser = await chromium.launch(launchOptions);
  } catch (error) {
    throw new Error(
      `Failed to launch browser channel "${args.channel}". Try --channel msedge, --channel chrome, or run "npx playwright install chromium". Original error: ${error.message}`
    );
  }

  const page = await browser.newPage({
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    viewport: { width: 1440, height: 1200 },
  });
  page.setDefaultTimeout(args.timeout);
  await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: args.timeout });
  try {
    await page.waitForLoadState("networkidle", { timeout: Math.min(args.timeout, 30000) });
  } catch {
    // Some official pages keep long-polling or analytics requests open.
  }
  if (args.waitText) {
    await page.getByText(args.waitText).first().waitFor({ timeout: args.timeout });
  }
  await page.waitForTimeout(1500);
  let expandedClicks = 0;
  if (args.expandAll) {
    for (let round = 0; round < 8; round += 1) {
      const clicked = await page.evaluate(() => {
        const candidates = Array.from(document.querySelectorAll("a,button,span,td,div"))
          .filter((element) => {
            const text = (element.textContent || "").trim();
            if (text !== "+") return false;
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          });
        let count = 0;
        for (const element of candidates) {
          const rect = element.getBoundingClientRect();
          const eventOptions = {
            bubbles: true,
            cancelable: true,
            clientX: rect.left + rect.width / 2,
            clientY: rect.top + rect.height / 2,
          };
          element.dispatchEvent(new MouseEvent("mousedown", eventOptions));
          element.dispatchEvent(new MouseEvent("mouseup", eventOptions));
          element.dispatchEvent(new MouseEvent("click", eventOptions));
          count += 1;
        }
        return count;
      });
      expandedClicks += clicked;
      if (!clicked) break;
      await page.waitForTimeout(800);
    }
  }
  const text = await page.locator("body").innerText({ timeout: args.timeout });
  fs.mkdirSync(path.dirname(args.output), { recursive: true });
  fs.writeFileSync(args.output, text, "utf8");
  if (args.screenshot) {
    fs.mkdirSync(path.dirname(args.screenshot), { recursive: true });
    await page.screenshot({ path: args.screenshot, fullPage: true });
  }
  if (args.linksOutput) {
    const links = await page.locator("a").evaluateAll((anchors) =>
      anchors.map((anchor) => ({
        text: anchor.innerText || anchor.textContent || "",
        href: anchor.href || "",
      }))
    );
    fs.mkdirSync(path.dirname(args.linksOutput), { recursive: true });
    fs.writeFileSync(args.linksOutput, JSON.stringify(links, null, 2), "utf8");
  }
  await browser.close();
  console.log(
    JSON.stringify(
      {
        ok: true,
        url: args.url,
        output: args.output,
        chars: text.length,
        expandedClicks,
        screenshot: args.screenshot || "",
        linksOutput: args.linksOutput || "",
        channel: args.channel,
      },
      null,
      2
    )
  );
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
