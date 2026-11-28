import assert from 'node:assert/strict';

async function replyBody(response, id) {
  if (!response.headers.get('content-type')?.includes('text/event-stream')) return response.json();
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const {value, done} = await reader.read();
      buffer = (buffer + decoder.decode(value, {stream: !done})).replaceAll('\r\n', '\n');
      let end;
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const event = buffer.slice(0, end); buffer = buffer.slice(end + 2);
        const data = event.split('\n').filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart()).join('\n');
        if (data) { const reply = JSON.parse(data); if (reply.id === id) return reply; }
      }
      assert(buffer.length <= 64 * 1024 * 1024, 'MCP event exceeds the response limit');
      if (done) break;
    }
    // Some HTTP implementations omit the last empty SSE separator.
    for (const line of buffer.split('\n')) if (line.startsWith('data:') && line.slice(5).trim()) {
      const reply = JSON.parse(line.slice(5)); if (reply.id === id) return reply;
    }
    throw Error(`MCP stream closed without response ${id}`);
  } finally { await reader.cancel(); }
}

/** Streamable HTTP client shared by deployed smoke and acceptance checks. */
export class Mcp {
  constructor(base, token, project = 'default') {
    this.url = new URL('mcp', base.replace(/\/?$/, '/')).href;
    this.token = token; this.project = project;
    this.session = null; this.protocol = null; this.counter = 0;
  }

  async post(message) {
    const headers = {'Content-Type': 'application/json', Accept: 'application/json, text/event-stream',
      Authorization: `Bearer ${this.token}`};
    if (this.session) headers['Mcp-Session-Id'] = this.session;
    if (this.protocol) headers['MCP-Protocol-Version'] = this.protocol;
    const response = await fetch(this.url, {method: 'POST', headers, body: JSON.stringify(message), redirect: 'error',
      signal: AbortSignal.timeout(120000)});
    this.session = response.headers.get('mcp-session-id') || this.session;
    return response;
  }

  async request(method, params = {}) {
    const id = ++this.counter;
    const response = await this.post({jsonrpc: '2.0', id, method, params});
    assert.equal(response.status, 200, `${method}: HTTP ${response.status}`);
    const reply = await replyBody(response, id);
    assert.equal(reply.id, id, `${method}: mismatched JSON-RPC response`);
    assert(!reply.error, `${method}: ${JSON.stringify(reply.error)}`);
    return reply.result;
  }

  async notify(method) {
    const response = await this.post({jsonrpc: '2.0', method});
    assert([200, 202].includes(response.status), `${method}: HTTP ${response.status}`);
    await response.body?.cancel();
  }

  async initialize() {
    const info = await this.request('initialize', {protocolVersion: '2025-06-18', capabilities: {},
      clientInfo: {name: 'charts-native-acceptance', version: '1'}});
    this.protocol = info.protocolVersion;
    await this.notify('notifications/initialized');
    return info;
  }

  async tool(name, args = {}) {
    const result = await this.request('tools/call', {name, arguments: {projectRoot: this.project, ...args}});
    let value = result.structuredContent ?? JSON.parse(result.content.find(item => item.type === 'text').text);
    assert(!result.isError, `${name}: ${JSON.stringify(value)}`);
    const envelope = value?.transport;
    if (envelope) {
      assert.equal(envelope.encoding, 'base64-json-v1', `${name}: unsupported transport encoding`);
      assert(Number.isInteger(envelope.chunks) && envelope.chunks > 0 && envelope.chunks <= 4096,
        `${name}: invalid transport page count`);
      const pages = [];
      for (let index = 0; index < envelope.chunks; index++) {
        const chunk = await this.tool('runtime_result_chunk', {projectRoot: args.projectRoot ?? this.project,
          requestId: envelope.requestId, index});
        pages.push(chunk.data);
      }
      const raw = Buffer.from(pages.join(''), 'base64');
      assert.equal(raw.length, envelope.bytes, `${name}: chunked response size mismatch`);
      value = JSON.parse(raw);
    }
    return value;
  }
}
