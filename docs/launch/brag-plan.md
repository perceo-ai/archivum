# Brag Plan: Archivum

## What is this app?
Archivum is self-hosted memory for coding agents: the decisions, fixes, and repo
context your agents learn live in one markdown vault you own, reachable from every
machine you link, reviewed and cited before anything is written.

## The angle
Not "AI memory, but faster." The project's own docs forbid that claim — an
Archivum lookup is a network round trip and is *slower* than reading a local
`CLAUDE.md`. So the video brags about the two things that are actually true and
actually rare: **the same memory on every machine**, and **memory you can open,
cite, and revoke.** The premise is a quiet infrastructure film: start at the
problem (memory stranded on one laptop), then show the real terminal and the real
answer, then land on the review line that is literally in the product's UI —
*"Nothing enters without you."*

Specificity comes from using only real strings: the real install one-liner, the
real `amk_…` key prefix, the real `recall_fix` call, and a real bug from the
README (a streamable-HTTP client hitting `/sse` gets `405 Method Not Allowed`).

## Hook (first 2-3 seconds)
Near-black frame. One small mono file chip — `~/.claude/CLAUDE.md` — with a dim
label `this laptop only`. Then the line lands hard and holds:
**"Your agents' memory is stuck on one laptop."**
The chip stays lit for a beat, then goes grey. That grey is the problem.

## Key moments (the middle)
- The install one-liner typing out character by character, then three real
  confirmations landing one at a time: CLI installed → device key minted
  `amk_9f2c…` → clients configured (Claude Code · Cursor · Codex · Hermes).
- `archivum index` run from inside a repo, with a plain file/chunk count — the
  point being it runs on the machine the code is actually on.
- An agent calling `recall_fix(symptom="405 Method Not Allowed")` and getting a
  short, correct answer back **with a citation chip** pointing at the page it
  came from. This is the whole product in one frame.
- The review row: something waiting, not written. `Nothing enters without you.`

## Outro / punchline
The wordmark, then the line the README leads with, reframed as a promise rather
than a feature: **"Memory your agents use. Memory you can open."** Under it, the
quiet one: `your data, your disk.`

## User flow worth showing
Entry → key action → result, all three are real and all three are in the video:
1. **Entry:** `curl -fsSL https://your-archivum/install | sh` on a fresh machine —
   the CLI installs, mints this machine its own key, and configures every client
   it finds.
2. **Key action:** `archivum index` inside a repo, uploading what git will admit
   to, so the server can build the code graph.
3. **Result:** an agent calls `recall_fix(...)` from a *different* machine and
   gets a cited answer — plus the review queue holding back anything under the
   confidence threshold.

## Tone
- Preset: `polished`
- Creative direction: honest infrastructure film — the confidence is in the
  restraint and in refusing the claim everyone else makes
- Interpretation: long holds, few elements per frame, soft crossfades and slides,
  no zooms or flashes. Type does the work. Motion is small and exact — a chip
  settling, a check line dropping in, a cursor blinking. Nothing bounces.

## Format: landscape — 1920x1080
## Duration: 24.02s — four clips carrying five beats. The link → index → recall
flow is the strongest material the video has, so beats 3 and 4 share one
continuous "workbench" clip rather than cutting between two terminals; that is
also what keeps the scene count at `polished`'s 3–4.

## Visual identity (from the project)
- Background: `#0b0b0c` (`--n-0`), panels `#111112` (`--n-1`), raised `#17171a`
- Accent: `#8b6cff` (`--a-500`), lighter accent text `#a58aff` (`--a-400`),
  accent-soft fill `rgba(139,108,255,0.14)`
- Text: `#f2f2f4` primary, `#a4a4ae` secondary, `#74747f` tertiary
- Semantic: ok `#3fb950`, warn `#d8a232`
- Borders: `rgba(255,255,255,0.075)`; radii 6/8/12/16px; motion ease
  `cubic-bezier(0.32, 0.72, 0, 1)`
- Display font: Instrument Sans (`--font-sans`)
- Body/code font: JetBrains Mono (`--font-mono`) — the terminal and every key,
  path, and tool call must be mono; it is half the product's visual identity
- Serif accent available but unused: Newsreader
- Strongest visual element: the dark panel + hairline border + violet-soft chip
  vocabulary from `tokens.css` (`.card`, `.chip`, `.chip-accent`, `.eyebrow`,
  `.kbd`), rebuilt as a terminal and a result card

## Share copy (draft)
Built Archivum: self-hosted memory for coding agents. One curl per machine, your
own markdown vault, every answer cited back to the page it came from — and
nothing gets written to it without you.

## Audio direction
- Role: sparse professional accents over a low, steady bed
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` — steady and
  clean, the `polished` pick
- Music treatment: start at 0, volume 0.30, 0.6s fade-in, fade out over the last
  1.2s under the wordmark. No swell, no drop.
- Music cue guidance: bundled preset read
  (`assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`,
  109.96 BPM). Three strong-cue locks: **8.74s** (terminal appears), **17.47s**
  (the answer sets), **18.56s** (the citation lands). Beat grid for the three
  install confirmations: every *other* beat at 10.37 / 11.46 / 12.55 (~1.09s
  apart), never consecutive beats — each line must clear the reading floor.
- Audio-reactive treatment: subtle; let the violet accent glow and the terminal
  panel's presence breathe slightly with RMS. No waveform, no equalizer, no text
  scaling.
- SFX posture: sparse, motion-matched, 0.55–0.70 volume. Randomized keypresses
  during typing only, one soft drop per confirmation line, one restrained bell on
  the cited answer, one soft accent on the wordmark. Nothing aggressive anywhere.
- Audio-coupled moments: the typed install line; the three confirmations landing
  one by one; the citation chip appearing under the answer; the wordmark.
- Restraint rule: no impact punches, no glitch, no error buzzes, no stacked hits.
  If a cue is not matched to something visibly moving, cut it. Silence between
  cues is correct for this tone.

## Storyboard

Final timings as built. Four root clips, overlapping by 0.40s so each scene
crossfades through the persistent background rather than cutting to black.

### Clip 1 — The stranded laptop — 0 → 4.79s (content 0 → 4.39)
Left-anchored headline **"Your agents' memory is stuck on one laptop."** (88px,
three lines, staggered in from 0.70s, fully settled by ~1.45s and held ~2.9s).
Right: a panel holding the mono path `~/.claude/CLAUDE.md` with the label
`this laptop only`, settling at 0.30s. At 3.60s the panel desaturates to grey and
the problem is stated without a word of copy about it.
Sequential/interaction: yes — panel settles, then the headline arrives line by
line, then the panel greys. Three discrete beats.
Audio intent: establish quiet; the bed is fading in and almost nothing else.
Audio-coupled: one soft `interface/drop_001` at 0.25s as the panel settles.
Nothing on the greying — the absence of sound is the point.
Transition mood: soft crossfade → Clip 2

### Clip 2 — Archivum — 4.39 → 9.14s (content 4.39 → 8.74)
Left-anchored lockup: the real `perceo-logo.png` plus the wordmark **Archivum**
(104px) from 4.60s; a violet rule draws left→right from 5.05s; the line
**"Memory your agents use. Memory you can audit."** (48px) at 5.42s, held ~2.9s;
mono sub `self-hosted · markdown on your disk` at 6.02s. Right: a slowly drifting
stack of three markdown pages built from the app's own panel tokens — the vault,
not a ghost letterform.
Sequential/interaction: yes — lockup, rule draw, line, mono sub.
Audio intent: arrival, but calm. A product with nothing to shout about.
Audio-coupled: `interface/bong_001` at 5.05s on the rule draw, quiet.
Transition mood: soft crossfade → Clip 3

### Clip 3 — The workbench: link, index, recall — 8.74 → 20.06s (content 8.74 → 19.66)
One continuous clip carrying two beats in the same two-column frame.

*Beat A — one line, any machine.* The terminal panel rises at 8.74s
(**beat-locked**). Eyebrow `ANY MACHINE` and the linked-devices panel — three real
rows, `macbook-pro / studio-desktop / ci-runner-03` each with its own `amk_…` key
and last-seen — arrive on the right. From 9.10s the install one-liner
`$ curl -fsSL https://your-archivum/install | sh` types character by character
over 1.1s behind a violet block cursor. Three confirmations then land one at a
time at **10.37 / 11.46 / 12.55s** (**beat-grid**, every other beat): `✓ CLI
installed`, `✓ device key minted amk_9f2c…`, `✓ configured Claude Code · Cursor ·
Codex · Hermes`. All three hold together until 14.20s.

*Beat B — index, then recall.* At 14.20s the confirmations clear and the same
panel takes `$ archivum index` (typed 14.40–14.90s), resolving into `walking
repository · honouring .gitignore` (15.00s), `847 files · 12,304 chunks ·
uploaded` (15.55s), `✓ code graph rebuilt on the server` (16.10s). The devices
panel hands the right column over at 16.06s and the result card slides in from
the right at 16.38s, labelled `A DIFFERENT MACHINE`: the call
`recall_fix(symptom="405 Method Not Allowed")` at 16.80s, the answer
**"Streamable-HTTP client pointed at /sse. Use /mcp."** at **17.47s**
(**beat-locked**, held 2.2s), and the violet citation chip
`docs/architecture/agent-access.md` at **18.56s** (**beat-locked**).
Sequential/interaction: yes throughout — per-character typing with a block
cursor, three staggered confirmations, three staggered index lines, then a
five-step card reveal.
Audio intent: the sound of the thing actually working — small, dry, mechanical —
then one earned accent.
Audio-coupled: randomized `keyboard/keypress-*.wav` at 0.20 every fourth
character on both typed commands; one `interface/drop_001` at 0.55 per
confirmation, on the beat grid; `casino/card-slide-3` as the card enters; one
`impact/impactBell_heavy_000` at 0.55 as the citation lands — the only bell in
the video, because the citation is the claim.
Transition mood: soft crossfade → Clip 4

### Clip 4 — Nothing enters without you — 19.66 → 24.02s
A review row from `StreamSurface` arrives at 19.66s: `mcp streamable-http
transport` with a warn chip reading `waiting for review` — something the vault is
deliberately *not* writing. The line **"Nothing enters without you."** (76px)
lands at 19.90s and holds 1.6s. At 21.50s the row clears; at 21.84s the wordmark
returns with a violet rule, **"Memory you can open."** (52px), and the mono sub
`your data, your disk.` at 22.37s. The bed fades out under it.
Sequential/interaction: yes — row + chip, the line, then the handover to the
wordmark. Both closing lines hold to the last frame.
Audio intent: close the loop and get out of the way.
Audio-coupled: one `interface/drop_002` as the `waiting for review` chip appears.
Nothing on the wordmark — after a bell in Clip 3, silence is the stronger ending.
Transition mood: hold to end

**Music mood for this video:** steady, clean, low — present but never leading.
**Audio summary:** A quiet bed runs the full 24 seconds, fading in over 0.6s to
0.30 and out over the last 1.2s; typing and three dropped confirmations give the
middle its texture; a single bell marks the cited answer; the outro is
deliberately near-silent. Throughout, the violet ambience breathes with
pre-extracted per-frame RMS and bass — nothing carrying text moves.
