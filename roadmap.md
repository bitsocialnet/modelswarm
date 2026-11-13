# Roadmap

What is built, what is next, what each step waits on, and where each decision is written down. Update this file in the same change that finishes or reshapes an item.

Durations are rough estimates of focused work, not dates. Last reviewed 2026-11-13.

## Built

- [x] Idea docs: [README.md](README.md), [how-it-could-work.md](how-it-could-work.md), [open-questions.md](open-questions.md) (2026-11-13).

No code yet.

## What Blocks What

| Part | Depends on | State of the dependency (2026-11-13) |
|---|---|---|
| Making, verifying and pulling releases from a manifest | A BitTorrent v2 library with web seeds | Available outside Bitsocial. Which library is [open](open-questions.md#torrents) |
| The Hugging Face endpoint | The requests existing tools make | Public, and need to be recorded per tool. Nothing in Bitsocial blocks it |
| Publishing releases | Author communities ([BSIP-14](https://bsips.bitsocial.net/bsip-14)) on a node the publisher runs | Implemented in pkc-js. Publishers without a node wait for hosted profiles on a public RPC |
| Hubs | Communities ([BSIP-3](https://bsips.bitsocial.net/bsip-3)) and crossposts ([BSIP-12](https://bsips.bitsocial.net/bsip-12)) | Implemented in pkc-js |
| Search | `bitsocial-indexer`, extended to parse manifests | The indexer exists; manifest parsing does not |
| Names, tips | `.bso` names ([BSIP-13](https://bsips.bitsocial.net/bsip-13)), Bitsocial Chain | Optional. Publishers work as bare keys until then |

The first three milestones need no Bitsocial data at all, and none of the six waits on an earlier phase of the master plan.

## Next

### 1. Measurements

Two numbers decide the design, so they come before any product code.

- [ ] **Community size.** Extend the seeded-board benchmark in `pkc-js-benchmarks` beyond its current 2,000 posts, to the sizes a busy publisher profile and a popular hub would reach. Record load time for a reader, and CPU, disk and memory for the operator. Answers [open-questions.md](open-questions.md#scale).
- [ ] **Piece verification over HTTP.** Take a multi-gigabyte model file, build a v2 torrent, and download it from an HTTP mirror while checking every piece against the pieces root. Record hashing cost and the time to detect a modified file. Answers part of [open-questions.md](open-questions.md#torrents).
- [ ] **A swarm with web seeds.** Seed the same torrent from one machine with Hugging Face as a web seed, and download from another with a candidate library.

Estimate: about 1 week. Blocked by: nothing.

### 2. Manifest and command line

- [ ] Manifest format v0, recorded here as a prototype convention until the BSIP.
- [ ] `modelswarm make`: hash files, build the torrent, write the manifest.
- [ ] `modelswarm verify`: check files on disk against a manifest.
- [ ] `modelswarm pull` from a manifest file: download from torrent peers and HTTP mirrors together, verify each piece, place files in the cache layout that `transformers` and llama.cpp read.
- [ ] Format detection, and the flagged-format rule from [how-it-could-work.md](how-it-could-work.md#safety).

Estimate: 2 to 3 weeks. Blocked by: the library choice from milestone 1.

### 3. The Hugging Face endpoint

- [ ] Record the requests made by `huggingface_hub`, `transformers`, the `hf` command, llama.cpp and Ollama.
- [ ] `modelswarm serve`: answer them from local manifests.
- [ ] Pass-through for models with no manifest: fetch from Hugging Face, verify whole files against its metadata.
- [ ] Tests that run each real tool against the endpoint.

Estimate: about 2 weeks. Blocked by: milestone 2.

After this milestone the tool is useful to one person with no network of publishers: verified downloads, resumable from several sources.

### 4. Publishing and reading releases

- [ ] `modelswarm publish`: post a release to the publisher's profile on a node they run.
- [ ] `pull` and the endpoint resolve releases from profiles.
- [ ] Mirror records v0: publish one when seeding a Hugging Face model, and check records on completed downloads.
- [ ] A demo publisher profile on a Bitsocial node we run, with real releases of permissively licensed models, the way WeTube's demo channel works.
- [ ] Web client, read-only: publisher pages, release pages with the model card, file list, format flags and sources. On the stack of 5chan and WeTube.

Estimate: 3 to 4 weeks. Blocked by: the name question in [open-questions.md](open-questions.md#names-and-impersonation) needs a prototype answer.

### 5. Hubs and search

- [ ] Crosspost a release into a hub; replies and votes in the web client.
- [ ] Hub lists in the client settings.
- [ ] Manifest parsing in `bitsocial-indexer`, with filters for base model, format, quantization, license and size.
- [ ] Search in the client across several indexers.

Estimate: 2 to 3 weeks. Blocked by: milestone 4.

### 6. Desktop client

- [ ] Desktop build with a Bitsocial node and a torrent engine.
- [ ] Transfers dashboard, seeding by default with a ratio cap.
- [ ] The local endpoint running inside the app.

Estimate: 3 to 4 weeks. Blocked by: milestones 3 and 5.

## BSIPs

All existing BSIPs are drafts. Modelswarm builds on BSIP-2, 3, 10, 12, 13, 14 and 15, and would add:

| BSIP | Category | Requires | Written when |
|---|---|---|---|
| Model releases: the manifest, file hashes, sources, the `base` link and withdrawal | Application | 2, 14 | After milestone 4, once real publishing has tested the format |
| Mirror records and confirmations | Application | Model releases | After milestone 4 |
| Scan results | Application | Model releases | When a second scanner exists |

## Later

- [ ] Scanner services and the scan result record.
- [ ] Datasets.
- [ ] `.bso` names for publishers and tips on Bitsocial Chain.
- [ ] Hosted profiles for publishers without a node, when a public RPC offers them.
- [ ] Hub-funded seedboxes.
- [ ] Mobile clients for browsing and discussion.
