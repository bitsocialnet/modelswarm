# Download engine prototype

An isolated experiment with **libtorrent 2.1.1** (the native binding reports `2.1.1.0`), Python 3.11, BitTorrent **v2-only** torrents and BEP 19 HTTP web seeds. This is not the ModelSwarm CLI or a publisher-signature implementation. It handles one regular file per torrent, including libtorrent's virtual tail padding.

See [EVALUATION.md](EVALUATION.md) for measured results, failures found during development and the viability decision.

## Reproduce

From the repository root, with `uv` installed:

```sh
uv venv --python 3.11 prototypes/download-engine/.venv
uv pip install --python prototypes/download-engine/.venv/bin/python --only-binary :all: -r prototypes/download-engine/requirements.txt
prototypes/download-engine/.venv/bin/python -m unittest discover -s prototypes/download-engine -p 'test_*.py' -v
prototypes/download-engine/.venv/bin/python prototypes/download-engine/experiment.py --output prototypes/download-engine/artifacts/local --size-mib 128
```

For a synthetic file above 2 GiB, run the transport subset with `--size-mib 2049 --transport-only` and a new output directory. This checks file-size handling without repeating the slower fault and checkpoint scenarios.

Each run requires a new output directory; it never reuses old payloads or checkpoints. The harness writes JSON results, JSONL worker events, request logs, torrent metadata and data files beneath that directory. `.venv/`, `artifacts/` and bytecode are ignored by Git. Allow roughly eight times the input file size in disk space for a complete run. The fixture and seeds bind to loopback; DHT, LSD, PEX, trackers, UPnP and NAT-PMP are disabled. Every worker has a timeout and is stopped on failure. The harness closes its HTTP and peer sessions.

The experiments cover:

- Peers alone, HTTP alone, and both sources supplying data.
- An HTTP server that changes a byte, then recovery from a healthy peer.
- A deliberately malicious peer that skips sender-side checking and sends a changed byte, then recovery from healthy HTTP. Receiver checks are always enabled.
- A partial download paused after verified pieces, a disk-complete checkpoint, SIGKILL, and recovery in a new process. Assertions require retained pieces, less than a full download, and no HTTP re-request of completed pieces.
- An optional real HTTPS web seed. All completed files are checked against an independently computed whole-file SHA-256.

## Pinned real-model fixture

The tested public Apache-2.0 fixture is Qwen's `qwen2.5-0.5b-instruct-q4_k_m.gguf` at revision `9217f5db79a29953eb74d5343926648285ec7e67`. It is 491,400,032 bytes; upstream SHA-256 is `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`.

```sh
mkdir -p prototypes/download-engine/artifacts/hf-source
curl --fail --location --retry 2 --output prototypes/download-engine/artifacts/hf-source/qwen2.5-0.5b-instruct-q4_k_m.gguf 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf'
shasum -a 256 prototypes/download-engine/artifacts/hf-source/qwen2.5-0.5b-instruct-q4_k_m.gguf
prototypes/download-engine/.venv/bin/python prototypes/download-engine/experiment.py --output prototypes/download-engine/artifacts/real-model --source prototypes/download-engine/artifacts/hf-source/qwen2.5-0.5b-instruct-q4_k_m.gguf --http-url 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf'
```

Compare the `shasum` result with the value above before running. The initial HTTP download establishes the local fixture; the optional final experiment independently downloads the full file through libtorrent from Hugging Face. No model is loaded or executed. The downloads require network access and approximately 983 MB of public model traffic, plus protocol overhead.

## Engine boundary

`engine.py make SOURCE TORRENT` hashes a file and prints its metadata. `engine.py download TORRENT DESTINATION --torrent-sha256 EXPECTED --peer 127.0.0.1:PORT` or `--http URL` starts an isolated download. `--external-http` permits non-loopback HTTP connections; peer endpoints remain loopback-only. The expected torrent SHA-256 must come from a trusted caller. Hashing a torrent yourself after downloading it does not authenticate its publisher. A future signed manifest must authenticate the file roots and release metadata.

Resume blobs are trusted local state, not accepted network records. Restore validates the torrent identity and overrides destinations, peers, trackers and web seeds. The prototype has not been hardened to process hostile filesystem paths, URL input or arbitrary metadata. Do not load untrusted resume files or run it as a public service.

The `.torrent` includes its piece layers. A magnet by itself is insufficient for this HTTP-only path when no peer can provide those hashes. Piece verification rejects bad data after a complete piece is received; the final whole-file SHA-256 is a second check. Unverified data may exist on disk during transfer; a future streaming endpoint must gate what it serves on verified-piece state.
