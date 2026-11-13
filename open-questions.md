# Open Questions

Design decisions not yet made. These need answers before Modelswarm moves from idea to spec.

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

- Is the manifest a field of the comment, or a separate document referenced by its content identifier? Which fields may a comment carry beyond those in BSIP-2?
- Which fields are required?
- How are very large repositories handled, with hundreds of shards?
- How are quantizations expressed: one release with many files, or one release per quantization linked by `base`?
- Is the model card the comment's text, a file in the torrent, or both?
- How does a publisher withdraw a release, and what does a client show for a withdrawn release whose files are still seeded?

## Torrents

- BitTorrent v2 only, or hybrid torrents that v1 clients can join? Hybrid torrents add padding files and a second set of hashes.
- Which piece size, given that the piece layer has to be fetched before the first piece can be checked?
- One torrent per release, or one per file? Per-file torrents let a reader fetch a single quantization without the rest; a v2 client can also select files inside one torrent.
- Which torrent library for the desktop client and the command line, and does it support v2, web seeds and hash requests well enough?
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

- Existing tools ask for `organization/model`. What does that resolve to: a publisher's `.bso` name, a name in a list the reader chose, or a mapping kept by each hub?
- Anyone can publish a release called `llama-4`. How does a reader tell the real publisher from an imitator before `.bso` names are common?
- How does a publisher prove that a Hugging Face organization and a Bitsocial key belong to the same party? Candidates: the key posted in the organization's Hugging Face profile or model card, on its website, or in its GitHub organization.
- What happens to a publisher's releases when the key is lost or stolen?

## Safety

- Which formats are data-only by default, and who maintains that list as formats appear?
- How does the client detect a file whose content does not match its declared format?
- What is the record format for scan results, and how does a reader choose scanners?
- Should hubs be able to require a scan from a scanner they name before accepting a release?
- How are flagged files shown without training readers to click through every warning?
- Repositories that require `trust_remote_code`: flagged, or refused by the local endpoint unless the user allows them per publisher?

## The Hugging Face Endpoint

- Which requests do `huggingface_hub`, `transformers`, llama.cpp and Ollama actually make, and how stable are they between versions?
- Ollama does not read `HF_ENDPOINT`. Is a registry-style route enough, or does it need a change upstream?
- When a name exists both on Modelswarm and on Hugging Face with different files, which one does the endpoint serve, and how is the user told?
- Gated and private models need a Hugging Face token. Does the endpoint pass requests through for those, or refuse them?

## RPC Hosting

Forge RPC as the optional default is settled: users must be able to switch compatible providers or self-host. It does not settle default hubs or indexers, and RPC revenue remains speculative.

- How do users select a provider or a self-hosted node, and what happens when their chosen provider is unavailable?
- How do publishers migrate hosted profiles between providers while retaining their keys and releases?
- Would publishers pay for metadata hosting, and what customer evidence would justify paid tiers? Model weight seeding is a separate service, not supplied by the RPC connection.

## Seeding

- Who seeds a model nobody has downloaded this month?
- Does seeding by default with a ratio cap keep rarely used models alive, or do they need sponsors?
- Could hubs or publishers fund seedboxes through tips on Bitsocial Chain, and should the client show who is seeding what?
- Could an outside incentive network, such as a Bittensor subnet or Filecoin, pay for seeding rarely used models? How would it prove independent storage and public availability, instead of bytes fetched on demand when challenged? Someone other than the project would have to run it.
- How much disk and upload does default seeding cost a typical user, and what should the default cap be?

## Licenses and Takedowns

- Many model licenses restrict redistribution, and some models are gated. Does the client warn before seeding a model whose license forbids it?
- What does a hub operator do with a takedown request, and what does the project say to one, given that it hosts nothing?
- Leaked weights will be published by someone. Is that left entirely to each hub's rules?
- Does shipping a client with no default hub and no default hub list change the legal position, and is it worth the worse first experience?

## Datasets

- Same manifest, or different fields?
- Datasets are often many small files or very large ones. Does that change the torrent layout?
- Datasets raise privacy and copyright problems models mostly do not. Is that left to hubs as well?
