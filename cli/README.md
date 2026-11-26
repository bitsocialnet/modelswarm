# ModelSwarm CLI prototype

`modelswarm make`, `verify` and `pull` implement the unsigned manifest/CLI milestone with Python 3.11+ and pinned libtorrent 2.1.1. `modelswarm serve` now exposes a [local Hugging Face endpoint with verified public fallback](ENDPOINT.md). The [signed publisher release milestone](RELEASES.md) adds `keygen`, `profile-init`, `profile-start`, `profile-renew`, `publish`, profile/CID pulls and signed endpoint registration. The landing page remains a separate static app. See [MANIFEST.md](MANIFEST.md) for v0 and [EVALUATION.md](EVALUATION.md) for tested behavior and remaining work.

## Install locally

From the repository root, with `uv` installed:

```sh
uv venv --python 3.11 cli/.venv
uv pip install --python cli/.venv/bin/python -e cli
cli/.venv/bin/modelswarm --help
```

This installs the `modelswarm` command only in the worktree's environment. Nothing is published to PyPI or installed globally. Source installation was tested on macOS arm64 and Linux x86-64. Other platforms remain unverified.

## Make, verify and pull

Put model files, configuration, tokenizer files and documentation in one directory. Nested paths are supported. The output manifest must be outside that directory and must not already exist.

`make` skips checkout metadata at the source root, including the `.git/`, `.hg/` and `.svn/` directories and the `.git` file used by Git worktrees. It also skips the root `.cache/huggingface/` directory that `hf download --local-dir` uses for local metadata and partial downloads. Other `.cache/` paths are included. If `make` encounters an error reading the source tree, it exits without writing a manifest.

```sh
cli/.venv/bin/modelswarm make ./model \
  --output ./release.json --name example/model --version v1 --license apache-2.0 \
  --http-base https://mirror.example.org/model/

cli/.venv/bin/modelswarm verify ./release.json ./model

cli/.venv/bin/modelswarm pull ./release.json \
  --manifest-sha256 DIGEST_PRINTED_BY_MAKE \
  --cache-dir ./model-cache
```

The example mirror must actually serve those files, including HTTP Range requests. `--http-base` can be repeated for multiple mirrors or omitted for peer-only distribution. File paths are appended to each base URL. With a pinned Hugging Face revision, the base is `https://huggingface.co/OWNER/REPO/resolve/COMMIT/`.

Payload source URLs cannot contain a query delimiter (`?`) or query parameters: the pinned native web-seed transport does not support them. For files with torrent padding, the decoded URL basename must match the model filename. Unsupported URLs are rejected during manifest validation. A signed release's separate HTTPS manifest URL can still use query parameters.

Each command prints one JSON result to stdout; progress events go to stderr. Errors return status 1; an interrupted pull that saves its progress returns 130. `verify` checks all listed files by default, including flagged ones, without executing them. A missing file, changed size/hash/root or detected format mismatch makes verification fail.

`make` builds one v2-only torrent per nonempty file and embeds complete metadata, including piece layers, into the JSON manifest. An empty file needs no torrent. The manifest is portable: neither relative `.torrent` paths nor online peers are needed to bootstrap an HTTP download.

### Select files and formats

```sh
cli/.venv/bin/modelswarm pull ./release.json --file weights/model.gguf
cli/.venv/bin/modelswarm verify ./release.json ./model --file weights/model.gguf
cli/.venv/bin/modelswarm pull ./release.json --allow-unsafe
```

Default pulls exclude code, pickle/ZIP-based model files and unknown formats. Known risky filename suffixes are excluded even if a manifest claims a safe format. `--file` is repeatable; explicitly selecting a flagged path requires `--allow-unsafe`. This flag permits downloading, never execution. The output lists any excluded paths as `skipped_flagged`. To verify a default snapshot containing only a safe subset, pass the same `--file` selection, or download the full release explicitly before verifying all files.

GGUF detection checks its header, not every tensor descriptor. Safetensors detection checks bounded header structure, dtype/shape and data offsets. JSON/text receive content checks. A misleading declaration is rejected before publication to the cache, although its bytes may already have been downloaded into staging. Formats that only hold data can still trigger bugs in consuming applications; a hash is not a safety verdict.

### Peers, discovery and recovery

```sh
cli/.venv/bin/modelswarm pull ./release.json --peer 192.0.2.10:6881
cli/.venv/bin/modelswarm pull ./release.json --no-discovery --timeout 120
```

By default libtorrent uses DHT discovery as well as manifest HTTP sources; `--peer` adds explicit endpoints and is repeatable. `--no-discovery` disables DHT, leaving explicit peers and HTTP. Tracker, LSD and PEX discovery are disabled in v0. Downloading can upload verified pieces to peers while the command runs; there is no persistent background seeder after it exits.

Pulls retain partial data privately in `<cache>/.modelswarm/`. Ctrl-C/SIGTERM and the per-file timeout request a flushed checkpoint. During active progress a checkpoint is also requested every 15 seconds; `--checkpoint-interval` changes this (minimum one second). Periodic checkpoints flush to disk while the transfer continues. Completion, interruption and timeout pause the transfer before the final save. `--rate-limit` sets bytes per second; zero means unlimited.

Rerun the same pull with the same cache to resume. Existing staged data is rechecked before network sources are enabled, so modified completed pieces can be repaired. A forced kill can lose bytes still buffered since the last checkpoint; recovery after a completed checkpoint is tested. Power-loss durability is not established. A malformed checkpoint is ignored and available file data is rechecked. A corrupt published cache blob is reported rather than silently overwritten.

The native-session `--timeout` defaults to 300 seconds and includes resume rechecking and periodic checkpoint work. For a large partial file or slow disk, raise it to allow both the recheck and the remaining transfer; repeatedly using a budget shorter than the recheck cannot make download progress. Checkpoint shutdown after the budget expires and synchronous file verification before or after the native session can extend total command time beyond this budget.

### Use the verified cache

The default root is `~/.cache/modelswarm/hub`, overridden by a nonempty `MODELSWARM_CACHE` or `--cache-dir`. An empty environment value uses the default; an explicit `--cache-dir` still takes precedence. This keeps ModelSwarm's declared model namespace separate from the normal Hugging Face cache. JSON output provides `cache_dir`, `revision` and `snapshot`:

```text
models--example--model/
  blobs/<whole-file-sha256>
  snapshots/<manifest-digest-prefix>/<relative-file-path>
```

The revision is the first 40 hex characters of the manifest's SHA-256, not a Hugging Face Git commit. A full-digest marker detects revision-prefix conflicts. There are no `refs/main` updates. Snapshot files are relative symlinks to verified blobs; only a successfully validated selection becomes visible. A new snapshot is published atomically. Extending an existing safe subset adds complete files atomically after the selected set verifies, but the extension is not transactional as a group.

```python
from huggingface_hub import snapshot_download

directory = snapshot_download(
    repo_id="example/model",
    revision="REVISION_FROM_PULL",
    cache_dir="CACHE_DIR_FROM_PULL",
    local_files_only=True,
)
```

Consumers can also use the returned snapshot directory directly; a GGUF consumer uses the file path inside it. Offline `snapshot_download` and `hf_hub_download` were tested with huggingface_hub 2.4.0. Transformers and llama.cpp inference were not executed. For online SDK downloads through `HF_ENDPOINT`, see [serve setup and limitations](ENDPOINT.md).

The selected cache root's parent path is resolved, so system aliases such as `/tmp` and `/var` can contain a cache. The cache root itself and its internal directories must be real directories; symlinks there, foreign snapshot entries and corrupt existing blobs are rejected. The cache assumes local directories are controlled by the current user, not concurrently writable by an attacker. Staging and cache publication may temporarily require roughly twice the payload size; staging is currently retained for recovery and reuse.

## Trust boundary

Manifests are **unsigned** in v0. A local manifest is trusted input; an independently obtained `--manifest-sha256` pins its exact bytes. A digest received from the same untrusted source does not establish publisher identity. Embedded torrent roots and final SHA-256 checks bind downloaded bytes to that manifest. The displayed owner/model and license are declarations, not independently verified claims. [Publisher release URIs](RELEASES.md) authenticate the manifest digest against an explicit signing key; they do not prove upstream organization ownership or model safety.

## Tests

```sh
uv pip install --python cli/.venv/bin/python -r cli/requirements-test.txt
cli/.venv/bin/python -m unittest discover -s cli/tests -v
```

Tests use local servers and explicit loopback peers with DHT disabled. They exercise the installed package in subprocesses, safe/flagged selection, nested files, metadata rejection, cache reuse, corrupted sources, checkpoint recovery and the real Hugging Face SDK with networking disabled. The separate real-model experiment in [EVALUATION.md](EVALUATION.md) uses a pinned public HTTPS model. Signed profile tests need the optional Node bridge and Kubo 0.43.1; see [release test setup](RELEASES.md#reproduce-the-tests). Without that Kubo version they explicitly skip.

See [PR scope and hardening](PR-READINESS.md) for the latest review corrections, verification and remaining milestone boundaries.
