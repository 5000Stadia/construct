# Pinned Awareness — host spec (DRAFT, under group review)

**Status:** initial draft, circulated to K / Cx / PB for full draft-then-review
before any build. Construct-owned (host layer). Element 1 of the
[Awareness & Shape](AWARENESS-AND-SHAPE.md) plan; PB round-robin conclusion
(dev_inbox 060/061) assigned the awareness layer to Construct, leaning on
existing engine reads (containment, valid-time, presence) with **no new engine
primitive** (scoped-pin inheritance is a host recipe over closure reads, per
RFC-001 Fork A).

## 1. Purpose
Some world facts must be in the agent's awareness **unconditionally within their
scope** — not only when a scope read happens to touch them. Gravity ½ on a
planet, "water −1000 L/hr," "bomb in 12h," "this group takes offense at the word
*vegetable*." Today Construct briefs only *scope-derived* facts (the room + arc
entities); a universal that isn't in the current room never lands. This layer
adds a **pin channel**: facts/conditions that are foregrounded every turn their
scope is active, with a salience that rises toward relevance and a lifecycle that
lets them recede to history once spent.

It is the generalization of the existing **arc clocks** (which already do "if X
by turn N"): a pinned countdown is a clock whose urgency is briefed.

## 2. What a pin is
A pin marks an existing canon fact/condition as awareness-bearing. Proposed
shape — a `pin:<id>` entity (authored at session-zero or minted at runtime):
- `subject` — the fact/entity/condition it foregrounds (e.g. `place:luna·gravity`,
  a `fact:`, or a clock).
- `scope` — one of: **region** (an anchor entity; active when the protagonist is
  within its containment subtree), **temporal** (a valid-time window), **social**
  (an entity/group; active when a member is present in the scene). A pin may carry
  more than one axis (a region+temporal pin: "only on Luna, only during the
  storm").
- `salience_kind` — how urgency is derived (see §4).
- `text`/`directive` — the host-facing phrasing the narrator weaves in (the
  *meaning* layer; engine never sees it).

A truly-global universal is just a pin anchored to the world root.

## 3. Scope resolution (reuses existing engine reads — no new primitive)
Each turn the loop already computes the three context axes; a pin is **in frame**
iff its scope matches:
- **Region** → `locate(protagonist)` + containment ancestry. A pin anchored to
  `place:luna` is active in every place contained in Luna (read up the chain).
  *Host recipe over closure reads; PB ruled no engine primitive needed.*
- **Temporal** → the pin's `valid_from`/`valid_to`. Active iff `now ∈ window`.
- **Social/presence** → `contents(scene)` ∩ the pin's entity/group. Active iff a
  member is present.

**Awareness = scene-reads ∪ active-scoped-pins**, assembled in the briefing.

## 4. Salience (urgency as a function of scope-proximity)
A pin carries a salience score the briefing uses to order/foreground it and to
modulate the nudge/pacing ladder:
- **Temporal:** rises as the deadline nears — at 6/12 hours the bomb is loud; at
  11/12 it dominates. Proposed: `salience = f(1 − remaining/window)`.
- **Region:** steady-state while in-scope (a constant law).
- **Social:** spikes the turn a member enters; steady while present.

Salience never *forces* prose (P7 — interpretation stays the narrator's); it
ranks what the narrator must be *aware* of and how hard to foreground it.

## 5. Lifecycle (pinned-while-live → yesterday's history)
A pin's active window closes when its scope lapses — the temporal window passes,
the region is left, the group departs, or the underlying condition resolves
(the bomb fires / is defused). On close it **recedes from awareness to history**:
it is no longer pinned, but its firing is a normal event in the timeline,
retrievable via `what_happened`/the situation lens. This is exactly the situation
lens's live-vs-dead distinction — a pin is a live thread while in-scope, a closed
event after. (A region/social pin doesn't "fire"; it simply isn't in frame when
out of scope, and returns when back in scope — laws are evergreen, not spent.)

## 6. Integration point
The turn loop's briefing assembly (`turnloop.run_turn`, the BRIEFING section)
gains a `PINS (in frame now)` block: resolve active pins, order by salience,
render their directives. Clocks feed temporal pins. No engine write-path change.

## 7. Explicitly out of scope (deferred / triggered — per the conclusion)
- **Rate quantities** (water −1000 L/hr) — stored baseline/rate/reference facts +
  host as-of arithmetic. A *temporal pin can reference* such a fact, but the
  rate-fact mechanism itself is triggered-deferred (needs a draining-resource
  fiction). This spec just pins the awareness of it.
- **Looping time** — host orchestration (re-enter as-of + per-iteration frames);
  a temporal pin may *announce* a loop but doesn't implement it.
- No new engine primitive is requested by this spec.

## 8. Open questions for the reviewers
- **K (host discipline):** does the `pin:` entity + briefing-block fit the
  arc/clock layer cleanly, or should pins *be* clocks with a salience field?
  Is the scope-resolution recipe the right host shape, and is anything here
  drifting toward the engine?
- **Cx (shape / adversarial):** is "awareness = scene ∪ scoped-pins" sound under
  as-of (a pin's window + the scene read must share the same `valid_as_of`)? Any
  way region-inheritance or presence-resolution forces a full-log scan (→ would
  need the engine affordance after all)? Salience formula failure modes?
- **PB (engine truth):** confirm the scope reads (containment ancestry, valid-time
  window, scene-contents membership) are all expressible on shipped porcelain
  with no new primitive — and flag if the region-pin inheritance read wants the
  same affordance as the frame-inheritance question you've been circling.

## 9. Not built yet
This is a draft for review. On integration of the group's markup, Construct
implements the pin channel in the turn loop; nothing ships before the review
lands.
