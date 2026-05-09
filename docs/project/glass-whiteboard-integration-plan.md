# Glass Whiteboard Integration Plan (Mounting, Alignment, Hardware)

**Owner:** wrench  
**Project:** Modular Wood Desk Organizer + Glass Whiteboard

## Goal
Create a safe, repeatable mounting approach for a glass whiteboard, including:
- Dimension capture procedure
- Alignment/leveling checks
- A mounting hardware checklist
- Clearance considerations (especially power / power strip proximity)

---

## Assumptions / Constraints
- The glass is **tempered** (typical for whiteboards) and must be handled using edge protection.
- Mounting plane is vertical (wall/board/vertical frame). If yours is different, adjust anchor strategy.
- The board’s weight and attachment method must be treated as **non-negotiable** (follow manufacturer load guidance where available).

---

## Required Inputs (measure before choosing hardware)
Record these in your build log:
1. **Board footprint**
   - Width (W)
   - Height (H)
   - Thickness (T)
2. **Mounting point geometry**
   - Distance from top edge to first mounting hole/fastener (Y1)
   - Distance between mounting points (Y2) or pattern (e.g., 2-point vs 4-point)
   - Whether mounting holes are **in glass** or the board has a **frame/backer**
3. **Clearances**
   - Minimum distance from mounting plane to any obstruction (cables, trim, outlet covers)
   - Desired gap between glass and any structural element (recommended: use spacers)
4. **Wall / substrate**
   - Material (stud/plywood/MDF/brick/metal rail)
   - Allowable fastener types (wood screws vs anchors vs through-bolts)
   - Surface flatness (roughness)

---

## Recommended Mounting Approach (conservative + serviceable)
### Option A (recommended): Two vertical rails + standoff spacers + compliant isolators
Use this when you want predictable alignment and lower risk of localized stress on glass.

**Concept:**
- Install **two vertical rails** (left/right) on the substrate.
- Use **standoffs/spacers** and **compliant isolation** (rubber/EPDM gaskets) between rail and glass frame.
- Glass is located by a consistent datum (rails + spacer stack), then fastened using the board’s intended interface (often through slots/holes in a frame).

**Why this works:**
- Distributes load across rails.
- Makes alignment verification straightforward.
- Allows easy re-leveling by adjusting shims/fastener tolerance.

### Option B: Bracket + corner pads (only if the board design is explicitly bracket-friendly)
Use if your specific whiteboard is meant to be installed with bracket points.

---

## Mounting Hardware Checklist (types, not brand)
Use a checklist like the one below to confirm every component exists **before** drilling.

### Structural / location
- [ ] Two vertical rails (or equivalent mounting channels)
- [ ] Rail brackets/landing points (stud anchors, threaded inserts, or through-bolts)
- [ ] Shims (thin steel/plastic) for fine alignment

### Isolation / glass protection
- [ ] EPDM/rubber isolation pads or gaskets (rated for the load interface)
- [ ] Edge-safe glass interface protectors (if your design uses pads at mounting points)
- [ ] Spacer set (nylon/aluminum with non-marring surfaces as needed)

### Fasteners
- [ ] Substrate fasteners matching the substrate type (wood screws, lag bolts, or anchors)
- [ ] Rail-to-substrate fasteners (with washers)
- [ ] Glass-to-rail interface fasteners (only those that match the board/frame design)

### Tools & measuring helpers
- [ ] Laser level (or long level) for vertical and horizontal reference
- [ ] Tape measure
- [ ] Marker + square
- [ ] Drill bits appropriate for substrate
- [ ] Torque driver (recommended)

---

## Alignment & Verification Procedure
Do these checks in order; stop if you’re outside tolerance.

### 1) Establish datums
- [ ] Mark a **centerline** for the board placement height.
- [ ] Mark the **left/right mounting datums** where rails will land.

### 2) Install rails (first pass)
- [ ] Mount the rails using slotted mounting holes or shim tolerance.
- [ ] Verify:
  - [ ] Rails are **plumb** within your tolerance target (aim for ≤1–2 mm deviation over board height).
  - [ ] Rail spacing matches board mounting interface geometry.

### 3) Dry-fit the glass (no final tightening)
- [ ] Place spacers/gaskets in the intended stack.
- [ ] Seat the glass/frame onto the rails.
- [ ] Confirm:
  - [ ] The glass sits flat against spacers (no rocking)
  - [ ] Fasteners engage smoothly without forcing the glass
  - [ ] Alignment matches the datums

### 4) Final leveling
- [ ] Use shims to correct any slight tilt.
- [ ] Tighten fasteners gradually and evenly.
- [ ] Re-check laser level after tightening.

### 5) Mechanical safety checks
- [ ] Confirm no glass edge contacts sharp metal.
- [ ] Confirm isolators are fully seated (no pinching).
- [ ] Confirm the mount can’t shift if gently pushed (within safe handling limits).

---

## Power / Power-Strip Clearance Guidance
Because this build often overlaps desk electronics:
- [ ] Identify all outlet/power strip locations **before** finalizing rail placement.
- [ ] Maintain a clearance buffer to allow:
  - Cable bend radius
  - Plug insertion/removal
  - Service access without removing the board
- [ ] If using a power strip behind/near the mount plane, ensure ventilation space and avoid direct contact with any surface that can trap heat.

> Practical rule: if a cable must pass within a few cm of the mount plane, re-check your rail/fastener locations so you never end up drilling into the cable path.

---

## Documentation Artifacts to Create During the Build
After measurements, save the following so the integration is repeatable:
- [ ] A one-page measurement sheet with W/H/T and mounting point distances
- [ ] A simple diagram of rail locations and spacer stack-up
- [ ] Photos of:
  - Rails installed and plumb
  - Dry-fit before final tightening
  - Final mounted assembly
- [ ] Complete the full assembly/finish/power checklist: `docs/project/modular-wood-desk-organizer-glass-whiteboard-assembly.md`

---

## Open Questions (fill in during real measurements)
- [ ] What is the board’s mounting interface (holes in frame vs slots vs corner brackets)?
- [ ] What substrate are we drilling into (studs/plywood/MDF/etc.)?
- [ ] Final target location: centerline height from desk surface?

---

**Next action (wrench):** capture actual mounting-point distances from the specific whiteboard, then convert this plan into a dimensioned rail layout for the final build.