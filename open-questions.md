# Open Questions

Design decisions not yet made. These need answers before ModelSwarm moves from idea to spec.

## Who Publishes First

The hardest question is not technical. Publishers already have their audience on Hugging Face, and its tools are the default everywhere.

- Why would a publisher sign releases here as well? Candidates: the release survives a takedown, their identity is a key they hold, and it costs one command next to their existing upload.
- Which publishers have had models removed or gated, and would they come first?
- Is the first useful version the one that needs no publishers at all: existing tools downloading Hugging Face models through the swarm with piece verification?
- Would projects that train models on decentralized networks, such as Bittensor subnets, publish here first? They already release open weights and have an audience used to peer-to-peer tools.
- Does a model author ever publish here, or is the network mostly mirror records by third parties? The design has to be useful in both cases.

## Scale

- How many posts does a Bitsocial community serve comfortably today? `pkc-js-benchmarks` measures seeded boards of 300 posts with about 16,000 comments and 2,000 posts with about 113,000 comments. Nothing larger is measured.
- How large does a busy publisher's profile get? A quantization group can publish thousands of releases.
- How large does a popular hub get, counting crossposts and replies, and what does that cost its operator?
- How many profiles can one indexer follow, and how fresh are its results?
- If a size limit shows up, is the answer sharding a profile, or a different record for releases than a comment?

## Manifest

The CLI implements [manifest v0](cli/MANIFEST.md): a separate portable JSON file, required name/version/license/files, one embedded v2 torrent per nonempty file, and explicit per-file HTTP sources. Nested files/shards work. The [release prototype](cli/RELEASES.md) authenticates its digest in native owner-signed PKC profile posts; manifests live separately at HTTPS/IPFS locations. This is a tested prototype convention, not a finalized BSIP. The following richer release semantics remain undecided.

- Is the manifest a field of the comment, or a separate document referenced by its content identifier? Which fields may a comment carry beyond those in BSIP-2?
- Which fields are required?
- How are very large repositories handled, with hundreds of shards?
- How are quantizations expressed: one release with many files, or one release per quantization linked by `base`?
- Is the model card the comment's text, a file in the torrent, or both?
- How does a publisher withdraw a release, and what does a client show for a withdrawn release whose files are still seeded?

## Torrents

The [download-engine prototype](prototypes/download-engine/EVALUATION.md) established libtorrent 2.1.1 as a viable candidate on macOS arm64. The [CLI](cli/EVALUATION.md) now implements releases containing several files using one embedded v2-only torrent per file, 1 MiB pieces by default (configurable), and complete piece layers for HTTP-only startup. Standalone manifests remain unsigned; profile releases now authenticate their exact digest. Cross-platform packaging, production-scale shard counts and WAN operation remain untested; this is a provisional engine choice.

- BitTorrent v2 only, or hybrid torrents that v1 clients can join? Hybrid torrents add padding files and a second set of hashes.
- Which piece size, given that the piece layer has to be fetched before the first piece can be checked?
- One torrent per release, or one per file? Per-file torrents let a reader fetch a single quantization without the rest; a v2 client can also select files inside one torrent.
- Which torrent library for the desktop client and the command line, and does it support v2, web seeds and hash requests well enough? The [CLI stack assessment](docs/reference/cli-stack-assessment.md) records the Python/libtorrent rationale, TypeScript tradeoffs and evidence needed for the production language and packaging choice.
- How does the HTTP path get a file's piece layer when no torrent peer is online? Candidates: a `.torrent` file among the sources, or the layer stored next to the manifest.
- Can a browser client download anything useful, and if so from whom?

## Mirror Records

- Is a mirror record a release in the mirror's own profile, or a separate lighter record?
- How are confirmations published and counted, and how does a client stop one party from confirming its own record under many keys?
- If the upstream repository changes a file, how do records for the old and new revisions coexist?
- If the upstream is removed, which records does a client trust by default: those with the most confirmations, those from followed publishers, those listed by a followed hub?
- When the real author later publishes the same files, how are existing mirror records linked to the author's release? The matching `pieces_root` and `sha256` make this checkable.
- Should the client offer to publish a mirror record automatically when a user seeds, or only on request?

## Names and Impersonation

The prototype requires a full publisher Peer ID and explicit version, with optional immutable CID pinning. It checks that the requested key signed the release in its own profile; this prevents another key from claiming that namespace but does not prove ownership of a human-readable name. Version scans can detect observed conflicts, not feed completeness/freshness.

- Existing tools ask for `organization/model`. What does that resolve to: a publisher's `.bso` name, a name in a list the reader chose, or a mapping kept by each hub?
- Anyone can publish a release called `llama-4`. How does a reader tell the real publisher from an imitator before `.bso` names are common?
- How does a publisher prove that a Hugging Face organization and a Bitsocial key belong to the same party? Candidates: the key posted in the organization's Hugging Face profile or model card, on its website, or in its GitHub organization.
- What happens to a publisher's releases when the key is lost or stolen?

## Safety

The [CLI policy](cli/README.md#select-files-and-formats) implements conservative header/content classification, flags code/pickle/unknown files, checks risky suffixes independently of declarations, and rejects a mismatched format before cache publication. This is not complete format parsing or malware scanning; scanner services and the remaining policy questions below are still open.

- Which formats are data-only by default, and who maintains that list as formats appear?
- How does the client detect a file whose content does not match its declared format?
- What is the record format for scan results, and how does a reader choose scanners?
- Should hubs be able to require a scan from a scanner they name before accepting a release?
- How are flagged files shown without training readers to click through every warning?
- Repositories that require `trust_remote_code`: flagged, or refused by the local endpoint unless the user allows them per publisher?

## The Hugging Face Endpoint

The [SDK endpoint prototype](cli/ENDPOINT.md) answers model info/tree and HEAD/GET/range requests. Explicitly registered local names own their entire namespace; missing local files/revisions never fall back upstream. Fallback is public-only and never forwards client credentials. Complete bytes are verified before serving. These provisional choices leave the broader product questions below open.

- Which requests do `huggingface_hub`, `transformers`, llama.cpp and Ollama actually make, and how stable are they between versions?
- Ollama does not read `HF_ENDPOINT`. Is a registry-style route enough, or does it need a change upstream?
- When a name exists both on ModelSwarm and on Hugging Face with different files, which one does the endpoint serve, and how is the user told?
- Gated and private models need a Hugging Face token. Does the endpoint pass requests through for those, or refuse them?

## RPC Hosting

Forge RPC as the optional default is settled: users must be able to switch compatible providers or self-host. It does not settle default hubs or indexers, and RPC revenue remains speculative.

- How do users select a provider or a self-hosted node, and what happens when their chosen provider is unavailable?
- How do publishers migrate hosted profiles between providers while retaining their keys and releases?
- Would publishers pay for metadata hosting, and what customer evidence would justify paid tiers? Model weight seeding is a separate service, not supplied by the RPC connection.
- Should a signed release be able to list endpoints that sell inference for it, such as x402 services on [Agentic Market](https://agentic.market/)? Agents could find the weights and a paid way to run them through one publisher signature, and publishers could earn from inference rather than metadata hosting. The client could not verify that an endpoint actually runs those weights.

## Seeding

- Who seeds a model nobody has downloaded this month?
- Does seeding by default with a ratio cap keep rarely used models alive, or do they need sponsors?
- Could hubs or publishers fund seedboxes through tips on Bitsocial Chain, and should the client show who is seeding what?
- Could an outside incentive network, such as a Bittensor subnet or Filecoin, pay for seeding rarely used models? How would it prove independent storage and public availability, instead of bytes fetched on demand when challenged? Someone other than the project would have to run it.
- How much disk and upload does default seeding cost a typical user, and what should the default cap be?

## Agents as Participants

ModelSwarm is designed for people who publish and download models. AI agents could use the same command line and take on work the network is short of. This is an idea, not a plan, and none of the six milestones depends on it.

- Which jobs can an agent do that anyone can check? Candidates: seeding, confirming mirror records and publishing scan results. A post in a hub cannot be checked the same way.
- Could a treasury pay agents for those jobs? It would have to be a contract with fixed payout rules and no key that can withdraw the funds, on Ethereum or Bitsocial Chain, and the project could not hold it. Where its money would come from is not known.
- One operator can run thousands of agents. What stops them collecting rewards many times for the same bytes, or for bytes fetched only when challenged? This is the proof problem of paid [seeding](#seeding), with more reason to cheat.
- Do hubs want agents posting? Each hub sets its own rules and can refuse them. Should agent accounts be labelled, and can a label be enforced when an agent is only a key?
- Model cards and hub discussion are untrusted text to an agent that reads them. How does the tooling keep a post from instructing an agent that seeds or holds funds?
- An agent that runs on open weights pulled from the swarm does not depend on one model provider. It still rents compute from someone. Does that change who can shut it down?
- The README says ModelSwarm is not a blockchain. Can a treasury stay optional, so that releases, discussion and downloads work the same without it?
- Is this part of ModelSwarm, or a separate Bitsocial client for agents that uses ModelSwarm for its models and its paid work?

## Licenses and Takedowns

- Many model licenses restrict redistribution, and some models are gated. Does the client warn before seeding a model whose license forbids it?
- What does a hub operator do with a takedown request, and what does the project say to one, given that it hosts nothing?
- Leaked weights will be published by someone. Is that left entirely to each hub's rules?
- Does shipping a client with no default hub and no default hub list change the legal position, and is it worth the worse first experience?

## Datasets

- Same manifest, or different fields?
- Datasets are often many small files or very large ones. Does that change the torrent layout?
- Datasets raise privacy and copyright problems models mostly do not. Is that left to hubs as well?
