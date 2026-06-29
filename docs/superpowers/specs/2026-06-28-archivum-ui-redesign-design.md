# Archivum UI Redesign

Date: 2026-06-28
Status: Proposed and user-approved in chat

## Goal

Redesign Archivum into a calmer, better-looking workspace with:

- fewer top-level tabs
- a stronger editorial/workspace feel
- better typography
- better colors
- less clutter
- a clearer mental model for finding pages and switching modes

The target shell is a `library + studio hybrid` with a strict grouped navigation model:

- `Library`
- `Workflows`
- `Tools`

## Customer Impact

- Makes the product feel intentional instead of improvised
- Reduces navigation overload by removing the current wall of tabs
- Makes reading and editing feel more trustworthy and less exhausting
- Keeps power-user page management available without forcing it on screen at all times
- Gives the product one coherent identity across wiki, planning, and utility surfaces

## Current Problems

The current frontend has a few obvious issues:

- The top bar is overloaded with too many equal-weight destinations
- The shell feels like separate tools bolted together instead of one product
- The permanent left tree and right panel make the app feel cramped
- The dark palette and default font stack make the app feel generic and heavy
- Important workflows compete visually with utility routes
- The right sidebar uses tabs, which adds another layer of chrome inside an already crowded shell

## Chosen Direction

### Shell model

Use a focused studio shell:

- one permanent left icon rail
- one slim top bar with a command/search surface
- one main content column
- one quiet contextual right inspector
- one slide-out vault drawer for page selection and page management

### Page selection

Page selection will use a vault drawer, not a permanent second column and not only a quick switcher.

The drawer should:

- open from the `Library` section
- support search/filter
- support folder browsing
- support page creation and folder creation
- preserve drag/drop and move flows where practical
- close when the user has selected a page or dismissed it

### Navigation model

Replace the current many-tab top navigation with three grouped sections:

#### Library

Primary home for:

- wiki reading/editing
- page search
- vault navigation

This is the default mode of the product.

#### Workflows

Group these together:

- daily
- projects
- tasks
- decisions
- activity

These routes should no longer appear as separate global tabs. They should live under a shared page-level workspace with internal navigation.

#### Tools

Group these together:

- graph
- ingest
- lint
- settings

These routes stay accessible, but become secondary to the core library/workflow experience.

## UX Rules

### Navigation and shell

- Remove the global top tab row entirely
- Use the icon rail as the primary app-wide navigation
- Keep labels visible through tooltips and section headers, not a dense always-open nav strip
- Preserve route continuity so switching sections feels like moving inside one system

### Vault drawer

- The drawer is the primary page picker
- It should feel lightweight and fast, not like a heavy modal
- It should keep current useful actions: new page, new folder, filter, import
- It should visually emphasize reading/browsing over admin chrome

### Right inspector

- Remove the current tabbed feel
- Turn it into a quieter contextual inspector
- Prefer stacked sections instead of mini-tab switching
- Show only information that supports the current page or route

### Search

- Promote search into the top bar as a command surface
- Search should feel global and keyboard-first
- Search inside the vault drawer can stay focused on page selection and filtering

### Page headers

- Every major surface should use a calmer editorial header
- Titles should be larger and cleaner
- Metadata should be quieter
- Actions should be fewer, clearer, and right-aligned

## Visual System

### Theme

Use a warm light workspace palette:

- parchment or warm-ivory background
- soft white surfaces
- dark slate text
- muted blue-gray supporting text
- restrained amber accent for active states and highlights
- deep ink/blue rail for shell contrast

This should feel like a crafted library workspace, not a dark app and not a generic SaaS dashboard.

### Typography

- Replace the default system-feel body stack with a more intentional editorial sans
- Keep monospace only for technical metadata, slugs, paths, and system details
- Strengthen hierarchy between titles, metadata, body copy, and chrome labels
- Make editor typography cleaner and more document-like

### Shape and spacing

- Medium radii, not pill-heavy and not fully square
- Fewer visible borders, more soft contrast and spacing
- More breathing room in headers and content surfaces
- Less card spam

### Motion

- Small transitions only
- Drawer slide, hover, focus, and panel transitions
- No decorative animation

## Route Behavior

### Library

#### Wiki

- Becomes the flagship surface
- Use a cleaner document header
- Keep title, tags, save, share, delete
- Improve spacing and hierarchy around metadata and actions
- Keep the editor central and readable

#### Search

- Move core search affordance into the top bar
- The dedicated search route can remain as an expanded results/workbench surface inside Library

### Workflows

Workflows becomes one grouped area with internal sub-navigation or segmented switching for:

- daily
- projects
- tasks
- decisions
- activity

This area should feel like one planning studio, not five unrelated apps.

### Tools

Tools becomes one grouped area with internal navigation or a tools index for:

- graph
- ingest
- lint
- settings

This area can be denser and more utilitarian, but still uses the same shell and visual system.

## Implementation Shape

### Shared shell rewrite

Rewrite first:

- `Layout.tsx`
- shared navigation structure
- top bar
- icon rail
- vault drawer
- contextual inspector
- status bar styling
- theme tokens
- button/input/card styling where needed

### Route integration

Then adapt routes to the grouped shell:

- Library routes
- Workflows grouped surface
- Tools grouped surface

### Inspector simplification

Refactor the right sidebar so it supports:

- stacked panels
- route-aware sections
- no inner tab clutter unless absolutely necessary

## Non-Negotiables

- Do not keep the current top tab row
- Do not keep the current dark generic look
- Do not make page selection harder than it is now
- Do not hide core page creation behind confusing flows
- Do not turn the product into a generic analytics dashboard
- Do not add abstraction-heavy architecture unless the rewrite needs it

## Verification Bar

Before calling the redesign done:

- verify the grouped shell works on desktop and mobile widths
- verify page selection through the vault drawer
- verify wiki editing still feels fast and readable
- verify workflows and tools are easier to scan than before
- run frontend tests if available
- run typecheck if available
- run lint if available

Success means:

- the app no longer feels visually cramped
- the app no longer feels tab-heavy
- the UI has a clear visual point of view
- the main user flows are still easy to reach
- the product feels like one coherent workspace
