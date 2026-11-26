# Versioning and release readiness

Use this guide before recommending a version, changing the CLI version, or preparing a release. Choose the version from the published baseline and the compatibility impact of the whole change.

## Choosing the version

ModelSwarm uses [Semantic Versioning](https://semver.org/). Keep documented usage compatible within a pre-1.0 minor line so people can upgrade between patches.

| Change                                                                 | Before 1.0                     | From 1.0 onward                |
| ---------------------------------------------------------------------- | ------------------------------ | ------------------------------ |
| Compatible bug fix, performance improvement, or dependency maintenance | Patch                          | Patch                          |
| New documented capability or deprecation                               | Minor                          | Minor                          |
| Intentional break to supported usage                                   | Minor, with migration guidance | Major, with migration guidance |
| Website, docs, tests, or internal tooling only                         | Usually no CLI release         | Usually no CLI release         |

The supported CLI surface includes documented commands, flags, environment variables, exit codes, and JSON output consumed by scripts. Check whether a change still reads supported manifests and signed releases and can resume existing transfers or explain how users migrate. Check changes to supported Python, Node, Kubo, and platform versions. Internal implementation details are free to change within those contracts.

The CLI package version is in [`cli/pyproject.toml`](../../cli/pyproject.toml) and the displayed `modelswarm --version` value is in [`cli/src/modelswarm/__init__.py`](../../cli/src/modelswarm/__init__.py). Update both for a CLI release. Use a matching `vX.Y.Z` Git tag and GitHub release. The website and Node bridge are private packages. Versioned manifest and signed-release schemas have their own compatibility rules, and a publisher’s model release version identifies the model files.

## First release

`v0.1.0` is the first public CLI milestone. Scope it as an experimental GitHub release installed from source, covering verified downloads, signed publishing and pulls with a compatible PKC node, and the local Hugging Face SDK endpoint. State which platforms and installation methods were exercised. Forge RPC onboarding, search, desktop packaging, and untested platforms can follow in later releases.

Before publishing:

1. Check GitHub tags and releases and any package registry used by the project. Verify the intended commit and release contents against the actual published baseline.
2. Install from a clean checkout of the candidate on each platform listed as supported. Check the package version, `modelswarm --version`, the [quickstart](../../README.md#getting-started), and the optional bridge on platforms where signed releases are supported.
3. Run the relevant [repository checks](verification.md), including interrupt/resume and a signed, peer-only WAN pull with default checkpoint settings. Run the signed integration suite with its pinned Kubo version when verifying signed publishing or reading.
4. Write release notes with installation commands, changes, supported platforms, and known limitations. Verify the published tag’s source and install path. Treat PyPI, standalone installers, and new platform support as separate distribution decisions.

The 2026-11-26 checkpoint fix (commit `df10383`) passed a clean source install on macOS arm64. A [fresh Linux x86-64 runner](https://github.com/bitsocialnet/modelswarm/actions/runs/45834809533/job/139960727104) installed from source and verified the 491 MB signed model and license from a public peer with the default checkpoint interval and timeout. Use the same checks for the release tag.

## Readiness for 1.0

- Document the supported CLI commands, machine-readable output, configuration, platforms, and install and upgrade paths.
- Define compatibility and migration for persisted caches, manifests, signed releases, and the local SDK endpoint. Verify reader upgrades against earlier supported data and releases.
- Verify the supported publishing and download paths against real peers and under interruption. Document discovery, recovery, and network conditions that fall outside the supported cases.

Publish 1.0 when the project can maintain these guarantees for the 1.x line.
