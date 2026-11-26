# Run a ModelSwarm catalogue

The website is a static build. You can serve it from localhost, your own domain or an IPFS gateway path. A catalogue combines the bundled signed Qwen demo with an optional Pirate Face snapshot and an optional Bitsocial community snapshot. Opening the site reads those local build files. Downloads go from the torrent client to the swarm, and the indexed websites can be offline.

## Serve the website

From a checkout of ModelSwarm with Node and Corepack installed:

```sh
corepack yarn install --immutable
corepack yarn build
python3 -m http.server 8080 --bind 127.0.0.1 --directory build
```

Open [the model catalogue](http://127.0.0.1:8080/catalogue.html). To publish your instance, serve the contents of `build/` from any static host.

## Import an existing swarm

The bundled preview uses public Pirate Face listings. For broader imports, the [Pirate Face magnet index](https://pirateface.co/pirateface/magnet-index) dataset card invites mirrors and identifies the index as [MIT-licensed](PIRATE-FACE-INDEX-LICENSE). Each exported model has its own upstream license. The importer validates public access and the license at the pinned model revision. When given the official export, it also applies the index's removals. The catalogue shows the source of imported entries, and a Pirate Face listing does not count as a ModelSwarm publisher signature.

The catalogue serves the original torrent identifiers. Imported releases offer an original tracker-assisted magnet when available and a peer-only magnet that uses DHT. Both preserve the torrent's infohashes. Neither includes an HTTP web seed. Availability depends on reachable peers. Seed counts are observations from the snapshot date. A model marked **Unknown** has no count in the snapshot.

To replace the preview, provide a text file with one `owner/model` repository per line. The importer checks the public listing and upstream revision before adding each entry.

```sh
python3 catalogue/import_pirateface.py --repos my-repos.txt \
  --output src/data/pirateface-index.json
corepack yarn build
```

If you maintain an offline copy of the official export, add `--index-cache /path/to/pf-cache/index` to pin the import to its completed shards and removals. The cache is created by [`pf index --sync`](https://pypi.org/project/pirateface/). To repeat the verification with your own saved public listing and upstream responses, use `--evidence FILE` in place of `--repos`. The optional generated index stays local to your checkout.

## Publish and discuss in a community

Install the [CLI and optional bridge](../cli/RELEASES.md#install-the-optional-bridge). Connect to your own compatible Bitsocial node using `MODELSWARM_RPC`. See the [demo setup](../cli/demo/README.md) for an example of running Kubo and the PKC node. For discussion, start the node with `PKC_ENABLE_PUBSUB=1` and enable Kubo pubsub (`ipfs config Pubsub.Enabled --json true` before starting the daemon). The feed-only demo uses its existing settings. RPC credentials and signing keys stay outside the static build.

Create a key and host a community. The default community allows submissions and replies without a challenge. Pick which communities you follow on each instance.

```sh
cli/.venv/bin/modelswarm keygen -o contributor.key.json
cli/.venv/bin/python catalogue/community.py init --key contributor.key.json
```

Use the returned community key and a [published release URI with its CID](../cli/RELEASES.md#create-and-publish). Sharing creates a native Bitsocial crosspost. The underlying release keeps its original publisher signature. A reply goes to the crosspost in that community.

```sh
cli/.venv/bin/python catalogue/community.py share COMMUNITY 'pkc://PUBLISHER/owner/model@v1#RELEASE_CID' --key contributor.key.json
cli/.venv/bin/python catalogue/community.py reply COMMUNITY POST_CID --key contributor.key.json --text 'I verified this release.'
```

On the catalogue machine, sync one snapshot per followed community. Set `MODELSWARM_RPC` there to your reader node.

```sh
cli/.venv/bin/python catalogue/community.py sync COMMUNITY --output src/data/community-my-hub.json
corepack yarn build
```

Sync verifies the original release, fetches the manifest by its signed digest and exports torrent files for downloads the CLI allows by default. Flagged files are shown with their hashes and require the CLI's explicit override. The browser reads the resulting files and discussion without reaching the publishing node or signing anything. Run sync and rebuild to pick up new releases and replies. The exporter reads a bounded set of recent posts and direct replies. If the scan reaches its limit or cannot fetch a post, sync preserves the previous snapshot and reports the failure. Use `--max-posts 200` to raise the default scan limits for busy communities. When a manifest fails to refresh, sync keeps the last verified copy for the same crosspost and signed release CID. Use `--torrent-dir public/hub-torrents` for a different public subdirectory. Generated links use its path under `public/`. The node keeps the community available and publishers or peers keep the manifest and torrent payloads available.
