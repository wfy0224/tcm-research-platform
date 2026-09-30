/** Minimal CDP client shared by the mock and real-backend browser checks. */
export class Cdp {
  constructor(url) {
    this.ws = new WebSocket(url); this.pending = new Map(); this.nextId = 1;
    this.ready = new Promise((done, fail) => { this.ws.onopen = done; this.ws.onerror = fail; });
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { done, fail, timer } = this.pending.get(message.id);
        clearTimeout(timer); this.pending.delete(message.id);
        message.error ? fail(new Error(message.error.message)) : done(message.result);
      }
    };
    this.ws.onclose = () => {
      for (const { fail, timer } of this.pending.values()) {
        clearTimeout(timer); fail(new Error("CDP connection closed"));
      }
      this.pending.clear();
    };
  }
  async send(method, params = {}) {
    await this.ready; const id = this.nextId++;
    return new Promise((done, fail) => {
      const timer = setTimeout(() => {
        this.pending.delete(id); fail(new Error(`CDP timed out: ${method}`));
      }, 15000);
      this.pending.set(id, { done, fail, timer });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expression) {
    const result = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
  close() { this.ws.close(); }
}

export function sleep(ms) { return new Promise((done) => setTimeout(done, ms)); }
export async function until(check, label, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await check()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}
export async function connect(port) {
  await until(async () => {
    try { return (await fetch(`http://127.0.0.1:${port}/json/version`)).ok; }
    catch { return false; }
  }, "Edge CDP startup");
}
