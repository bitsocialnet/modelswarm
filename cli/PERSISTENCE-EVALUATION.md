# Restart and delegation renewal evaluation — 2026-11-13

**A publisher node keeps its profile, delegation and releases across clean restarts and hard kills, and the owner can renew the delegation.** Two behaviours of the pinned SDK need operator attention after a restart; both are measured below. Everything here ran on one machine against the isolated private node. It is not cross-machine, public-network or NAT evidence.

Commands and operator guidance are in [RELEASES.md](RELEASES.md#keep-a-profile-hosted). The earlier signed-release evidence is in [RELEASES-EVALUATION.md](RELEASES-EVALUATION.md).

## What was added

- `profile-start PUBLISHER`: asks the RPC node to host an existing delegated profile again. Needs no key. Safe on a running profile; refuses publishers the node does not host.
- `profile-renew --key KEY`: asks the node for the next delegation sequence, signs the record locally with the owner key, and has the node verify and publish it. Same minter, publisher and release CIDs.
- The test fixture can resume an existing data directory (`--resume`), and tests can stop it cleanly or SIGKILL the node together with its Kubo daemon.

## Evidence

Environment: macOS 27.0 arm64, Python 3.11.15, Node 26.12.1, `@pkcprotocol/pkc-js` 0.0.142, Kubo 0.43.1. **87 Python tests passed in 341 seconds with no skips** (81 existing, 6 new in `cli/tests/test_persistence.py`); 22 Node protocol tests passed. The raw log is `cli/artifacts/persistence-tests.log`.

```sh
MODELSWARM_KUBO_BIN=/absolute/path/to/kubo-0.43.1/ipfs MODELSWARM_NODE=/absolute/path/to/node \
  cli/.venv/bin/python -m unittest discover -s cli/tests -p 'test_persistence.py' -v
```

Each test owns a fresh node and publisher profile, publishes through the real CLI, and pulls into empty caches after the restart so nothing is served from earlier state.

| Scenario | Result |
|---|---|
| Clean stop (SIGTERM), restart on the same data | Node hosts the profile again without any client. Same publisher, minter and delegation sequence. Version discovery and CID-pinned pulls return the pre-restart release CID with verified bytes. A repeated publish is recognised as the same release; `profile-init` still refuses to replace the delegation; a new version publishes and pulls. |
| SIGKILL of node and Kubo, restart after 11 seconds | Same as a clean restart: the node recovers by itself. |
| SIGKILL, immediate restart | The node does **not** host the profile (see below). `profile-start` succeeds once the lock is stale, after which all checks above pass. Repeated with a second kill directly after the post-recovery publication; both releases survive. |
| Renewal | Sequence 0 → 5 → 10. Version and CID pulls, and publish reuse, are unaffected. The node rejects a replayed sequence, an equal sequence, a record pointing at another minter and a record signed by another key, each with the owner's genuine key where applicable. A key with no profile on the node is refused. |
| Renewal across restarts | Sequence 5 survives a clean restart, renews to 10, survives a kill and delayed restart; old release still resolves and a new one publishes. |

## Findings in the pinned SDK

Both were reproduced deterministically and traced in the node's debug log. Neither loses data.

1. **A killed node restarted within 10 seconds stops hosting its profiles and never retries.** The start lock left by the killed process is still considered held, auto-start fails with `ERR_COMMUNITY_ALREADY_STARTED`, and nothing retries it. Observed for 97 seconds with no recovery. Until recovered, `publish` fails with `ERR_COMMUNITY_CHALLENGE_EXCHANGE_DISABLED`; published releases stay readable. A process supervisor with a short restart delay would hit this on every crash. Mitigations verified here: restart after more than 10 seconds, or run `profile-start`.
2. **Version discovery lags the first post-restart publication by 60 seconds on the isolated node.** Before publishing its next record a restarted minter resolves its own IPNS name; Kubo with no peers and no routing holds that lookup for its full 60-second timeout, then the record is published normally. A release announced in that window is accepted and CID-addressable immediately and joins the profile feed with that record (measured: about 61 seconds, against about 1 second without a restart). Whether a networked node resolves faster is untested.

## Limits of this evidence

- One machine, loopback only, private swarm with no peers. A second node resolving the delegation after a restart or renewal is not covered here.
- The delegation lifetime is a fixed constant of about 100 years in the SDK, so expiry and renewal of an expired delegation cannot be exercised.
- Renewal keeps the same node and minter. Moving a profile to another node, rotating to a new minter and revoking a leaked minter are not implemented or tested.
- Kills hit an idle node shortly after a completed publication. Kills during a write, disk-full conditions and real power loss are untested.
- A Kubo crash while the PKC process survives stops the test fixture by design; that case says nothing about a production supervisor.
