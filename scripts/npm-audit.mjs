import { spawnSync } from 'node:child_process';
import { setTimeout } from 'node:timers/promises';
import { pathToFileURL } from 'node:url';

function invoke() {
  return spawnSync('npm', [
    'audit', '--json', '--audit-level=high',
    '--fetch-retries=0', '--fetch-timeout=30000',
  ], {
    encoding: 'utf8', shell: process.platform === 'win32',
    timeout: 120000, maxBuffer: 10 * 1024 * 1024,
  });
}

export async function audit({ run = invoke, sleep = setTimeout, log = console.log } = {}) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const result = run();
    log(`npm audit attempt ${attempt}/3`);
    log(result.stdout || '');
    log(result.stderr || '');
    let report;
    try {
      report = JSON.parse(result.stdout);
    } catch {
      // Missing or malformed reports must never count as a successful audit.
    }
    const counts = report?.metadata?.vulnerabilities;
    if (!result.error && !report?.error && counts &&
        Number.isInteger(counts.high) && counts.high >= 0 &&
        Number.isInteger(counts.critical) && counts.critical >= 0) {
      return counts.high + counts.critical > 0 ? 1 : (result.status === 0 ? 0 : 1);
    }
    if (attempt < 3) await sleep(attempt * 15000);
  }
  log('Audit unavailable after 3 attempts; failing closed. Retry after registry recovery.');
  return 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await audit();
}
