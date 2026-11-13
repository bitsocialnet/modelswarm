<img src="site/public/logo.svg" alt="Modelswarm logo" width="72" height="72">

# Modelswarm

**Modelswarm is an idea for a hub of open AI models that nobody owns.** The name means models distributed by a swarm of peers, as in a BitTorrent swarm, so no company has to host them. Publishers sign their releases from their own Bitsocial profile, and every piece of every file is checked against the signed release as it downloads. No company decides which models are listed, which stay available or what can be said about them.

> **Status: idea stage.** This repository reserves the name and collects the design. Nothing here is built; [roadmap.md](roadmap.md) tracks what comes next and what each step waits on. It fits [Phase 5 of the Bitsocial master plan](https://bitsocial.net/#master-plan-phase-5), the long tail of Bitsocial clients. Most of it needs only what Bitsocial and BitTorrent already ship, so the first milestones are not blocked by earlier phases.

## The Thesis

Hugging Face hosts over 3 million models, by Nvidia's count. On 2 September 2026 Nvidia [agreed to buy it for $12.9 billion](https://techcrunch.com/2026/09/03/nvidia-confirms-it-will-buy-hugging-face-for-12-9-billion/), a deal the US Department of Justice has since [asked questions about](https://www.reuters.com/world/us-doj-is-inquiring-about-nvidias-purchase-hugging-face-sources-say-2026-10-28/). Whoever owns it, one company holds the files, the list of what exists and the place where each model is discussed.

That company can remove a model, and others can make it do so:

- Hugging Face restricted access to [GPT-4chan](https://thegradient.pub/gpt-4chan-lessons/) in 2022.
- Meta's [DMCA notice of March 2023](https://github.com/github/dmca/blob/master/2023/03/2023-03-21-meta.md) had GitHub take down repositories for downloading the leaked LLaMA weights.

Torrents already solve the storage half. [Academic Torrents](https://academictorrents.com/) and [Pirate Face](https://pirateface.co/) publish models as magnet links, and a file with seeders cannot be deleted by any host. The list of magnets and the discussion around them still sit on one website each, and a magnet link says nothing about who published the file.

Modelswarm splits the hub into parts that no single party holds:

| | Hugging Face | A torrent index site | Modelswarm |
|---|---|---|---|
| Where the files are | Hugging Face's servers | Seeders | Seeders, plus any HTTP mirror, including Hugging Face |
| Who can delist a model | Hugging Face | The site's operator | Nobody across the network. A hub can drop a release from its own board, not from the publisher's profile |
| Who published this file | A Hugging Face account | Whoever submitted the magnet | A signing key, the same across every release by that publisher |
| When a corrupted or swapped file is caught | The host is trusted | After the download, against a checksum | During the download, piece by piece |
| Where discussion happens | Hugging Face | The site, or Reddit and Discord | Peer-to-peer communities, each with its own rules |
| Works with existing tools | Yes | Manual download | Yes, through a local endpoint that speaks the Hugging Face API |

## Checked While It Downloads

A checksum of a whole file can only be compared when the download is finished. For a 40 GB model that means finding out at the end.

Modelswarm releases carry what [BitTorrent v2](https://www.bittorrent.org/beps/bep_0052.html) calls a pieces root for each file: the root of a SHA-256 hash tree built over 16 KiB blocks of that file. The root is inside the signed release, so:

- every piece is verified when it arrives, and a bad one is thrown away and fetched again from another source;
- the check is the same whether the piece came from a torrent peer or an HTTP mirror, so Hugging Face or any other mirror can serve the bytes without being trusted;
- the same file always has the same root, in any torrent and any release, so identical files share seeders.

See [how-it-could-work.md](how-it-could-work.md#verification).

## Integrity Is Not Safety

A signature proves who published a file and that it arrived unchanged. It does not prove the file is harmless. Model files in pickle-based formats can run code when they are loaded, which is why Hugging Face [scans for them](https://huggingface.co/docs/hub/security-pickle). Modelswarm has no central scanner, so the defaults carry the weight:

- formats that hold tensors and metadata, such as [safetensors](https://huggingface.co/docs/safetensors/index) and GGUF, download normally;
- pickle-based files and repositories that ship code to execute are flagged and need an explicit confirmation;
- a hub can refuse them as a posting rule;
- scanners are replaceable services that publish signed results, the way indexers are replaceable.

See [how-it-could-work.md](how-it-could-work.md#safety).

## No Hub Holds Everything

A catalogue the size of Hugging Face cannot live in one Bitsocial community, and it does not have to. A release lives in its publisher's own profile, which holds only that publisher's models. Hubs are ordinary communities that curate: they carry crossposts of releases and the discussion about them. The catalogue is the sum of many small communities, and an indexer makes it searchable.

Models that exist only on Hugging Face need no listing at all to be downloaded: the client can read Hugging Face's own metadata. A record is published the first time someone seeds such a model, so the peer-to-peer index grows with what people actually use. See [how-it-could-work.md](how-it-could-work.md#models-that-are-only-on-hugging-face).

## What It Is Not

- **Not a host.** The project would publish a client and tooling. It would run no hub, no index and no seedbox that others depend on.
- **Not a tracker site.** There is no website whose removal takes the list of models with it.
- **Not a replacement for Hugging Face's compute.** No hosted inference, no Spaces.
- **Not a blockchain.** Releases and discussion are signed Bitsocial records; files are torrents. [Bitsocial Chain](https://chain.bitsocial.net) would only be used for `.bso` publisher names and tips.

## Prior Art

- [HuggingSocial](https://github.com/Rinse12/huggingsocial), by Bitsocial developer Rinse12, proposes the same combination of Bitsocial and BitTorrent, and is the source of the local Hugging Face endpoint idea used here. Modelswarm differs in where releases live (publisher profiles, not hubs), in verifying pieces instead of whole files, in its format defaults and in not mirroring Hugging Face in bulk.
- [Pirate Face](https://pirateface.co/) and [Academic Torrents](https://academictorrents.com/) index models as torrents on their own websites.

## Documents

- [how-it-could-work.md](how-it-could-work.md): publishers, releases, the manifest, verification, safety, hubs, downloading, the Hugging Face endpoint and search
- [open-questions.md](open-questions.md): design decisions not yet made
- [roadmap.md](roadmap.md): what is next and what each step waits on
- [site/](site/): the page for modelswarm.org, a React and Vite app on the stack of 5chan and WeTube. Run `corepack yarn install` and `corepack yarn start` from the repository root; `corepack yarn build` writes static files to `site/build/`

## License

[GPL-3.0-or-later](LICENSE) for this repository. Models keep whatever license their publisher gave them; see [open-questions.md](open-questions.md#licenses-and-takedowns).

## Ecosystem Context

- Bitsocial protocol docs: https://bitsocial.net
- Bitsocial Improvement Proposals: `bitsocialnet/BSIPs` and https://bsips.bitsocial.net
- Indexer: `bitsocialnet/bitsocial-indexer`
- Bitsocial Chain (names, payments): `bitsocialnet/bitsocial-chain` and https://chain.bitsocial.net
- Sibling idea-stage repos: [WeTube](https://github.com/bitsocialnet/wetube) (YouTube alternative), [Gitcommons](https://github.com/bitsocialnet/gitcommons) (GitHub alternative), [Infinipedia](https://github.com/bitsocialnet/infinipedia) (encyclopedia), [Hopium](https://github.com/bitsocialnet/hopium) (social trading)
