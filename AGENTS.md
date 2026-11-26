# AGENTS.md

## Purpose and priority

These are the shared instructions for agents working on ModelSwarm. Explicit user instructions take precedence over repository workflow guidance. MUST rules are mandatory; SHOULD rules are defaults. Read linked playbooks only when the task needs them.

Use judgment for routine implementation choices and continue authorized work. Ask only when missing information materially changes the outcome or an action needs authorization that has not already been given. Do not turn a skill's suggested procedure into an extra approval gate.

## Product and source of truth

ModelSwarm is an experimental design for a hub of open-weight AI models that nobody owns: publishers sign releases from their own Bitsocial profile, weights move over BitTorrent, and every piece is checked against the signed release as it downloads. The name means models distributed by a swarm of peers, as in a BitTorrent swarm; keep that meaning explicit in the README, the site hero and the GitHub description. Say "open-weight" models, never "open AI" models, which reads as OpenAI. The landing page, isolated [download-engine prototype](prototypes/download-engine/README.md), and experimental Python/libtorrent [CLI](cli/README.md) exist. The CLI implements manifest v0 and make/verify/pull/serve, plus signed publisher releases through keygen/profile-init/publish, profile/CID pulls and endpoint registration. Its loopback Hugging Face endpoint supports the SDK and verified public upstream fallback. Signed release integration is tested against real PKC nodes. The public demo uses explicit WAN peers for one verification run. Hosted defaults, automatic peer discovery, catalogue and desktop client remain. Consumer compatibility beyond the SDK is still unverified. The design lives in the docs at the repository root: [README.md](README.md), [how-it-could-work.md](how-it-could-work.md), [open-questions.md](open-questions.md) and [roadmap.md](roadmap.md).
The landing page and demo release page for modelswarm.org are a static React and Vite app at the repository root (`index.html`, `src/`, `public/`), on the stack of 5chan and WeTube. Its copy summarises the root docs.
Vercel deploys it to modelswarm.org from every push to `master`, so pushing `master` publishes the site.

The repository is public. Do not announce it or publish anything without an explicit request.

Code, manifests, source docs, and runtime evidence establish behavior. This file, skills, playbooks, and task logs are orientation and policy; verify their technical claims against source before editing. Check the installed dependency version before assuming a nearby repository supplies its code.

For an unexpected repo-specific issue, tell the contributor and continue independent work. After confirmation, record only recurring issues with a concrete mitigation in [known-surprises.md](docs/agent-playbooks/known-surprises.md).

## Working principles

- Define completion for non-trivial work. Continue through implementation, relevant verification, and fixes until the requested outcome is complete; stop at the user's requested boundary.
- Understand the flow before editing. Prefer skipping unnecessary work, reusing repository code, standard-library/native features, then installed dependencies, before writing new code.
- Keep diffs scoped. Preserve unrelated edits; do not reformat, rename, or refactor adjacent code without a task-related reason.
- Simplicity must preserve correctness, clarity, accessibility, validation, security, and useful tests.
- For a bug tied to a file or line, inspect `git log`/`git blame`, then relevant `git show`, before fixing it. See [bug-investigation.md](docs/agent-playbooks/bug-investigation.md).
- Use existing evidence or a focused test before adding instrumentation. Remove task-owned instrumentation after verification.
- When a change finishes or reshapes an item in [roadmap.md](roadmap.md), or settles a decision in [how-it-could-work.md](how-it-could-work.md) or [open-questions.md](open-questions.md), update that document in the same change.
- When the root docs change a claim the site repeats (status, comparison, roadmap steps, open questions), update the site's copy in `src/` in the same change.

## Task router

| Task | Required guidance/check |
|---|---|
| Files under `src/` or `scripts/` | Read the directory's `AGENTS.md` |
| Visual design, layout, CSS, typography, or colour | Use the tokens in `src/index.css`; use the `impeccable` skill for design work |
| Code or automation changed | Select affected checks using [verification.md](docs/agent-playbooks/verification.md); use `agent:verify` for integration/build changes or an explicitly requested full pass |
| React state, effects, or rendering performance changed | Review relevant React guidance; use advisory `yarn doctor` for newly introduced diagnostics |
| Choosing a native control, focus behavior, browser API, or browser-sensitive layout | Consult [Modern Web Guidance](.agents/skills/modern-web-guidance/SKILL.md) for the relevant feature |
| UI behavior/layout changed | Verify the affected flow; select browsers/viewports using [verification.md](docs/agent-playbooks/verification.md) |
| `package.json` changed | Run `corepack yarn install` to synchronize `yarn.lock`; keep `yarn deps:check-pinned` passing |
| Dependencies, moved files, or imports changed | Run advisory `yarn knip`; resolve relevant new findings |
| AI workflow files changed | Edit shared sources, run `yarn ai-workflow:sync`, then `yarn ai-workflow:check` and `yarn ai-workflow:test` |
| Version recommendation, bump, or release preparation | Read [versioning.md](docs/agent-playbooks/versioning.md) |
| Open PR feedback or merge readiness | Use `review-and-merge-pr` within the user's requested scope |
| Work needs a durable handoff/resumption, or one run is long enough to hit context compaction | Use [long-running-agent-workflow.md](docs/agent-playbooks/long-running-agent-workflow.md) |

## Code and design

- Use Corepack-managed Yarn 4, never npm for project dependency changes. Pin exact versions and keep the lockfile synchronized. Yarn enforces a 3-day `npmMinimalAgeGate` and runs no install scripts; preapprove a package or enable scripts in `.yarnrc.yml` only with a stated reason.
- Stack: React 19, TypeScript, Vite, CSS modules, oxlint, oxfmt, the same versions as WeTube. Keep the site static: no router, no server code, no runtime data fetching.
- Add comments for non-obvious constraints or logic, not for obvious code.

## Git and ownership

- Keep `master` releasable. Start new changes on short-lived `codex/feature/*`, `codex/fix/*`, `codex/docs/*`, or `codex/chore/*` branches unless the user requests otherwise.
- For an unrelated task while another branch is active, create a separate descriptive worktree from `master`. Prefer `./scripts/create-task-worktree.sh <type> <descriptive-slug>`; it installs dependencies.
- Related delegated slices may share the task worktree with non-overlapping file ownership. Never switch branches underneath another agent.
- Stage only task-owned changes, using a selective index patch when files contain mixed edits. Do not use `git add -A` as a default.
- Never commit secrets or generated build output. Preserve preexisting artifacts and unrelated changes during cleanup.
- Only commit, push, publish, or merge when authorized. Permission already given for the action persists through its necessary steps.
- When opening a requested PR, target `master` and make it ready for review so review bots run.
- After an authorized merge, clean up only the verified merged branch/worktree; preserve any later or unrelated work. Do not run Git cleanup from lifecycle hooks.
- Use `gh` for GitHub operations. Commit/issue formatting lives in [commit-issue-format.md](docs/agent-playbooks/commit-issue-format.md); provide suggestions when requested, not on every answer.

## Verification and resource ownership

- Verify the affected behavior with the narrowest reliable checks. Add regression tests for non-trivial, testable bugs; do not add tests that merely restate a reversible wording or formatting edit.
- Run applicable checks for the final change once. Repeat or broaden them only after relevant edits, failures, or unresolved concerns. Preserve explicit user, CI, and release requirements. Documentation-only changes need document/workflow checks.
- Before heavy work, inspect existing processes. Stop only stale processes owned by this task; never stop a process of unclear ownership.
- Serialize installs, builds, React Doctor, and browser work across the task. One agent owns heavy verification.
- React Doctor is guidance for newly introduced issues, not a score target. Knip is advisory; do not invent new repository-wide gates.
- Default to fresh isolated Playwright sessions. Reuse a contributor's current browser only when explicitly authorized.
- Use `./scripts/pw-session.sh open <session> ...` and `close <session>` for every browser session. One browser may be active machine-wide. Exit 75 means busy; defer or use the wrapper's bounded wait. Never use `close-all` or `kill-all`.
- Reuse a compatible dev server in the same worktree when safe. Otherwise record and clean up the server/process you start. Never start a server for a documentation-only task.
- Review the final task-owned diff. Use `code-quality-review` for non-trivial changes or an explicit review request; apply high-confidence findings within existing authorization.
- After a bug fix or substantive review correction exposes a preventable mistake, use [retro](.agents/skills/retro/SKILL.md) before finishing to consider the smallest useful prevention.

## Skills and delegation

- Shared skills live in `.agents/skills/`; shared roles in `.agents/roles/` (`browser-check`, `reviewer`). `.claude/skills/` and harness agent files are generated compatibility outputs. See [skills-and-tools.md](docs/agent-playbooks/skills-and-tools.md).
- `impeccable` is a third-party skill installed from `pbakaus/impeccable` and recorded in `skills-lock.json`, as in bitsocial-web; update it from upstream rather than editing it by hand.
- Keep harness-specific hooks, permissions, and metadata explicit; byte-identical files do not establish equivalent runtime behavior.
- Keep model and reasoning choices out of committed skills and custom agents. Use the app's runtime defaults, parent inheritance, and supported invocation-time choices.
- Delegate substantial independent work when it improves speed, context isolation, or independent review. Give each child its scope, acceptance criteria, context, file ownership, and evidence to return; check that evidence before accepting a child's result. Use at most four active workers by default. Browser work always remains serialized.
- Use relevant React skill guidance for state, effect, or performance work, and load only rules that fit a static Vite page; use `you-might-not-need-an-effect` for a focused effect review when the reason is unclear.
- Prefer existing tools and local CLIs. Do not search for or install additional skills merely because a normal coding task mentions their domain.

## Development tooling

Development builds load Agentation and `window.__ELEMENT_SOURCE__` (from `src/lib/dev-tools.ts`) for visual feedback and source inspection; production builds omit both. Use `inspect-elements` for source attribution.

## Local commands and playbooks

Canonical dev URL: `https://modelswarm.localhost` (`corepack yarn start`); other worktrees may use branch-scoped `*.modelswarm.localhost`. Preserve the launcher's HTTPS proxy on port 443. Direct Vite fallback: `PORTLESS=0 yarn start` (port 5191). `corepack yarn build` writes the production build to `build/`.

Common checks: `yarn agent:verify` (lint, type-check, build, conditional workflow check, advisory Knip), `yarn doctor`, `yarn knip`, `yarn deps:check-pinned`, `yarn ai-workflow:sync`, `yarn ai-workflow:check`, `yarn ai-workflow:test`, `./scripts/pw-session.sh status`.

Load details on demand: [hooks](docs/agent-playbooks/hooks-setup.md), [verification](docs/agent-playbooks/verification.md), [skills/tools](docs/agent-playbooks/skills-and-tools.md), [long-running work](docs/agent-playbooks/long-running-agent-workflow.md), [known surprises](docs/agent-playbooks/known-surprises.md).
