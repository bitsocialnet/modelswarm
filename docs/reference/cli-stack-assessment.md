# ModelSwarm CLI stack assessment

Assessment date: 2026-11-14.

Python with libtorrent is a reasonable stack for the working prototype. Keep that implementation while evaluating distribution and integration costs before choosing the production CLI and desktop architecture. The existing experiments establish engine feasibility; they do not establish that Python is the best production language or that another language would improve download speed.

## Current architecture

| Layer | Technology | Responsibility |
| --- | --- | --- |
| CLI and application logic | Python 3.11+ | Commands, manifests, validation, cache, local HTTP endpoint and ordinary Hugging Face fallback |
| Torrent engine | C++ libtorrent 2.1.1 through Python bindings | BitTorrent v2 transfers, HTTP web seeds, piece verification and resume |
| Publisher integration | Node.js with the PKC SDK | Profiles, signing, release discovery and verification |

The [package definition](../../cli/pyproject.toml) installs the `modelswarm` command. Users do not need to invoke individual `.py` files. Both languages have established CLI tooling: Hugging Face's [`hf` CLI](https://huggingface.co/docs/huggingface_hub/en/guides/cli) comes from a Python package, while [oclif](https://oclif.io/docs/introduction/) generates TypeScript CLIs for Node.js. The command-line interface alone does not determine the language.

The [engine adapter](../../cli/src/modelswarm/engine.py) delegates torrent transfers to native libtorrent. Its [Python bindings](https://libtorrent.org/python_binding.html) provide direct access to that library; Python is not implementing the BitTorrent transport. The [engine evaluation](../../prototypes/download-engine/EVALUATION.md) records v2-only peer and HTTP transfers, mixed sources, corrupted-source recovery and saved-checkpoint recovery after SIGKILL. These results support the provisional engine choice, without constituting a comparison against other stacks or a power-loss guarantee.

## Python and TypeScript tradeoffs

Python provided a practical route to the existing libtorrent bindings and the first CLI. It also fits the Python model-tooling ecosystem. Retaining it preserves the tested transfer, cache and validation behavior, and avoids a rewrite whose benefit has not been measured.

TypeScript is worth evaluating for the main application logic because the landing page already uses it and the PKC SDK runs in Node.js. Direct SDK integration could simplify publishing and profile operations and allow shared code with future clients. It would still need a libtorrent binding, a separate engine process, or a replacement engine with equivalent verified behavior.

The current [publisher bridge](../../cli/src/modelswarm/releases.py) launches Node processes and exchanges JSON for control operations and manifests. Model payloads do not pass through that bridge. The [installation instructions](../../cli/RELEASES.md#install-the-optional-bridge) require separate Node dependencies, including native `better-sqlite3`; the Python wheel includes bridge sources and a lockfile, but does not bundle the Node runtime or dependencies. Local manifest commands and ordinary upstream fallback do not require the bridge. Installation has been tested on macOS arm64; Linux and Windows installation remain unverified.

That installation and maintenance burden is a stronger reason to reconsider the architecture than the `.py` extension. A TypeScript CLI that still launches a Python engine helper would continue to ship both runtimes. A native binding or helper would introduce its own build, distribution and lifecycle responsibilities. Rust or Go would also need suitable torrent and PKC integration; selecting a compiled language alone would not resolve those dependencies.

A JavaScript torrent library is not automatically an equivalent replacement. At the assessment date, WebTorrent's [BitTorrent v2 tracking issue](https://github.com/webtorrent/webtorrent/issues/1117) was open. Recheck current releases and test v2-only transfers before considering it; the issue status alone does not establish every supported feature. Preserve complete piece layers for HTTP-only startup and the existing integrity and recovery guarantees when evaluating any engine.

## Evidence for a future production choice

Before expanding the prototype into a distributed desktop product, compare the current stack with a small alternative implementation only where it could remove a concrete integration or installation cost:

1. **Installation and updates:** exercise clean macOS, Windows and Linux installs, including native dependencies and signed publisher commands. Compare a packaged Python implementation with any proposed TypeScript/native-engine combination from the user's installation experience.
2. **Engine and protocol behavior:** preserve v2-only torrents, peer/HTTP mixing, HTTP-only startup, corruption rejection, checkpoint recovery, signed release validation and verified cache publication. Reuse the existing [CLI](../../cli/EVALUATION.md) and [release](../../cli/RELEASES-EVALUATION.md) scenarios as acceptance criteria.
3. **Process ownership:** evaluate startup, cancellation, shutdown, errors and upgrades across the CLI, engine and PKC integration. Keep the engine interface explicit enough that CLI and desktop clients can reuse it.
4. **Measured resource costs:** compare representative model sizes, shard counts, memory, disk use and transfer performance. Distinguish language overhead from engine behavior, concurrency policy, network and storage limits.

Retain Python/libtorrent unless an alternative demonstrates a meaningful improvement against these requirements. TypeScript remains a candidate for the product's main application logic; the production language, engine interface and desktop packaging are still open decisions. Cross-platform installation evidence would inform that choice without establishing public-network reliability or production readiness by itself.
