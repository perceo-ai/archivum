# Conductor Docs UI Redesign

Date: 2026-06-21
Status: Proposed and user-approved in chat

## Goal

Rewrite the Archivum frontend so the whole product flow and feel matches `conductor.build/docs`, while keeping Archivum's existing product features and Linux-specific workflow customizations.

This is not a partial reskin. The target is a page-by-page rewrite around the Conductor docs mental model:

- shared docs-style shell
- docs-style interaction rhythm
- docs-style typography, spacing, search, and navigation behavior
- Archivum-specific Linux flavor layered on top

## Customer Impact

- Makes the product feel intentional instead of like "AI with bad colors, bad UI, bad UX"
- Reduces friction by giving every route the same predictable shell and interaction pattern
- Preserves existing Archivum value while making the interface easier to trust and use every day
- Keeps Linux/workstation identity visible instead of copying generic SaaS or Mac UI patterns

## Scope

In scope:

- Full frontend shell rewrite
- Page-by-page UI rewrite to the Conductor docs model
- Shared design tokens and component restyling
- Navigation, search, sidebars, headers, empty states, and status feedback
- Linux-specific UI layer that keeps the app feeling workstation-native

Out of scope:

- Copying Conductor marketing/footer/company sections
- Rewriting backend logic unless a small adapter is needed for UI fit
- Removing Archivum-specific product features

## Product Frame

Archivum should feel like a docs-native product shell instead of a dark app with disconnected tools.

### Shell rules

- Use a bright Conductor-docs-style canvas with near-white surfaces.
- Keep a slim top bar, a left navigation rail, a centered primary content column, and a contextual right inspector.
- Keep the shell stable across routes so the user feels like they are moving through one product, not switching apps.
- Keep the status bar, but make it quieter and more system-like.

### Linux flavor rules

- Keep Linux/workstation language in the chrome: `workspace`, `vault`, `host`, `session`, path-like labels.
- Use monospace for technical metadata, shortcuts, slugs, and filesystem references.
- Surface keyboard-first behavior clearly.
- Avoid fake Mac styling and avoid dark neon terminal cosplay.

## Interaction Model

The frontend should move like Conductor docs.

### Navigation

- Left rail is the primary navigation system.
- Active states should be soft, obvious, and consistent.
- Route changes should preserve shell continuity and avoid jarring panel resets.

### Search

- Search should move into the top bar as a first-class command surface.
- Search interaction should be keyboard-first and fast to focus.
- Results should feel like docs search results, but open Archivum routes and records.

### Page headers

- Each route gets an editorial header with:
  - clear page title
  - small metadata row
  - sparse actions on the right
- Remove bulky utility-strip styling.

### Scrolling and pane behavior

- Main content scrolls cleanly inside the content pane.
- Sidebars should feel pinned and calm.
- Headers should remain visually anchored.

### Control language

- Default to smaller, quieter controls.
- Use emphasis only for truly primary actions.
- Empty states should look like docs guidance blocks, not blank dead panels.

## Visual System

### Color

- Match the Conductor docs light base as closely as practical.
- Use near-white backgrounds, pale gray borders, dark text, muted secondary text, and one restrained accent.
- Linux flavor should come from a subtle terminal-adjacent accent, not from a dark theme.

### Typography

- Primary UI and reading typography should follow the Conductor docs editorial style.
- Reserve monospace for technical UI and metadata only.

### Shape and spacing

- Smaller radii
- Flatter surfaces
- Minimal card-heavy framing
- Tight shell chrome with generous content rhythm

### Motion

- Minimal motion
- Hover, focus, expand/collapse, and small state transitions only

### Icons

- Quiet editorial iconography
- No chunky or glossy app-style icons

## Route-by-Route Rewrite

### Shared shell

Rewrite first:

- top bar
- left rail
- right inspector
- status bar
- buttons
- inputs
- cards
- badges
- dialogs
- search shell
- shared page container

### High-traffic routes

Rewrite second:

- `Wiki`
- `Search`
- `Projects`
- `Daily`
- `Tasks`

### Remaining routes

Rewrite third:

- `Decisions`
- `Activity`
- `Graph`
- `Ingest`
- `Settings`
- `Login`

## Page-Specific Design Constraints

### Wiki

- Treat the page like a docs reading/editorial surface.
- Use a cleaner header, quieter metadata, and a readable content frame for the editor.
- Keep save, share, and delete actions, but reduce visual noise.

### Search

- Search should feel like a docs-native search surface, not a utility page bolted on later.
- Results should use strong hierarchy and minimal chrome.

### File tree / vault rail

- Left rail should feel like Conductor docs navigation first, vault browser second.
- Keep Archivum folder and page actions, but hide them behind calmer affordances.

### Right sidebar / inspector

- Keep contextual information only.
- It should feel like a supporting inspector, not a second app column demanding attention.

### Projects / Tasks / Daily / Decisions / Activity

- Present them as editorial workflow/reference pages inside the docs shell.
- Avoid standalone mini-dashboard styling.

### Graph / Ingest / Settings

- Preserve utility behavior.
- Still restyle them into the same docs shell and control language.

## Non-Negotiables

- Do not add marketing-style footer or company chrome.
- Do not preserve the current dark UI direction.
- Do not turn the product into a generic SaaS dashboard.
- Do not remove Linux-specific customization.
- Do not rewrite backend systems unless necessary for small frontend fit issues.

## Recommended Implementation Order

1. Build shared shell and tokens.
2. Rewrite wiki, search, and vault/tree interactions.
3. Rewrite remaining routes into the same system.

This preserves the user's requested "whole product" rewrite, but avoids pointless churn.

## Verification Bar

Before calling the redesign done:

- Compare the implemented shell against `conductor.build/docs`.
- Verify route-to-route continuity across the main product surfaces.
- Verify Linux-specific UI traits still show up in chrome and workflows.
- Run frontend verification for desktop and mobile widths.
- Run tests, typecheck, lint, and build if available in the repo.

Success means:

- The app no longer reads as "AI with bad colors/UI/UX".
- The whole frontend feels like a Conductor-docs-shaped product shell.
- Archivum-specific flows still work.

