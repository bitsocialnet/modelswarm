# Manifest and CLI milestone — 2026-11-13

**The prototype milestone is implemented:** installable `modelswarm make`, `verify` and `pull`, portable unsigned manifest v0, nested files, format policy, resumable v2/HTTP transfers and verified Hugging Face-compatible cache snapshots. This is ready for the local-endpoint milestone and further hardening, not a production release.

The subsequent [endpoint milestone](ENDPOINT-EVALUATION.md) implements `serve` and public upstream fallback; the results below remain the original manifest/CLI evaluation.

## Implemented

- `make DIR`: enumerate regular files without following source symlinks; inspect formats; calculate SHA-256 and v2 roots; embed one complete torrent per nonempty file; write a deterministic, versioned JSON manifest without replacing existing output.
- `verify MANIFEST DIR`: validate manifest/torrent consistency, recompute local sizes, SHA-256 and pieces roots, inspect formats and report every mismatched/missing selected file. It can read HF snapshot links and never executes code.
- `pull MANIFEST`: validate before network/cache writes; use explicit peers and/or DHT plus HTTP; reject bad pieces; check complete-file hashes/formats; preserve partial data/checkpoints; expose only verified files through the cache. Known code/pickle suffixes remain flagged even if metadata claims otherwise.
- Selection via repeatable `--file`; flagged files excluded by default, explicit `--allow-unsafe`; finite bounded timeouts and rate limits; progress JSON on stderr and result JSON on stdout.
- Private staging, per-manifest process locks, validated cache reuse, content-addressed blobs and immutable revision snapshots. The default separate Modelswarm cache does not alter upstream `refs/main`.

## Evidence

Tested on macOS arm64, Python 3.11.15, libtorrent package 2.1.1 (native `2.1.1.0`) and huggingface_hub 2.4.0.

The CLI suite has **45 passing tests** (27.733 seconds): 12 subprocess workflows, 10 manifest tests, 7 format tests and 16 cache tests. Run it with:

```sh
cli/.venv/bin/python -m unittest discover -s cli/tests -v
```

The subprocess workflows cover deterministic make/verify; nested safetensors/GGUF/config/text/empty files; non-overwrite behavior; HTTP-only, peer-only and mixed-source pulls; corrupt HTTP fallback; flagged-file exclusion and later inclusion; SDK offline cache lookup; metadata digest rejection; misleading formats; path traversal/symlink rejection; unavailable-source timeout; non-finite timeout rejection; Ctrl-C checkpoint recovery; SIGKILL after a periodic checkpoint; and repair of a modified checkpointed piece. The cache tests include foreign data preservation, corrupted blobs, safe-subset extension, revision-prefix conflicts and concurrent blob publication.

The actual installed command also processed Qwen's **491,400,032-byte** `qwen2.5-0.5b-instruct-q4_k_m.gguf`, at upstream revision `9217f5db79a29953eb74d5343926648285ec7e67`:

1. `make` produced manifest SHA-256 `ed19ee7d15599a97a629a96d5d950bad70145b4d4afec0937c8a2a12a8e5065f`.
2. `verify` matched the source, including upstream file SHA-256 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db` and its v2 root.
3. `pull --no-discovery` downloaded from the pinned Hugging Face HTTPS URL into an empty cache and published a verified snapshot. The first unrestricted run's transfer loop completed in 9.359 seconds.
4. A second empty-cache run with `--rate-limit 33554432 --checkpoint-interval 2` completed in 33.426 seconds, exercising 15 flushed periodic checkpoints and continued HTTPS transfers. These settings deliberately slow the transfer; this is not a throughput comparison.
5. The CLI's `verify` independently checked the final snapshot. Offline Hugging Face SDK snapshot/file lookup found the same snapshot and exact GGUF file; an independent SHA-256 calculation matched all 491,400,032 bytes. No model inference or remote code was executed.

The real commands and artifacts are reproducible from [README.md](README.md); this worktree retains raw evidence under `cli/artifacts/real-model/`. [evaluation-results.json](evaluation-results.json) records the source identifiers and measured results without local paths. The earlier isolated engine prototype remains unchanged, with its own [evaluation](../prototypes/download-engine/EVALUATION.md).

Repository lint, TypeScript, production build, advisory Knip, workflow validation and all 29 workflow tests pass. Independent code review has no remaining actionable findings. Root docs and landing-page status copy reflect the completed prototype; no visual layout work or browser verification was performed. The checkpoint, recheck and finite-timeout regressions provide the prevention selected by the repository's retrospective check.

## Corrections and important limits

- **Unsaved bytes can disappear on a process kill.** The initial SIGKILL-without-checkpoint test failed: at one verified MiB, libtorrent still had no payload file on disk. Periodic pause/flush/save/resume was added. Recovery is proven after a completed checkpoint; newer buffered work may be downloaded again. This is not a power-loss guarantee.
- **Recheck ordering matters.** libtorrent ignores `force_recheck()` during initial resume-data checking. The CLI now waits until that state finishes, requests a recheck of existing staged bytes, waits for completion, then enables sources. A regression modifies a checkpointed piece and verifies successful repair.
- **Timeouts must be finite.** Review caught NaN/infinity bypassing the timeout comparison. Input validation and subprocess tests now reject these values before cache creation.
- **Native payload counters reset after pause/resume.** Progress reports explicitly name `payload_bytes_since_resume`; they must not be summed or read as whole-command traffic. Resume bandwidth assertions use a fresh process with no intermediate checkpoint. Verified-piece counts, final size and hashes establish completion.
- **Safe publication has a defined boundary.** A new snapshot appears atomically. Extending an existing safe subset adds verified file links individually after all selected inputs verify, so readers can temporarily see a verified subset. Local cache ownership is assumed; this is not a multi-user adversarial filesystem service.
- **Native deprecation warnings remain.** The pinned binding supports the current file-storage APIs but marks some deprecated. Packaging and binding upgrades need separate validation.

## Still missing

- Publisher signatures, key/name proofs, release publishing, withdrawal and mirror attestations. The local manifest is trusted input; optional digest pinning provides integrity, not author authentication.
- `serve`/`HF_ENDPOINT`, automatic Hugging Face fallback for models without manifests, upstream name/revision resolution and gated/private-model authentication.
- Public hubs, search/indexing, hosted profiles, desktop UX and persistent seeding/ratio controls.
- Windows/Linux installers, WAN/NAT/discovery tests, many concurrent downloads, production-scale shard counts, multi-GiB real-model CLI tests, disk-full recovery and power-loss tests. Several files are supported as independent torrents; a shared multi-file torrent is not implemented.
- Full GGUF parsing, malware scanning, exhaustive format support and inference validation in Transformers/llama.cpp. Unknown formats fail conservatively; the snapshot/path interface is the integration surface currently tested.
- Storage/performance tuning: staging is retained and verified cache publication can require roughly twice the payload disk space. Frequent checkpoint pauses interrupt connections; the default is 15 seconds, not the aggressive two-second experiment.

No commit, push, package publication or deployment was performed. The canonical checkout remains untouched; all work is in the existing download-engine worktree.
