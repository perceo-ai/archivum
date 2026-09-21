# Launch video

A 24-second tour of Archivum: memory stranded on one laptop, then the install
one-liner, `archivum index`, and a different machine getting a cited answer back
out of the vault.

| File | What it is |
|---|---|
| [`brag.mp4`](brag.mp4) | The video — 1920×1080, 30fps, 24.0s, music and SFX baked in. The poster is baked as frame 0, so link previews land on it. |
| [`brag.jpg`](brag.jpg) | The poster still, for `<video poster>` or a platform that takes a custom thumbnail. |
| [`share-copy.txt`](share-copy.txt) | The caption. |
| [`brag-plan.md`](brag-plan.md) | The creative plan and the final storyboard, beat by beat. |
| [`composition-brief.md`](composition-brief.md) | The handoff brief: source material, palette, copy that had to appear verbatim. |
| `composition/` | The [HyperFrames](https://hyperframes.heygen.com) project the video renders from. |

Every string on screen is real: the install command, the `amk_…` key prefix, the
client list, the `405 Method Not Allowed` bug (straight out of the root README),
and the review line from `apps/frontend/src/surfaces/StreamSurface.tsx`. The
palette and type come from `apps/frontend/src/styles/tokens.css`.

## Re-rendering

The music track is **not committed** — its license terms were never verified for
redistribution, so only the rendered video carries it. Put a track back before
rendering:

```bash
cd docs/launch/composition
cp <your-track>.mp3 assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3
npx hyperframes check     # the gate: lint, runtime, layout, motion, WCAG contrast
npx hyperframes render --quality looks --output ../brag.mp4
```

Until a file is at that path, `check` stops on
`audio_src_not_found: ... The rendered video will be silent.` That is a lint
**error**, which also switches off the layout and contrast audits — so a clean
`0 error(s)` there means nothing until the track is back. Restore it first, then
read the result.

Everything the music drives is committed, so putting the track back restores the
sync with no re-analysis: the beat-locked reveals read
`assets/music/cues/*.music-cues.json`, and the ambient glow reads pre-extracted
per-frame RMS/bass from `assets/music/audio-bands.js`. A *different* track needs
both regenerated — `npx hyperframes beats` for the grid, and the
`extract-audio-data.py` helper in the `hyperframes-creative` skill for the
bands.

## Asset licensing

| Asset | Source | Licence |
|---|---|---|
| `assets/sfx/{casino,impact,interface}` | [Kenney.nl](https://kenney.nl) | CC0 |
| `assets/sfx/keyboard` | [Keyboard Soundpack #1](https://opengameart.org/content/keyboard-soundpack-1-typing-and-single-keystrokes) by unicae_games | CC0 |
| `assets/fonts/InstrumentSans-latin.woff2` | [Instrument Sans](https://fonts.google.com/specimen/Instrument+Sans) | SIL Open Font License 1.1 |
| `assets/fonts/JetBrainsMono-latin.woff2` | [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) | SIL Open Font License 1.1 |
| Music (not committed) | "Happy Beats / Business Moves" by [ende.app](https://ende.app/en) | Unverified — see above |
