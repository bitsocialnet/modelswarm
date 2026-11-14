# Signed release evaluation — 2026-11-13

**The requested publishing/reading slice works in the isolated prototype.** Native owner-signed PKC profile posts authenticate manifest digests, and both `pull` and the local Hugging Face endpoint consume them. Proceed with operator lifecycle and public-network validation; this does not establish a production release service or complete roadmap milestone 4.

## Implemented

- Local Ed25519 key generation, private file permissions, and delegated author-profile initialization on a specified PKC RPC node. The node holds a distinct minter key; the publisher's owner key stays local.
- `publish` checks already-hosted manifest bytes, posts the native signed announcement/model card, then reads back and verifies its immutable CID and signature. Identical observed retries are reused; different observed content for a version is refused.
- `pull pkc://PUBLISHER/owner/model@VERSION[#CID]` verifies native CBOR/Ed25519 signatures, record CIDs, signer/community/selector binding and manifest digest/name/version before enabling the existing peer/HTTP engine.
- Explicit-version profile scans traverse pages and reject observed conflicts. CID pins select exact immutable records. No implicit latest or bare human-name resolution.
- `serve --release` resolves at startup, retains publisher/CID provenance, and supports the existing SDK API and public upstream fallback. Registered names own their namespace.
- Public HTTPS sources by default, bounded DNS/redirect validation for manifest HTTP, native nonpublic IP filtering for model peers/webseeds, and an explicit local-source opt-in. Existing unsafe-format opt-in remains separate.

Usage and exact limitations are in [RELEASES.md](RELEASES.md).

## Runtime evidence

Environment: macOS 27.0.1 arm64, Python 3.11.15, libtorrent 2.1.1 (native 2.1.1.0), Node 26.12.1, `@pkcprotocol/pkc-js` 0.0.142, Kubo 0.43.1, `huggingface_hub` 2.4.0. The pinned PKC bridge is optional for local manifest commands and ordinary upstream fallback.

Final validation: **81 Python tests passed in 80.806 seconds, with no skips**, including all 65 existing tests and 16 new tests. **22 Node protocol tests passed in 0.491 seconds.** Repository lint, TypeScript, build, advisory Knip, dependency pinning, workflow validation and all 29 workflow tests passed. Independent code-quality review has no remaining actionable findings. Raw local logs are `cli/artifacts/release-tests.log`, `release-protocol-tests.log`, `release-root-checks.log` and `release-wheel.log`; the failed first run is retained as `release-tests-first.log`.

```sh
MODELSWARM_KUBO_BIN=/absolute/path/to/kubo-0.43.1/ipfs \
  cli/.venv/bin/python -m unittest discover -s cli/tests -v
# In cli/src/modelswarm/bridge:
corepack yarn test
# At repository root:
corepack yarn agent:verify
uv build --wheel cli --out-dir cli/artifacts/release-wheel
```

The integration fixture starts an actual PKC minter/RPC server and fresh Kubo repository with a private swarm key, zero bootstrap peers, disabled mDNS/AutoTLS and loopback listeners. Real SDK calls publish and read native records through that node; no fake profile service substitutes for the protocol. Commands run in fresh Python/Node processes, and the publisher profile remains hosted after each client exits. The fixture stops its processes and removes its private repositories afterwards.

Coverage:

| Check | Evidence |
|---|---|
| Native release verifier | 22 Node tests: valid records, exact CID, CBOR/Ed25519 tampering, publisher/community binding, required signed properties, schemas and limits |
| Real profile CLI | 10 E2E tests: key/profile setup, publishing, version/CID pulls, unchanged retries and conflicting versions, safe subsets and complete file digests |
| Feed ambiguity | Two valid differing owner announcements on separate real pages; version lookup refuses, either pinned CID succeeds |
| Manifest integrity | Tampered bytes refused before model requests; restored bytes work; signed name/version mismatch rejected |
| IPFS manifest | Kubo add → publish `ipfs://CID` → pull, without an HTTP manifest fetch |
| Profile safety | Repeated initialization refused; original minter and delegation remain; wrong publishers/selectors refused; CLI output contains no owner key or RPC capability |
| Signed endpoint | Actual CLI server and fresh Hugging Face SDK process download from a signed release, with independent file digest checks |
| Network policy | Four native tests: numeric loopback/DNS webseeds and peers blocked with zero payload; explicit opt-in transfers and verifies the same files |
| Cancellation | Real Node stalled on a loopback WebSocket handshake is killed/reaped on Python SIGTERM; prior signal handler restored |
| Final disk synchronization | Real JSON/GGUF transfers wait for the native pause/flush alerts before final verification; the previous engine fails the ordering regression |
| Package/browser | Wheel inspected for the five required bridge runtime/dependency files and exclusion of node_modules/keys; Chrome status copy checked at 1440 and 375 pixels, no horizontal overflow or console errors |

The new signed-profile E2E uses small synthetic model files. The prior unsigned CLI and endpoint milestones tested a 491,400,032-byte real Qwen model; that experiment was not rerun as a signed public release. No model inference or public publication occurred here.

## Corrections during verification

- Review reproduced an orphaned Node bridge when Python received SIGTERM. Scoped cleanup now kills/reaps it and restores the caller's handler. The real-process regression fails when that guard is disabled and passes with the fix.
- The first full 80-test run had one intermittent `size mismatch: config.json` after native completion. Final verification previously read immediately on `is_seeding`. It now pauses and waits for native disk shutdown plus a flushed checkpoint before reading the completed file. This follows libtorrent's documented [disk synchronization alert](https://libtorrent.org/reference-Alerts.html#torrent_paused_alert). A real-transfer ordering regression covers the boundary.
- Wheel inspection caught setuptools discovering Python files inside the nested Node dependency tree. Explicit regular-package discovery and an explicit package-data allowlist now exclude them; rebuilt wheel inspection passes.

The repository retrospective selected focused lifecycle/transfer regressions and explicit packaging boundaries. No broad new workflow rule was introduced. A first browser launch exceeded the local Unix socket path limit; using a shorter owned session name passed and the session was closed.

## Still missing

- **Public operation:** no live Forge default, hosted-profile onboarding, public WAN/NAT test, persistent operator service or public demo release. Tests prove client exit does not stop the profile. Node restarts, crash recovery, delegation renewal, a separate reader node and one cross-machine pull of a real model were tested afterwards; see [PERSISTENCE-EVALUATION.md](PERSISTENCE-EVALUATION.md). That run was between two machines at one site, not over the public internet. Migration and key recovery still need work.
- **Trust and lifecycle:** no `.bso`/upstream organization proofs, withdrawal/revocation, key rotation, signed lineage, mirror records or scan attestations. A trusted key must come from outside the untrusted feed. CID-pinned reads ignore subsequent withdrawal/deletion status.
- **Discovery guarantees:** RPC-provided pages can omit/replay records. Scans detect observed conflicts, not completeness, freshness or global uniqueness. Limits are 32 pages/1,024 candidates; larger profiles require a pinned CID. Concurrent publication is not globally serialized.
- **Distribution and packaging:** publishers must host/pin manifests and seed/upload weights separately. No background seeder, automatic manifest pinning, installer bundling Node/native dependencies, or Linux/Windows installation evidence. Large manifests, alternative IPFS layouts, native redirect chains, production scale and power-loss durability remain untested.
- **Product:** no read-only release web client, catalogue/search, hubs or desktop client. The broader endpoint gaps remain: non-SDK consumers/inference, private/gated models and streaming verified pieces.

Work is local to the existing prototype worktree. No Git push, deployment or public test publication is part of this milestone.
