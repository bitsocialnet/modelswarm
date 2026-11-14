# Experimental CLI PR scope — 2026-11-14

This branch is intended to merge the experimental download engine, manifest CLI, local Hugging Face SDK endpoint, signed publisher releases, and persistent-node validation. It does **not** complete the broader publishing/web-client milestone or claim production readiness.

## Review corrections

- Reject case/Unicode aliases in shared directory prefixes before cache writes. Previously, `Dir/a.txt` and `dir/b.txt` could share one directory on a case-insensitive filesystem, and a repeated pull rejected its own snapshot.
- Reject unsupported query-bearing payload URLs and invalid basenames for padded torrents during manifest validation. Previously, these could time out without requests or prevent valid alternate sources from being tried. Query-bearing HTTPS manifest references and supported piece-aligned aliases remain allowed.
- Reject a blocked explicit peer on signed `pull` before staging, with the peer and required opt-in in the error. Native IP filtering still applies to discovered peers and web seeds.
- Reject upstream metadata that marks a repository private or gated, including successful HTTP 200 responses, before caching it or downloading payloads.
- Reject explicitly empty CID/digest pins rather than silently performing unpinned discovery.
- Enforce and explain the pinned PKC RPC's 1 MiB IPFS manifest limit. Equivalent CIDv0/CIDv1 references work at the exact boundary; alternative IPFS file layouts remain unsupported. HTTPS retains the manifest format's 16 MiB limit.
- Check the complete encoded signed publication against PKC's 40,000-byte limit before sending it. A card smaller than the raw 24 KiB limit can exceed this after JSON escaping.

The fixes have focused regressions. Independent reviews covered the download/cache/endpoint and signed-release paths. Historical evaluation notes now distinguish their original results from later milestones, and the design doc includes profile restart recovery and same-minter renewal.

## Verification

Environment: macOS arm64, Python 3.11.15, libtorrent 2.1.1, Node 26.12.1, PKC SDK 0.0.142 and Kubo 0.43.1. Raw local logs and screenshots are retained under the ignored `cli/artifacts/pr-readiness/` directory.

| Check | Result |
| --- | --- |
| Complete Python suite with real private PKC/Kubo fixtures | 103 passed, no skips, 411.669 seconds |
| Signed-release and input tests after the final CID/diagnostic refinements | 14 passed, no skips, 56.179 seconds |
| Bridge protocol suite | 22 passed, no skips |
| `corepack yarn agent:verify` | Lint, TypeScript, production build and advisory Knip passed |
| Wheel build and isolated installation | Required bridge sources/lockfile included; no nested Node dependencies/tests; installed command passed help, make, HTTP pull and verify for three files |
| Production landing page in Chromium | Status/roadmap copy checked at 1440px and 375px; no horizontal overflow or console errors |
| Merge check | The original readiness check passed against `origin/master` at `f4b4904`. Before PR submission, the task-owned `.tmp/` ignore rule was moved to avoid an append conflict with a newer ignore rule on `master`; its behavior is unchanged. |

The complete suite preceded the final CID normalization and local validation-message refinements; the final 14-test release run covers those changes. Earlier failed regression runs are retained: they caught size/error handling, and one CIDv1 fixture incorrectly re-added the file with a different internal DAG. That fixture now converts the original CID, and the final run passes. No failed check remains unresolved. Existing native binding deprecation warnings remain non-fatal.

The repository retrospective selected these focused regressions as prevention; no additional workflow rules were needed. Test fixtures, the temporary wheel environment, the task's browser session and its HTTP server were cleaned up.

## Remaining scope

The existing [roadmap](../roadmap.md) remains authoritative. Public-internet/NAT/DHT operation, Linux/Windows installation, other consumer applications, profile migration/revocation, write-interruption/disk-full/power-loss recovery, hosted onboarding, mirror records, a public demo and the read-only web client remain unverified or unimplemented as documented in the linked evaluations.

The prior cross-machine test used two Macs at one site over a private swarm and Tailscale; this readiness pass does not extend that evidence. The repository currently has a PR review workflow but no automated CLI test workflow, so the local suite results are not a claim of GitHub CI coverage.

This evaluation records the local readiness pass before PR submission. Merging to `master` publishes the landing-page updates through Vercel.
