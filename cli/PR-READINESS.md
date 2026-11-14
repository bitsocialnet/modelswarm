# Experimental CLI PR scope — 2026-11-14

This branch is intended to merge the experimental download engine, manifest CLI, local Hugging Face SDK endpoint, signed publisher releases, and persistent-node validation. It does **not** complete the broader publishing/web-client milestone or claim production readiness.

## Review corrections

- Reject case/Unicode aliases in shared directory prefixes before cache writes. Previously, `Dir/a.txt` and `dir/b.txt` could share one directory on a case-insensitive filesystem, and a repeated pull rejected its own snapshot.
- Reject unsupported query-bearing payload URLs and invalid basenames for padded torrents during manifest validation. Previously, these could time out without requests or prevent valid alternate sources from being tried. Query-bearing HTTPS manifest references and supported piece-aligned aliases remain allowed.
- Reject a blocked explicit peer on signed `pull` before staging, with the peer and required opt-in in the error. Native IP filtering still applies to discovered peers and web seeds.
- Reject upstream metadata that marks a repository private or gated, including successful HTTP 200 responses, before caching it or downloading payloads.
- Reject explicitly empty CID/digest pins rather than silently performing unpinned discovery.
- Enforce and explain the pinned PKC RPC's 1 MiB IPFS manifest limit. Equivalent CIDv0/CIDv1 references work at the exact boundary; alternative IPFS file layouts remain unsupported. HTTPS retains the manifest format's 16 MiB limit.
- Check the complete encoded signed publication against PKC's 40,000-byte limit before sending it. A card smaller than the raw 24 KiB limit can exceed this after JSON escaping.

The fixes have focused regressions. Independent reviews covered the download/cache/endpoint and signed-release paths. Historical evaluation notes now distinguish their original results from later milestones, and the design doc includes profile restart recovery and same-minter renewal.

## PR feedback corrections

- Warm local and signed endpoint requests reuse a published snapshot directly. They validate snapshot ownership and structure and fully verify the requested file, without staging it again or reading unrelated payload bytes. Snapshot traversal errors fail closed. Cold acquisition retains the existing download/publication path.
- Native endpoint transfers accept timeouts above one hour while public upstream operations retain their existing one-hour cap. Signed `serve` rejects blocked explicit peers before starting, with the same opt-in diagnostic as `pull`.
- Manifest creation fails on source traversal errors instead of publishing an incomplete release. It excludes root VCS metadata and the root `.cache/huggingface/` bookkeeping subtree, so checkout state, SDK timestamps and partial downloads do not become release contents. Nested reserved paths and source symlinks remain rejected.
- Restart fixtures accept a healthy automatic restart after a slow boot, while retaining explicit held-lock recovery coverage. HTTP experiment reports wait for request handlers to finish before reading their events and include valid range requests cancelled during response headers.
- The original real-model evaluation now identifies its pinned source and reproducible commands precisely.
- Cache paths resolve explicitly selected parent aliases such as macOS `/tmp`, including `..` traversal after an alias, while rejecting symlinks at the cache root and in internal directories. Key generation resolves the chosen output directory and retains private permissions and exclusive, no-follow file creation.
- Valid safetensors headers can share short pickle or code signatures. Full structural validation now disambiguates those bytes while preserving risky filename rules and rejection of malformed data. Existing manifests that misclassified these files need regeneration; signed releases require a new version rather than a verification bypass.
- Endpoint cache contention returns `503 ReleaseBusy` with `Retry-After`. Other internal verification/configuration failures return a generic `502` with detailed diagnostics in the server log; malformed requests retain `400` responses. Lock I/O failures unrelated to contention preserve their original error type.
- An empty `MODELSWARM_CACHE` uses the default cache instead of writing into the working directory. Explicit cache-directory choices retain precedence.
- The landing page's endpoint description and comparison row now limit compatibility claims to the tested Hugging Face SDK; `transformers` and llama.cpp remain untested, matching the root docs.
- The hero describes peers sharing model hosting without claiming every downloader keeps seeding. The CLI uploads only while running; default background seeding remains planned for the desktop client.
- `make --http-base` accepts a host-only origin as well as the equivalent trailing-slash base. Raw malformed characters, credentials, queries and fragments remain rejected before output; per-file source validation is unchanged.

The review's upstream timeout/resume concern remains a documented prototype limitation: upstream operations have a total deadline, and interrupted upstream payloads restart from zero. Native registered-manifest transfers support checkpoint resume. Adding upstream resume or changing deadline semantics is outside this correction; see [ENDPOINT.md](ENDPOINT.md) and [ENDPOINT-EVALUATION.md](ENDPOINT-EVALUATION.md).

Native resume rechecking intentionally consumes the per-file native-session timeout. A large partial file or slow disk needs a budget covering both rechecking and remaining transfer; repeatedly choosing a shorter budget cannot make progress. A simulated 310-second recheck timed out and requested a checkpoint with a 300-second budget, while a 320-second budget reached source attachment and completion; cancellation also requested a checkpoint. This was a fake-clock/native-alert experiment, not a large-model performance measurement. The docs now distinguish this budget from checkpoint shutdown and synchronous file verification, which can extend wall time.

## Verification

Environment: macOS arm64, Python 3.11.15, libtorrent 2.1.1, Node 26.12.1, PKC SDK 0.0.142 and Kubo 0.43.1. Raw local logs and screenshots are retained under the ignored `cli/artifacts/pr-readiness/` and `cli/artifacts/pr-1-feedback/` directories. Bridge, build and packaging evidence below is reused from the submission pass. The later site correction changes prose only; it was checked against the root docs and with the formatter, reusing the prior browser coverage for unchanged rendering.

| Check | Result |
| --- | --- |
| Complete Python suite through the safetensors correction, with real private PKC/Kubo fixtures | 125 passed, no skips, 441.291 seconds |
| CLI, endpoint and upstream modules after final HTTP error correction | 48 passed, no skips, 44.665 seconds; a real held release lock produced 503 and the same GET succeeded after release |
| Cache suite after empty-environment correction | 23 passed, no skips; the fallback regression failed before the fix and explicit paths retained precedence |
| CLI and manifest modules after HTTP-base correction | 20 CLI tests and 15 manifest tests passed, no skips; host-only origins produce identical manifests to trailing-slash bases, and malformed raw URLs fail before output |
| Final affected cache, CLI, endpoint and release-input modules | 55 passed, no skips, 41.795 seconds, after the VCS metadata and path-alias follow-ups |
| Format, CLI, endpoint and upstream modules after safetensors correction | 54 passed, no skips, 43.529 seconds; CLI workflows use a colliding 896-byte header, and a real endpoint served all six collision cases successfully |
| Real Git source and path-alias smoke checks | Clone, linked worktree and metadata-free source produced identical manifests; HTTP pulls through `/tmp` via argument and environment, verification and real bridge key generation passed; key mode 0600 and no-overwrite confirmed |
| Prototype metadata and request-handler tests | 8 passed; delayed handler completion and header-failure regressions fail against their original implementations |
| Final synthetic 128 MiB experiment | Peer-only, HTTP-only, mixed, corrupt HTTP, corrupt peer and SIGKILL/resume passed; 32 pieces retained and 100,532,224 bytes transferred after restart |
| Documented real-model manifest command | Recreated the recorded manifest digest from the existing 491,400,032-byte source and verified it; no repeated public model download |
| Bridge protocol suite | 22 passed, no skips |
| `corepack yarn agent:verify` | Lint, TypeScript, production build and advisory Knip passed |
| Wheel build and isolated installation | Required bridge sources/lockfile included; no nested Node dependencies/tests; installed command passed help, make, HTTP pull and verify for three files |
| Production landing page in Chromium | Status/roadmap copy checked at 1440px and 375px; no horizontal overflow or console errors |
| Merge check | The original readiness check passed against `origin/master` at `f4b4904`. Before PR submission, the task-owned `.tmp/` ignore rule was moved to avoid an append conflict with a newer ignore rule on `master`; its behavior is unchanged. |

The complete 125-test suite covers all corrections through safetensors detection; later endpoint error mapping, cache-environment handling and HTTP-base handling use affected-module verification. Earlier failed regression runs are retained: they caught size/error handling, and one CIDv1 fixture incorrectly re-added the file with a different internal DAG. That fixture now converts the original CID. The added feedback regressions reproduce silent source-tree omissions, warm-request over-reading, false restart assumptions, incomplete request logs, alias traversal errors and format signature collisions. The first path-alias smoke run supplied a lexical root to the test HTTP server, whose resolved-path check returned 404; resolving only that fixture's source root fixed the harness while preserving `/tmp` paths for the CLI checks. No failed check remains unresolved. Existing native binding deprecation warnings remain non-fatal.

The independent review of the feedback corrections found no remaining actionable findings. The repository retrospective selected these focused regressions as prevention; no additional workflow rules were needed. Test fixtures and experiment processes exited. The earlier temporary wheel environment, task browser session and HTTP server were cleaned up.

## Remaining scope

The existing [roadmap](../roadmap.md) remains authoritative. Public-internet/NAT/DHT operation, Linux/Windows installation, other consumer applications, profile migration/revocation, write-interruption/disk-full/power-loss recovery, hosted onboarding, mirror records, a public demo and the read-only web client remain unverified or unimplemented as documented in the linked evaluations.

The prior cross-machine test used two Macs at one site over a private swarm and Tailscale; this readiness pass does not extend that evidence. The repository currently has a PR review workflow but no automated CLI test workflow, so the local suite results are not a claim of GitHub CI coverage.

This evaluation records the local readiness passes before submission and after PR feedback. Merging to `master` publishes the landing-page updates through Vercel.
