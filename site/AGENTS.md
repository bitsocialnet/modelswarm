# site/AGENTS.md

These rules apply to `site/**`, the landing page for modelswarm.org. Follow the repo-root `AGENTS.md` first.

- The page summarises the root design docs. Its words live in `src/data/content.ts` and in the section components under `src/sections/`; when a doc changes a claim the page repeats, change the page in the same commit, and never state anything the docs do not.
- Colours and fonts come from the tokens at the top of `src/index.css`: an acid lime accent on graphite, Oxanium for headings and the wordmark, Red Hat Mono for everything else. The accent marks a verified piece everywhere, so do not use it for decoration. Derive tints with `color-mix()` from the tokens instead of adding literal colours.
- Each component keeps its styles in a CSS module next to it. Section components go in `src/sections/`, shared pieces in `src/components/<name>/`.
- The logo is a 5x5 piece map that spells M with the centre piece still arriving. `public/logo.svg` (favicon and README) and `src/components/logo/logo.tsx` must draw the same mark.
- The hero terminal in `src/components/pull-terminal/` is an illustration of a download, not a real client; its timeline is seeded so every visit shows the same sequence. It starts when it scrolls into view and shows the finished state under reduced motion.
- Keep the build static: relative asset paths (`base: './'`), no router, no runtime requests to other origins. Fonts are self-hosted through `@fontsource-variable` packages.
- Check layout at desktop and at 375px width with no horizontal scroll, and keep visible keyboard focus.
