/** Local frontend + real API/Worker runtime with automatic development sessions. */
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createServer, request } from "node:http";
import { extname, resolve, sep } from "node:path";
import { createInterface } from "node:readline";
import { workspaceModelConfig } from "./workspace_model_config.mjs";
import { loadWorkspaceModelCatalog } from "./workspace_model_catalog.mjs";

const workspacePort = Number(process.env.TCM_WORKSPACE_PORT || 18067);
const apiPort = Number(process.env.TCM_WORKSPACE_API_PORT || 18068);
const database = process.env.TCM_WORKSPACE_DATABASE || "tcm_vib62_workspace_test";
if (![workspacePort, apiPort].every(port => Number.isInteger(port) && port >= 1024 && port <= 65535) ||
  !/^tcm_vib62_[a-z0-9_]+_test$/.test(database)) throw new Error("Invalid isolated workspace settings");
const origin = `http://127.0.0.1:${workspacePort}`;
const dist = resolve(import.meta.dirname, "..", "dist");
const modelConfig = loadWorkspaceModelCatalog(workspaceModelConfig(process.env));
const api = spawn("docker", ["exec", "-i", ...modelConfig.args, "-e", "PYTHONPATH=/workspace/backend/src",
  "-e", "PYTHONDONTWRITEBYTECODE=1", "tcm-vib54-py", "python",
  "/workspace/backend/scripts/serve_workspace_demo.py", "--database", database,
  "--port", String(apiPort), "--origin", origin], { env: modelConfig.env, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
let server, stopping = false;
const sockets = new Set();
function shutdown() {
  if (stopping) return;
  stopping = true;
  if (!api.stdin.destroyed) api.stdin.end(JSON.stringify({ stop: true }) + "\n");
  server?.close(); for (const socket of sockets) socket.destroy();
}
process.on("SIGINT", shutdown); process.on("SIGTERM", shutdown);
const controls = createInterface({ input: process.stdin });
controls.on("line", (line) => { if (line.trim() === "stop") shutdown(); });
api.stderr.on("data", (value) => process.stderr.write(value));
api.on("error", (error) => { console.error(error.message); shutdown(); process.exitCode = 1; });
api.on("exit", (code) => { if (code) process.exitCode = code; shutdown(); controls.close(); });
const lines = createInterface({ input: api.stdout });
for await (const line of lines) {
  let result; try { result = JSON.parse(line); } catch { continue; }
  if (!result.ready) continue;
  if (result.database !== database || result.model_doubles !== false) throw new Error("Unexpected demo runtime");
  server = createServer(async (req, res) => {
    const path = new URL(req.url, origin).pathname;
    if (path.startsWith("/api/")) {
      const upstream = request(`http://127.0.0.1:${apiPort}${req.url}`, { method: req.method,
        headers: { ...req.headers, host: `127.0.0.1:${apiPort}` } }, (reply) => {
        res.writeHead(reply.statusCode, reply.headers); reply.pipe(res);
      });
      upstream.on("error", () => { if (!res.headersSent) res.writeHead(502, { "Content-Type": "application/json" }); res.end('{"detail":"本地API尚未就绪，请稍后重试。"}'); });
      res.on("close", () => upstream.destroy()); req.pipe(upstream); return;
    }
    try {
      const file = resolve(dist, path === "/" ? "index.html" : `.${decodeURIComponent(path)}`);
      if (file !== dist && !file.startsWith(dist + sep)) { res.writeHead(403); res.end(); return; }
      const bytes = await readFile(file);
      const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };
      res.writeHead(200, { "Content-Type": types[extname(file)] || "application/octet-stream", "Cache-Control": "no-store" }); res.end(bytes);
    } catch { res.writeHead(404); res.end(); }
  });
  server.on("connection", (socket) => { sockets.add(socket); socket.on("close", () => sockets.delete(socket)); });
  server.on("error", (error) => { console.error(`Workspace server: ${error.code || "START_FAILED"}`); process.exitCode = 1; shutdown(); controls.close(); });
  server.listen(workspacePort, "127.0.0.1", () => console.log(JSON.stringify({ url: origin, database: result.database, model_doubles: false, research_model: modelConfig.modelVersion, outbound_mode: result.outbound_mode })));
  break;
}
