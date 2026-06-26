# Changelog

Notable changes to The Construct. Pre-1.0; dates are development milestones, not releases.

## Unreleased (2026-06)

### Added
- **The conclusion clock** — a story now ends on its own *decisive event* ("IT"), authored per-story
  from what the story is about (the accusation, the protectee's death, the bomb's hour). **Turns
  never force a close**: a no-deadline investigation stays open until the player concludes it — study
  a clue for 300 turns if you like. See `docs/design/CONCLUSION-AND-OUTCOME.md`.
- **Time as a per-story thread** — a soft diegetic deadline (the King's dinner, a bomb timer) is
  authored *only* when time genuinely belongs to the story, as a `Quantity` over the in-world clock;
  it advances before the terminal check so a single big wait crosses it that turn. A leisurely
  mystery authors none, and time-of-day still governs *texture* (appropriateness / NPC availability).
  See `docs/design/DIEGETIC-TIME.md`.
- **Gauge primitive** — numeric quantities as a live dramatic constraint (oxygen draining, a speed
  floor, fuel): a `gauge_level` accrue total + a `Quantity` threshold condition that ends or colors
  the story when crossed, surfaced as mounting narrator pressure (never a HUD). Built on
  pattern-buffer's accrue ledger. See `docs/design/GAUGE-PRIMITIVE.md`.
- **Episodic continuation** — a concluded story offers the next chapter: same protagonist and world,
  the prior adventure as the lead-in, a reputation callback, and a fresh hidden arc.
- **Build progress in plain language** — the world-build narrates evocative stages ("Dreaming up the
  story…", "Settling what's true and lasting…") instead of engine jargon, including the longest
  (durability) stage so the bar never appears to stall.

### Changed
- The refusal/conclusion model no longer uses turn counters: the post-climax window is retired and
  the refusal clock is now an explicit-abandonment condition (fires only when the player walks away,
  never on quiet turns); a runtime guard prevents any counter-based refusal from fabricating a
  conclusion in canon. The model is story-agnostic — a casual/endless card is never force-concluded.

### Fixed
- **Protagonist binding (real-build invariant):** the build now refuses an unstageable protagonist
  (a generic extracted role with no location) — re-authoring against the located cast, with a
  rebuild-from-proposal fallback — so cast staging, clue delivery, and the durable map actually
  govern a generated world (not just hand-authored test worlds).
- **Episodic continuation:** the next episode now loads its own arc across reopen (portfolio
  superseded via retraction under constitutive folding), scopes its cold open to that arc, and no
  longer terminates on turn 1.
- **Epilogue-no-canon:** terminal/curtain prose is archived but never promoted to canon, so a
  closing line's descriptive phrases can't become a later episode's character names; display names
  prefer the real `name` over any late descriptive alias.

### Known follow-ups
- `continuation_intro` is a one-shot injected after reopen (a cold process break between conclude and
  the next opening would lose the framing note — same durability class as the per-slot scope/epoch).
- Identity-closure: a renderer pass to collapse `maybe_same_as` duplicates into one display identity.
