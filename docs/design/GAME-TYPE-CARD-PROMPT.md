# Prompt — generate a long list of game-type cards

> Hand the text between the rules below to another agent. It is self-contained.

---

You are designing the **game-type taxonomy** for an interactive-fiction / text-RPG
engine. Your job: produce a **long, comprehensive list of "game-type cards,"** each
rigorously filled out to the schema below.

## What a "game type" is (read carefully — this is the bar)
A game type is **NOT a genre and NOT a tone.** It is a claim about the **shape of
engagement** — the *core loop the player is actually playing*, and therefore what
the story should **dramatize vs. hand-wave**, how **tension** builds, and what
**winning and losing** mean — valid only for a world whose substance can **support**
that loop.

- **Genre/setting** (fantasy, sci-fi, noir, western…) is a SEPARATE, orthogonal
  layer. Do NOT produce genres as game types. Any game type must pair with many
  genres (e.g. a "heist" works in fantasy, sci-fi, or modern).
- **Tone** (comedy, tragedy, grim, campy) is also separate — a modifier, not a
  type. Do not produce tones as types.
- The test of a real type: it changes **what the narrator dwells on vs. skips** and
  **what victory means**. If two candidates don't differ on those, MERGE them
  (e.g. "noir" is a tone on "mystery"; "slasher" is a flavor of "survival horror").

Draw on the traditions of tabletop RPGs (D&D, Call of Cthulhu, Blades in the Dark,
Vampire, Pendragon, etc.), film/TV, and prose fiction. Aim for **breadth**: cover
investigation, schemes/infiltration, action/combat, survival, exploration,
social/relationship, horror, and anything else that is a genuinely distinct
engagement shape. Target **at least 20–30 distinct cards.**

## The card schema (fill every field, crisply)
For each game type, output a card with exactly these fields:

- **Name** — the game type (2–4 words).
- **One-line pitch** — what playing it feels like, in a sentence.
- **Core loop** — what the player is actually doing, turn to turn, that IS the fun.
- **Dramatize** — what the narrator slows down and renders in rich detail (the
  substance). Be specific.
- **Hand-wave** — what compresses to a sentence as connective tissue. Be specific.
- **Tension shape** — how pressure builds (e.g. ratchet toward a climax, accrete/
  tighten, grind/attrition, slow warming, episodic spikes).
- **Win condition** — what victory concretely means for this type.
- **Loss condition** — how it concretely goes wrong.
- **World requires** — the concrete things a world MUST contain for this loop to run
  at all (this is a support-check: if a given fiction lacks these, the type doesn't
  fit it — e.g. you can't run "romance" on a world with no possible love interest).
- **Directive** — a 2–4 sentence instruction TO A NARRATOR, distilled from Core
  loop + Dramatize + Hand-wave + Tension. Write it as a usable runtime instruction,
  opinionated and sharp. Lead it `PLAY STYLE — <NAME>: …`.

## Gold-standard example (match this rigor)
**Name:** Mystery / Whodunnit
**One-line pitch:** You sift clues and conflicting testimony to expose a hidden truth.
**Core loop:** gather information and reason toward a concealed answer.
**Dramatize:** clues, witness testimony, scenes of evidence, the contradictions
between accounts; the player weighing motive, history, and red herrings.
**Hand-wave:** travel, logistics, the passage between locations — getting somewhere
is never the game.
**Tension shape:** accretion — the noose tightens as facts align and suspects squirm.
**Win condition:** name the truth / make the correct accusation, supported by what
was actually uncovered.
**Loss condition:** a wrong accusation, or the trail goes cold and the case is lost.
**World requires:** a concealed truth; ≥2 suspects with plausible motives;
discoverable evidence; at least one red herring.
**Directive:** `PLAY STYLE — MYSTERY: Compress travel and logistics to a sentence —
getting somewhere is never the game. Slow down and give deep clarity to clues,
testimony, scenes of evidence, and the contradictions between witnesses' stories;
let the player sift motive, history, and red herrings toward the truth. Withhold the
answer and reward deduction.`

## Output format
- Group the cards by family (Investigation; Schemes & Infiltration; Action & Combat;
  Survival; Exploration; Social & Relationship; Horror; and any others you find).
- One card per type, every field present, in the order above.
- After the cards, add a short **"Merged / excluded"** note listing near-variants you
  folded in (and the tonal/genre items you deliberately left out), so the curator
  sees your reasoning.

Produce the full list now. Favor completeness and distinctness over brevity.
