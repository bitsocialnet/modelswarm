import { once } from 'node:events';
import { randomBytes } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const require = createRequire(new URL('../src/modelswarm/bridge/package.json', import.meta.url));
const { default: RPC } = await import(pathToFileURL(require.resolve('@pkcprotocol/pkc-js/rpc')));
const data = process.env.PKC_DATA_PATH;
if (!data) throw new Error('Set PKC_DATA_PATH to a private directory');
const kubo = process.env.KUBO_API ?? 'http://127.0.0.1:5001/api/v0';
const host = process.env.PKC_RPC_HOST ?? '127.0.0.1';
const port = Number(process.env.PKC_RPC_PORT ?? 18666);

await mkdir(data, { recursive: true, mode: 0o700 });
const authFile = join(data, 'rpc-key');
try {
  await writeFile(authFile, randomBytes(32).toString('hex'), { mode: 0o600, flag: 'wx' });
} catch (error) {
  if (error.code !== 'EEXIST') throw error;
}
const authKey = await readFile(authFile, 'utf8');

const server = createServer();
const rpc = await RPC.PKCWsServer({
  server,
  authKey,
  allowPrivateKeyExport: false,
  startStartedCommunitiesOnStartup: true,
  pkcOptions: {
    dataPath: join(data, 'pkc'),
    kuboRpcClientsOptions: [kubo],
    pubsubKuboRpcClientsOptions: [],
    httpRoutersOptions: [],
    ipfsGatewayUrls: [],
    nameResolvers: [],
    resolveAuthorNames: false,
    validatePages: true,
  },
});
rpc.on('error', (error) => console.error('PKC RPC error', error.code));
server.listen(port, host);
await once(server, 'listening');
console.log('ModelSwarm PKC node ready');

const shutdown = async () => {
  await rpc.destroy();
  server.close();
};
process.once('SIGTERM', shutdown);
process.once('SIGINT', shutdown);
