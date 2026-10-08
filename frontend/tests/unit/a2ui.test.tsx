import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import { JSDOM } from 'jsdom';
import { A2uiSurface, type ReactComponentImplementation } from '@a2ui/react/v0_9';
import { MessageProcessor, STRICT_VALIDATION } from '@a2ui/web_core/v0_9';
import { engineeringCatalog, WorkspaceContext } from '../../components/assistant/catalog';
import { validateSurface, actionSchema, dataSchemas, PROTOCOL } from '../../lib/a2ui-contract';

const fixture = () => JSON.parse(readFileSync(new URL('../fixtures/a2ui-surface.json', import.meta.url), 'utf8'));
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost:3000', pretendToBeVisual: true });
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  self: { value: dom.window, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, HTMLElement: { value: dom.window.HTMLElement, configurable: true },
  IS_REACT_ACT_ENVIRONMENT: { value: true, writable: true },
});

async function renderer(value: unknown) {
  const bundle = validateSurface(value);
  const p = new MessageProcessor<ReactComponentImplementation>([engineeringCatalog], undefined, { version: PROTOCOL, validationConfig: STRICT_VALIDATION });
  p.processMessages(bundle.messages);
  const surface = p.getSurface(bundle.surface_id);
  assert.ok(surface);
  const node = bundle.messages[1].updateComponents.components.at(-1);
  assert.ok(node && 'data' in node);
  const gate = dataSchemas.ApprovalGate.parse(node.data);
  const host = document.createElement('div'); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<WorkspaceContext.Provider value={{ busy: false, gate, selectScope: () => undefined }}><A2uiSurface surface={surface}/></WorkspaceContext.Provider>); });
  const html = host.innerHTML;
  await act(async () => root.unmount()); host.remove();
  p.dispose();
  return html;
}

test('real React renderer accepts server v0.9.1 surface and renders all seven custom components', async () => {
  const html = await renderer(fixture());
  for (const label of ['Security intent', 'Impact assessment', 'Policy change', 'Evidence &amp; readiness', 'Exception review', 'Draft rollout plan', 'Human decision']) assert.ok(html.includes(label), label);
  assert.ok(html.includes('search-customer'));
  assert.ok(html.includes('Simulation estimate'));
  assert.ok(html.includes('Prepare governed handoff'));
});

test('untrusted inventory and findings render as text, never executable markup', async () => {
  const b = fixture();
  b.messages[1].updateComponents.components[1].data.name = '<img src=x onerror=alert(1)>';
  const html = await renderer(b);
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(!html.includes('<img src=x'));
});

for (const mutation of ['component', 'catalog', 'html', 'cycle', 'duplicate', 'expression', 'version', 'metric', 'oversized']) {
  test(`client rejects invalid surface: ${mutation}`, () => {
    const b = fixture(), nodes = b.messages[1].updateComponents.components;
    if (mutation === 'component') nodes[1].component = 'ExecutableHTML';
    if (mutation === 'catalog') b.messages[0].createSurface.catalogId = 'https://untrusted.invalid/catalog';
    if (mutation === 'html') nodes[1].html = '<script>alert(1)</script>';
    if (mutation === 'cycle') nodes[0].children[0] = 'root';
    if (mutation === 'duplicate') nodes[2].id = 'summary';
    if (mutation === 'expression') nodes[1].data.name = { call: 'eval', args: { code: 'alert(1)' } };
    if (mutation === 'version') b.messages[0].version = 'v1.0';
    if (mutation === 'metric') nodes[2].data.counts.COMPLIANT = -1;
    if (mutation === 'oversized') nodes[1].data.name = 'x'.repeat(210000);
    assert.throws(() => validateSurface(b));
  });
}

test('stale evidence and viewer permission flags disable sensitive actions', async () => {
  const b = fixture(), gate = b.messages[1].updateComponents.components.at(-1).data;
  Object.assign(gate, { current: false, stale_reasons: ['A newer inventory snapshot exists'], can_request: false, can_plan: false });
  const html = await renderer(b);
  assert.ok(html.includes('Evidence changed. Reassess before continuing.'));
  assert.match(html, /disabled=""[^>]*>Draft exception for review/);
  assert.match(html, /disabled=""[^>]*>Prepare governed handoff/);
});

test('action bridge rejects approval, deployment and injected command context', () => {
  for (const name of ['approve', 'deploy', 'eval', 'export']) assert.equal(actionSchema.safeParse({ name, context: {} }).success, false);
  assert.equal(actionSchema.safeParse({ name: 'prepare_handoff', context: { approve: true } }).success, false);
  assert.equal(actionSchema.safeParse({ name: 'draft_exception', context: { resource_ids: ['search-2'] } }).success, true);
});

test('A2UI dispatches a custom action through its maintained protocol processor', async () => {
  const b = validateSurface(fixture());
  let received: unknown;
  const p = new MessageProcessor<ReactComponentImplementation>([engineeringCatalog], action => { received = action; }, { version: PROTOCOL });
  p.processMessages(b.messages);
  await p.getSurface(b.surface_id)!.dispatchAction({ event: { name: 'draft_exception', context: { resource_ids: ['search-2'] } } }, 'exceptions');
  assert.equal((received as { name: string }).name, 'draft_exception');
  assert.equal((received as { surfaceId: string }).surfaceId, b.surface_id);
  p.dispose();
});
