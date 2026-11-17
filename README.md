<img src="public/logo.svg" alt="ModelSwarm logo" width="72" height="72">

# ModelSwarm

**ModelSwarm is an idea for a hub of open-weight AI models that nobody owns.** The name means models distributed by a swarm of peers, as in a BitTorrent swarm, so no company has to host them. Publishers sign their releases from their own Bitsocial profile, and every piece of every file is checked against the signed release as it downloads. No company decides which models are listed, which stay available or what can be said about them.

> **Status: experimental CLI.** The landing page, [download-engine prototype](prototypes/download-engine/README.md), and [manifest/CLI milestone](cli/README.md) exist. `make`, `verify` and `pull` work with unsigned local manifests, v2 peers/HTTP, format checks, checkpoint recovery and verified cache snapshots. The [local Hugging Face endpoint](cli/ENDPOINT.md) serves these manifests and verified public upstream fallback, tested with the SDK. The [signed release prototype](cli/RELEASES.md) adds local keys, publisher profile setup, publishing, profile/CID pulls and endpoint registration, tested with an isolated real PKC node. Hosted defaults, public-network operation, search and desktop client remain; [roadmap.md](roadmap.md) tracks the remaining work. It fits [Phase 5 of the Bitsocial master plan](https://bitsocial.net/#master-plan-phase-5), the long tail of Bitsocial clients. Most of it needs only what Bitsocial and BitTorrent already ship, so the first milestones are not blocked by earlier phases.

> **Credit.** ModelSwarm builds on [HuggingSocial](https://github.com/Rinse12/huggingsocial) ([huggingsocial.co](https://huggingsocial.co/)), the original design by Bitsocial developer [Rinse12](https://github.com/Rinse12). Most of the architecture comes from it: Bitsocial for releases and discussion, BitTorrent and HTTP mirrors for the weights, signed manifests checked on the reader's machine, hubs, indexers, the command line and the local Hugging Face endpoint. ModelSwarm changes where releases live, how downloads are verified, how formats that can run code are handled and how models that are only on Hugging Face are covered; see [Prior Art](#prior-art).

## The Thesis

Hugging Face hosts over 3 million models, by Nvidia's count. On 2 September 2026 Nvidia [agreed to buy it for $12.9 billion](https://techcrunch.com/2026/09/03/nvidia-confirms-it-will-buy-hugging-face-for-12-9-billion/), a deal the US Department of Justice has since [asked questions about](https://www.reuters.com/world/us-doj-is-inquiring-about-nvidias-purchase-hugging-face-sources-say-2026-10-28/). Whoever owns it, one company holds the files, the list of what exists and the place where each model is discussed.

That company can remove a model, and others can make it do so:

- Hugging Face restricted access to [GPT-4chan](https://thegradient.pub/gpt-4chan-lessons/) in 2022.
- Meta's [DMCA notice of March 2023](https://github.com/github/dmca/blob/master/2023/03/2023-03-21-meta.md) had GitHub take down repositories for downloading the leaked LLaMA weights.

Torrents already solve the storage half. [Academic Torrents](https://academictorrents.com/) and [Pirate Face](https://pirateface.co/) publish models as magnet links, and a file with seeders cannot be deleted by any host. Each list is still run by one website, which also hosts the discussion, and a magnet link says nothing about who published the file. Pirate Face's CLI can keep a copy of its magnet index on the user's machine, so listed models stay reachable when the site is down; what gets listed is still Pirate Face's decision.

ModelSwarm splits the hub into parts that no single party holds:

| | Hugging Face | Pirate Face | ModelSwarm |
|---|---|---|---|
| Where the files are | Hugging Face's servers | Seeders, with Hugging Face as a web seed | Seeders, plus any HTTP mirror, including Hugging Face |
| Who can delist a model | Hugging Face | Pirate Face, which runs the list. A copy of its index synced earlier still finds the model | Nobody across the network. A hub can drop a release from its own board, not from the publisher's profile |
| Who published this file | A Hugging Face account | A Pirate Face handle, verified through the matching Hugging Face account | A signing key, the same across every release by that publisher |
| When a corrupted or swapped file is caught | The host is trusted | Each piece against the listed torrent's hashes during the download, then each whole file against Hugging Face's SHA-256 | During the download, piece by piece, against the release its publisher signed |
| Where discussion happens | Hugging Face | On Pirate Face | Peer-to-peer communities, each with its own rules |
| Works with existing tools | Yes | Yes, through its `pirateface` pip package for Python tools | Yes, through a local endpoint that speaks the Hugging Face API |

Pirate Face as described on [pirateface.co](https://pirateface.co/) and in its [CLI README](https://github.com/pirateface/pirateface_cli) on 17 November 2026.

## Checked While It Downloads

A checksum of a whole file can only be compared when the download is finished. For a 40 GB model that means finding out at the end.

ModelSwarm releases carry what [BitTorrent v2](https://www.bittorrent.org/beps/bep_0052.html) calls a pieces root for each file: the root of a SHA-256 hash tree built over 16 KiB blocks of that file. The root is inside the signed release, so:

- every piece is verified when it arrives, and a bad one is thrown away and fetched again from another source;
- the check is the same whether the piece came from a torrent peer or an HTTP mirror, so Hugging Face or any other mirror can serve the bytes without being trusted;
- the same file always has the same root, in any torrent and any release, so identical files share seeders.

See [how-it-could-work.md](how-it-could-work.md#verification).

## Integrity Is Not Safety

A signature proves who published a file and that it arrived unchanged. It does not prove the file is harmless. Model files in pickle-based formats can run code when they are loaded, which is why Hugging Face [scans for them](https://huggingface.co/docs/hub/security-pickle). ModelSwarm has no central scanner, so the defaults carry the weight:

- formats that hold tensors and metadata, such as [safetensors](https://huggingface.co/docs/safetensors/index) and GGUF, download normally;
- pickle-based files and repositories that ship code to execute are flagged and need an explicit confirmation;
- a hub can refuse them as a posting rule;
- scanners are replaceable services that publish signed results, the way indexers are replaceable.

See [how-it-could-work.md](how-it-could-work.md#safety).

## No Hub Holds Everything

A catalogue the size of Hugging Face cannot live in one Bitsocial community, and it does not have to. A release lives in its publisher's own profile, which holds only that publisher's models. Hubs are ordinary communities that curate: they carry crossposts of releases and the discussion about them. The catalogue is the sum of many small communities, and an indexer makes it searchable.

Models that exist only on Hugging Face need no listing at all to be downloaded: the client can read Hugging Face's own metadata. A record is published the first time someone seeds such a model, so the peer-to-peer index grows with what people actually use. See [how-it-could-work.md](how-it-could-work.md#models-that-are-only-on-hugging-face).

## Optional Forge RPC

The planned client would use Forge RPC by default for its Bitsocial connection. Forge RPC is optional: users can switch to another compatible provider or self-host a node, and publishers keep their own keys. ModelSwarm remains decentralized; model files travel over BitTorrent and HTTP mirrors, not through the RPC.

RPC revenue from ModelSwarm is speculative, not a strong monetization pitch. RPC hosts release metadata and discussion, not the model weights, so metadata hosting alone may offer little reason to pay. Publisher willingness to pay is unvalidated. Reliable weight seeding, managed distribution or enterprise support could be separate paid services, but they go beyond RPC and are not committed features. The repository keeps its GPL-3.0-or-later license.

## What It Is Not

- **Not a host.** The project would publish a client and tooling. It would run no hub, no index and no seedbox that others depend on.
- **Not a tracker site.** There is no website whose removal takes the list of models with it.
- **Not a replacement for Hugging Face's compute.** No hosted inference, no Spaces.
- **Not a blockchain.** Releases and discussion are signed Bitsocial records; files are torrents. [Bitsocial Chain](https://chain.bitsocial.net) would only be used for `.bso` publisher names and tips.

## Prior Art

- [HuggingSocial](https://github.com/Rinse12/huggingsocial), by Bitsocial developer Rinse12, is the design ModelSwarm builds on, and the source of most of its architecture (see [its DESIGN.md](https://github.com/Rinse12/huggingsocial/blob/master/DESIGN.md)). ModelSwarm differs in four ways: releases live in each publisher's own profile and hubs carry crossposts, so no hub can delist a release; every piece is verified during the download against a BitTorrent v2 pieces root, instead of whole files afterwards; formats that can run code are flagged and left out of default downloads; and mirror records are created when someone seeds a model, instead of mirroring Hugging Face in bulk.
- [Pirate Face](https://pirateface.co/) lists models as magnet links with Hugging Face web seeds, checks files against Hugging Face's SHA-256 and offers a `pip` package and [CLI](https://github.com/pirateface/pirateface_cli) that download, seed and build torrents without changes to existing Python code. The CLI can keep a local copy of the magnet index for when the site is down, and can submit a model that was never on Hugging Face. Pirate Face still decides what is listed, verifies creators through their Hugging Face accounts and hosts discussion on its own website. [Academic Torrents](https://academictorrents.com/) indexes models as torrents on its own website.
- [Tensorseed](https://tensorseed.dev/) mirrors Hugging Face models and datasets over BitTorrent v2 with HTTP and S3 mirrors, and checks every file against a signed catalog anchored on the Chia blockchain. Clients pin the key of the catalog's publisher, and the project serves its own catalog (nine entries in November 2026). In ModelSwarm each publisher signs their own releases from their own profile, and no blockchain is involved.
- [Hippius Hub](https://hippius.com/hippius-hub) is a registry for models and containers with a drop-in replacement for `huggingface_hub`. Files are split across independent storage miners on a Bittensor subnet; accounts, namespaces and the search index are run by Hippius.
- [Radicle](https://radicle.xyz/) is peer-to-peer Git in which repositories are signed by their maintainers' keys and no company holds the list. Radworks [said in November 2026](https://x.com/radworks_/status/2122279596402061811) that model weight distribution over Radicle is being worked on; nothing had shipped at the time.

## Documents

- [how-it-could-work.md](how-it-could-work.md): publishers, releases, the manifest, verification, safety, hubs, downloading, the Hugging Face endpoint and search
- [open-questions.md](open-questions.md): design decisions not yet made
- [roadmap.md](roadmap.md): what is next and what each step waits on
- [src/](src/): the page for modelswarm.org, a React and Vite app on the stack of 5chan and WeTube. The app, Vite config, Node tooling and tests use strict TypeScript; `corepack yarn type-check` checks both the app and scripts. Use Node 22.18+ (22.x) or 24+. Run `corepack yarn install`, then `corepack yarn start` to open it at `https://modelswarm.localhost`; `corepack yarn build` writes static files to `build/`, and Vercel deploys every push to `master`

## License

[GPL-3.0-or-later](LICENSE) for this repository. Models keep whatever license their publisher gave them; see [open-questions.md](open-questions.md#licenses-and-takedowns).

## Ecosystem Context

- Bitsocial protocol docs: https://bitsocial.net
- Bitsocial Improvement Proposals: `bitsocialnet/BSIPs` and https://bsips.bitsocial.net
- Indexer: `bitsocialnet/bitsocial-indexer`
- Bitsocial Chain (names, payments): `bitsocialnet/bitsocial-chain` and https://chain.bitsocial.net
- Sibling idea-stage repos: [WeTube](https://github.com/bitsocialnet/wetube) (YouTube alternative), [GitCommons](https://github.com/bitsocialnet/gitcommons) (GitHub alternative), [Infinipedia](https://github.com/bitsocialnet/infinipedia) (encyclopedia), [Hopium](https://github.com/bitsocialnet/hopium) (social trading)
