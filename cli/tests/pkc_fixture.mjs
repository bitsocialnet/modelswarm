#!/usr/bin/env node
// A real PKC minter and private Kubo repo, owned entirely by one test process.
import { spawn, execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
import { once } from "node:events";
import { createWriteStream } from "node:fs";
import { chmod, lstat, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import http from "node:http";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const root = fileURLToPath(new URL("../../", import.meta.url));
const require = createRequire(new URL("../src/modelswarm/bridge/package.json", import.meta.url));
const token = randomBytes(24).toString("base64url");
const originalStdout = process.stdout.write.bind(process.stdout);
const originalStderr = process.stderr.write.bind(process.stderr);
const redact = (value) => String(value).replaceAll(token, "[redacted]");
// The first stdout line is a machine-readable capability. Library diagnostics
// belong on stderr and must never repeat the RPC capability token.
process.stderr.write = (chunk, ...args) => originalStderr(redact(chunk), ...args);
process.stdout.write = (chunk, ...args) => process.stderr.write(chunk, ...args);
process.env.DEBUG = "";
process.env.NODE_DISABLE_COMPILE_CACHE = "1";

let kubo, rpc, httpServer, dataDir;
let stopping = false;
let stopPromise;
const logs = [];

function report(event, fields = {}) {
    process.stderr.write(JSON.stringify({ event, ...fields }) + "\n");
}

async function bounded(promise, milliseconds, message) {
    let timer;
    try {
        return await Promise.race([
            promise,
            new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(message)), milliseconds); }),
        ]);
    } finally {
        clearTimeout(timer);
    }
}

async function stop(exitCode) {
    if (stopPromise) return stopPromise;
    stopping = true;
    stopPromise = (async () => {
        let cleanupFailed = false;
        if (rpc) {
            try {
                await bounded(rpc.destroy(), 8000, "RPC shutdown timed out");
            } catch (error) {
                report("cleanup_error", { message: error.message });
                cleanupFailed = true;
            }
        }
        if (httpServer?.listening) {
            httpServer.closeAllConnections();
            await bounded(new Promise((resolve) => httpServer.close(resolve)), 2000, "HTTP shutdown timed out")
                .catch((error) => { report("cleanup_error", { message: error.message }); cleanupFailed = true; });
        }
        if (kubo && kubo.exitCode === null && kubo.signalCode === null) {
            const exited = once(kubo, "exit");
            kubo.kill("SIGTERM");
            try {
                await bounded(exited, 8000, "Kubo shutdown timed out");
            } catch {
                kubo.kill("SIGKILL");
                await bounded(exited, 2000, "Kubo did not exit after SIGKILL").catch(() => { cleanupFailed = true; });
            }
        }
        await Promise.all(logs.map((stream) => new Promise((resolve) => stream.end(resolve))));
        report("fixture_stopped", { pid: process.pid, kubo_pid: kubo?.pid, cleanup_ok: !cleanupFailed });
        process.exit(cleanupFailed ? 1 : exitCode);
    })();
    return stopPromise;
}

// Keep handlers registered during asynchronous cleanup: signal-exit (used by
// PKC locks) otherwise sees no user listener after once() fires and re-kills us.
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => { void stop(0); });

function argumentsFrom(argv) {
    const usage = "usage: pkc_fixture.mjs [--kubo PATH] [--data-dir EMPTY_DIRECTORY | --data-dir FIXTURE_DIRECTORY --resume]";
    const options = { kubo: process.env.MODELSWARM_KUBO_BIN || "ipfs", dataDir: undefined, resume: false };
    for (let index = 0; index < argv.length; index++) {
        const name = argv[index];
        if (name === "--resume") { options.resume = true; continue; }
        if (!["--kubo", "--data-dir"].includes(name) || !argv[index + 1]) throw new Error(usage);
        options[name === "--kubo" ? "kubo" : "dataDir"] = argv[++index];
    }
    if (options.resume && !options.dataDir) throw new Error(usage);
    return options;
}

async function waitForKubo(repo) {
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
        if (stopping) throw new Error("fixture is stopping");
        if (kubo.exitCode !== null || kubo.signalCode !== null) throw new Error("Kubo exited before readiness");
        try {
            const address = (await readFile(path.join(repo, "api"), "utf8")).trim();
            const match = /^\/ip4\/127\.0\.0\.1\/tcp\/(\d+)$/.exec(address);
            if (!match) throw new Error("Kubo API is not bound to loopback");
            const base = `http://127.0.0.1:${match[1]}/api/v0`;
            const response = await fetch(`${base}/id`, { method: "POST", signal: AbortSignal.timeout(1000) });
            if (response.ok) return base;
        } catch {
            // The API file appears before the listener is necessarily ready.
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("Kubo did not become ready within 30 seconds");
}

async function main() {
    const options = argumentsFrom(process.argv.slice(2));
    const version = (await run(options.kubo, ["version", "--number"], { timeout: 5000 })).stdout.trim();
    if (version !== "0.43.1") throw new Error(`fixture requires Kubo 0.43.1; found ${version}`);
    if (options.resume) {
        // Restart the same node: same Kubo identity, swarm key, PKC database and
        // minter keys. Nothing is reinitialized, so this also models crash recovery.
        dataDir = path.resolve(options.dataDir);
        if ((await lstat(dataDir)).isSymbolicLink()) throw new Error("fixture data directory must be a real directory");
        for (const name of ["kubo/config", "kubo/swarm.key", "pkc"])
            await lstat(path.join(dataDir, name)).catch(() => { throw new Error(`cannot resume: ${name} is missing`); });
    } else if (options.dataDir) {
        dataDir = path.resolve(options.dataDir);
        await mkdir(dataDir, { recursive: true, mode: 0o700 });
        if ((await lstat(dataDir)).isSymbolicLink() || (await readdir(dataDir)).length)
            throw new Error("fixture data directory must be an empty, real directory");
        await chmod(dataDir, 0o700);
    } else {
        await mkdir(path.join(root, ".tmp"), { recursive: true });
        dataDir = await mkdtemp(path.join(root, ".tmp", "pkc-fixture-"));
    }
    const repo = path.join(dataDir, "kubo");
    const environment = { ...process.env, IPFS_PATH: repo, LIBP2P_FORCE_PNET: "1",
                          GOLOG_LOG_LEVEL: "error", IPFS_LOGGING: "error", GOMAXPROCS: "2" };
    if (!options.resume) await initializeRepository(options.kubo, repo, environment);
    // A killed daemon leaves its old API address behind; never probe a stale port.
    await rm(path.join(repo, "api"), { force: true });
    for (const name of ["kubo.stdout.log", "kubo.stderr.log"])
        logs.push(createWriteStream(path.join(dataDir, name), { flags: options.resume ? "a" : "wx", mode: 0o600 }));
    kubo = spawn(options.kubo, ["daemon"], { env: environment, stdio: ["ignore", "pipe", "pipe"] });
    kubo.stdout.pipe(logs[0], { end: false });
    kubo.stderr.pipe(logs[1], { end: false });
    kubo.once("error", (error) => { report("kubo_error", { message: error.message }); void stop(1); });
    kubo.once("exit", (code, signal) => {
        if (!stopping) { report("kubo_exited", { code, signal }); void stop(1); }
    });
    const kuboApi = await waitForKubo(repo);
    const { default: RPC } = await import(pathToFileURL(require.resolve("@pkcprotocol/pkc-js/rpc")));
    if (stopping) return;
    httpServer = http.createServer();
    rpc = await RPC.PKCWsServer({
        // Only a resumed node has previously started profiles to host again.
        server: httpServer, authKey: token, startStartedCommunitiesOnStartup: options.resume,
        allowPrivateKeyExport: false, exportFileMaxAgeMs: 0,
        pkcOptions: {
            dataPath: path.join(dataDir, "pkc"), kuboRpcClientsOptions: [kuboApi],
            pubsubKuboRpcClientsOptions: [], httpRoutersOptions: [], ipfsGatewayUrls: [],
            nameResolvers: [], resolveAuthorNames: false,
            publishInterval: 500, updateInterval: 250, validatePages: true,
        },
    });
    rpc.on("error", (error) => report("rpc_error", { code: error.code, message: error.message }));
    httpServer.listen(0, "127.0.0.1");
    await once(httpServer, "listening");
    const address = httpServer.address();
    originalStdout(JSON.stringify({ event: "pkc_fixture_ready", rpc_url: `ws://127.0.0.1:${address.port}/${token}`,
                                   kubo_api: kuboApi, data_dir: dataDir, pid: process.pid,
                                   kubo_pid: kubo.pid, resumed: options.resume }) + "\n");
}

async function initializeRepository(kuboBinary, repo, environment) {
    await run(kuboBinary, ["init", "--profile=test,autoconf-off"], { env: environment, timeout: 15000 });
    const configPath = path.join(repo, "config");
    const config = JSON.parse(await readFile(configPath, "utf8"));
    config.Addresses = { ...config.Addresses, API: "/ip4/127.0.0.1/tcp/0",
                         Gateway: "/ip4/127.0.0.1/tcp/0", Swarm: ["/ip4/127.0.0.1/tcp/0"],
                         Announce: [], AppendAnnounce: [], NoAnnounce: [] };
    config.Bootstrap = [];
    config.Peering = { Peers: [] };
    config.AutoConf = { ...config.AutoConf, Enabled: false };
    config.AutoTLS = { ...config.AutoTLS, Enabled: false };
    config.Discovery = { ...config.Discovery, MDNS: { Enabled: false } };
    config.Routing = { Type: "none" };
    config.Pubsub = { ...config.Pubsub, Enabled: true };
    config.Ipns = { ...config.Ipns, UsePubsub: true, MaxCacheTTL: "1s" };
    config.Swarm = { ...config.Swarm, DisableNatPortMap: true,
                     RelayClient: { Enabled: false }, RelayService: { Enabled: false } };
    await writeFile(configPath, JSON.stringify(config, null, 2), { mode: 0o600 });
    await writeFile(path.join(repo, "swarm.key"),
                    `/key/swarm/psk/1.0.0/\n/base16/\n${randomBytes(32).toString("hex")}\n`, { mode: 0o600 });
}

main().catch(async (error) => {
    report("fixture_error", { name: error.name, code: error.code, message: error.message, data_dir: dataDir });
    await stop(1);
});
