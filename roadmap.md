# Roadmap

What is built, what is next, what each step waits on, and where each decision is written down. Update this file in the same change that finishes or reshapes an item.

Durations are rough estimates of focused work, not dates. Last reviewed 2026-11-13.

## Built

- [x] Idea docs: [README.md](README.md), [how-it-could-work.md](how-it-could-work.md), [open-questions.md](open-questions.md) (2026-11-13).
- [x] Static landing page.
- [x] Isolated [download-engine prototype](prototypes/download-engine/README.md): libtorrent 2.1.1, v2-only peers and HTTP, corrupted-source recovery and persisted resume after SIGKILL (2026-11-13). See the [evaluation](prototypes/download-engine/EVALUATION.md).
- [x] Unsigned [manifest v0 and CLI](cli/README.md): `make`, `verify`, `pull`, nested files, format policy, resumable transfers and a verified Hugging Face-compatible cache (2026-11-13).

- [x] [Local Hugging Face endpoint prototype](cli/ENDPOINT.md): `serve`/`HF_ENDPOINT`, registered manifests, verified public upstream fallback and real SDK end-to-end downloads (2026-11-13).
- [x] [Signed publisher release prototype](cli/RELEASES.md): local keys, delegated profile setup, signed publication, profile/version/CID pulls and endpoint registration through a private real PKC node (2026-11-13).

The experimental CLI, SDK endpoint and signed publishing are implemented. Public operation, catalogue and desktop client remain. The prototypes do not complete the measurements milestone.

## What Blocks What

| Part | Depends on | State of the dependency (2026-11-13) |
|---|---|---|
| Making, verifying and pulling releases from a manifest | A BitTorrent v2 library with web seeds | libtorrent 2.1.1 passed the isolated prototype on macOS arm64. Production packaging and broader validation remain [open](open-questions.md#torrents) |
| The Hugging Face endpoint | The requests existing tools make | SDK 2.4.0 routes and downloads tested; other consumers still need their own evidence |
| Publishing releases | Author communities ([BSIP-14](https://bsips.bitsocial.net/bsip-14)) on a node the publisher runs | Implemented in pkc-js. Publishers without a node wait for hosted profiles on a public RPC |
| Hubs | Communities ([BSIP-3](https://bsips.bitsocial.net/bsip-3)) and crossposts ([BSIP-12](https://bsips.bitsocial.net/bsip-12)) | Implemented in pkc-js |
| Search | `bitsocial-indexer`, extended to parse manifests | The indexer exists; manifest parsing does not |
| Names, tips | `.bso` names ([BSIP-13](https://bsips.bitsocial.net/bsip-13)), Bitsocial Chain | Optional. Publishers work as bare keys until then |

The first three milestones need no Bitsocial data at all, and none of the six waits on an earlier phase of the master plan.

## Next

### 1. Measurements

Two numbers decide the design, so they come before any product code.

- [ ] **Community size.** Extend the seeded-board benchmark in `pkc-js-benchmarks` beyond its current 2,000 posts, to the sizes a busy publisher profile and a popular hub would reach. Record load time for a reader, and CPU, disk and memory for the operator. Answers [open-questions.md](open-questions.md#scale).
- [ ] **Piece verification over HTTP.** Take a multi-gigabyte model file, build a v2 torrent, and download it from an HTTP mirror while checking every piece against the pieces root. Record hashing cost and the time to detect a modified file. Answers part of [open-questions.md](open-questions.md#torrents).
  - The prototype records hashing and corruption timing with a 491 MB real model. A multi-gigabyte real-model benchmark and CPU/memory profiling remain to do.
- [ ] **A swarm with web seeds.** Seed the same torrent from one machine with Hugging Face as a web seed, and download from another with a candidate library.
  - Local peer/HTTP combinations and direct Hugging Face HTTPS passed separately. Distinct-machine/WAN testing remains to do.

Estimate: about 1 week. Blocked by: nothing.

### 2. Manifest and command line

- [x] [Manifest format v0](cli/MANIFEST.md), a prototype convention until the BSIP: unsigned JSON, one embedded v2 torrent per nonempty file, complete piece layers and explicit sources.
- [x] `modelswarm make`: hash a directory, build per-file torrents and write the manifest.
- [x] `modelswarm verify`: check local sizes, SHA-256, pieces roots and formats against a manifest.
- [x] `modelswarm pull` from a manifest file: download from peers and HTTP, verify pieces and complete files, resume from flushed checkpoints, and publish verified snapshots in a Hugging Face-compatible cache. Offline `huggingface_hub` lookup is tested; GGUF consumers can use the returned file path. Inference with `transformers` or llama.cpp is not tested.
- [x] Format inspection and the flagged-format download rule: code, pickle and unknown files are excluded by default and require `--allow-unsafe`.

Prototype completed 2026-11-13; see [verification and remaining work](cli/EVALUATION.md). This does not establish production readiness, publisher identity, cross-platform installation, WAN operation or power-loss durability.

### 3. The Hugging Face endpoint

- [x] Record and implement `huggingface_hub` 2.4.0 model info, tree, HEAD and file/range requests.
- [x] `modelswarm serve`: serve registered local manifests through a loopback endpoint.
- [x] Fallback for unregistered public models: pin upstream revisions, verify whole files against LFS SHA-256 or Git blob SHA-1, then serve them.
- [x] Real SDK end-to-end tests, including a 491 MB model through local manifests and public HTTPS fallback.
- [ ] Record and test `transformers`, the `hf` command, llama.cpp and Ollama independently; compatibility with the SDK does not establish all of them.

SDK prototype completed 2026-11-13; see [evidence and remaining scope](cli/ENDPOINT-EVALUATION.md). Private/gated models, streaming verified pieces and production hardening remain. The original two-week estimate covered the broader multi-consumer milestone.

After this milestone the tool is useful to one person with no network of publishers: verified downloads, resumable from several sources.

### 4. Publishing and reading releases

- [x] Explicit RPC connection settings (`--rpc`/`MODELSWARM_RPC`); publishers retain their keys locally.
- [ ] A validated hosted Forge default and provider-hosted profile onboarding.
- [x] `keygen`, `profile-init` and `modelswarm publish`: initialize a delegated author profile and post a locally signed manifest announcement on an operator-controlled PKC node.
- [x] `pull pkc://…` and `serve --release` resolve explicit publisher/version or CID-pinned releases, verify signatures and bind the manifest before downloading.
- [ ] Mirror records v0: publish one when seeding a Hugging Face model, and check records on completed downloads.
- [ ] A demo publisher profile on a Bitsocial node we run, with real releases of permissively licensed models, the way WeTube's demo channel works.
- [ ] Web client, read-only: publisher pages, release pages with the model card, file list, format flags and sources. On the stack of 5chan and WeTube.

The signed CLI/profile slice is implemented; see [evidence and remaining scope](cli/RELEASES-EVALUATION.md). It uses explicit bare publisher keys rather than unproven human-readable names. Tests use a private real PKC/Kubo network, not public hosting. Mirror records, a public demo, name proofs and the read-only web client remain. The original 3–4 week estimate covered this broader milestone.

### 5. Hubs and search

- [ ] Crosspost a release into a hub; replies and votes in the web client.
- [ ] Hub lists in the client settings.
- [ ] Manifest parsing in `bitsocial-indexer`, with filters for base model, format, quantization, license and size.
- [ ] Search in the client across several indexers.

Estimate: 2 to 3 weeks. Blocked by: milestone 4.

### 6. Desktop client

- [ ] Desktop build with a Bitsocial node and a torrent engine.
- [ ] Transfers dashboard, seeding by default with a ratio cap.
- [ ] The local endpoint running inside the app.

Estimate: 3 to 4 weeks. Blocked by: milestones 3 and 5.

## BSIPs

All existing BSIPs are drafts. Modelswarm builds on BSIP-2, 3, 10, 12, 13, 14 and 15, and would add:

| BSIP | Category | Requires | Written when |
|---|---|---|---|
| Model releases: the manifest, file hashes, sources, the `base` link and withdrawal | Application | 2, 14 | After milestone 4, once real publishing has tested the format |
| Mirror records and confirmations | Application | Model releases | After milestone 4 |
| Scan results | Application | Model releases | When a second scanner exists |

## Later

- [ ] Scanner services and the scan result record.
- [ ] Datasets.
- [ ] `.bso` names for publishers and tips on Bitsocial Chain.
- [ ] Hosted profiles for publishers without a node, when Forge RPC or another compatible provider offers them. Revenue from this metadata hosting is speculative; validate publisher willingness to pay before treating it as a business case.
- [ ] Hub-funded seedboxes.
- [ ] Mobile clients for browsing and discussion.
