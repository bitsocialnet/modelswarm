# Local Hugging Face endpoint evaluation — 2026-11-13

**The requested SDK milestone works:** `modelswarm serve` provides `HF_ENDPOINT` downloads from registered local manifests and verified public Hugging Face fallback. It is ready for consumer-specific integration work; it is not complete Hub compatibility or a production service.

This records the original endpoint milestone. The subsequent [signed-release milestone](RELEASES-EVALUATION.md) added publisher authentication and `serve --release`; [restart and renewal testing](PERSISTENCE-EVALUATION.md) followed. The results and limits below describe the endpoint at the time of its evaluation.

## Implemented and tested

- Loopback server with model information, recursive/shallow file trees, lightweight HEAD metadata, pinned-revision redirects and verified GET/range responses.
- Registered manifests own their names. Unknown local revisions/files fail explicitly; only unregistered names use upstream fallback.
- Local files reuse the native peer/HTTP engine, checkpoints, format checks and verified cache. The endpoint shares transfer logic with `pull` without installing signal handlers in request threads.
- Public fallback resolves a commit and checks complete files against LFS SHA-256 or Git blob SHA-1 plus byte count before publication/serving. It strips client credentials by constructing its own outbound requests, validates redirect addresses, and uses bounded network operations with cancellation.
- Conservative format filtering, separated upstream blobs, reverified cache reuse, at most 16 HTTP connections, serialized file acquisition, and shutdown that closes persistent sockets before joining workers.

Environment: macOS 27.0.1 arm64, Python 3.11.15, libtorrent 2.1.1 (native 2.1.1.0), `huggingface_hub` 2.4.0. No new dependencies were needed.

The complete suite passed **65 tests in 38.487 seconds**: the previous 45 CLI/manifest/format/cache tests, 14 upstream tests and 6 endpoint E2E tests. The endpoint tests launch the actual CLI and use new SDK processes with `HF_ENDPOINT` set before import, fresh caches and default Xet behavior. They exercise `model_info`, `list_repo_tree`, `snapshot_download` and `hf_hub_download`.

Coverage includes nested/empty/selected files, metadata without downloading payloads, pinned aliases, explicit/suffix ranges and 416, cache reuse across local endpoint restarts, code exclusion/opt-in, local-miss ownership, corrupt bytes never receiving a successful file response, upstream Git/LFS verification, credentials not being forwarded, forged metadata and changed commits, unsafe redirects, corrupted cache preservation, total timeouts, cancellation, cross-site browser rejection and shutdown with a held keep-alive connection.

```sh
cli/.venv/bin/python -m unittest discover -s cli/tests -v
```

## Real SDK downloads

Both scenarios used the public Apache-2.0 Qwen file `qwen2.5-0.5b-instruct-q4_k_m.gguf`, **491,400,032 bytes**, upstream revision `9217f5db79a29953eb74d5343926648285ec7e67`. An independent client-side SHA-256 calculation matched `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db` after each SDK download.

| Scenario | Result |
|---|---|
| Registered local manifest, previously verified server cache, empty SDK cache | PASS; model info, HEAD alias redirect, pinned GET and final digest; 2.809 seconds |
| No local manifests, empty server and SDK caches, public Hugging Face HTTPS | PASS; model info/tree, filtered snapshot of README and `.gitattributes`, then full GGUF; 10.084 seconds |

The local snapshot revision was `ed19ee7d15599a97a629a96d5d950bad70145b4d`, derived from the manifest. The upstream scenario retained the actual upstream commit. Server logs confirm all requested file bytes were served by the local endpoint. Git metadata files exercised Git blob hashing; the model exercised LFS SHA-256. Client timeout was explicitly raised to 600 seconds. Times include SDK work and the final client hash; warm-local and cold-upstream cases are not comparative performance benchmarks. No model inference or remote code was executed.

Reproduction setup is in [ENDPOINT.md](ENDPOINT.md). Register the manifest produced by the [CLI real-model experiment](EVALUATION.md) for the local case; omit `--manifest` and request the pinned upstream revision for fallback. [endpoint-evaluation-results.json](endpoint-evaluation-results.json) retains source IDs, measured results and request traces without local paths. Raw local evidence is under `cli/artifacts/endpoint-real/` and `cli/artifacts/endpoint-tests.log`.

Repository lint, TypeScript, production build, advisory Knip, workflow validation and all 29 workflow tests pass. Workflow generation changed no outputs. Independent code-quality review found no remaining actionable issues. Root docs and landing-page status copy were updated; no browser layout change or browser session was part of this milestone.

## Corrections and limits

Review found that checking Origin alone misses cross-site browser resource GETs without that header; fetch-site validation and a regression now cover them. It also found that joining keep-alive handlers could delay shutdown; the server now shuts down active sockets and a regression holds a connection during SIGTERM. The repository retrospective selected these focused regressions as prevention; no new broad workflow rule was added.

- **Whole-file gating:** cold responses wait until verification completes. Increase `HF_HUB_DOWNLOAD_TIMEOUT` as documented, including time queued behind other downloads. Streaming already-verified pieces and cancelling shared work on a client disconnect remain future work.
- **Fallback is not swarm distribution:** fallback currently uses HTTPS and upstream whole-file hashes. It does not generate/share mirror records, use peers or resume an interrupted upstream download. Client range reads work once the whole file is verified; native checkpoint resume applies to local manifests.
- **Metadata persistence:** pinned upstream metadata is retained only in process memory. A server restart requires upstream availability even when payload blobs remain cached. This is not a complete offline upstream mirror.
- **Trust and identity:** local manifests remain unsigned and may shadow upstream names; use a separate SDK cache. Upstream fallback trusts Hugging Face's metadata. Publisher signatures, profile/name proofs, releases and mirror attestations remain unimplemented.
- **Compatibility:** SDK 2.4.0 is tested. Transformers, the `hf` CLI, llama.cpp and Ollama still need independent request/behavior tests; inference is untested. Datasets, Spaces, write/account/inference APIs, gated/private authentication and arbitrary Hub proxying are unsupported. The installed SDK also limits its ordinary HTTP download path to 50 GB per file.
- **Scale/platform:** single-process, trusted-local-user prototype; no public deployment. Windows/Linux packaging, WAN/NAT, production concurrency/shard counts, disk-full and power-loss tests remain. Local cache staging can roughly double storage, and the SDK maintains its own downloaded copy.
- **Formats:** header/content checks are conservative, not malware scanning or full GGUF parsing. Some legitimate binary tokenizer formats require explicit unsafe opt-in. Native binding deprecation warnings remain non-fatal on the pinned version.

The work is committed locally on the existing worktree branch. Nothing was pushed, published or deployed; the canonical checkout was not modified by this task.
