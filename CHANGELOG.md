# Changelog

Notable changes to The Construct. Pre-1.0; dates are development milestones, not releases.

## Unreleased (2026-07)

### Added
- **Death & the testament** — a per-chapter `death_policy` (`mortal` / `premise` / `shielded`)
  decides whether the player character's death ends the story, is transformed by the premise
  (time loops, ghosts), or is capped by genre convention. Mortal peril must be *staged* — the
  world makes the stakes unmistakable and lands the first risk short of death; only persistence
  into staged peril can kill, and only on the deck's terrible-failure tier. A death renders THE
  FALL + THE TESTAMENT (the world after you, and your effect on it) and is permanent: death ends
  endless worlds too, and no next chapter is ever offered. `docs/design/DEATH-TESTAMENT.md`.
- **The Remembrancer** — the protagonist's own memory as a silent turn participant, symmetric
  with NPC engines: a concealment-screened `knows:` digest contributing felt interiority only
  (never dialogue, never action), gated to self-questions, deliberate recall, declarations, and
  protagonist-knowledge turns. Includes **player-authored memory (retcon)**: "I remember my
  childhood friend John Johnson" commits real autobiography through a guarded channel — world
  claims become beliefs that can never satisfy arc coverage, protected/concealed material is
  screened at storage, named past people are admitted as minimal offscene canon stubs, and
  direct contradictions quarantine in favor of the first established truth (surfaced as
  in-fiction tension, never a silent overwrite). `docs/design/REMEMBRANCER.md`.
- **First-mention permanence** — a proper-named detail the world establishes ("The Hart and
  Bell") commits immediately as a minimal, non-present place/person stub through the Entity
  Authority seam; engagement paints the rest. The gate's evidence is real casing — recovered
  from the prose itself when the lean extractor omits name rows — and fail-closed: generic
  descriptions ("the street") still never mint. Narration-channel only; player input still
  cannot conjure people or places. `docs/design/ENTITY-AUTHORITY.md` (Cx 415 amendment).
- **Consequence callbacks & settled history** — every ending writes deterministic canon
  consequence events (word spreads, reputation shifts) with causal receipts; the next chapter's
  opening carries exactly ONE unsurfaced callback (the newspaper seam), receipt-gated against
  repetition. Answered questions become settled history the generator is prohibited from
  re-opening as mystery; the notebook marks them closed; personal promises are extracted as
  first-class continuation fuel the next chapter must honor or consciously pay off.
- **Vocative title resolution** — "Chief!" resolves to the unique canon title-holder,
  address-syntax-gated ("my chief concern" never matches). Present → they take the floor and
  their knowledge delivers; absent → no present character answers in their stead, and the
  address lands on their absence honestly.
- **Ending voice branches** — a commitment-owned close gets the RECKONING scene; a silent /
  world-event close gets THE SETTLING (the world registering the matter closing — no verdict,
  no judgment scene the player never convened).

### Evaluation & method
- **Adversarial critic campaign** — player-agents primed to break immersion and file their own
  `/feedback` reports, including deliberate off-path runs and chapter-2 continuations; every
  filing independently triaged against engine ground truth (`docs/design/eval/09`).
- **The optimal-IF synthesis** — the corpus distilled into five portable pillars
  (`docs/design/OPTIMAL-IF-EXPERIENCE.md`).
- **Cast identity coherence gate** at build (one id can no longer be authored as two people);
  containment-aware presence (a person in an alcove within the study is present in the study).

### Changed
- The default shipped world is **The Rain in Bluegate Yard** (`bodycase`); the original anchor
  world is retired to `worlds/attic/`.

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
- EP2 cast anchoring: the persisted next-episode `arc_scope` is narrow (the new arc's referents +
  protagonist), so a cold open's cast is partly carried from existing canon rather than a broad
  structured scope — adequate today, a candidate to strengthen if a future opening needs firmer
  cast anchoring (Cx 196).
- Source-to-live role drift: ingest can leave a residual adaptation oddity (a source-prose
  protagonist surviving as a secondary name when live play re-centers on a different protagonist) —
  locally coherent, tracked near identity-closure / ingest-fidelity (Cx 196).
