# Hyperframes Composition Brief: Archivum

## Objective
Create a short launch-style brag video for Archivum — self-hosted memory for
coding agents. Not a feature tour: a proof that the thing works and that you can
see inside it.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 22.93s

## Source Material
- Project root: `/Users/kitts/conductor/workspaces/archivum/beirut`
- Primary files read: `README.md`, `AGENTS.md`,
  `apps/frontend/src/styles/tokens.css`, `apps/frontend/src/shell/AppShell.tsx`,
  `apps/frontend/src/shell/BrandMark.tsx`, `apps/frontend/src/surfaces/StreamSurface.tsx`,
  `apps/frontend/src/sheets/AskSheet.tsx`, `apps/frontend/index.html`
- Product name: Archivum
- Tagline / strongest claim: "Memory your coding agents use and you can audit."
  Second-strongest, and the one the product's own docs insist on: **same memory
  on every machine, less context for the same answer** — explicitly *not*
  "faster than a local file."
- Key UI to recreate: the dark Archivum shell vocabulary from `tokens.css` — a
  `#111112` panel with a `rgba(255,255,255,0.075)` hairline border and 12px
  radius, violet `.chip-accent` pills, uppercase tertiary `.eyebrow` labels, and
  a JetBrains Mono terminal. Plus the real review line from `StreamSurface.tsx`.
- Logo: `assets/img/perceo-logo.png`, copied from `apps/frontend/public/perceo-logo.png`
  (the same file the app uses for its BrandMark and favicon).
- Copy that must appear verbatim:
  - `~/.claude/CLAUDE.md`
  - `$ curl -fsSL https://your-archivum/install | sh`
  - `amk_9f2c…` (the real device-key prefix)
  - `Claude Code · Cursor · Codex · Hermes`
  - `$ archivum index`
  - `recall_fix(symptom="405 Method Not Allowed")`
  - `Streamable-HTTP client pointed at /sse. Use /mcp.`
  - `docs/architecture/agent-access.md`
  - `Nothing enters without you.`
  - `your data, your disk.`

## Creative Direction
- Tone preset: `polished`
- Creative direction: honest infrastructure film — the confidence is in the
  restraint and in refusing the claim everyone else makes
- Interpretation: few elements per frame, long holds, soft crossfades and short
  slides. No zooms, no flashes, no bounce. Motion is small and exact: a chip
  settling, a check line dropping in, a cursor blinking, an underline drawing.
  Type carries the video.
- Angle: Archivum can't claim to be faster than reading a local `CLAUDE.md` — its
  own `AGENTS.md` forbids that claim, because a lookup is a network round trip.
  So the video brags about what *is* true and rare: the same memory on every
  machine, and memory you can open, cite, and revoke. Start at the problem
  (memory stranded on one laptop), show the real terminal and a real cited
  answer, land on the product's own review line: "Nothing enters without you."
- Hook: near-black frame, one mono chip reading `~/.claude/CLAUDE.md` labelled
  `this laptop only`, then the line **"Your agents' memory is stuck on one
  laptop."** The chip greys out and the problem is stated without a word of copy
  about it.
- Outro / punchline: **"Memory your agents use. Memory you can open."** then
  `your data, your disk.`
- Avoid:
  - Generic SaaS language ("streamline", "supercharge", "10x")
  - Any claim that Archivum is faster than a local file — this is a hard product
    constraint, not a style note
  - Abstract filler visuals, particle fields, equalizer/waveform graphics
  - Redesigning the product's look; use its real tokens

## Visual Identity
- Background: `#0b0b0c` (`--n-0`); panel `#111112` (`--n-1`); raised `#17171a` (`--n-2`)
- Text: `#f2f2f4` primary, `#a4a4ae` secondary, `#74747f` tertiary
- Accent: `#8b6cff` (`--a-500`); accent text `#a58aff` (`--a-400`); accent-soft
  fill `rgba(139,108,255,0.14)`
- Semantic: ok `#3fb950`, warn `#d8a232`
- Border: `rgba(255,255,255,0.075)`; strong `rgba(255,255,255,0.13)`
- Radii: 6 / 8 / 12 / 16px. Ease: `cubic-bezier(0.32, 0.72, 0, 1)`
- Display font: Instrument Sans — shipped locally at
  `assets/fonts/InstrumentSans-latin.woff2` (variable, 400–700), declared with an
  in-file `@font-face`
- Body/code font: JetBrains Mono — shipped locally at
  `assets/fonts/JetBrainsMono-latin.woff2` (variable, 400–700). Every path, key,
  command, and tool call must be mono; it is half the product's identity.
- Visual references from the project: the `.card` / `.chip` / `.chip-accent` /
  `.eyebrow` primitives in `tokens.css`; the sidebar+canvas dark shell; the
  review row in `StreamSurface.tsx`
- Scale for video, not web: headlines 72–104px, body 30–40px, mono 28–34px,
  labels 20–24px, borders 2px, decorative opacity 12–25%

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. **The stranded laptop** — 4.39s — mono chip `~/.claude/CLAUDE.md` with
   `this laptop only`; headline "Your agents' memory is stuck on one laptop.";
   chip greys at the end.
2. **Archivum** — 4.35s — Perceo mark + wordmark, violet underline drawing
   left→right, line "Memory your agents use. Memory you can audit."
3. **One line, any machine** — 4.37s — terminal panel; the install one-liner
   types character by character; three `✓` confirmations land one at a time
   (CLI installed / device key minted `amk_9f2c…` / configured across four
   clients). Eyebrow `ANY MACHINE`. All three visible together before the cut.
4. **Index, then recall** — 5.45s — `$ archivum index` resolves to
   `847 files · 12,304 chunks`; frame slides left, result card enters from the
   right showing `recall_fix(symptom="405 Method Not Allowed")`, the answer
   "Streamable-HTTP client pointed at /sse. Use /mcp.", then a violet citation
   chip `docs/architecture/agent-access.md`. Label above the card: `a different machine`.
5. **Nothing enters without you** — 4.37s — review row with a warn chip
   `waiting for review`; the line "Nothing enters without you."; fade to wordmark
   with "Memory your agents use. Memory you can open." and `your data, your disk.`

## Audio
- Audio role: sparse professional accents over a low, steady bed
- Audio arc: bed fades in over 0.6s and holds at 0.30; the middle gets texture
  from typing and three dropped confirmation lines; one bell marks the cited
  answer at the payoff; the outro is near-silent with the bed fading out over the
  last 1.2s.
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
  (steady and clean — the `polished` pick)
- Music treatment: volume 0.30, `data-automation` fade-in 0→0.30 across the first
  0.6s, fade-out 0.30→0 across the last 1.2s under the wordmark. No swell, no drop.
- Music cue guidance: bundled preset copied to
  `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`
  (109.96 BPM). Scene boundaries are already authored on strong cues — lock three:
  **8.74s** (terminal appears), **13.11s** (index→recall turn), **18.56s** (the
  audit beat). Beat grid for the three install confirmations: every *other* beat
  at 10.37 / 11.46 / 12.55 so each line clears the reading floor. Never
  consecutive beats for readable text.
- Audio-reactive treatment: subtle. Per-frame bands are pre-extracted and trimmed
  to the first 700 frames at `assets/music/audio-bands.js`
  (`window.AUDIO_BANDS = { fps, totalFrames, rms[], bass[] }`, both normalized
  0–1 over the used window). Drive only: the ambient violet radial glow's opacity
  and scale, and the terminal/result panel's border luminance and shadow
  presence. Ranges stay inside ±6% on anything carrying text. No waveform, no
  equalizer, no strobing, no text scaling.
- Audio-coupled moments:
  - Scene 1 chip settles — soft drop
  - Scene 2 underline draws — `interface/bong_001`, quiet
  - Scene 3 typed install line — randomized `keyboard/keypress-*.wav` per character
  - Scene 3 three confirmations — one `interface/drop_001` each, on the beat grid
  - Scene 4 result card enters — `casino/card-slide-3` or `interface/drop_002`
  - Scene 4 citation chip lands — `impact/impactBell_heavy_000` at 0.55, the only
    bell in the video, because the citation is the claim
  - Scene 5 `waiting for review` chip — soft drop; **nothing on the wordmark**
- SFX selection guidance: everything must be matched to something visibly moving.
  Keypresses only while characters appear; drops only on line arrivals; the bell
  only on the citation. Volumes 0.30–0.70. If a cue is not matched to motion, cut
  it — silence between cues is correct for this tone.
- SFX analysis guidance:
  `/Users/kitts/.claude/plugins/cache/brag/brag/0.2.2/skills/brag/assets/sfx/sfx-analysis.md`
  — prefer low high-frequency-risk files; the repeated keypresses and drops must
  be low-risk.
- Exact SFX choice: Hyperframes chooses filenames, timestamps, density, and volume
  based on the implemented animation. Files already copied into
  `assets/sfx/{interface,impact,casino,keyboard}/`.
- Audio files: all under `brag-output/composition/assets/` — music, cue preset,
  trimmed bands, SFX, fonts, and the Perceo logo.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core`,
`hyperframes-animation`, `hyperframes-creative`, `hyperframes-keyframes`,
`hyperframes-cli`. This is the `/brag` workflow; do not enter the `hyperframes`
entry-point intent interview or route into its generic promo workflow.

Requirements:
- Show real UI, copy, and visual elements from Archivum (the terminal, the token
  palette, the chip vocabulary, the review line, the real logo file).
- Keep all text readable: short labels ≥0.8s settled, sentences ≥0.3s per word.
- Total duration 22.93s.
- Include the music bed, the SFX layer, and the subtle audio-reactive treatment.
- Treat music cues as hints; ignore any that hurt readability or pacing.
- Lock 3 strong cues (8.74 / 13.11 / 18.56) within ±0.15s, marked `// beat-locked`.
- Snap the three install confirmations to the beat grid (10.37 / 11.46 / 12.55)
  within ±0.10s, marked `// beat-grid`.
- Fade the music under the closing wordmark.
- Use local assets only; no network fetches at render time (GSAP from the CDN in
  `<head>` is the one exception, per the scaffold).
- Run `npx hyperframes check` before render — it is brag's single gate.
