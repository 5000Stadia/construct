# Design documents — the map

The Construct is a design-first project: every substantive mechanism was specified on
paper, adversarially reviewed, and only then built — and each document below records
the decision, the live failure or founder finding that motivated it, and how it
shipped. This index groups the 63 documents by layer. **Bold** entries are the
recommended spine for a first read.

## Start here

| Doc | What it is |
| --- | --- |
| **[../CONCEPT.md](../CONCEPT.md)** | The founding brief: vision, session-zero flow, host-over-substrate architecture, the arc layer as the new design surface. |
| **[OPTIMAL-IF-EXPERIENCE.md](OPTIMAL-IF-EXPERIENCE.md)** | The research synthesis: five pillars of the optimal interactive-fiction experience, distilled from the whole evaluation corpus. The intellectual center of the project. |
| **[AUDIT-2026-07-FRESH-EYES.md](AUDIT-2026-07-FRESH-EYES.md)** | A commissioned fresh-eyes architecture audit: intention vs. shape, what accreted, what to defend. Honest by design. |
| [../LEXICON.md](../LEXICON.md) | The working vocabulary (holonovel, frames, cohorts, the membrane…). |

## Evaluation ([eval/](eval/))

| Doc | What it is |
| --- | --- |
| **[eval/00-CONSOLIDATED-REPORT.md](eval/00-CONSOLIDATED-REPORT.md)** | The engineering verdict over 5 scenarios × 18 turns: strengths to defend, every clunk attributed (model craft vs. mechanism), findings ranked. |
| [eval/01–05](eval/) | Per-scenario assessments (noir, survival trek, undersea thriller, inheritance mystery, Victorian procedural). |
| [eval/06–08](eval/) | Chapter-2 continuation probes: does quality survive coherence-carrying? |
| **[eval/09-critic-campaign.md](eval/09-critic-campaign.md)** | Adversarial player-agents primed to break immersion and file their own bug reports; every filing independently triaged against engine truth before any fix. |

## The turn loop (the host spine)

| Doc | What it covers |
| --- | --- |
| **[TURN-LOOP.md](TURN-LOOP.md)** | The serial mutation spine + parallel assembly fan-out + single render; writes land before the narrator ever looks. |
| [TURN-LOOP-IMPROV.md](TURN-LOOP-IMPROV.md) | Good-DM improvisation with authority: resolve-and-commit upstream, the narrator stays leashed. |
| [TURN-LATENCY.md](TURN-LATENCY.md) | The latency ledger: folded cohort calls, the deferred post-send settle, one draw per turn. |
| [ACTION-RESOLUTION.md](ACTION-RESOLUTION.md) | The pre-rolled deterministic outcome deck: assured actions just succeed; uncertain ones draw a fail-forward tier. No per-check model call. |
| [NARRATION-DISCIPLINE.md](NARRATION-DISCIPLINE.md) | Make-it-real: an off-script pursued thread becomes a real route to an unfilled cause — route-flex, never answer-flex. |
| [NARRATOR-CONTEXT-SHAPE.md](NARRATOR-CONTEXT-SHAPE.md) · [CONSTRUCT-DIALOGUE.md](CONSTRUCT-DIALOGUE.md) | What the narrator is handed and how it must speak; conversation conventions (who is being spoken to, presence holds, proportion). |
| [AS-OF-PLAY-HORIZON.md](AS-OF-PLAY-HORIZON.md) | Timeline-entry coherence: every read this turn bound to the play horizon so future source rows never leak backward. |

## World truth & the write boundary

| Doc | What it covers |
| --- | --- |
| **[ENTITY-AUTHORITY.md](ENTITY-AUTHORITY.md)** | The one coreference+typing-disciplined seam every free-text canon write passes: bind-before-mint, channel-scoped mint permissions, first-mention permanence, the prose-casing evidence gate. |
| [GATED-INGEST-COHORT.md](GATED-INGEST-COHORT.md) | The gated doorway between model output and canon: proposal, screen, commit. |
| [EXTRACTION-AND-DISCOVERY.md](EXTRACTION-AND-DISCOVERY.md) | How prose becomes structured fact, and how off-scene people are discovered then visited. |
| [EXAMINE-CHANNEL.md](EXAMINE-CHANNEL.md) | Close inspection as an evidence channel: object-held clues surface into the player's frame, earned. |
| [WORLD-TICK.md](WORLD-TICK.md) | The world moves without you: off-screen cast deltas, committed through the doorway, discovered rather than narrated. |
| [CAST-MOVES.md](CAST-MOVES.md) | The licensed narration-seam movement lane: narrated on-screen arrivals/departures become canon presence truth under five stagecraft rules. |
| [WORLD-CHANGING-AGENCY.md](WORLD-CHANGING-AGENCY.md) | Earned "miraculous" agency: reshaping settled canon (revive the dead) through a judged, sanctioned channel — the arc adapts. |

## The arc layer (the drama engine)

| Doc | What it covers |
| --- | --- |
| **[ARC-LAYER.md](ARC-LAYER.md)** | The hidden destination: beats, clocks, the pacing ladder, anti-railroading guards. |
| **[CONCLUSION-AND-OUTCOME.md](CONCLUSION-AND-OUTCOME.md)** | The conclusion clock: a story ends on its own decisive event; turns never force a close; conclusion-as-effect. |
| [COMMITMENT-AS-EFFECT.md](COMMITMENT-AS-EFFECT.md) · [CONCLUSIVE-OUTCOME-SPEC.md](CONCLUSIVE-OUTCOME-SPEC.md) · [STORY-SHAPE-AND-RESOLUTION.md](STORY-SHAPE-AND-RESOLUTION.md) | The decisive move: clarified before judged, graded from established causes, landed as a scene. |
| [CONVERGENCE-TO-CONCLUSION.md](CONVERGENCE-TO-CONCLUSION.md) | All roads lead to the ending — dramatic pull without reveals or rails. |
| [BEAT-DELIVERY-COHERENCE.md](BEAT-DELIVERY-COHERENCE.md) · [EVENT-OCCURS-FIRING.md](EVENT-OCCURS-FIRING.md) | Arc beats and clue delivery share one truth; act-beats fire from real committed events. |
| [DEATH-TESTAMENT.md](DEATH-TESTAMENT.md) | Death as staged permanence: per-chapter policy, the warning before the kill, the testament epilogue, no next chapter. |
| [EPISODIC-CONTINUATION.md](EPISODIC-CONTINUATION.md) | Conclude → continue: consequences as canon events, settled history never re-opened, personal threads honored. |
| [LIVING-WORLD-GENERATOR.md](LIVING-WORLD-GENERATOR.md) · [LIVING-WORLD-GENERATOR-P2.md](LIVING-WORLD-GENERATOR-P2.md) | The regenerative arc engine: side-arc lifecycle, fallout as canon consequence, the opportunistic generator. |
| [WORLD-GROWTH.md](WORLD-GROWTH.md) | The world grows where the player walks: the improv-Assessor cohort reasons plausible places/encounters into canon on open-ended travel — the drawer/room make-it-real element generalized to geography and society; the closed-map stonewall (Ironhold probe) dies here. |
| [DRIFT-HANDLING.md](DRIFT-HANDLING.md) | When the player leaves the road: relocate-the-beat, absence-consequence, alternative-path repair, gentle nudge tuning — the founder's four-part drift design. |
| [WIN-LOSS-CONDITIONS.md](WIN-LOSS-CONDITIONS.md) · [GAUGE-PRIMITIVE.md](GAUGE-PRIMITIVE.md) · [DIEGETIC-TIME.md](DIEGETIC-TIME.md) | Authored stakes: failure conditions, numeric gauges as live drama, in-world time as the only clock. |

## Character & knowledge

| Doc | What it covers |
| --- | --- |
| **[REMEMBRANCER.md](REMEMBRANCER.md)** | The protagonist's own memory as a silent turn participant — and player-authored retconning with contradiction quarantine. |
| [CHARACTER-CREATION.md](CHARACTER-CREATION.md) · [CHARACTER-GROUNDING.md](CHARACTER-GROUNDING.md) · [CHARACTER-IN-PLAY.md](CHARACTER-IN-PLAY.md) | The Foyer (conversational character creation), the Picard model of grounded identity, and how cast holds coherent in play. |
| [AWARENESS-AND-SHAPE.md](AWARENESS-AND-SHAPE.md) · [PINNED-AWARENESS.md](PINNED-AWARENESS.md) | Pinned universals, knowledge-as-object, polymorphic identity; the pin channel. |
| [NARRATIVE-MEMORY-AND-CONTEXT.md](NARRATIVE-MEMORY-AND-CONTEXT.md) | The two-store discipline: facts in the substrate, narrative feel in a compacted host-side ledger. |
| [PLAYER-NOTES-SPEC.md](PLAYER-NOTES-SPEC.md) | The player's journal — per main character, carried across chapters. |

## Genre & authoring

| Doc | What it covers |
| --- | --- |
| **[STORY-SHAPES.md](STORY-SHAPES.md)** | The nine genre shapes and how each earns its payoff — the pillar/cause structure under every mystery, quest, and contest. |
| [STORY-SHAPES-CATALOG.md](STORY-SHAPES-CATALOG.md) · [SHAPE-STRUCTURES.md](SHAPE-STRUCTURES.md) · [STORY-SHAPE-GAMBIT.md](STORY-SHAPE-GAMBIT.md) | The shape grammar in full. |
| [INVESTIGATION-SHAPE.md](INVESTIGATION-SHAPE.md) · [GENRE-SIGNATURE-ELEMENTS.md](GENRE-SIGNATURE-ELEMENTS.md) | The whodunit done genre-faithfully; each genre's signature elements as its spirit. |
| [GAME-TYPE-TAXONOMY.md](GAME-TYPE-TAXONOMY.md) · [GAME-TYPES.md](GAME-TYPES.md) · [GAME-TYPE-CARDS.md](GAME-TYPE-CARDS.md) · [GAME-TYPE-PALETTE.md](GAME-TYPE-PALETTE.md) · [GAME-TYPE-CARD-PROMPT.md](GAME-TYPE-CARD-PROMPT.md) | The 155-card play-style taxonomy: maintained narrator directives per style, and the pre-built juice cards woven into play. |
| [CARD-WEAVING.md](CARD-WEAVING.md) | Story governance: when a pre-built card serves the moment vs. when the player's tangent is the richer story. |
| [NARRATIVE-FLAVOR-INGEST.md](NARRATIVE-FLAVOR-INGEST.md) | Feel, charm, and clue-trails as host annotations over a genre-agnostic engine. |

## Sessions, transports & surfaces

| Doc | What it covers |
| --- | --- |
| [SESSION-ZERO.md](SESSION-ZERO.md) · [STARTUP-ENTRY.md](STARTUP-ENTRY.md) | Building a world from a document or a live interview; the guided entry menu. |
| [INGEST-PROGRESS-NOTIFICATIONS.md](INGEST-PROGRESS-NOTIFICATIONS.md) | The build narrated as the world coming into being, not engine jargon. |
| [CLI.md](CLI.md) · [PROVIDER-INTERFACE.md](PROVIDER-INTERFACE.md) | The command surface; bring-any-LLM provider contract. |
| [SCENE-IMAGERY.md](SCENE-IMAGERY.md) | Per-location illustration, regenerated only when the scene truly changes. |
| [../DISCORD.md](../DISCORD.md) | Phone play over an outbound-only bot. |
