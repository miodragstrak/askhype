// Run with Node 22 and a local Chromium installation. Uses only synthetic localhost HTTP.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, extname, join } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { once } from 'node:events';

const durable = process.argv.includes('--durable');
const serverOrigin = 'http://localhost:4178';
const authKey = 'sb-localhost-auth-token';
const accounts = {
  a: '00000000-0000-4000-8000-000000000001',
  b: '00000000-0000-4000-8000-000000000002',
};
const directory = await mkdtemp(join(tmpdir(), 'askhype-history-'));
const dist = join(directory, 'dist');
const build = spawnSync('node', ['node_modules/vite/bin/vite.js', 'build', '--outDir', dist], {
  env: { ...process.env, VITE_SUPABASE_URL: serverOrigin, VITE_API_BASE_URL: serverOrigin,
    VITE_SUPABASE_PUBLISHABLE_KEY: 'synthetic-test-key', VITE_SERVER_CHAT_TURNS_ENABLED: String(durable) }, stdio: 'inherit',
});
if (build.status !== 0) {
  await rm(directory, { recursive: true, force: true });
  process.exit(1);
}

const rows = { a: new Map(), b: new Map() };
const messages = { a: new Map(), b: new Map() };
const idB = '00000000-0000-4000-8000-000000000010';
const timestamp = '2026-11-26T00:00:00.000Z';
rows.b.set(idB, { id: idB, title: 'Account B fixture', created_at: timestamp, updated_at: timestamp });
const researchId = '00000000-0000-4000-8000-000000000011';
const report = { research_id: researchId, status: 'completed', title: 'Synthetic research',
  summary: 'Recovered research example', sections: [], sources: [], limitations: [], generated_at: timestamp,
  provider: 'gemini', model: 'synthetic' };
messages.b.set(researchId, { id: researchId, conversation_id: idB, role: 'assistant', created_at: timestamp,
  response: { conversation_id: 'research-fixture', provider: 'gemini', answer_type: 'deep_research',
    summary: report.summary, research: report, recommendations: [], follow_up_actions: [], sources: [],
    generated_at: timestamp } });

const gate = () => {
  let release;
  let arrive;
  const wait = new Promise((resolve) => { release = resolve; });
  let arrived = false;
  arrive = () => { arrived = true; };
  const entered = () => waitFor(() => arrived, "deferred request reached mock server");
  return { release, entered, async pause() { arrive(); await wait; } };
};
let blockedHistory;
let blockedChat;
let failRole;
let chatCalls = 0;
let legacyWorker = true;
let disconnectAfterSettlement = false;
const turns = new Map();


const mime = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json' };
const server = createServer(async (req, res) => {
  const url = new URL(req.url, serverOrigin);
  const path = url.pathname;
  const account = req.headers.authorization?.match(/^Bearer synthetic-([ab])$/)?.[1];
  const json = (value, status = 200) => {
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(value));
  };
  const body = async () => {
    let data = '';
    for await (const chunk of req) data += chunk;
    return JSON.parse(data);
  };
  if (path === '/api/usage') return json({ identity: account ? 'authenticated' : 'guest', plan: 'free',
    used: 0, limit: 10, remaining: 10, reset_at: null });
  if (path === '/api/research') return json([]);
  if (path === '/auth/v1/user' || path.startsWith('/storage/v1/')) return json({ synthetic: true });
  if (path.startsWith('/api/chat/turns/')) {
    const id = path.split('/').at(-1);
    const existing = turns.get(id);
    if (!account || (existing && existing.owner !== account)) return json(null, 404);
    if (req.method === 'GET') return existing ? json(existing.view, existing.view.status === 'processing' ? 202 : 200) : json(null, 404);
    const request = await body();
    const conversation = url.searchParams.get('conversation_id');
    if (existing) {
      if (existing.conversation !== conversation || JSON.stringify(existing.request) !== JSON.stringify(request)) return json(null, 409);
      return json(existing.view, existing.view.status === 'processing' ? 202 : 200);
    }
    const created = new Date().toISOString();
    const view = { id, conversation_id: conversation, assistant_message_id: crypto.randomUUID(),
      status: 'processing', created_at: created, completed_at: null, response: null };
    turns.set(id, { owner: account, conversation, request, view });
    if (!rows[account].has(conversation)) rows[account].set(conversation, {
      id: conversation, title: request.message, created_at: created, updated_at: created,
    });
    messages[account].set(id, { id, conversation_id: conversation, role: 'user', text: request.message,
      metadata: { ordinary_turn: true }, created_at: created });
    chatCalls += 1;
    if (blockedChat) {
      const pending = blockedChat;
      blockedChat = undefined;
      await pending.pause();
    }
    if (!rows[account].has(conversation)) return json(null, 404);
    const completed = new Date().toISOString();
    Object.assign(view, { status: 'completed', completed_at: completed, response: {
      conversation_id: 'provider-conversation', provider: 'mock', answer_type: 'chat',
      summary: `Reply to ${request.message}`, recommendations: [], sources: [], follow_up_actions: [], generated_at: completed,
    } });
    messages[account].set(view.assistant_message_id, { id: view.assistant_message_id, conversation_id: conversation,
      role: 'assistant', metadata: { ordinary_turn_id: id }, response: view.response, created_at: completed });
    rows[account].get(conversation).updated_at = completed;
    if (disconnectAfterSettlement) {
      disconnectAfterSettlement = false;
      return res.destroy();
    }
    return json(view);
  }
  if (path === '/api/chat') {
    chatCalls += 1;
    const request = await body();
    if (blockedChat) {
      const pending = blockedChat;
      blockedChat = undefined;
      await pending.pause();
    }
    return json({ conversation_id: 'provider-conversation', provider: 'mock', answer_type: 'chat',
      summary: `Reply to ${request.message}`, recommendations: [], follow_up_actions: [], sources: [],
      generated_at: timestamp });
  }
  if (path === '/rest/v1/profiles') return json({ user_id: accounts[account], plan: 'free' });
  if (path.startsWith('/rest/v1/')) {
    if (!account) return json({ code: '42501' }, 403);
    const conversations = path.endsWith('/conversations');
    const table = conversations ? rows[account] : messages[account];
    const id = url.searchParams.get('id')?.replace(/^eq\./, '');
    if (req.method === 'GET') {
      if (conversations && account === 'a' && blockedHistory) {
        const pending = blockedHistory;
        blockedHistory = undefined;
        await pending.pause();
      }
      const conversationFilter = url.searchParams.get('conversation_id');
      const conversationsToRead = conversationFilter?.startsWith('eq.') ? [conversationFilter.slice(3)]
        : conversationFilter?.startsWith('in.(') ? conversationFilter.slice(4, -1).split(',') : null;
      const filter = url.searchParams.get('or')?.match(/(?:updated_at|created_at)\.lt\.([^,]+),and\([^,]+,id\.lt\.([^)]*)/);
      const column = conversations ? 'updated_at' : 'created_at';
      const descending = conversations || url.searchParams.get('order')?.startsWith('created_at.desc');
      const listed = [...table.values()].filter((item) => (!conversationsToRead || conversationsToRead.includes(item.conversation_id)) &&
        (!filter || item[column] < filter[1] || (item[column] === filter[1] && item.id < filter[2])))
        .sort((left, right) => (descending ? -1 : 1) *
          (left[column].localeCompare(right[column]) || left.id.localeCompare(right.id)));
      return json(listed.slice(0, Number(url.searchParams.get('limit') ?? listed.length)));
    }
    if (req.method === 'POST') {
      const value = await body();
      if (value.role && failRole === value.role) return json({ code: 'XX000' }, 500);
      if (!conversations && !rows[account].has(value.conversation_id)) return json({ code: '23503' }, 409);
      if (!table.has(value.id)) table.set(value.id, value);
      return json(null, 201);
    }
    if (req.method === 'PATCH') {
      const value = await body();
      if (!table.has(id)) return json(null);
      Object.assign(table.get(id), value);
      return json([{ id }]);
    }
    if (req.method === 'DELETE') {
      table.delete(id);
      for (const [messageId, message] of messages[account]) {
        if (message.conversation_id === id) messages[account].delete(messageId);
      }
      return json(null);
    }
  }
  if (path === '/sw.js' && legacyWorker) {
    res.writeHead(200, { 'Content-Type': mime['.js'], 'Cache-Control': 'no-store' });
    return res.end("self.addEventListener('install', () => self.skipWaiting()); self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));");
  }
  try {
    const filename = resolve(dist, path === '/' ? 'index.html' : `.${path}`);
    if (!filename.startsWith(dist + '/')) return res.writeHead(404).end();
    res.writeHead(200, { 'Content-Type': mime[extname(filename)] ?? 'application/octet-stream' });
    res.end(await readFile(filename));
  } catch {
    res.end();
  }
});
const waitFor = async (condition, label) => {
  for (let i = 0; i < 150; i++) {
    const result = await condition();
    if (result) return result;
    await sleep(100);
  }
  throw new Error(`Timed out: ${label}`);
};
let chrome;
const sockets = [];
try {
  server.listen(4178, '127.0.0.1');
  await once(server, 'listening');
  chrome = spawn(process.env.CHROME_BIN ?? 'google-chrome', [
    '--headless', '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
    '--disable-sync', '--no-proxy-server', '--no-sandbox', '--remote-debugging-port=0',
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost', `--user-data-dir=${join(directory, 'chrome')}`,
  ], { stdio: 'ignore' });
  const port = await waitFor(async () => {
    try { return (await readFile(join(directory, 'chrome', 'DevToolsActivePort'), 'utf8')).split('\n')[0]; }
    catch { return undefined; }
  }, 'Chromium debugging port');
  const endpoint = `http://127.0.0.1:${port}`;
  const openTab = async () => {
    const tab = await (await fetch(`${endpoint}/json/new?about:blank`, { method: 'PUT' })).json();
    const ws = new WebSocket(tab.webSocketDebuggerUrl);
    sockets.push(ws);
    await once(ws, 'open');
    let id = 0;
    const cdp = (method, params = {}) => new Promise((resolve, reject) => {
      const currentId = ++id;
      const listener = ({ data }) => {
        const result = JSON.parse(data);
        if (result.id !== currentId) return;
        ws.removeEventListener('message', listener);
        if (result.error) reject(new Error(result.error.message));
        else resolve(result.result);
      };
      ws.addEventListener('message', listener);
      ws.send(JSON.stringify({ id: currentId, method, params }));
    });
    const evaluate = async (expression) => {
      const result = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description);
      return result.result.value;
    };
    const check = (text, present = true) => waitFor(async () => (await evaluate(
      `Boolean(document.body?.innerText.includes(${JSON.stringify(text)}))`)) === present, text);
    const click = (query) => evaluate(`document.querySelector(${JSON.stringify(query)}).click()`);
    const submit = async (text) => {
      await waitFor(() => evaluate("Boolean(document.querySelector('textarea:enabled'))"), 'composer enabled');
      await evaluate(`{
        const field = document.querySelector('textarea');
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(field, ${JSON.stringify(text)});
        field.dispatchEvent(new Event('input', { bubbles: true }));
      }`);
      await click('button[aria-label="Pošalji poruku"]');
    };
    return { cdp, evaluate, check, click, submit };
  };
  const first = await openTab();
  const accountSession = (account) => account ? { access_token: `synthetic-${account}`, refresh_token: 'synthetic',
    expires_at: Math.floor(Date.now() / 1000) + 3600, token_type: 'bearer',
    user: { id: accounts[account], email: `synthetic-${account}@example.test`, user_metadata: {},
      app_metadata: {}, aud: 'authenticated' } } : null;
  const transition = (tab, account) => tab.evaluate(`{
    const session = ${JSON.stringify(accountSession(account))};
    if (session) localStorage.setItem(${JSON.stringify(authKey)}, JSON.stringify(session));
    else localStorage.removeItem(${JSON.stringify(authKey)});
    const channel = new BroadcastChannel(${JSON.stringify(authKey)});
    channel.postMessage({ event: session ? 'SIGNED_IN' : 'SIGNED_OUT', session });
    channel.close();
  }`);
  await first.cdp('Page.navigate', { url: serverOrigin });
  await first.check('Tvoji razgovori');
  await waitFor(() => first.evaluate('Boolean(navigator.serviceWorker.controller)'), 'legacy worker active');
  await first.evaluate(`caches.open('offlineCache').then(cache => cache.put('/rest/v1/conversations',
    new Response('synthetic obsolete private data')))`);
  await first.evaluate("caches.open('unrelated-test-cache').then(() => true)");
  legacyWorker = false;
  await first.evaluate('navigator.serviceWorker.getRegistration().then(registration => registration.update()).then(() => true)');
  await waitFor(() => first.evaluate("caches.keys().then(keys => !keys.includes('offlineCache') && keys.some(key => key.includes('precache')))"),
    'new worker cleans legacy cache and installs static precache');
  assert.ok(await first.evaluate("caches.keys().then(keys => keys.includes('unrelated-test-cache'))"));
  await first.cdp('Page.reload');

  if (durable) {
    await transition(first, 'a');
    await first.submit('Owned normal');
    await first.check('Reply to Owned normal');
    assert.equal(messages.a.size, 2);
    await first.cdp('Page.reload');
    await first.check('Reply to Owned normal');
    await first.click('button[aria-label="Novi razgovor"]');
    disconnectAfterSettlement = true;
    await first.submit('Lost HTTP acknowledgement');
    await first.check('Reply to Lost HTTP acknowledgement');
    assert.equal(chatCalls, 2);

    blockedChat = gate();
    const pending = blockedChat;
    await first.click('button[aria-label="Novi razgovor"]');
    await first.submit('Reload during processing');
    await pending.entered();
    const accepted = [...turns.values()].find((turn) => turn.request.message === 'Reload during processing');
    const second = await openTab();
    await second.cdp('Page.navigate', { url: serverOrigin });
    await second.check('Reload during processing');
    const replayStatus = await second.evaluate(`fetch('/api/chat/turns/${accepted.view.id}?conversation_id=${accepted.conversation}', {
      method:'POST', headers:{ Authorization:'Bearer synthetic-a','Content-Type':'application/json' },
      body:JSON.stringify(${JSON.stringify(accepted.request)})
    }).then(r => r.status)`);
    assert.equal(replayStatus, 202);
    await first.cdp('Page.reload');
    await first.check('Reload during processing');
    pending.release();
    await first.check('Reply to Reload during processing');
    await second.check('Reply to Reload during processing');
    assert.equal(chatCalls, 3);

    blockedChat = gate();
    const accountSwitch = blockedChat;
    await first.click('button[aria-label="Novi razgovor"]');
    await first.submit('Private pending reply');
    await accountSwitch.entered();
    await transition(first, null);
    await first.check('Private pending reply', false);
    await transition(first, 'b');
    await first.check('Recovered research example');
    accountSwitch.release();
    await first.check('Reply to Private pending reply', false);
    assert.equal(chatCalls, 4);

    // Seed one older thread and one long thread. Request the real UI cursor path.
    for (let index = 0; index < 31; index++) {
      const id = crypto.randomUUID();
      rows.b.set(id, { id, title: 'Archived thread ' + index, created_at: '2000-01-01T00:00:00Z',
        updated_at: '2000-01-01T00:00:00Z' });
      const messageId = crypto.randomUUID();
      messages.b.set(messageId, { id: messageId, conversation_id: idB, role: 'user', text: 'Archived message ' + index,
        created_at: '2000-01-01T00:00:00Z' });
    }
    await first.cdp('Page.reload');
    await first.check('Recovered research example');
    await first.evaluate("[...document.querySelectorAll('button')].find(b => b.textContent === 'Prikaži starije razgovore').click()");
    await waitFor(() => first.evaluate("[...document.querySelectorAll('aside button')].filter(b => b.textContent.startsWith('Archived thread')).length === 31"),
      'stable thread pagination');
    await first.evaluate("[...document.querySelectorAll('button')].find(b => b.textContent === 'Prikaži starije poruke').click()");
    await waitFor(() => first.evaluate("document.querySelectorAll('main p').length > 31"), 'older message page rendered');
    await first.check('Recovered research example');
  } else {
    blockedHistory = gate();
    const history = blockedHistory;
    await transition(first, 'a');
    await history.entered();
    await transition(first, null);
    await transition(first, 'b');
    await first.check('Recovered research example');
    history.release();
    await first.check('Account B fixture');
    await transition(first, 'a');
    await first.check('Account B fixture', false);
    await first.check('Recovered research example', false);

    await first.submit('Normal lifecycle');
    await first.check('Reply to Normal lifecycle');
    await waitFor(() => messages.a.size === 2, 'ordinary turn saved');
    await first.cdp('Page.reload');
    await first.check('Reply to Normal lifecycle');
    await first.click('button[aria-label="Novi razgovor"]');
    for (const role of ['user', 'assistant']) {
      failRole = role;
      await first.submit(`Fail ${role}`);
      await first.check(`Reply to Fail ${role}`);
      await first.check('Nesačuvano');
      await first.check('Ponovi čuvanje');
      const failed = [...rows.a.values()].find((row) => row.title === `Fail ${role}`);
      const saved = () => [...messages.a.values()].filter((msg) => msg.conversation_id === failed.id);
      assert.deepEqual(saved().map((msg) => msg.role), role === 'user' ? [] : ['user']);
      const count = chatCalls;
      failRole = undefined;
      await first.evaluate("[...document.querySelectorAll('button')].find(button => button.textContent === 'Ponovi čuvanje').click()");
      await first.check('Ponovi čuvanje', false);
      assert.equal(chatCalls, count);
      assert.deepEqual(saved().map((msg) => msg.role), ['user', 'assistant']);
      await first.click('button[aria-label="Novi razgovor"]');
    }

    // Navigation selects loaded threads synchronously. A pending reply must stay in its originating thread.
    blockedChat = gate();
    const navigation = blockedChat;
    await first.submit('Pending navigation');
    await navigation.entered();
    await first.evaluate("[...document.querySelectorAll('aside button')].find(button => button.textContent.includes('Normal lifecycle')).click()");
    await first.check('Reply to Normal lifecycle');
    navigation.release();
    await waitFor(() => [...messages.a.values()].some((msg) => msg.response?.summary === 'Reply to Pending navigation'),
      'background reply saved to originating thread');
    await first.check('Reply to Pending navigation', false);

    blockedChat = gate();
    const pending = blockedChat;
    await first.click('button[aria-label="Novi razgovor"]');
    await first.submit('Pending account A');
    await pending.entered();
    await transition(first, null);
    await first.check('Pending account A', false);
    await transition(first, 'b');
    await first.check('Recovered research example');
    pending.release();
    await first.check('Reply to Pending account A', false);
    assert.equal([...messages.b.values()].some((msg) => msg.response?.summary.includes('Pending account A')), false);

    await transition(first, 'a');
    await first.check('Normal lifecycle');
    await first.click('button[aria-label="Novi razgovor"]');
    blockedChat = gate();
    const deleted = blockedChat;
    await first.submit('Delete while pending');
    await deleted.entered();
    await first.click('button[aria-label="Obriši razgovor: Delete while pending"]');
    await waitFor(() => ![...rows.a.values()].some((row) => row.title === 'Delete while pending'), 'pending conversation deleted');
    deleted.release();
    await waitFor(() => first.evaluate("Boolean(document.querySelector('textarea:enabled'))"), 'late reply ignored');
    await first.check('Delete while pending', false);
    assert.ok(![...messages.a.values()].some((msg) => msg.response?.summary === 'Reply to Delete while pending'));

    const second = await openTab();
    await second.cdp('Page.navigate', { url: serverOrigin });
    await second.check('Normal lifecycle');
    await first.click('button[aria-label="Novi razgovor"]');
    await second.click('button[aria-label="Novi razgovor"]');
    await Promise.all([first.submit('First tab'), second.submit('Second tab')]);
    await first.check('Reply to First tab');
    await second.check('Reply to Second tab');
    await waitFor(() => [...messages.a.values()].filter((msg) => /Reply to (First|Second) tab/.test(msg.response?.summary)).length === 2, 'both tab replies saved');
    await first.cdp('Page.reload');
    await first.check('Second tab');
    const ordered = await first.evaluate("[...document.querySelectorAll('aside button[aria-current], aside button')].map(b => b.textContent)");
    const tabTitles = ordered.filter((title) => /^(First|Second) tab$/.test(title));
    const expectedTitles = [...rows.a.values()].filter((row) => /^(First|Second) tab$/.test(row.title))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.id.localeCompare(a.id)).map((row) => row.title);
    assert.deepEqual(tabTitles, expectedTitles);
    assert.equal(await first.evaluate("[...document.querySelectorAll('aside button')].filter(b => b.textContent === 'First tab').length"), 1);
    await second.click('button[aria-label="Obriši razgovor: Second tab"]');
    await waitFor(() => ![...rows.a.values()].some((row) => row.title === 'Second tab'), 'other tab deleted');
    await first.cdp('Page.reload');
    await first.check('First tab');
    await first.check('Second tab', false);

  }

  await first.evaluate("Promise.all(['/rest/v1/conversations','/rest/v1/profiles','/api/usage','/api/research','/auth/v1/user','/storage/v1/object/private/mock'].map(path => fetch(path, {headers: {Authorization:'Bearer synthetic-a'}})))");
  const cached = await first.evaluate('caches.keys().then(keys => Promise.all(keys.map(k => caches.open(k).then(c => c.keys())))).then(groups => groups.flat().map(r => new URL(r.url).pathname))');
  assert.ok(cached.some((path) => path.startsWith('/assets/')));
  assert.ok(!cached.some((path) => /^\/(?:api|auth\/v1|rest\/v1|storage\/v1)\//.test(path)));
  await first.cdp('Network.enable');
  await first.cdp('Network.emulateNetworkConditions', {
    offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0,
  });
  await first.cdp('Page.reload');
  await first.check('Istorija razgovora trenutno nije dostupna');
  await first.check(durable ? 'Reply to Private pending reply' : 'Reply to First tab', false);
  console.log(`PASS Chromium (${durable ? 'server-owned turns' : 'legacy history'}): lifecycle, account changes, tabs, research reopen and PWA upgrade`);
} finally {
  for (const socket of sockets) socket.close();
  if (chrome && chrome.exitCode === null) {
    chrome.kill();
    await once(chrome, 'exit');
  }
  server.close();
  await rm(directory, { recursive: true, force: true, maxRetries: 4 });
}
