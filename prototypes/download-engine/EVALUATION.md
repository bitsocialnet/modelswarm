# Download engine evaluation — 2026-11-13

**Decision: proceed with libtorrent as the provisional native engine for the CLI milestone.** The tested build handles v2-only peers, HTTP web seeds, mixed sources, bad bytes from either source, and persisted recovery after a forced process kill. No engine blocker remains in this scope. This is a transport feasibility result, not production readiness or a publisher-authentication implementation.

## Environment and inputs

- macOS 27.0.1, arm64; Python 3.11.15; PyPI `libtorrent==2.1.1`, native version `2.1.1.0`.
- Real model: Qwen/Qwen2.5-0.5B-Instruct-GGUF, revision `9217f5db79a29953eb74d5343926648285ec7e67`, `qwen2.5-0.5b-instruct-q4_k_m.gguf` (Apache-2.0).
- File size: **491,400,032 bytes** (491.4 MB / 468.6 MiB). SHA-256 independently checked against [Hugging Face's pinned tree metadata](https://huggingface.co/api/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/9217f5db79a29953eb74d5343926648285ec7e67): `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`.
- Large synthetic fixture: **2,148,532,224 bytes** (2,049 MiB, above 2 GiB), deterministic SHAKE-256 data; whole-file SHA-256 `5e7edfd80e4cd2d66c0c9c3d32abe4f2ece8bc699fb6e9b8d85065ae569b761a`.
- Complete v2-only `.torrent` metadata, 1 MiB pieces; roots/piece layers generated from the known input. No v1 fallback. All peers and controlled HTTP servers use loopback; discovery is disabled. Only the explicit Hugging Face HTTPS scenario uses an external server.

## Observed results

Every completed transfer matched the original whole-file SHA-256. The real-model scenarios all used separate empty destinations except the deliberately resumed download.

| Scenario | Outcome | Evidence |
|---|---|---|
| Real model, peer only | PASS | 491,400,032 payload bytes from the explicit seed; 1.802 s |
| Real model, HTTP only | PASS | Range requests served all 491,400,032 bytes; no peers; 1.336 s |
| Real model, mixed sources | PASS | Peer uploaded 342,884,352 bytes; HTTP sent 151,317,344 bytes; receiver recorded 2,786,468 redundant bytes; 17.474 s with a 32 MiB/s cap |
| Corrupted HTTP, healthy peer fallback | PASS | First 1 MiB piece rejected at 1.529 s, with zero verified pieces; 1,048,576 failed bytes; successful recovery |
| Malicious peer, healthy HTTP fallback | PASS | First 1 MiB piece rejected at 2.029 s, with zero verified pieces; 1,048,576 failed bytes; successful recovery |
| Forced kill and fresh-process resume | PASS | Checkpoint retained 118 pieces / 123,349,856 verified bytes; fresh process restored 118 pieces and fetched 367,984,640 bytes, re-requesting no completed HTTP pieces |
| Real model, direct Hugging Face HTTPS | PASS | Native libtorrent fetched all 491,400,032 bytes through the pinned HTTPS web seed; final upstream SHA-256 matched; 17.904 s |
| 2,049 MiB synthetic file, peer only | PASS | Full digest match; 2.875 s |
| 2,049 MiB synthetic file, HTTP only | PASS | Full digest match; 2.373 s |

The resumed payload is slightly smaller than the bytes outside completed pieces because libtorrent also retained some partial-piece blocks. Checkpoints were saved after `torrent_paused_alert`, written and fsynced, then the worker was killed with SIGKILL. This tests a process crash after a saved checkpoint, not sudden power loss or damage to the checkpoint/data files.

Hashing the real model into v2 metadata **and computing its whole-file SHA-256** took 0.454 s; the synthetic file took 1.952 s. Torrent metadata was 15,311 and 65,828 bytes respectively. These are warm local-machine observations, not cold-disk benchmarks. Transfer times include the worker's final SHA-256 check; they are not pure network-throughput measurements. No CPU or peak-memory profile was taken.

Six focused checks also pass: v2-only/root consistency; rejection of a modified piece layer even with the original infohash; rejection of a checkpoint from another torrent; rejection of an unexpected torrent digest before destination creation; exact handling of virtual tail padding; and exclusion of unverified partial blocks from verified-byte counts.

Repository validation also passed: `yarn agent:verify` (lint, TypeScript, production build and advisory Knip), `yarn ai-workflow:check`, and all 29 `yarn ai-workflow:test` tests. Workflow synchronization changed no generated files. Independent code-quality review found no remaining actionable issues after the HTTP attribution correction. Site edits are status copy only; no browser behavior changed or browser session was started.

Local raw evidence is under `artifacts/real-model-03/` and `artifacts/large-file-01/`, including `results.json`, `.torrent` files, worker JSONL and HTTP request logs. [evaluation-results.json](evaluation-results.json) preserves the numeric results without local paths or process identifiers. Generated transfer copies may be removed after verification; [README.md](README.md) gives reproduction commands.

## Failures found and corrected

1. **Premature resume snapshot.** Initial tests (`run-01`–`run-03`) produced zero completed-piece bits. `total_done` includes incomplete/unverified blocks, and immediate save after `pause()` races disk completion. The fix gates on completed-piece state and waits for `torrent_paused_alert` before requesting the checkpoint. `run-04` then preserved 16/64 pieces; the real-model run preserved 118/469. The integration assertions and focused counter test prevent recurrence. [Byte counter source](https://github.com/arvidn/libtorrent/blob/v2.1.1/src/torrent.cpp#L4376), [pause completion](https://github.com/arvidn/libtorrent/blob/v2.1.1/src/torrent.cpp#L10127).
2. **Tail padding and web-seed URL semantics.** The first real-model attempt rejected the virtual pad file. After allowing it, an exact-file HTTP URL still failed because libtorrent treats the padded torrent as multi-file and appends a path to a directory URL. The prototype now excludes padding from model-byte totals and normalizes that URL to its containing directory. Local and Hugging Face HTTPS tests then passed. A focused padding test preserves this case.
3. **LAN rate-limit exemption.** Default session limits do not constrain loopback peers. Test sessions now explicitly include loopback in the global rate-limit class; the checkpoint fixture also throttles its HTTP server. Throttled scenario timing is not an intrinsic engine limit.
4. **Resume evidence attribution.** Review found old HTTP handlers could append events after restart, misclassifying old requests as resumed requests. Restart now uses a new server/event stream, also exercising replacement of web-seed URLs during restore.

The Python binding emits deprecation warnings for its file-storage constructor/accessors. They are non-fatal on the pinned build; production bindings/API selection need review before upgrading.

## What is still unproven

- WAN peers, NAT traversal, discovery, separate machines, unreliable networks, or sustained seeding availability.
- Windows/Linux packaging and other libtorrent 2.x versions. The Python prototype does not settle the production language, native-process boundary or desktop distribution strategy.
- Multi-file/sharded releases, many simultaneous downloads, tens-of-GB model files, disk-full recovery, damaged checkpoints or power-loss durability. The >2 GiB test uses synthetic bytes, not a multi-GiB real model.
- Gated/private Hugging Face models, credentials, all CDN/mirror behaviors, or comparative speed against Hugging Face's normal downloader. One pinned public model worked; this is not blanket Hub compatibility.
- Publisher signatures, key/name resolution, a signed manifest, adversarial metadata/resource limits, safe URL/path policies, and a streaming API that exposes only verified bytes. Integrity does not imply a model is safe to load.

## Next implementation

Build a small CLI around this proven path: versioned manifest and authenticated roots, `make`/`verify`/`pull`, deterministic cache placement, error reporting and a maintained native-engine boundary. Before calling it a public beta, test two machines over a real network, multiple shards, missing/unavailable sources, damaged checkpoint recovery and installable packages. Preserve complete piece layers for HTTP-only startup; a bare magnet is insufficient without a peer to supply verification data. See [BEP 52](https://www.bittorrent.org/beps/bep_0052.html).
