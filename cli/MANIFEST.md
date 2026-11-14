# Unsigned manifest v0

This is a prototype convention for the CLI milestone, not a BSIP or the future signed publisher record. `manifest.py` implements validation; `make` emits canonical UTF-8 JSON with sorted keys, compact separators and a trailing newline. A manifest's identity/digest is the SHA-256 of its exact bytes. `load_manifest` accepts other JSON whitespace but rejects duplicate keys and non-finite numbers.

The complete top-level object has exactly these fields:

```json
{
  "schema": "modelswarm/manifest/v0",
  "name": "example/model",
  "version": "v1",
  "license": "apache-2.0",
  "files": [
    {
      "path": "weights/model.gguf",
      "size": 123456789,
      "sha256": "<64 lowercase hex characters>",
      "pieces_root": "<64 lowercase hex characters>",
      "format": "gguf",
      "torrent": {
        "infohash_v2": "<64 lowercase hex characters>",
        "metadata": "<base64 complete canonical v2-only .torrent>"
      },
      "sources": [
        {"type": "http", "url": "https://mirror.example.org/weights/model.gguf"}
      ]
    }
  ]
}
```

The placeholder example is illustrative, not a valid downloadable manifest. Every nonempty file has its own torrent, named by the basename of `path`. This permits separate source directories, selective downloads and staging without exposing arbitrary torrent paths. A release can contain nested paths and several shards; this is not one multi-file torrent spanning the entire release.

`name` must be a bounded `owner/model` identifier; it is only a cache namespace. `version` is a bounded label, not an upstream revision resolver. `license` is a nonempty label. These fields are mandatory. `format` is one of `gguf`, `safetensors`, `json`, `text`, `code`, `pickle`, or `unknown`.

An empty file is represented with `size: 0`, the SHA-256 of the empty byte string, `pieces_root: null`, `torrent: null`, and `sources: []`. libtorrent cannot create a zero-length torrent; the CLI creates and verifies that empty file locally.

## Validation invariants

- A file path is relative POSIX syntax with no empty/dot/dot-dot components, backslashes, control characters, reserved Windows names, reserved VCS/cache/padding paths, trailing dots/spaces or file/directory conflicts. Case and Unicode-normalized collisions, including differently spelled shared directory prefixes, are rejected for portable snapshots.
- `size` is an integer, never a boolean. Digests are lowercase SHA-256 hex strings.
- Embedded torrent bencoding is canonical. Only `info` and `piece layers` are allowed outside `info`; sources, trackers, peers and DHT nodes cannot be hidden there.
- `info` contains exactly the v2 version, basename, piece length and single-file tree. Name, size and root must match the manifest. The computed infohash must match `infohash_v2`. Hybrid/v1 torrents and hidden extra files are rejected.
- The exact necessary piece layer must be present, and libtorrent authenticates it against the file root. Piece sizes are powers of two from 16 KiB to 16 MiB; `make` defaults to 1 MiB. Only libtorrent's expected virtual alignment pad is allowed.
- Each HTTP source is an HTTP(S) file URL without userinfo, query delimiters/parameters, fragments or control characters. The pinned native web-seed transport does not support query-bearing payload URLs. Loopback/private addresses are permitted for explicit local use; signed releases require `--allow-local-sources`. The decoded URL basename must match the file basename when libtorrent needs directory web-seed semantics for virtual padding; validation rejects mismatches before a bad source can prevent alternate sources from being tried. These payload restrictions do not apply to the separate HTTPS manifest reference, which supports query parameters.
- Unknown fields and schema versions fail closed. Future schema changes require an explicit version transition.

Limits: 16 MiB JSON, 4,096 files, 1 TiB per file, 4 TiB total declared size, 16 sources per file, 1,024-byte relative paths and at most 32 components. These are input bounds, not claims of tested capacity. Tiny pieces on a huge release can exceed the manifest limit; choose larger pieces or split releases.

## Integrity and safety

The chain is: trusted manifest bytes → validated v2 metadata/root → verified incoming pieces → final whole-file SHA-256 and format inspection → cache publication. Verification of a local directory also recomputes each nonempty file's pieces root.

`pull` omits flagged files by default, also checking risky filename suffixes independently of the declared format. Selected flagged files require explicit `--allow-unsafe`. No model or code file is executed. Unknown formats and malformed safe-format headers are flagged; parser safety and malware scanning are separate concerns.

Sources are untrusted byte suppliers. The unsigned manifest's author is not authenticated, and the library's parsed model format is not a safety verdict. The [signed release envelope](RELEASES.md) now authenticates the exact manifest digest and a model card through an explicit publisher key. Human-readable key proofs, withdrawal, lineage/base links, upstream mirror attestations and signed scan results remain for later milestones.
