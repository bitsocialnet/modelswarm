# Public signed demo

The [release page](https://modelswarm.org/release.html) lists the original Qwen weights and license. ModelSwarm's demo publisher signs a release announcement on its own PKC profile. Kubo serves the announcement and its pinned manifest, and a separate BitTorrent v2 seeder serves the model and license. The manifest has no HTTP weight source. For a download without a PKC reader, use the [HTTP quickstart](../../README.md#getting-started).

## Pull from the public seeder

Install the [CLI](../README.md#install-locally) and [Node bridge](../RELEASES.md#install-the-optional-bridge). For an existing compatible PKC reader, connect its Kubo to the demo's public swarm address below and use the command from the release page. To start your own temporary reader, install [Kubo](https://docs.ipfs.tech/install/command-line/), then run from the checkout root:

```sh
reader="$(mktemp -d)"
export IPFS_PATH="$reader/kubo"
ipfs init --profile=server
ipfs config Addresses.API /ip4/127.0.0.1/tcp/15001
ipfs config Addresses.Gateway /ip4/127.0.0.1/tcp/18081
ipfs config Addresses.Swarm --json '["/ip4/127.0.0.1/tcp/0"]'
ipfs config Pubsub.Enabled --json true
ipfs config Ipns.UsePubsub --json true
ipfs daemon > "$reader/kubo.log" 2>&1 &
kubo_pid=$!

# Wait for `ipfs swarm peers` to succeed before connecting.
ipfs swarm connect /ip4/159.195.210.230/tcp/4401/p2p/12D3KooWFWfDcwh5EcGNDoNVk2Q3PYD8MszboqjNPtgptt8D44Ag
PKC_DATA_PATH="$reader/pkc" KUBO_API=http://127.0.0.1:15001/api/v0 \
  node cli/demo/node.mjs > "$reader/pkc.log" 2>&1 &
pkc_pid=$!

# Wait for "ModelSwarm PKC node ready" in "$reader/pkc.log".
export MODELSWARM_RPC="ws://127.0.0.1:18666/$(cat "$reader/pkc/rpc-key")"
```

Paste the pull command from the release page in the same shell. It pins the exact announcement and uses the seeder's public address. The demo command leaves periodic checkpoints out of the transfer window to keep the direct peer connection open. Interruptions and timeouts still save a checkpoint. The final JSON includes `signed: true`, the release CID and the verified `snapshot` directory. To shut down the temporary reader afterward, run `kill "$pkc_pid" "$kubo_pid"` and `unset MODELSWARM_RPC IPFS_PATH`.

## Operate the demo

The Compose stack keeps the publisher and Kubo API on its internal Docker network. Publish TCP port 4401 for IPFS swarm traffic and 51413 for the torrent seeder. These are the only public listeners in this stack.

1. On the host, place the [peer-only manifest](../../public/demo/qwen-signed-manifest.json) at `$DEMO_FILES/signed-manifest.json`. Place its two original files under `$DEMO_FILES/model/`, preserving the paths in the manifest. The seeder checks the files against the manifest before listening.
2. Set `DEMO_FILES` to the absolute path of that directory and `DEMO_IPFS_ANNOUNCE` to `/ip4/HOST_PUBLIC_IP/tcp/4401`. Export both or pass an env file to Compose, then run `docker compose -f cli/demo/compose.yaml up -d --build` from the root.
3. Pin the manifest with `docker compose -f cli/demo/compose.yaml exec -T kubo ipfs add -Q /demo/signed-manifest.json`. In the publisher container, set `MODELSWARM_RPC="ws://127.0.0.1:18666/$(cat /data/rpc-key)"` and follow the [signed publishing instructions](../RELEASES.md#create-and-publish) with an `ipfs://` manifest URL. Pin the emitted release CID in Kubo as well. Keep the owner key and PKC data in the publisher volume. When restoring this demo, reuse the existing publisher and Kubo volumes to retain the signing identity, announcement CIDs and swarm address.
4. Check for `"seeding": true` in the seeder logs. After a restart, test a CID-pinned pull before checking profile version discovery. The [publisher guide](../RELEASES.md#keep-a-profile-hosted) covers recovery after an abrupt restart.

The seeder uses a fixed peer address. This demo exercises an explicit public IPFS peer and an explicit BitTorrent peer. Automatic DHT discovery, inbound connections to a reader behind NAT and production capacity remain unverified.
