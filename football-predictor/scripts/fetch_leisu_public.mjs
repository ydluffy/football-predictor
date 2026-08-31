import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_URL = "https://www.leisu.com/";

function parseArgs(argv) {
  const out = {
    url: DEFAULT_URL,
    output: path.join(ROOT, "data", "external", "leisu_home_rendered.html"),
    screenshot: "",
    channel: "chrome",
    timeout: 60000,
    waitText: "情报",
    headful: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--url") out.url = argv[++i];
    else if (arg === "--output") out.output = path.resolve(argv[++i]);
    else if (arg === "--screenshot") out.screenshot = path.resolve(argv[++i]);
    else if (arg === "--channel") out.channel = argv[++i];
    else if (arg === "--timeout") out.timeout = Number(argv[++i]);
    else if (arg === "--wait-text") out.waitText = argv[++i];
    else if (arg === "--headful") out.headful = true;
    else if (arg === "--help") {
      console.log(`Usage: node scripts/fetch_leisu_public.mjs [options]

Options:
  --url URL              Page URL. Default: ${DEFAULT_URL}
  --output PATH          Rendered HTML output.
  --screenshot PATH      Optional screenshot output for debugging.
  --channel NAME         Browser channel: chrome, msedge, or empty for bundled chromium.
  --timeout MS           Navigation/render timeout. Default: 60000.
  --wait-text TEXT       Text that indicates the page is ready. Empty disables it.
  --headful              Show browser window.`);
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return out;
}

function requireLocalPlaywright() {
  const candidates = [
    path.join(ROOT, "node_modules", ".pnpm", "playwright@1.61.0", "node_modules", "playwright"),
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
  const launchOptions = { headless: !args.headful };
  if (args.channel) launchOptions.channel = args.channel;

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
    // Some sports pages keep analytics or streaming requests open.
  }
  if (args.waitText) {
    try {
      await page.getByText(args.waitText).first().waitFor({ timeout: Math.min(args.timeout, 20000) });
    } catch {
      // Continue and save the rendered HTML so the parser/audit can report what happened.
    }
  }
  await page.waitForTimeout(1500);
  const html = await page.content();
  fs.mkdirSync(path.dirname(args.output), { recursive: true });
  fs.writeFileSync(args.output, html, "utf8");
  if (args.screenshot) {
    fs.mkdirSync(path.dirname(args.screenshot), { recursive: true });
    await page.screenshot({ path: args.screenshot, fullPage: true });
  }
  await browser.close();
  console.log(
    JSON.stringify(
      {
        ok: true,
        url: args.url,
        output: args.output,
        chars: html.length,
        screenshot: args.screenshot || "",
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
