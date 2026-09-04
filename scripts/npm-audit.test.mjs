import assert from 'node:assert/strict';
import test from 'node:test';
import { audit } from './npm-audit.mjs';

const report = (high = 0, critical = 0, status = 0) => ({
  status, stdout: JSON.stringify({ metadata: { vulnerabilities: { high, critical } } }),
});

async function check(results, expected, attempts) {
  let calls = 0;
  const delays = [];
  const code = await audit({
    run: () => results[Math.min(calls++, results.length - 1)],
    sleep: async (ms) => { delays.push(ms); }, log: () => {},
  });
  assert.equal(code, expected);
  assert.equal(calls, attempts);
  assert.equal(delays.length, attempts - 1);
}

test('valid clean report passes immediately', () => check([report()], 0, 1));
test('high vulnerability fails without retry', () => check([report(1, 0, 1)], 1, 1));
test('critical vulnerability fails even with zero process status', () => check([report(0, 1)], 1, 1));
test('HTTP error retries then recovers', () => check([
  { status: 1, stdout: '{"error":{"code":"E503"}}' }, report(),
], 0, 2));
test('continuous outage fails after three attempts', () => check([
  { status: 1, stdout: '{"error":{"code":"E500"}}' },
], 1, 3));
test('invalid JSON never passes', () => check([{ status: 0, stdout: 'invalid' }], 1, 3));
test('empty report never passes', () => check([{ status: 0, stdout: '{}' }], 1, 3));
test('timeout never passes', () => check([{ status: null, error: new Error('timeout') }], 1, 3));
test('nonzero status with a report still fails', () => check([report(0, 0, 1)], 1, 1));
