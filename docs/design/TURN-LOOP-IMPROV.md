# Turn-Loop Improvisation & Authority — proposal for round-robin (K → Cx → PB)

**Status:** DRAFT for group review. Founder-directed architecture; leash→license
flip is implemented but **uncommitted**, feeding the probe below. Nothing finalizes
until the round-robin lands.

## 1. The problem
A holodeck world must answer player actions the pattern-buffer has not yet
established — open an undescribed drawer, search for an ordinary item, attempt a
lock — with *good-DM improvisation*, not a refusal. Today the narrator is held by
a **render leash** ("introduce NO new facts; narrate honest uncertainty; the world
will resolve it next turn") — but nothing resolves player-probed aspects, so they
never get answered. A prose-free probe against `anchor` (pure PB projection, no
source text) showed every improv case stalling (§5 BEFORE).

## 2. The architecture (founder-stated) — three roles per turn
1. **Retrieval cohort** — assembles the *relevant* pattern-buffer data for the
   player's input. **This is the concealment boundary**: it hands the narrator
   only player-frame/scoped data, NEVER hidden frames (`plot:`, `knows:<other>`).
2. **Primary narrative agent (narrator)** — receives *(player input + retrieved
   data)* → assembles the response. **Improvisation lives here**: it invents
   plausible detail *grounded in what it was given*.
3. **Ingest cohort (post-response)** — examines *both* the narrator's response and
   the player's action; writes new/changed facts to the PB **before the next
   message**, so the world is current for the next retrieval.

## 3. The change
Relocate concealment from the *leash* onto *retrieval scoping*, and flip the
narrator's directive:
- OLD `RENDER_LEASH`: "introduce NO new facts; narrate honest uncertainty."
- NEW `NARRATOR'S LICENSE`: the briefing is established truth — never contradict
  it, never reveal beyond it (what it omits, the narrator does not know). WITHIN
  that grounding, improvise like a good GM: plausible ordinary detail for
  player-probed open aspects; grant reasonable attempts and let plausibility
  decide; **do not fabricate momentous/plot-significant discoveries** (those come
  only from established facts); the player's words are an **attempt, not the
  world's compliance** (no fiat). What's made real is captured by the ingest
  cohort.

**This is the only code change.** The retrieve→narrate→ingest loop is already
wired: the player action is extracted to canon+player-frame at ingest
(`turnloop` ~319), and the narrator's prose is extracted+mirrored post-render
(~605). The leash was the sole blocker.

## 4. Why concealment still holds (the load-bearing claim to test)
The narrator briefing is built from **player-frame reads only** — it provably
carries zero `plot:` rows (the existing briefing-segregation invariant). So the
narrator cannot reveal a hidden fact *because it was never handed one*.
Loosening "don't invent" is therefore safe: invention is bounded to the
player-visible world, and plot-significant content is gated by (a) retrieval never
surfacing hidden frames and (b) the arc/beat layer. **The guarantee moves from
"narrator forbidden to invent" to "narrator never sees what must stay hidden."**

## 5. Evidence — prose-free probe against `anchor` (pure PB, no source)
**BEFORE (leash):** every probe stalled —
- drawer → *"What is inside the drawer is not yet clear."*
- paperclip → *"whether a paperclip is in or around the desk is not yet clear."*
- lockpick → (action restated; attempt not adjudicated at all)

**AFTER (license):**
- drawer → *"…revealing ordinary office clutter: a few loose papers, a pen… nothing obviously unusual."* (improvises, no momentous fabrication)
- paperclip → *"The search turns up an ordinary paperclip tucked in with the papers."* (grants the ordinary)
- lockpick → *"The lock resists under your attention… it does not simply yield at once."* (adjudicates the attempt by plausibility)
- revolver-by-fiat → *"the thing you reach for is not there… not a weapon that has never been established here."* (**refuses fiat**)

## 6. Authority model (the spectrum)
- **ambient/ordinary** (papers, a paperclip) → grant freely, commit.
- **attempts** (pick a lock) → "you can try," outcome by plausibility; backstory/
  competence is *framing that raises plausibility*, never fact-creation.
- **load-bearing** (the murder weapon, a secret, the hidden answer) → only from
  established facts; never player-asserted; arc/beat-gated.
- **fiat** (conjuring a revolver) → narrate the honest result of the attempt
  (it isn't there), never compliance.

## 7. Open questions per reviewer
- **Kernos (host discipline):** Is relocating concealment from the leash onto
  retrieval-scoping sound — does the player-frame-only briefing fully substitute
  for "narrator forbidden to invent"? Is the three-role split the right shape, or
  does it overlap your cognitive-UI/cohort patterns in a way worth aligning?
- **Cx (adversarial):** Failure modes of grounded improv: can the narrator
  contradict an **established-but-not-retrieved** fact (retrieval incompleteness →
  the narrator invents over a real fact it wasn't handed)? Does "don't fabricate
  momentous" actually hold the line, or is it a soft prompt-hope that needs a
  structural guard? Fiat/attempt edge cases?
- **PB (engine truth):** Is retrieve→narrate→ingest sound on shipped reads, and
  does post-response extraction reliably persist improvised facts? **Intersection:**
  "retrieval as a respected cohort" assumes retrieval is *complete* — but
  `materialize`/`state` is currently dropping present, stated, literal `plot:main`
  rows at world scale (separate report). Does that read-drop also threaten
  player-frame retrieval, i.e. could the narrator be handed an *incomplete* world
  and improvise over a gap that's actually established?

## 8. Not finalized
Leash→license is implemented + probe-validated but uncommitted. On round-robin
consensus (or revision), finalize + commit; if the concealment-relocation or the
"momentous" guard needs a structural backstop, that becomes the follow-up slice.
