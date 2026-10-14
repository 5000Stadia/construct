# Intent, consequence and interpretation: how construct adopts the ruleset

**Status:** adoption note, 2026-10-13. It is the decision record for milestone M9 (R38 to R47, and R48 under Later).
**Source:** Kabe's "Construct — Intent, Consequence & Interpretation Ruleset" (Claude Docs, 2026-10-13). Its text is archived at `/media/k/Blank/construct-scratch/intent-ruleset/`. Kabe, adopting it: "Yes, you captain the best judgement for shape in construct… elegantly implement what is practical and effective. If something isnt compatible we should have a good reason, or a good reason why it should be implemented."

## The governing idea, adopted whole

**The player owns their intentions. The world owns its consequences. Characters own their interpretations. The narrator keeps the three apart.**

It extends construct's existing bets:
- the membrane, and secrets kept by absence from a context;
- `knows:` frames;
- the occurrence rule;
- turns are free and only diegetic time drives.

Nothing in it needs a new engine. Every adopted slice is a deterministic host pass, or a field on a cohort that already exists.

## What the code does today (verified 2026-10-13 against main 5e3e3b3)

The ruleset's "Construct today" column was checked against the code, file by file:

| Failure | The ruleset said | Verified | What differs |
|---|---|---|---|
| F1 false abandonment | contemplation never counts as drift | **partly** | Drift needs the story clock quiet for 240 minutes (drift.py:56, 113-128), but the rung is turn-counted (drift.py:87-100), and a contemplative turn still advances the clock by 1 minute (clock.py:258-282). There is no purpose model |
| F2 frozen opportunity | gap for appointments made in play | true | Only authored clocks lapse (drift.py:403-415) |
| F3 premature commit | the hedge fix swallows conditions | **true, and worse** | The classify prompt says any hedged naming commits (cohorts.py:2721-2729). The only counter-text, `decisive_note` ("only prepares… not a commitment"), is injected only near the climax (turnloop.py:2528-2532), where the two instructions conflict |
| F4 invented motive | no structural barrier | true | A prompt rule only (`player_constraint`, cohorts.py:2586-2597); no check on the prose |
| F5 belief as truth | strong; narrator framing is the seam | true | `knows:` frames are separate, and knows-bound extraction is dropped (turnloop.py:1391-1419) |
| F6 utterance as fact | lies to NPCs need a belief path | **true, and worse** | In-character speech is an action, and its statement sentences go through player-input extraction into canon (turnloop.py:4717-4775). A spoken lie can become world truth. The fact-by-fiat denial covers only `pure` mode (turnloop.py:4631-4645) |
| F7 unaware as refusal | drift isn't frame-aware | true | `drift_state` takes no knowledge input (drift.py:113) |
| F8 re-preached refusal | a decline isn't remembered | true | Only `last_nudge_thread`, and only in cast-less worlds (turnloop.py:7093-7116) |
| F9 rescued failure | the deck rescues wanted failures | partly | True for contested actions (resolution.py:33-98). An uncontested deliberate failure is likely judged assured and never drawn |
| F10 over-clarification | one gate, no scene policy | partly | There are two commitment gates (the stage gate, once per episode, cohorts.py:2886-2909; and the bounce), plus a move-destination clarify beat. No policy decides when to ask |
| F12 private-intent leak | no private channel | partly | `/note` is truly private, never read by a model (commands.py:179-203). `/ooc` wishes reach the narrator briefing only, never a `knows:` frame (session.py:533-555; briefing.py:238-247) |
| F13 summary drift | compaction loses provenance | true | `compact_memory` folds player lines and narration into untagged text (cohorts.py:2278-2297), handed to the narrator as the through-line |

**Also verified:**
- The classify schema has no purpose, condition or decline field (cohorts.py:43-226).
- `drift_state` is pure, as the ruleset assumes.
- The notebook (`/notebook`) is a deterministic case board over `knows:<protagonist>`.
- Personal promises are extracted only at episode end.
- **Tangent adoption is not a stated-intent channel:** a model confirms a declared aim by judging a later action consistent (tangent.py:207). That matters for R40 (below).

## Adopted, with the shape construct gives it

| Ruleset | Construct shape | Item |
|---|---|---|
| I1, hedge vs condition (IR-18) | A `commit_condition` field on classify (none, hedge, precondition, conditional). **The host gates, not the prompt:** only none and hedge may commit. A conditioned commitment becomes a pending decision on the session frame that the briefing carries, so the world can invite it back. It never fires on its own | R38 |
| I2, unaware is computed (IR-15) | `drift_state` gains the protagonist's knowledge as an input: a pending beat whose subject the player has never learned of is not drift | R39 |
| IR-16, abandonment is never inferred | **The walk-away as a declared decision.** A detected walk-away opens one in-world question with the stakes shown. Only an explicit yes reaches the refusal clock. Ambiguity, silence or a deflection is a no. The ruleset's limits on asking apply (never twice per thread; an unanswered question resolves to the literal reading). It replaces B1's held change 1, whose turn-gap design measured persistence rather than intent | R40 |
| I3, the intent frame, stated only | `intent:<player>` as a host frame (never canon, IR-4) with source, scope and channel. The notebook mirrors it; `/note` stays private and unchanged | R41 |
| I4, narrator discipline, and the new F6 finding | Stated intents in the briefing, never guesses. **Utterance is not fact (IR-5):** a spoken claim commits as a speech event, and statement sentences in speech stop reaching canon by extraction. This defect is worse than the ruleset knew, so it ranks right after R38 to R40 | R42 |
| I5 to I9 | As the ruleset lays out; each gets its own spec when its turn comes | R43 to R47 |
| I10 | Genre and experience profiles | R48 (Later) |

## Bent or deferred, with the reason

- **Tempo judged by a model at scene boundaries (I8).** Deferred to R46. R40's single question uses a fixed, medium-tempo in-world form (a present character, or the narrator's framing when no one is there). That adds no call; tempo can refine the form later.
- **The prose check for invented motive (validate_narration check 1).** Deferred inside R42. It is a model pass before send, against the turn-latency goal (M6), so the structural checks come first. The motive check would run only on turns that touch an L3/L4 surface, or in the deferred settle.
- **The tangent as "stated intent".** Not treated as stated: B1's `elsewhere` category is an outcome label, not an abandonment, so IR-16 isn't at stake. If R41 needs the tangent as a stated purpose, the adoption confirm must become the player's explicit word.
- **Interface repair by re-adjudication (I9).** Kept to the last turn, single player only, as the ruleset says. The seeded deck makes it exact.
