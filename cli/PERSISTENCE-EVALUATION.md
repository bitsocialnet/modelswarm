# Restart, renewal and cross-machine evaluation — 2026-11-13

**A publisher node keeps its profile, delegation and releases across clean restarts and hard kills, the owner can renew the delegation, and a separate reader node resolves all of it over the swarm.** Two behaviours of the pinned SDK need operator attention after a restart; both are measured below. The automatic tests run on one machine over loopback in a private swarm. One manual run then put the reader on a second machine and pulled a real 491 MB model from the first. Both machines share a site and a Tailscale network, so this is cross-machine evidence, not public-internet, NAT or DHT evidence.

Commands and operator guidance are in [RELEASES.md](RELEASES.md#keep-a-profile-hosted). The earlier signed-release evidence is in [RELEASES-EVALUATION.md](RELEASES-EVALUATION.md).

## What was added

- `profile-start PUBLISHER`: asks the RPC node to host an existing delegated profile again. Needs no key. Safe on a running profile; refuses publishers the node does not host.
- `profile-renew --key KEY --minter MINTER`: asks the node for the next delegation sequence, signs the record locally with the owner key, and has the node verify and publish it. Same minter, publisher and release CIDs. The CLI signs only for the minter the owner names and refuses a sequence jump above 1,000, since both values come from the node.
- The test fixture can resume an existing data directory (`--resume`), and tests can stop it cleanly or SIGKILL the node together with its Kubo daemon. A second fixture can join the first one's private swarm (`--swarm-key`, `--peer`); a node keeps its swarm port across restarts so peers reconnect.

## Evidence

Environment: macOS 27.0 arm64, Python 3.11.15, Node 26.12.1, `@pkcprotocol/pkc-js` 0.0.142, Kubo 0.43.1. **90 Python tests passed in 406 seconds with no skips** (81 existing, 6 new in `cli/tests/test_persistence.py`, 3 new in `cli/tests/test_two_nodes.py`); 22 Node protocol tests passed. The raw log is `cli/artifacts/persistence-tests.log`.

```sh
MODELSWARM_KUBO_BIN=/absolute/path/to/kubo-0.43.1/ipfs MODELSWARM_NODE=/absolute/path/to/node \
  cli/.venv/bin/python -m unittest discover -s cli/tests -p 'test_persistence.py' -v
# and -p 'test_two_nodes.py'
```

Each test owns a fresh node and publisher profile, publishes through the real CLI, and pulls into empty caches after the restart so nothing is served from earlier state.

| Scenario | Result |
|---|---|
| Clean stop (SIGTERM), restart on the same data | Node hosts the profile again without any client. Same publisher, minter and delegation sequence. Version discovery and CID-pinned pulls return the pre-restart release CID with verified bytes. A repeated publish is recognised as the same release; `profile-init` still refuses to replace the delegation; a new version publishes and pulls. |
| SIGKILL of node and Kubo, restart after 11 seconds | Same as a clean restart: the node recovers by itself. |
| SIGKILL, immediate restart | The node reports the held lock and does **not** host the profile (see below). While unhosted, existing releases still pull by version and CID and a new publication is refused. `profile-start` succeeds once the lock is stale, after which all checks above pass. Repeated with a second kill directly after the post-recovery publication; both releases survive. |
| Renewal | Sequence 0 → 5 → 10. Version and CID pulls, and publish reuse, are unaffected. The node rejects a replayed sequence, an equal sequence, a record pointing at another minter and a record signed by another key, each with the owner's genuine key where applicable. A key with no profile on the node is refused, and so is a `--minter` other than the node's. |
| Renewal across restarts | Sequence 5 survives a clean restart, renews to 10, survives a kill and delayed restart; old release still resolves and a new one publishes. |
| Separate reader node | A second Kubo and PKC node, sharing only the swarm key and a peer address, resolves the delegation, profile, pages and release records without touching the publisher's RPC. Version and CID pulls verify bytes. The reader's node cannot start, renew or publish to the profile, and a wrong publisher fails verification. |
| Reader, no HTTP at all | Manifest pinned in the publisher's Kubo and published as `ipfs://CID`; weights from a BitTorrent peer only. The reader fetches the manifest through the swarm and the weights from the peer; zero HTTP requests. This is the shape a reader on another machine needs. |
| Reader across publisher restart and renewal | After the publisher restarts and renews, a release published afterwards reaches the reader's node, so the reader is reading the restarted node and not a cache. The reader's own node then restarts and discovers a release published after its restart. |

## Cross-machine run

`cli/tests/manual_cross_machine.py` is a manual test, outside automatic discovery. It ran once with small files and once with the real model; both passed. Logs: `cli/artifacts/cross-machine-test.log` and `cross-machine-report.json`.

| | Publisher | Reader |
|---|---|---|
| Machine | MacBook Pro, macOS 27.0 arm64 | Mac mini, macOS 27.2 arm64 |
| Runs | PKC node, Kubo 0.43.1, BitTorrent seeder, publishing CLI | its own PKC node and Kubo 0.43.1, pulling CLI |
| Node | 26.12.1 | 22.23.4 (bridge dependencies installed there with `corepack yarn install --immutable`) |

The two Kubo nodes share only a private swarm key and the publisher's address. They connected over Tailscale (WireGuard, direct path, 6–39 ms round trip); both machines are also on the same local network. The reader's CLI spoke only to the reader's own loopback RPC. The manifest travelled as `ipfs://CID` through the swarm and the weights over BitTorrent from an explicit `--peer`; no HTTP request was made.

| Step | Result |
|---|---|
| Pull without `--allow-local-sources` | Refused in effect: the tailnet peer is a non-public address, so the reader never connects, the seeder uploads 0 bytes and the pull times out after its `--timeout`. There is no explicit error naming the filtered peer. |
| CID-pinned pull with `--allow-local-sources` | 491,465,609 bytes in three files, including `qwen2.5-0.5b-instruct-q4_k_m.gguf` (491,400,032 bytes), in 22.8 seconds end to end including resolution and final verification. SHA-256 of every file on the reader equals the publisher's source; publisher, release CID and `signed` match. |
| Version discovery | Same release CID resolved from the publisher's profile through the reader's node in 1.7 seconds. |
| Publisher restart, renewal, new release | After a clean restart and `profile-renew` to sequence 5 on the publisher, a release published afterwards was discovered and pulled on the reader 9.4 seconds after it was announced. |

To repeat it, copy `cli/` to the second machine, create the Python environment and install the bridge there as in [RELEASES.md](RELEASES.md#install-the-optional-bridge), make Kubo 0.43.1 available as `ipfs`, then run the command in the test file's header. The test removes its data on the second machine afterwards.

## Findings in the pinned SDK

Both were reproduced and traced in the node's debug log. Neither loses data. The tests assert the behaviour; the durations quoted are single measurements from manual probe runs, not asserted thresholds.

1. **A killed node restarted within 10 seconds stops hosting its profiles and never retries.** The start lock left by the killed process is still considered held, auto-start fails with `ERR_COMMUNITY_ALREADY_STARTED`, and nothing retries it. In a probe it stayed unhosted for the 97 seconds observed. Until recovered, `publish` fails with `ERR_COMMUNITY_CHALLENGE_EXCHANGE_DISABLED`; published releases stay readable. A process supervisor with a short restart delay would hit this on every crash. Mitigations verified here: restart after more than 10 seconds, or run `profile-start`.
2. **Version discovery lags the first post-restart publication: about 61 seconds with no peers, about 10 seconds with one connected peer.** Before publishing its next record a restarted minter resolves its own IPNS name; Kubo with no peers and no routing holds that lookup for its full 60-second timeout, then the record is published normally. A release announced in that window is accepted and CID-addressable immediately and joins the profile feed with that record. Without a restart the same step takes about 1 second. Timing with public routing is untested.

## Limits of this evidence

- Private swarm of two nodes with routing disabled, on one machine or on two machines at one site joined by Tailscale. Peers find each other by configured address. DHT and HTTP-router discovery, public-internet paths, NAT traversal, relayed connections, real packet loss, Linux or Windows hosts and more than one reader are not exercised.
- The cross-machine run was done twice by hand in one direction. It is not part of the automatic suite and has no CI.
- The delegation lifetime is a fixed constant of about 100 years in the SDK, so expiry and renewal of an expired delegation cannot be exercised.
- Renewal keeps the same node and minter. Moving a profile to another node, rotating to a new minter and revoking a leaked minter are not implemented or tested.
- Kills hit an idle node shortly after a completed publication. Kills during a write, disk-full conditions and real power loss are untested.
- A Kubo crash while the PKC process survives stops the test fixture by design; that case says nothing about a production supervisor.
