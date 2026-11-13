# Local Hugging Face endpoint

`modelswarm serve` exposes a read-only model-download API on `127.0.0.1`. It serves explicitly registered local manifests and, by default, fetches public unregistered models from Hugging Face. Every GET waits for complete-file verification before returning model bytes. This is an experimental SDK-compatible subset, not a replacement for the whole Hub API.

## Start and use it

```sh
cli/.venv/bin/modelswarm serve \
  --manifest ./release.json \
  --cache-dir ./modelswarm-cache \
  --port 8866
```

Omit `--manifest` to use only upstream fallback, or repeat it for different model names. `--no-upstream` restricts the server to registered manifests. `--no-discovery` disables DHT for local-manifest transfers; `--peer`, `--rate-limit` and `--checkpoint-interval` have the same meaning as in `pull`. `--timeout` bounds each file transfer/upstream operation. Port zero selects an available port; the first stdout JSON event reports the actual `endpoint`. SIGINT/SIGTERM stop the server.

In another shell, set these variables **before importing the SDK**:

```sh
export HF_ENDPOINT=http://127.0.0.1:8866
export HF_HUB_DOWNLOAD_TIMEOUT=600
export HF_HUB_ETAG_TIMEOUT=30
# Keep the SDK cache separate from upstream's normal namespace.
export HF_HUB_CACHE="$PWD/sdk-cache"
cli/.venv/bin/python - <<'PY'
from huggingface_hub import hf_hub_download, snapshot_download

file = hf_hub_download("example/model", "weights/model.gguf", token=False)
folder = snapshot_download("example/model", allow_patterns=["*.json", "*.safetensors"], token=False)
print(file, folder)
PY
```

The file names and model identifier must match the registered release or a public upstream model. Cold GETs can take longer than the SDK's default timeout because verification precedes the response; choose a client download timeout above the server's transfer timeout. HEAD and model/tree metadata do not download payloads. A client timeout does not currently cancel a shared transfer.

## Resolution, integrity and policy

- **Local manifests win for their entire name.** `main`, the manifest version and the first 40 hex characters of its SHA-256 resolve to the registered release. Missing local revisions/files never fall back upstream. One manifest per model name is supported; registration is frozen at startup. These are unsigned local declarations, not proof of upstream ownership.
- **Aliases resolve to immutable identifiers.** File HEAD/GET aliases redirect within the local endpoint to a pinned revision. Local revisions derive from the manifest; upstream revisions are full commit hashes. SDK caches should be separate from the normal Hugging Face cache because local names can shadow upstream names.
- **Local content uses the existing engine.** Peer/HTTP pieces are checked, then final sizes, SHA-256 and formats are verified before cache publication and serving. Cache reuse is reverified.
- **Fallback trusts Hugging Face metadata.** The server resolves the upstream revision, fetches pinned metadata, then verifies an LFS SHA-256 or the Git blob SHA-1 (`blob <size>\0<content>`) and byte count. It never treats an ordinary file SHA-1 as a Git blob ID. Fallback files use a separate private cache namespace and are rechecked on reuse. Pinned metadata is cached only in memory: after a server restart, upstream must be reachable to resolve even an already cached file. Interrupted fallback downloads restart from zero; only local-manifest transfers have the native piece/checkpoint resume mechanism. No publisher signature or peer transfer is available for these files yet.
- **Flagged formats remain opt-in.** Local listings exclude code, pickle and unknown formats by default. Upstream listings use a conservative filename allowlist, followed by content inspection before bytes are served. Direct requests for excluded files return 403. `--allow-unsafe` opts in globally for that server; it never executes content. Some legitimate tokenizer/binary formats remain classified as unknown.
- **Public models only.** Client Authorization/Cookie headers and ambient HF tokens are not forwarded. Private/gated authentication and Hub write APIs are unsupported. The listener accepts only loopback binding, validates Host, Origin and browser fetch-site headers, and does not enable CORS. It is for a trusted local user, not public deployment or hostile shared machines.

## Implemented HTTP surface

| Method and path | Behavior |
|---|---|
| `GET /health` | Readiness |
| `GET /api/models/{repo}` | Model info at `main` |
| `GET /api/models/{repo}/revision/{revision}` | Pinned commit and policy-filtered siblings |
| `GET /api/models/{repo}/tree/{revision}[/{directory}]` | Policy-filtered files/directories, recursive or shallow |
| `HEAD /{repo}/resolve/{revision}/{path}` | ETag, full size and pinned commit without payload download |
| `GET /{repo}/resolve/{revision}/{path}` | Verified bytes, full or single HTTP byte range |

Repo IDs can be a legacy single name or `owner/model`; local manifests require `owner/model`. Paths are decoded and validated before use. Byte ranges support explicit, open-ended and suffix forms; unsatisfiable/multiple ranges return 416. Error headers distinguish repository, revision and file misses. Responses deliberately omit upstream Xet headers so the SDK downloads through the verifier.

The [official SDK download reference](https://huggingface.co/docs/huggingface_hub/package_reference/file_download) describes the client calls and Git/LFS ETag convention; compatibility here is established by the installed 2.4.0 source and runtime tests.

The process accepts at most 16 active HTTP connections and serializes expensive transfers. It implements neither API pagination nor arbitrary proxy routes. Unsupported Hub APIs fail explicitly. Models are the only repository type.

## Evidence and remaining scope

See [ENDPOINT-EVALUATION.md](ENDPOINT-EVALUATION.md) for exact SDK/runtime results. The broader roadmap still includes consumer tests with Transformers, llama.cpp and Ollama; authenticated models; streaming already-verified pieces; public discovery and seeding controls; publisher signatures; multi-platform packaging; and production-scale performance/durability work. The endpoint does not implement inference.
