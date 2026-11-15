# How It Could Work

This is a sketch, not a spec. The conventions would become an Application-category BSIP in `bitsocialnet/BSIPs` once the open questions are settled.

It builds on [HuggingSocial's design](https://github.com/Rinse12/huggingsocial/blob/master/DESIGN.md) by Rinse12: the layers, hubs, downloading and seeding, the Hugging Face endpoint, the command line and search below come from it. What ModelSwarm changes is listed under [Prior Art](README.md#prior-art).

## Layers

| Layer | What it is | Built from |
|---|---|---|
| Publisher | An author key, optionally with a `.bso` name | Bitsocial authors ([BSIP-2](https://bsips.bitsocial.net/bsip-2)) and names ([BSIP-10](https://bsips.bitsocial.net/bsip-10), [BSIP-13](https://bsips.bitsocial.net/bsip-13)) |
| Profile | The publisher's own list of releases, which only the publisher can post to | An author community ([BSIP-14](https://bsips.bitsocial.net/bsip-14)) |
| Release | One version of one model: a model card plus a manifest | A comment ([BSIP-2](https://bsips.bitsocial.net/bsip-2)) that references a manifest |
| Manifest | The list of files with their sizes, hashes and download sources | A small JSON document covered by the release's signature |
| Files | The weights | BitTorrent v2 ([BEP 52](https://www.bittorrent.org/beps/bep_0052.html)) and HTTP mirrors |
| Hub | A curated board of releases with discussion | An ordinary community ([BSIP-3](https://bsips.bitsocial.net/bsip-3)) carrying crossposts ([BSIP-12](https://bsips.bitsocial.net/bsip-12)) |
| Hub list | A curated list of hubs and publishers | A community list ([BSIP-15](https://bsips.bitsocial.net/bsip-15)) |
| Search | Full-text and faceted search over releases | `bitsocial-indexer` instances, remote or local |
| Scan results | A scanner's verdict on a file | Signed records from replaceable scanner services |
| Compatibility | Existing tools downloading through ModelSwarm | A local endpoint that speaks the Hugging Face Hub API |

Bitsocial carries text, so it holds releases, manifests and discussion. Model files never pass through it.

## RPC Provider Choice

The planned client defaults to Forge RPC for its Bitsocial connection, but users can select another compatible RPC provider or self-host a node. The current prototype requires an explicit `--rpc` or `MODELSWARM_RPC`; no hosted Forge endpoint has been validated. Publishers retain their signing keys. Forge is a convenience provider, not a required network operator; model files still move through torrents and HTTP mirrors, independently of RPC choice.

Optional paid RPC services, including hosted publisher profiles when supported, are a speculative revenue opportunity. RPC carries metadata and discussion rather than model weights; there is no validated willingness to pay for this hosting, so it is not a strong monetization pitch. Reliable weight seeding, managed distribution and enterprise support would be additional services beyond RPC, not commitments in this design. Provider selection and self-hosting must be available in the client; hosted profiles remain a dependency to implement, not a currently available feature.

## Publishers and Profiles

A publisher is a Bitsocial author: an Ed25519 key, optionally with a `.bso` name. A lab, a company and a single person fine-tuning at home are the same kind of thing.

Each publisher has a profile: an author community ([BSIP-14](https://bsips.bitsocial.net/bsip-14)) whose address is the publisher's key.

- **Only the publisher posts.** The profile's challenge rejects every other author.
- **The profile is the canonical place for a release.** Hubs can carry it or drop it; the publisher's signed copy stays where the publisher put it.
- **It stays small.** A profile holds one publisher's releases, not a share of the whole catalogue.
- **It needs an always-online node.** Publishers of models generally have a server or a workstation that is on, so this is less of a barrier here than for a phone-first social app. A publisher without one waits for hosted profile nodes on Forge RPC or another compatible provider; self-hosting remains an option.

A signature proves that the same key published a series of releases. It does not prove who holds the key. A publisher ties the key to their name the way projects publish a GPG key: on their website, their GitHub organization or a `.bso` name. See [open-questions.md](open-questions.md#names-and-impersonation).

## Releases and the Manifest

The experimental CLI implements [manifest v0](cli/MANIFEST.md) with complete per-file v2 metadata and explicit sources. A local manifest is trusted input. The [signed release prototype](cli/RELEASES.md) now authenticates its exact SHA-256 through an owner-signed post in a PKC author profile. Readers independently verify the record CID, native Ed25519 signature, publisher/community identity and manifest name/version before downloading. The richer lineage/schema sketch below remains future design.

A release is a post in the publisher's profile. In the prototype its signed content is a JSON envelope containing the model card, name/version and manifest URL/digest. The manifest is fetched separately from HTTPS or IPFS and checked against that authenticated digest.

A manifest could look like this:

```json
{
  "name": "example-7b-instruct",
  "version": "1.2.0",
  "license": "apache-2.0",
  "base": { "publisher": "<publisher address>", "name": "example-7b", "version": "1.0.0" },
  "tags": ["text-generation", "gguf"],
  "torrent": {
    "infohash_v2": "<sha-256 infohash>",
    "infohash_v1": "<sha-1 infohash, when the torrent is a hybrid>"
  },
  "files": [
    {
      "path": "example-7b-instruct.Q4_K_M.gguf",
      "size": 4368439584,
      "format": "gguf",
      "pieces_root": "<BitTorrent v2 merkle root of this file>",
      "sha256": "<sha-256 of the whole file>"
    }
  ],
  "sources": [
    { "type": "torrent" },
    { "type": "http", "url": "https://huggingface.co/example/example-7b-instruct/resolve/main/" }
  ]
}
```

- **A version is immutable.** A new version is a new release. The latest version is the publisher's most recent release under that name.
- **Two hashes per file.** `pieces_root` verifies the download as it happens. `sha256` is what Hugging Face, Ollama and most model cards already use, so it links a ModelSwarm release to the same file elsewhere.
- **`format` is declared and checked.** The client reads the file's header and refuses a file whose content does not match its declared format.
- **Where the manifest lives is open.** It could be a field of the comment or a separate document referenced by its content identifier. A model split into hundreds of shards makes a long manifest, which argues for the second. See [open-questions.md](open-questions.md#manifest).

## Verification

BitTorrent v2 hashes every file separately. Each file gets a SHA-256 hash tree built from 16 KiB blocks, and the root of that tree is the file's pieces root. A torrent also carries the tree layer that matches its piece size, the piece layers, and a client checks those against the root before using them.

Putting the pieces root in the signed manifest gives three properties:

**Pieces are checked as they arrive.** The client gets the piece layer for a file, checks it against the signed root, then checks every piece against the layer. A bad piece is discarded and fetched again. For a 5 GiB file with 4 MiB pieces the layer is 1,280 hashes, about 41 KB.

**HTTP mirrors are checked the same way.** The check depends on the bytes, not on how they arrived. A mirror that serves a modified file fails at the first modified piece, and the client switches source. Hugging Face can be used as a mirror without being trusted as one.

**Identical files share seeders.** The pieces root of a file is the same in every torrent that contains it. Two releases that include the same tokenizer file, or the same base weights, point at the same data.

The whole-file `sha256` is computed once the file is complete, as a second check and for tools that expect it.

This is only as strong as the party that signed the root. For a release signed by the model's author it is direct. For records published by third parties it is weaker; see [Models That Are Only on Hugging Face](#models-that-are-only-on-hugging-face).

## Safety

Verification answers "is this the file the publisher released". It does not answer "is this file safe to load".

- **Data-only formats are the default.** safetensors and GGUF hold tensors and metadata. They are safer, not safe: parsers have had bugs, and metadata such as chat templates is interpreted by the software that loads the model.
- **Pickle-based formats are flagged.** Files such as PyTorch `.bin`, `.pt` and `.ckpt` can run code when loaded. The client marks them, leaves them out of a default download and asks before fetching them.
- **Code is flagged.** A release that ships Python meant to be executed on load is marked the same way.
- **Hubs set posting rules.** A hub can refuse releases with flagged files, the way a community sets any other rule.
- **Scanners are services.** Anyone can run a scanner and publish signed results for a file's hash. The client shows which scanners examined a file and what they found, and the reader chooses which scanners to listen to. A file no scanner has examined is shown as unexamined, not as clean.

## Hubs

A hub is an ordinary Bitsocial community about a topic: a model family, a task, a quantization group, a language.

- **Hubs carry crossposts.** A crosspost ([BSIP-12](https://bsips.bitsocial.net/bsip-12)) embeds the release's signed record, so readers verify the publisher's signature without trusting the hub.
- **Hubs host the discussion.** Benchmarks, "does this run on my GPU", fine-tune requests and license arguments happen as replies, under the hub's own rules and anti-spam challenge.
- **A hub's removal is local.** Moderators can remove a release from the hub's board. They cannot remove it from the publisher's profile or from other hubs.
- **Hubs do not host files.** A hub may run a seedbox for the models it lists, as its own choice.
- **There is no default hub.** The client ships with a way to load hub lists ([BSIP-15](https://bsips.bitsocial.net/bsip-15)) from curators the reader picks.

Community members can add sources in replies, for example a new HTTP mirror. They need no trust, because every source is checked against the signed manifest.

## Downloading and Seeding

- **Sources are used together.** The client downloads from torrent peers and HTTP mirrors at once and verifies everything against the manifest.
- **Torrents carry web seeds.** A torrent that lists HTTP mirrors as web seeds can be downloaded when it has no peers yet, so a new release is available from its first minute without anyone re-hosting it.
- **Hybrid torrents.** A torrent can carry both v1 and v2 metadata, so older clients can still join the swarm. Whether that is worth the cost is [open](open-questions.md#torrents).
- **Downloaders seed by default.** The desktop client seeds what it downloads up to a ratio the user sets, and shows transfers in a dashboard. This is what keeps rarely used models available.
- **Browsers mostly browse.** A browser cannot join an ordinary BitTorrent swarm. The web client is for finding, reading and discussing; large downloads happen in the desktop client or the command line.
- **When there are no seeders and no mirror, the file is gone.** The release, the manifest and the discussion remain, so anyone who still has the file can seed it again and every reader can verify it is the same file.

## Models That Are Only on Hugging Face

Most models will have no publisher on ModelSwarm for a long time. Two cases:

**Downloading.** The client reads the repository's metadata from Hugging Face, including the SHA-256 it publishes for large files, and downloads from Hugging Face. No Bitsocial record is needed. This verifies whole files, after the download, against Hugging Face's own word.

**Seeding.** A user who has the files can make a torrent and publish a mirror record in their own profile: for each file, the upstream repository and revision, the `sha256` and the `pieces_root`. Other clients can now fetch that model from the swarm and verify pieces as they arrive.

A mirror record is a claim by its author that a file with a given `sha256` has a given `pieces_root`. Anyone holding the file can check the claim, and a client that completes a download checks it automatically against the upstream `sha256`. Clients can publish that they confirmed it, so a record collects confirmations over time.

If the model is later removed upstream, the mirror records, their confirmations and the swarm are what is left. At that point trust rests on who published and confirmed the records, which the client shows.

Records are created when someone seeds, so the index follows demand. There is no bulk import of the Hugging Face catalogue. See [open-questions.md](open-questions.md#mirror-records).

## The Hugging Face Endpoint

Most people do not download models by visiting a website. They run `transformers`, llama.cpp, Ollama or the `hf` command, which fetch from Hugging Face by name. The `huggingface_hub` library reads its server address from the [`HF_ENDPOINT`](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables) environment variable.

The CLI now implements a [loopback endpoint](cli/ENDPOINT.md), tested with `huggingface_hub` 2.4.0. The desktop integration and other consumers remain future work. In the prototype:

- model information is built from a local manifest or a verified publisher release registered with `--release`;
- a local file is acquired from torrent peers and mirrors, with piece checks and full-file verification before any response body is served;
- unregistered public models fall back to pinned Hugging Face downloads, verified against upstream whole-file metadata;
- uploads and account requests are refused.

With `HF_ENDPOINT` set before importing the SDK, SDK downloads use this endpoint. Cold downloads need a longer client timeout because the prototype waits for whole-file verification. Registered local names take precedence and never silently fall back on a missing file or revision. Broader tool compatibility is still to be tested. This idea comes from [HuggingSocial](https://github.com/Rinse12/huggingsocial).

A name such as `example/example-7b` has to resolve to one publisher's release. The prototype requires explicit `pkc://PUBLISHER/example/example-7b@VERSION[#CID]` registration, scoped to a bare publisher key. Human-readable name proofs remain [open](open-questions.md#names-and-impersonation).

## Command Line

The [Python CLI](cli/README.md) supports local manifests and [signed publisher releases](cli/RELEASES.md), with nested files, format checks, checkpoint recovery and verified snapshots. Current command shapes are:

```text
modelswarm make DIR -o MANIFEST --name OWNER/MODEL --version VERSION --license LICENSE
modelswarm verify MANIFEST DIR
modelswarm keygen -o KEY
modelswarm profile-init --key KEY --rpc RPC_URL
modelswarm profile-start PUBLISHER --rpc RPC_URL
modelswarm profile-renew --key KEY --minter MINTER --rpc RPC_URL
modelswarm publish MANIFEST --key KEY --manifest-url URL --rpc RPC_URL
modelswarm pull MANIFEST
modelswarm pull pkc://PUBLISHER/OWNER/MODEL@VERSION#CID --rpc RPC_URL
modelswarm serve --release pkc://PUBLISHER/OWNER/MODEL@VERSION#CID --rpc RPC_URL
```

Local manifest commands need no Bitsocial node. Publisher commands require a compatible RPC node; `publish` posts a signed reference to already-hosted manifest bytes and does not upload weights. Profiles persist across restarts; `profile-start` recovers hosting and `profile-renew` renews delegation to the same minter. See the [restart and cross-machine evidence](cli/PERSISTENCE-EVALUATION.md), including the pinned SDK's restart workarounds. Bare-name lookup, hosted defaults, migration and key revocation remain future work.

## Search and Discovery

- **Indexers.** The client keeps a list of `bitsocial-indexer` instances and queries several at once. An indexer that parses manifests can filter by base model, format, quantization, license and size.
- **An indexer can omit, not forge.** Results are hints. The client fetches the release from its profile and checks the signature.
- **A local indexer is one more entry in the list.** Trusting a third party and trusting only your own machine are the same mechanism.
- **Following.** A reader follows publishers and hubs; new releases appear in a feed.
- **Derivatives.** `base` links a fine-tune or a quantization to the release it came from, so a model page can list its quantizations and its ancestry.

## Scope

- Models first. Datasets later, with the same manifest and larger torrents.
- No hosted inference and no Spaces.
- The project publishes the client and tooling. It runs no hub, indexer or seedbox that others depend on.
