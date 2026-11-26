# Signed publisher releases

`keygen`, `profile-init`, `profile-start`, `profile-renew`, `publish`, `pull pkc://…` and `serve --release` implement a prototype over real PKC author communities. The publisher signs locally with Ed25519; readers verify the immutable record and its manifest before enabling downloads. See [evaluation](RELEASES-EVALUATION.md) and the [restart and renewal evaluation](PERSISTENCE-EVALUATION.md) for evidence and limits.

## Install the optional bridge

Install the [Python CLI](README.md) first, then install the separate Node bridge from this checkout:

```sh
cd cli/src/modelswarm/bridge
corepack yarn install --immutable
cd ../../../..
```

The bridge pins `@pkcprotocol/pkc-js` 0.0.163 and uses Node, Corepack Yarn 4.17.1 and the native `better-sqlite3` dependency. Install and run with the same Node major version; switching versions may require rebuilding the native dependency. Tested on macOS arm64 with Node 26.12.1. `MODELSWARM_NODE` selects another Node executable. The Python wheel includes bridge source/lockfile, but does not bundle Node, native dependencies or a node operator. A single-command cross-platform installer remains work to do.

Local manifest commands and ordinary upstream fallback do not need this bridge. Profile operations require an accessible PKC RPC node compatible with the pinned SDK. Set `MODELSWARM_RPC` or pass `--rpc`; remote connections require `wss://`, while loopback accepts `ws://`. RPC URLs may contain a capability in their path: keep them private. There is no assumed/default Forge URL. Publishing currently requires an operator-controlled node capable of creating and hosting delegated profiles.

## Create and publish

```sh
export MODELSWARM_RPC='wss://YOUR-PKC-NODE/PRIVATE-RPC-CAPABILITY'
cli/.venv/bin/modelswarm keygen -o ~/.config/modelswarm/publisher.key.json
cli/.venv/bin/modelswarm profile-init --key ~/.config/modelswarm/publisher.key.json

cli/.venv/bin/modelswarm make ./model -o ./release.json \
  --name example/model --version v1 --license apache-2.0 \
  --http-base https://YOUR-MIRROR/model/

# First host these exact manifest bytes at the URL below, or pin them in IPFS.
cli/.venv/bin/modelswarm publish ./release.json --key ~/.config/modelswarm/publisher.key.json \
  --manifest-url https://YOUR-MIRROR/release.json --card ./MODEL_CARD.md
```

The generated key file has mode 0600, is never overwritten, and must be backed up privately. `keygen` resolves the explicitly selected output directory, including path aliases such as `/tmp`; an existing file or symlink at the output filename is still refused. The publisher identity is its `12D3KooW…` Peer ID. The owner key stays in the CLI process/bridge stdin; RPC receives signed records and public identity. `profile-init` creates a distinct node-held minter, signs its initial delegation locally and starts hosting. It leaves that profile running when the command exits. It is an initial setup command, not profile migration or delegation renewal.

## Keep a profile hosted

```sh
# If a profile is not hosted after a restart: ask the node to host it. No key is needed.
cli/.venv/bin/modelswarm profile-start PUBLISHER

# Sign a newer delegation to the same node-held minter.
cli/.venv/bin/modelswarm profile-renew --key ~/.config/modelswarm/publisher.key.json --minter MINTER
```

A node that restarts on the same data directory hosts its profiles again with no client involved: same publisher, minter, delegation sequence and release CIDs. This holds for a node killed without cleanup (SIGKILL, power loss) and restarted at once, because the pinned SDK's start lock is released when its process dies. In the loopback tests the profile was hosted again within about a second of the restart, and a release published right after it was found by version within two seconds. Timing on a public network is untested. If a profile is not hosted after a restart, `profile-start` asks the node to host it; it is safe to repeat on a running profile and refuses publishers the node does not host.

`profile-renew` asks the node which sequence beats every delegation it knows (the SDK answers the highest known plus five), signs that record locally with the owner key, and has the node verify and publish it. `MINTER` is the minter Peer ID that `profile-init` printed: the CLI signs only for that minter and refuses a sequence more than 1,000 above the node's current one, because the node supplies both values and a signed delegation cannot be withdrawn. Keep the minter ID with the key backup. The node refuses records that roll the sequence back or repeat it, point at another minter, or carry another key's signature. The minter, publisher identity and existing release CIDs do not change. The SDK signs delegations with a fixed lifetime of about 100 years, so renewal re-asserts the current delegation; it is not needed to prevent expiry. Moving a profile to a new node or minter, and revoking a leaked minter, are not implemented.

`publish` fetches the manifest from the supplied HTTPS or `ipfs://CID` location and checks its exact SHA-256 against the local file before posting. IPFS manifests are limited to **1 MiB** by the pinned PKC RPC API; use HTTPS for larger manifests, up to the manifest format's 16 MiB limit. IPFS verification supports the default UnixFS layout from Kubo `add`; alternative chunking/raw-object layouts are unsupported. It does not upload/pin the manifest or seed model weights. The optional UTF-8 model card is limited to 24 KiB, and the complete signed publication must fit PKC's 40,000-byte limit. JSON escaping adds overhead, so some cards below 24 KiB need shortening; the CLI checks the encoded publication before sending it. Successful output includes `publisher`, `release_cid` and a pinned `release_uri`. The CLI reads the post back and verifies it locally before reporting success. An identical observed release is reused; an observed different announcement for the same version is refused. Concurrent publishers or incomplete feeds can still create conflicting records.

## Read a publisher release

```sh
# Paste the exact publisher identity and CID returned by publish.
cli/.venv/bin/modelswarm pull 'pkc://PUBLISHER/example/model@v1#RELEASE_CID'

# Alternatively discover an explicit version from the publisher's profile.
cli/.venv/bin/modelswarm pull 'pkc://PUBLISHER/example/model@v1'

cli/.venv/bin/modelswarm serve \
  --release 'pkc://PUBLISHER/example/model@v1#RELEASE_CID' --port 7861
```

`PUBLISHER` must be the actual canonical Ed25519 Peer ID, obtained through a trusted channel. Bare names and implicit `latest` are unsupported. A version lookup scans up to 32 pages/1,024 candidates and rejects differing valid announcements it observes. An RPC can omit or replay pages: this scan cannot prove completeness, freshness or global uniqueness. Retain the pinned URI for reproducibility. A CID pull verifies the exact record without requiring the current profile feed; withdrawal and deletion status are not checked.

For the endpoint, set `HF_ENDPOINT=http://127.0.0.1:7861` before importing `huggingface_hub`, use a separate SDK cache, and request `example/model`. See [SDK setup](ENDPOINT.md). Registration resolves once at startup and owns the whole model name; missing local files/revisions never fall back upstream. File responses include `X-Modelswarm-Publisher` and `X-Modelswarm-Release`. Unregistered names retain verified public Hugging Face fallback. Two registrations with the same model name are refused even if they have different publisher keys.

All existing file selection, format restrictions, checkpoint recovery and verified cache rules apply. Signed sources require public HTTPS by default, and native IP filters block nonpublic peer/webseed connections. A signed `pull` with a blocked explicit `--peer` fails before staging, names the peer and points to `--allow-local-sources`. That flag explicitly permits local fixture/LAN sources and peers; it is needed for loopback manifest URLs too. A signature alone never grants local network access. `--allow-unsafe` remains a separate explicit opt-in for code/pickle/unknown files, and never executes them.

## Wire format and verification

The native PKC post's signed `content` is canonical JSON:

```json
{
  "schema": "modelswarm/release/v0",
  "name": "example/model",
  "version": "v1",
  "manifest": {"url": "https://YOUR-MIRROR/release.json", "sha256": "64-lowercase-hex-characters"},
  "modelCard": "# Example model\n"
}
```

This is a prototype convention, not a BSIP. The standalone [manifest v0](MANIFEST.md) is unchanged and unsigned by itself. Its exact digest is authenticated by the release. Readers independently verify:

1. Exact raw PKC record bytes match the requested IPFS CID; the record is within 40 KiB.
2. Native Ed25519 signature over the CBOR-encoded signed properties, including content, timestamp, protocol version and community key.
3. The signer's derived Peer ID equals both the requested publisher and the signed community key. RPC-supplied author/profile fields cannot authorize a release.
4. The release matches the requested name/version; the fetched manifest matches the signed digest and repeats that name/version.
5. Manifest metadata/paths/sources pass validation; downloaded pieces, complete SHA-256 and format checks pass before cache publication or serving.

The protocol rejects malformed signatures, altered properties and unsupported envelopes. Transport failures fail the operation instead of silently turning an incomplete scan into an empty feed. A signature identifies a key, not a legal person, upstream organization, license grant or safe model. Key/name proofs, rotation/recovery, revocation/withdrawal, lineage and mirror attestations remain unimplemented.

The default RPC deadline is 120 seconds (`--rpc-timeout`, maximum 3,600). Cancellation terminates the child bridge. A timeout or interruption during publication can leave a successfully accepted record; resolve the explicit version before retrying. Hosting, supervised restarts and public network availability remain operator responsibilities.

## Reproduce the tests

```sh
cd cli/src/modelswarm/bridge
corepack yarn test
cd ../../../..
MODELSWARM_KUBO_BIN=/absolute/path/to/kubo-0.43.1/ipfs \
  cli/.venv/bin/python -m unittest discover -s cli/tests -v
```

Install [test dependencies](README.md#tests) first. `test_persistence.py` stops, kills and resumes that node on one data directory and takes about a minute. `test_two_nodes.py` adds a second node in the same private swarm that reads the publisher without using its RPC. The real profile tests start a fresh private Kubo swarm and a loopback PKC RPC node, then stop them and remove their disposable repositories. They do not publish public releases. Without Kubo 0.43.1 those integration tests explicitly skip; a skipped suite is not evidence of profile functionality.
