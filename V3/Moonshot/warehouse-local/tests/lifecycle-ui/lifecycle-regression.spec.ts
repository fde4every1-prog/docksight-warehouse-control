import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import { createServer } from 'node:net';
import { expect, test, type BrowserContext, type Route } from '@playwright/test';

const root = process.cwd();
const fixtureOrigin = 'http://127.0.0.1:18081';
const simulatorOrigin = 'http://127.0.0.1:18082';
const coreOrigin = 'http://127.0.0.1:18083';

type ManagedProcess = ChildProcess & { label?: string };
type LifecycleTask = {
  task_id: string;
  assignment_token: string;
  resource_id: string | null;
  resource_kind: 'robot' | 'control_asset';
  stage: string;
  started_at: string;
  due_at: string;
};

const supportedBrowserApis: Array<[string, RegExp]> = [
  ['GET', /^\/api\/fulfillment\/healthz$/],
  ['GET', /^\/api\/fulfillment\/lifecycle$/],
  ['GET', /^\/api\/fulfillment\/lifecycle\/tasks$/],
  ['POST', /^\/api\/fulfillment\/lifecycle\/tasks\/[^/]+\/kill$/],
  ['POST', /^\/api\/fulfillment\/lifecycle\/resources\/[^/]+\/recover$/],
  ['GET', /^\/api\/fulfillment\/state$/],
  ['GET', /^\/api\/fulfillment\/catalog$/],
  ['GET', /^\/api\/fulfillment\/resources\/robots$/],
  ['GET', /^\/api\/personas\/workspace$/],
  ['GET', /^\/api\/personas\/fleet\/issues$/],
  ['GET', /^\/api\/personas\/fleet\/issues\/[^/]+$/],
];

function start(label: string, command: string, args: string[], cwd: string, env: NodeJS.ProcessEnv = {}) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...env },
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  }) as ManagedProcess;
  child.label = label;
  let output = '';
  child.stdout?.on('data', chunk => { output = `${output}${chunk}`.slice(-4000); });
  child.stderr?.on('data', chunk => { output = `${output}${chunk}`.slice(-4000); });
  child.once('exit', code => {
    if (code && code !== 0) child.label = `${label} (exit ${code}): ${output}`;
  });
  return child;
}

async function stop(child: ManagedProcess | undefined) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
  try {
    process.kill(-child.pid, 'SIGTERM');
  } catch {
    return;
  }
  await Promise.race([
    new Promise<void>(resolve => child.once('exit', () => resolve())),
    new Promise<void>(resolve => setTimeout(resolve, 2_000)),
  ]);
  if (child.exitCode === null && child.signalCode === null) {
    try {
      process.kill(-child.pid, 'SIGKILL');
    } catch {
      // The process exited between the check and signal.
    }
    await Promise.race([
      new Promise<void>(resolve => child.once('exit', () => resolve())),
      new Promise<void>(resolve => setTimeout(resolve, 2_000)),
    ]);
  }
}

async function waitFor(url: string, process: ManagedProcess) {
  const deadline = Date.now() + 15_000;
  let lastError = '';
  while (Date.now() < deadline) {
    if (process.exitCode !== null || process.signalCode !== null) {
      throw new Error(`${process.label} stopped before becoming ready`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = String(error);
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`${process.label} did not become ready: ${lastError}`);
}

async function fixtureRequest<T>(pathname: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${fixtureOrigin}${pathname}`, init);
  if (!response.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${pathname}: ${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function startScenarioProcesses() {
  const processes: ManagedProcess[] = [];
  try {
    // Never reuse an already-listening fixture or frontend from another run.
    for (const port of [18081, 18082, 18083]) {
      await new Promise<void>((resolve, reject) => {
        const probe = createServer();
        probe.once('error', reject);
        probe.listen(port, '127.0.0.1', () => probe.close(error => error ? reject(error) : resolve()));
      });
    }
    processes.push(start(
      'isolated lifecycle fixture',
      path.join(root, '.pythonlibs/bin/python3'),
      ['lifecycle_ui_fixture.py'],
      path.join(root, 'artifacts/api-server'),
    ));
    await waitFor(`${fixtureOrigin}/__test__/resource`, processes[0]);

    processes.push(start(
      'Fleet Simulator Vite server',
      'pnpm',
      ['exec', 'vite', '--config', 'vite.config.ts', '--host', '127.0.0.1'],
      path.join(root, 'artifacts/robot-lifecycle'),
      { PORT: '18082', BASE_PATH: '/robot-lifecycle/' },
    ));
    processes.push(start(
      'Core Warehouse Vite server',
      'pnpm',
      ['exec', 'vite', '--config', 'vite.config.ts', '--host', '127.0.0.1'],
      path.join(root, 'artifacts/legacy-review'),
      { PORT: '18083', BASE_PATH: '/' },
    ));
    await Promise.all([
      waitFor(`${simulatorOrigin}/robot-lifecycle/`, processes[1]),
      waitFor(`${coreOrigin}/`, processes[2]),
    ]);
    return processes;
  } catch (error) {
    await Promise.all(processes.map(stop));
    throw error;
  }
}

async function installFailClosedForwarding(context: BrowserContext) {
  const unexpected: string[] = [];
  const forwarded: Array<{ method: string; pathname: string; persona?: string }> = [];
  const frontendOrigins = new Set([simulatorOrigin, coreOrigin]);

  await context.route('**/*', async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    // Fonts and the shared gateway heartbeat are not part of the fixture.
    // Abort these known optional requests too; never contact their real servers.
    if (method === 'GET' && (
      (url.origin === 'https://fonts.googleapis.com' && url.pathname === '/css2') ||
      (frontendOrigins.has(url.origin) && url.pathname === '/api/healthz')
    )) {
      await route.abort('blockedbyclient');
      return;
    }

    if (request.resourceType() === 'serviceworker') {
      unexpected.push(`service worker ${method} ${url.href}`);
      await route.abort('blockedbyclient');
      return;
    }

    if (frontendOrigins.has(url.origin) && url.pathname.startsWith('/api/')) {
      const supported = supportedBrowserApis.some(
        ([allowedMethod, pattern]) => allowedMethod === method && pattern.test(url.pathname),
      );
      if (!supported) {
        unexpected.push(`unsupported API ${method} ${url.pathname}`);
        await route.abort('blockedbyclient');
        return;
      }

      const headers = { ...request.headers() };
      delete headers.host;
      delete headers['content-length'];
      forwarded.push({
        method,
        pathname: url.pathname,
        persona: headers['x-demo-persona'],
      });
      const response = await route.fetch({
        url: `${fixtureOrigin}${url.pathname}${url.search}`,
        maxRedirects: 0,
        method,
        headers,
        postData: request.postDataBuffer() ?? undefined,
      });
      await route.fulfill({ response });
      return;
    }

    if (frontendOrigins.has(url.origin) && !url.pathname.startsWith('/api/')) {
      await route.continue();
      return;
    }

    unexpected.push(`unsupported network ${method} ${url.href}`);
    await route.abort('blockedbyclient');
  });

  return { unexpected, forwarded };
}

async function createAssignedOrder() {
  const requestId = crypto.randomUUID();
  const created = await fixtureRequest<{ control_tower_order_id: string }>('/api/bazaar/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      service: 'Same_Day',
      warehouse_id: 'W1',
      lines: [{ sku: 'A', quantity: 2 }],
      request_id: requestId,
    }),
  });
  await fixtureRequest('/api/fulfillment/assign-tasks', { method: 'POST' });
  const feed = await lifecycleFeed();
  expect(feed.tasks).toHaveLength(1);
  expect(feed.tasks[0]).toMatchObject({ resource_id: 'R1', resource_kind: 'robot', stage: 'pick' });
  return { orderId: created.control_tower_order_id, task: feed.tasks[0] };
}

async function lifecycleFeed() {
  return fixtureRequest<{ tasks: LifecycleTask[] }>('/api/fulfillment/lifecycle/tasks', {
    headers: { 'X-Demo-Persona': 'fleet' },
  });
}

async function recoverDirect(resourceId: string) {
  await fixtureRequest(`/api/fulfillment/lifecycle/resources/${encodeURIComponent(resourceId)}/recover`, {
    method: 'POST',
    headers: { 'X-Demo-Persona': 'fleet' },
  });
}

async function advanceToControlAsset(): Promise<LifecycleTask> {
  await recoverDirect('R1');
  await recoverDirect('R9');
  await fixtureRequest('/api/fulfillment/assign-tasks', { method: 'POST' });

  for (let elapsed = 0; elapsed <= 180; elapsed += 45) {
    const feed = await lifecycleFeed();
    const controlAsset = feed.tasks.find(task => task.resource_kind === 'control_asset');
    if (controlAsset) return controlAsset;
    await fixtureRequest('/__test__/advance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds: 45 }),
    });
    await fixtureRequest('/api/fulfillment/assign-tasks', { method: 'POST' });
  }
  throw new Error('Order did not reach a control-asset stage after controlled clock advances');
}

async function killVisibleFunction(
  page: import('@playwright/test').Page,
  resourceId: string,
  cancelFirst = false,
  onCancelled?: () => Promise<void>,
) {
  await page.getByRole('button').filter({ hasText: resourceId }).click();
  await expect(page.getByRole('dialog').getByText(resourceId, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Kill function' }).click();
  await expect(page.getByRole('alertdialog')).toContainText('Kill this function?');
  if (cancelFirst) {
    await page.getByRole('button', { name: 'Keep running' }).click();
    await expect(page.getByRole('alertdialog')).toBeHidden();
    await expect(page.getByRole('dialog').getByText(resourceId, { exact: true })).toBeVisible();
    await onCancelled?.();
    await page.getByRole('button', { name: 'Kill function' }).click();
  }
  await page.getByRole('button', { name: 'Confirm kill' }).click();
}

test.describe('isolated lifecycle browser regression', () => {
  let processes: ManagedProcess[] = [];
  let context: BrowserContext | undefined;

  test.beforeEach(async ({ context: projectContext }) => {
    processes = await startScenarioProcesses();
    context = projectContext;
    await context.addInitScript(() => localStorage.setItem('demo-persona', 'fleet'));
  });

  test.afterEach(async () => {
    // Close pages while context-wide interception is still installed.
    await context?.close();
    context = undefined;
    await Promise.all(processes.map(stop));
    processes = [];
  });

  test('kill, replace, wait, and explicitly recover a control asset', async () => {
    const forwarding = await installFailClosedForwarding(context!);
    const { task: firstAssignment } = await createAssignedOrder();
    const page = await context!.newPage();

    await page.goto(`${simulatorOrigin}/robot-lifecycle/`);
    await expect(page.getByRole('heading', { name: 'Ongoing functions' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Simulation role' })).toContainText('Fleet Ops');
    await expect(page.getByRole('button').filter({ hasText: 'R1' })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('combobox', { name: 'Simulation role' })).toContainText('Fleet Ops');

    await fixtureRequest('/__test__/advance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds: 15 }),
    });
    const r1Card = page.getByRole('button').filter({ hasText: 'R1' });
    await expect(r1Card).toContainText(/(?:2[7-9]|30)s/);
    await killVisibleFunction(page, 'R1', true, async () => {
      const afterCancel = (await lifecycleFeed()).tasks[0];
      expect(afterCancel).toMatchObject({
        resource_id: 'R1',
        assignment_token: firstAssignment.assignment_token,
      });
    });
    await expect(page.getByText('Automatic replacement complete')).toBeVisible();
    const r9Card = page.getByRole('button').filter({ hasText: 'R9' });
    await expect(r9Card).toBeVisible();
    await expect(r9Card).toContainText(/4[2-5]s/);
    const replacement = (await lifecycleFeed()).tasks[0];
    expect(replacement).toMatchObject({
      task_id: firstAssignment.task_id,
      resource_id: 'R9',
      resource_kind: 'robot',
    });
    expect(replacement.assignment_token).not.toBe(firstAssignment.assignment_token);
    expect(Date.parse(replacement.due_at) - Date.parse(replacement.started_at)).toBe(45_000);

    await killVisibleFunction(page, 'R9');
    await expect(page.getByText('Waiting for an eligible replacement', { exact: true })).toBeVisible();

    const controlAsset = await advanceToControlAsset();
    expect(controlAsset.resource_id).toBe('W1-PACK');
    await expect(page.getByRole('button').filter({ hasText: 'W1-PACK' })).toBeVisible();
    const sourceBefore = await fixtureRequest('/api/fulfillment/resources/control_assets');
    await killVisibleFunction(page, 'W1-PACK');
    await expect(page.getByText('Automatic replacement complete')).toBeVisible();

    await page.goto(`${coreOrigin}/workspace/fleet`);
    await expect(page.getByRole('heading', { name: 'Fleet Operator Workspace' })).toBeVisible();
    await expect(page.locator('header select')).toHaveValue('fleet');
    await page.reload();
    await expect(page.locator('header select')).toHaveValue('fleet');

    const issueCard = page.getByRole('button').filter({ hasText: 'Control asset readiness: W1-PACK' });
    await expect(issueCard).toBeVisible();
    await issueCard.click();
    await expect(page.getByRole('dialog')).toContainText('Simulator failure block:');
    await page.getByRole('button', { name: 'Mark resource recovered' }).click();
    await expect(page.getByRole('alertdialog')).toContainText('Mark W1-PACK recovered?');
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('alertdialog')).toBeHidden();
    await expect(page.getByRole('dialog')).toContainText('Simulator failure block:');

    await page.getByRole('button', { name: 'Mark resource recovered' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Mark resource recovered' }).click();
    await expect(page.getByText('Simulator failure block removed. Source readiness values were not changed.')).toBeVisible();
    await expect(page.getByRole('dialog')).not.toContainText('Simulator failure block:');

    const sourceAfter = await fixtureRequest('/api/fulfillment/resources/control_assets');
    expect(sourceAfter).toEqual(sourceBefore);
    await page.getByRole('button', { name: 'Close' }).click();
    await page.reload();
    await expect(page.getByRole('button').filter({ hasText: 'Control asset readiness: W1-PACK' })).toHaveCount(0);
    const persistedIssues = await fixtureRequest<{ items: Array<{ entity_id: string }> }>(
      '/api/personas/fleet/issues',
      { headers: { 'X-Demo-Persona': 'fleet' } },
    );
    expect(persistedIssues.items.some(issue => issue.entity_id === 'W1-PACK')).toBe(false);

    // The fixture's process-wide audit guard rejects operational file access
    // before it occurs, including import-time SQLite creation and migrations.
    expect(await fixtureRequest('/__test__/resource')).toMatchObject({
      storage_guard_enabled: true,
      storage_violations: [],
    });
    expect(forwarding.unexpected).toEqual([]);
    const sensitiveRequests = forwarding.forwarded.filter(request =>
      request.pathname.includes('/lifecycle/tasks') ||
      request.pathname.includes('/lifecycle/resources/') ||
      request.pathname.includes('/personas/fleet/issues'),
    );
    expect(sensitiveRequests.length).toBeGreaterThan(0);
    expect(sensitiveRequests.every(request => request.persona === 'fleet')).toBe(true);
  });
});