# src/AGENTS.md

These rules apply to `src/**`, the landing page for modelswarm.org. Follow the repo-root `AGENTS.md` first.

- The page summarises the root design docs. Its words live in `data/content.ts` and in the section components under `sections/`; when a doc changes a claim the page repeats, change the page in the same commit, and never state anything the docs do not.
- Colours and fonts come from the tokens at the top of `index.css`: an acid lime accent on graphite, Oxanium for headings and the wordmark, Red Hat Mono for everything else. The accent marks a verified piece everywhere, so do not use it for decoration. Derive tints with `color-mix()` from the tokens instead of adding literal colours.
- Each component keeps its styles in a CSS module next to it. Section components go in `sections/`, shared pieces in `components/<name>/`.
- The logo is four interlocking file pieces forming a hexagonal swarm mark, with the seams between them widened by a mask (gap 6, the outer size not rescaled). `../public/logo.svg` (favicon and README) and `components/logo/logo.tsx` must draw the same mark with the same gap.
- `../public/og.png` is the link-preview card (Open Graph, X and GitHub's social preview): the logo, wordmark and definition centered on graphite, 1280x640 rendered at 2x. Re-render it when the logo, name or definition changes.
- The hero terminal in `components/pull-terminal/` is an illustration of a download, not a real client; its timeline is seeded so every visit shows the same sequence. It starts when it scrolls into view and shows the finished state under reduced motion.
- Keep the build static: relative asset paths (`base: './'`), no router, no runtime requests to other origins. Fonts are self-hosted through `@fontsource-variable` packages. `lib/dev-tools.ts` is loaded only behind the `import.meta.env.DEV` guard in `main.tsx`; never import it from application code.
- Check layout at desktop and at 375px width with no horizontal scroll, and keep visible keyboard focus.
