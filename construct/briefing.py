"""The narrator BRIEFING: the per-turn prompt text that tells the narrator what is true,
present and binding this turn (no plot:, structurally — player-frame reads only).

Moved verbatim out of `turnloop.run_turn` (audit 2026-10, turnloop finding 2(a)): the text
and the order of every block are unchanged, and so is the code that builds them, except that
the identity block's display-name fallback arrives pre-computed (`protagonist_display`, from a
run_turn closure). `run_turn` builds one `BriefingInputs` and calls the two halves around the
one block that is not here:

    briefing_parts = build_briefing(inputs, trace)
    ...the DRIFT-HANDLING D2 consequence callback (stays in run_turn)...
    briefing_parts += build_briefing_rulings(inputs, trace)
    briefing = "\n".join(briefing_parts)

The consequence callback stays inline in `run_turn` because surfacing one WRITES its
once-only `surfaced` status to the session frame; keeping that write between the two halves
keeps the turn's read/write order exactly as it was. Both functions here only READ the
world. They record their telemetry on the `trace` they are given, as the rest of the turn
loop does: `build_briefing` writes `trace.point_reads`, `trace.dropped_cohorts`,
`trace.laws`, `trace.memory`, `trace.act` and `trace.present_homonyms`;
`build_briefing_rulings` writes `trace.adjudication` on a deflected question.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from construct import laws as _laws_mod
from construct import resolution
from construct.arc.executor import _human as _human_entity
from construct.arc.executor import arc_entities, climax_ready, current_phase
from construct.arc.grammar import Arc
from construct.gauge import gauge_lines

if TYPE_CHECKING:
    from construct.turnloop import TurnTrace

#: The moved assembly logs under the turn loop's logger, as it did before the move, so log
#: levels, routing and the `%(name)s` field in operator logs are unchanged.
logger = logging.getLogger("construct.turnloop")


@dataclass(frozen=True)
class BriefingInputs:
    """Everything the briefing reads from the turn, passed explicitly (no closure over
    `run_turn`). Built once, at the point the briefing used to start; the field comments
    name the `run_turn` local each value comes from where the names differ."""

    # World handles: the briefing only READS through them.
    world: Any  # the World (gauge levels)
    p: Any  # the turn's fail-open porcelain wrapper (snapshot / contents reads)
    live_reads: Any  # the horizon-bound PorcelainWorldReads
    horizon: float | None  # the play horizon every direct read is bound to; run_turn's `_h`

    # The turn's contract.
    arc: Arc  # the MAIN arc (gauge terminals already folded)
    player_input: str
    scope: list[str] | None
    endless: bool
    style: str
    play_style: str
    suspense: str
    death_policy: str
    world_laws: list  # the sealed law objects (dicts only); run_turn's `_world_laws`
    reality_line: str  # the reality register's one-line contract; run_turn's `_reality_line`

    # Continuity.
    recent: list  # the rolling transcript window (session:transcript); run_turn's `_recent`
    narrative_memory: str  # the compacted long-arc memory
    wishes: list  # the player's /ooc wishes

    # Where the player stands, and who is there.
    chain: list | None  # the protagonist's containment chain, nearest first
    scene: str | None
    pre_scene: str | None  # the scene before this turn's movement
    scene_features: list
    scene_lines: list[str]
    you_lines: list[str]
    names: dict  # player-frame entity -> display name
    canon_table: dict  # (entity, attribute) -> canon value
    protagonist_display: str  # the identity fallback name; run_turn's `_disp(arc.protagonist)`
    active_pins: list
    npcs: list[str]  # the present people, sorted
    npc_turn_results: dict  # npc -> the folded npc_turn decision

    # This turn's deliveries and decisions.
    weave_directive: str | None
    learned: list  # (npc, clue) pairs delivered this turn
    adapt_directives: list[str]
    asks_self: bool
    memory_result: dict | None  # the Remembrancer's decision
    memory_tensions: list[str]  # run_turn's `_memory_tensions`
    move_clarify: str  # the ambiguous destination phrase, if any; run_turn's `_move_clarify`
    voc_holder: str  # run_turn's `_voc_holder`
    voc_absent: bool  # run_turn's `_voc_absent`
    voc_name: str  # run_turn's `_voc_name`
    commitment: str
    commitment_clarified: str
    commitment_bounced: bool
    commitment_grade: str
    discovered: list  # (person, place) leads opened this turn
    nudge_directive: str | None

    # The ending.
    terminal: bool
    died: bool
    concluded: bool
    conc: dict | None  # the conclusion-as-effect verdict
    outcome: str | None
    reckoning_ready: bool  # run_turn's `_reckoning_ready`
    fallout_directives: list[str]
    gen_hooks: list[str]

    # The turn's rulings (read by build_briefing_rulings).
    grounding_runway: bool  # run_turn's `_grounding_runway`
    improv_query: str
    needs_test: bool
    resolved_tier: str  # run_turn's `_resolved_tier`
    uncertain_of: str
    death_staged: bool  # run_turn's `_death_staged`
    mortal_risk: bool


def build_briefing(inp: BriefingInputs, trace: TurnTrace) -> list[str]:
    """The narrator briefing's parts, in order, from the game-type directive through the
    drift relocate directive: voice, memory and recent story, time, place, scene, laws,
    pins, pressure, this turn's deliveries, movement and address directives, the ending
    (or convergence), identity, the player's act, what is carried, who is present, and
    the pacing/drift directives. Read-only over the world; see the module docstring for
    the trace fields it records."""
    # Turn-loop helpers still shared with run_turn. Imported at call time: turnloop
    # imports this module at load, so a module-level import back would be circular.
    from construct.turnloop import (
        _PIN_CAP, _RECENT_TURNS, _convergence_directive, _snap_or_empty,
    )
    # The turn state this half reads, bound to the names run_turn used, so the
    # body below is the original run_turn text.
    world = inp.world
    p = inp.p
    live_reads = inp.live_reads
    _h = inp.horizon
    arc = inp.arc
    player_input = inp.player_input
    scope = inp.scope
    endless = inp.endless
    style = inp.style
    play_style = inp.play_style
    suspense = inp.suspense
    _world_laws = inp.world_laws
    _reality_line = inp.reality_line
    _recent = inp.recent
    narrative_memory = inp.narrative_memory
    wishes = inp.wishes
    chain = inp.chain
    scene = inp.scene
    pre_scene = inp.pre_scene
    scene_features = inp.scene_features
    scene_lines = inp.scene_lines
    you_lines = inp.you_lines
    names = inp.names
    canon_table = inp.canon_table
    protagonist_display = inp.protagonist_display
    active_pins = inp.active_pins
    npcs = inp.npcs
    npc_turn_results = inp.npc_turn_results
    weave_directive = inp.weave_directive
    learned = inp.learned
    adapt_directives = inp.adapt_directives
    asks_self = inp.asks_self
    memory_result = inp.memory_result
    _memory_tensions = inp.memory_tensions
    _move_clarify = inp.move_clarify
    _voc_holder = inp.voc_holder
    _voc_absent = inp.voc_absent
    _voc_name = inp.voc_name
    commitment = inp.commitment
    commitment_clarified = inp.commitment_clarified
    commitment_bounced = inp.commitment_bounced
    commitment_grade = inp.commitment_grade
    discovered = inp.discovered
    nudge_directive = inp.nudge_directive
    terminal = inp.terminal
    died = inp.died
    concluded = inp.concluded
    conc = inp.conc
    outcome = inp.outcome
    _reckoning_ready = inp.reckoning_ready
    fallout_directives = inp.fallout_directives
    gen_hooks = inp.gen_hooks
    story_so_far = ""
    if _recent:
        beats = []
        for e in _recent[-_RECENT_TURNS:]:
            if e.get("player"):
                beats.append(f"› You: {e['player']}")
            if e.get("prose"):
                beats.append(e["prose"])
        story_so_far = "\n\n".join(beats)
    briefing_parts = []
    if play_style:
        # The game-type directive (GAME-TYPES.md): WHAT KIND of game this is — what
        # to hand-wave vs. dramatize, the tension posture. Maintained every turn so
        # the agent's awareness of the experience never lapses. A directive, not a
        # toggle matrix (founder).
        briefing_parts.append(f"{play_style}\n")
    if wishes:
        # The player floated these OUT OF CHARACTER (`/ooc`) and the engine agreed to
        # try. Weave ONE in only where it fits naturally and serves the story — never
        # if it would spoil or derail the trajectory or the game type's payoff. Let
        # them go otherwise; they are wishes, not instructions.
        briefing_parts.append(
            "PLAYER'S OUT-OF-CHARACTER WISHES (rule of cool — realize one where it "
            "fits naturally and deepens the story; NEVER if it would spoil or derail "
            "the trajectory or the game type's climax; otherwise let it pass):\n"
            + "\n".join(f"- {w}" for w in wishes[-4:]) + "\n")
    if style:
        # The world-level voice overlay (NARRATIVE-FLAVOR-INGEST): HOW to write,
        # distilled once at ingest. Shapes voice/tone only — never adds facts.
        briefing_parts.append(
            f"STYLE (render the grounded world in this voice — tone only, never "
            f"new facts): {style}\n")
    # WORLD-GROWTH G3: the NEAREST-ANCESTOR region card — grown territory
    # remembers WHY it exists (the assessment that grew it) and what the
    # player did arriving; chapter ten reads what chapter two wrote. Two
    # point reads, only when the scene actually sits under a card.
    try:
        _gregion = next((c for c in (chain or [])
                         if str(c).startswith("region:")), None)
        if _gregion:
            _gstyle = live_reads.state(_gregion, "style")
            _gorigin = live_reads.state(_gregion, "origin")
            trace.point_reads += 2
            if isinstance(_gstyle, str) and _gstyle.strip():
                briefing_parts.append(
                    "THIS TERRITORY (grown where the player walked — its "
                    "remembered voice; texture and society follow it, "
                    "never the abandoned map's): " + _gstyle.strip()
                    + (f" (Its origin — the player's own act, quoted: "
                       f"\"{_gorigin.strip()}\".)"
                       if isinstance(_gorigin, str) and _gorigin.strip()
                       else "") + "\n")
    except Exception:  # noqa: BLE001 — a briefing garnish, never a gate
        trace.dropped_cohorts.append("region_voice_read failed")
    if narrative_memory:
        briefing_parts.append(
            f"NARRATIVE MEMORY (the arc so far — standing dynamics, recurring "
            f"themes, unresolved threads; lower-resolution than the recent beats "
            f"below, but the through-line to honour):\n{narrative_memory}\n")
    if story_so_far:
        briefing_parts.append(
            f"THE STORY SO FAR (recent beats, in detail — your short-term memory of "
            f"what just happened; continue naturally, do not repeat or re-establish "
            f"what's here):\n{story_so_far}\n")
    if trace.time_now:
        # The diegetic hour, on THIS place's calendar — let it shape the light, who's
        # about, what's open; never state it as a clock readout.
        briefing_parts.append(
            f"THE TIME (render its FEEL — light, sounds, who is about — never as a "
            f"clock): {trace.time_now}\n")
    # THE LOCATION ANCHOR (task #10, critic campaign 2026-07-11 run 2,
    # verified): canon had committed a move three turns earlier, yet the
    # narrator re-placed the scene in the prior room ("There is no yard
    # gate in the briefing room"). The WHERE gets the same explicit force
    # the PRESENT CHARACTERS block gives the WHO — one line, every turn.
    # The label is PLAYER-FRAME-scoped (cr: a canon-only name the player
    # never learned must not ride into prose — the same frame discipline
    # as the scene-name resolver above); with no established name the
    # anchor goes name-free, keeping its anti-regression force.
    if scene:
        _scene_nm = str(names.get(scene) or "")
        _at = (f"YOU ARE AT: {_scene_nm}." if _scene_nm
               else "YOU ARE AT the place you now stand in.")
        briefing_parts.append(
            f"{_at} The scene is HERE and only here — if "
            f"earlier exchanges happened in another room, that place is "
            f"BEHIND you now; never re-place this scene, its doors, or its "
            f"furniture in an earlier location. Travel that was narrated "
            f"has happened.\n")
    briefing_parts += [
        # The narrator never sees internal frame ids — only the scene as it stands.
        "THE SCENE RIGHT NOW (what is true and present here):",
        "\n".join(scene_lines) or "(nothing established here yet — the grid shows through)",
    ]
    if scene_features:
        # Navigable sub-features of this place (PLACE-FEATURE; part_of-children),
        # distinct from the things merely in the room.
        briefing_parts.append("\nFEATURES OF THIS PLACE (its sub-features/"
                              "structures): " + ", ".join(scene_features))
    if _world_laws or _reality_line:
        # WORLD LAWS (#105, Cx 470 ruling 4): the constitution rides a RESERVED
        # lane AHEAD of the capped pins — a busy turn's clue/social/temporal
        # pins can never push a law out of the narrator's standing awareness.
        # Disclosure-split (founder): understood laws are open lived context;
        # discovered laws bind silently, their edges woven, never named. The
        # reality register's contract rides the same lane (no-law case incl.).
        _lane = "\n".join(p for p in (_reality_line,
                                      _laws_mod.law_lines(_world_laws)) if p)
        briefing_parts.append("\n" + _lane)
        trace.laws = [str(law.get("name") or "") for law in _world_laws]
    if active_pins:
        pin_lines = [f"[{ap.pin.scope_kind}] {ap.pin.directive}"
                     for ap in active_pins[:_PIN_CAP]]
        briefing_parts.append(
            "\nPINNED AWARENESS (foreground these — what is true and pressing "
            "here, ordered by urgency; weave in diegetically, do not list):\n"
            + "\n".join(pin_lines))
    # GAUGE surfacing (GAUGE §4): the live numeric constraint IS the tension. Urgency is
    # derived this turn from the folded level vs the floor (distance_to_floor/range, Cx 150)
    # — never stored. Ordered most-urgent first; the narrator dramatizes it, never prints a HUD.
    _glines = sorted(gauge_lines(arc, world, as_of=_h), key=lambda t: t[2])
    if _glines:
        def _phrase(u: float) -> str:
            return ("all but gone — act now" if u <= 0.1 else "critical" if u <= 0.25
                    else "running low" if u <= 0.5 else "holding")
        briefing_parts.append(
            "\nLIVE PRESSURE (foreground this mounting constraint diegetically — let it "
            "tighten the scene; do NOT print a number/HUD unless the fiction shows a gauge):\n"
            + "\n".join(f"- {g.label}: {int(round(lvl))} ({_phrase(u)})"
                        for g, lvl, u in _glines))
    if weave_directive:
        # Story governance (CARD-WEAVING.md): weave the chosen card at its seam. Replaces
        # the passive cast-threads nudge; on 'let_run' there is no directive (serve the path).
        briefing_parts.append(weave_directive)
    if learned:
        # Interview delivery (§8): the NPC reveals these pieces THIS turn, in character,
        # in response to the player's questioning — deliver them as dialogue/disclosure,
        # not as a fact dump, and never name them as "clues".
        reveal_lines = [f"{_human_entity(npc)} reveals: {a.replace('_', ' ')} "
                        f"of {_human_entity(e)} is {_human_entity(str(v))}"
                        for (npc, clue) in learned for (e, a, v) in [clue.surface_fact]]
        briefing_parts.append(
            "\nWHAT IS LEARNED THIS TURN (the questioned character discloses it now, in "
            "character — weave it into their reply, do not list or label it):\n"
            + "\n".join(reveal_lines))
    if adapt_directives:
        # make-it-real (NARRATION-DISCIPLINE.md): the player's pursued thread became the path
        # to an unfilled cause. Render the reveal as their OWN deduction from the detail they
        # chose — never a redirect back to the authored clue, never a witness lecture.
        briefing_parts.extend(adapt_directives)
    if asks_self:
        # ADDRESSED INWARD (founder 2026-07-03): the classify CHECKED that this question is
        # about the player's own life — the mechanical route that outranks last-speaker.
        briefing_parts.append(
            "\nADDRESSED INWARD (binding): the player's question is about their OWN life, "
            "memory, or circumstances — their own memory answers it, in second person, from "
            "what they know (plus ordinary plausible autobiography under the improv rules). "
            "If the memory holds NO answer, honest uncertainty IS the answer — 'you turn it "
            "over and find nothing certain' is grounded in the moment and valid; never "
            "fabricate, and never hand the question to someone else because the memory came "
            "up empty. No present character answers it for them; someone may ADD what they "
            "uniquely know (an arrangement made, a message sent) only AFTER the memory has "
            "spoken.")
    if memory_result and memory_result.get("stirs") and (memory_result.get("memory") or "").strip():
        # #97 THE REMEMBRANCER: the mind's contribution rides the briefing as felt
        # second-person interiority — PROPORTION-bound (a flicker, not a flashback).
        trace.memory = str(memory_result.get("memory") or "")[:300]
        _feel = (memory_result.get("feeling") or "").strip()
        briefing_parts.append(
            "\nYOUR OWN MIND THIS TURN (weave as FELT memory in second person — a "
            "flicker, not a flashback; never a recital, never dialogue, never an "
            "action): " + trace.memory
            + (f" — felt as {_feel}." if _feel else ""))
    if _memory_tensions:
        # #97 contradiction rule (Cx 434 constraint 5): a quarantined collision is
        # surfaced as in-fiction tension — the FIRST established truth stands.
        briefing_parts.append(
            "\nTHE MEMORY SITS ODDLY (render as felt tension, one beat, never a "
            "lecture; what is already established REMAINS the truth): "
            + "; ".join(_memory_tensions))
    if trace.distance_unknown:
        # #101 inversion (Cx 454): the map couldn't prove this was a local step — the
        # render is SCALE-NEUTRAL: true scale when the fiction establishes it, modest
        # when it doesn't; a flat map must never overdramatize "across the yard".
        briefing_parts.append(
            "\nMOVEMENT AT ITS TRUE SCALE (render the travel honestly): the player "
            "moved between places whose distance the map does not establish. Render "
            "the movement at the scale the FICTION has established — a walk down a "
            "lane is a beat; a ride to another town is departing, the way, and "
            "arriving, with weather and effort as the scene holds them. Where the "
            "distance is NOT established, keep the transit brief and modest — never "
            "invent roads, distances, or landmarks the world hasn't given you.")
    if trace.deliberating:
        # #102 (founder-shaped): the weighing is the character's OWN MIND — second-person
        # deliberation ending on the open question; never a menu, never decided for them.
        briefing_parts.append(
            f"\nYOUR OWN MIND WEIGHS IT (render as ONE beat of second-person "
            f"deliberation, then stop — the player has NOT moved): they mean to set "
            f"out for {trace.deliberating.split(' — ')[0]}, but the story's deadline "
            f"stands against the time the way would take "
            f"({trace.deliberating.split(' — ', 1)[-1]} — translate to FELT time, "
            f"never numbers). Voice it as their own thought — 'you consider it; but "
            f"if you go now, you may…' — and end on the open question: press on, or "
            f"see to what the deadline demands first? Their next word decides; if "
            f"they choose the road, it will not be questioned again.")
    if _move_clarify:
        # ASK, NEVER HALLUCINATE (founder 2026-07-04): the destination was ambiguous —
        # render ONE in-world clarify beat (a companion asking "which do you mean?",
        # the narrator putting the fork plainly); the player has NOT moved; do not
        # invent an arrival or pick for them.
        briefing_parts.append(
            f"\nTHE DESTINATION IS UNCLEAR (render as ONE brief in-world beat, then "
            f"stop — the player has NOT moved): they said they were going to "
            f"\"{_move_clarify}\", and more than one known place could be meant. Have "
            f"the world ask which they mean — a present character's natural question, "
            f"or the narrator laying out the fork plainly. Never guess, never invent "
            f"an arrival.")
    if _voc_holder:
        # #93 (Cx 404 C): the player addressed a unique canon title-holder who IS here —
        # the address binds to them, outranking the last-speaker convention.
        briefing_parts.append(
            f"\nSPOKEN TO BY TITLE (binding): the player's address names a title held "
            f"by {_voc_name} — the words go to THEM, not to whoever spoke last. They "
            f"have the floor and answer in their own voice.")
    elif _voc_absent:
        # #93 (Cx 404 C): the addressed title-holder is NOT here — never re-route
        # their floor to whoever is; render the honest not-here beat.
        briefing_parts.append(
            f"\nCALLED FOR SOMEONE NOT HERE (binding): the player's address names a "
            f"title held by {_voc_name} — who is NOT present. No one here answers FOR "
            f"them, takes the question in their stead, or volunteers their knowledge; "
            f"render the address landing on their absence honestly (the room notes it; "
            f"someone may say plainly they are not here, and where they might be found "
            f"if that is established). Never teleport them in.")
    if commitment_clarified:
        # #88A: the decisive move needs a concrete stage before it can be judged — render ONE
        # in-world clarification beat (a character asking, the empty room answering); do NOT
        # resolve or conclude anything this turn; the player's NEXT attempt is taken as given.
        briefing_parts.append(
            "\nTHE DECISIVE MOVE NEEDS ITS STAGE (render this as ONE in-world beat, then stop): "
            + commitment_clarified)
    if commitment_bounced:
        # COMMITMENT-AS-EFFECT slice 1: the player tried to force the finale before the causes are
        # covered. The world DECLINES to conclude on it — NOT a failure, a "not yet": the authority
        # won't act on what's unproven, the threads don't connect, the declaration rings premature.
        # Render that diegetically and leave the player IN the story to keep working. Never end here.
        briefing_parts.append(
            "\nTHE COMMITMENT DOES NOT LAND (render this, do NOT end the story): the player has "
            "moved to conclude — but they have NOT yet earned/proven it on what they've actually "
            "established. Show the world declining, in-genre and without a lecture: the authority "
            "won't act on so little, the case/claim doesn't hold up, the moment rings premature — "
            "and the player is left to keep going (there is more to uncover/earn). This is 'not "
            "yet,' NOT a defeat; do not narrate an ending or a verdict.")
    if discovered:
        # Discovery affordance (§3c layer 3): the player now knows where to find these
        # off-scene people. Offer the route diegetically (the witness mentions where they
        # are); the player can GO there next. Pacing/bookkeeping, not a stored route flag.
        seek_lines = [f"{_human_entity(ref)} can be found at {_human_entity(loc)}"
                      for (ref, loc) in discovered]
        briefing_parts.append(
            "\nA LEAD OPENS (the player just learned where to find someone not present — let "
            "it surface naturally, e.g. the witness says where they are; the player may now go "
            "to them). Surface it as a CONTINUATION of what this conversation has already "
            "established: if the person is already under discussion, the speaker simply ADDS "
            "where to find them — never a recognition beat ('Mr So-and-so? I know that name!') "
            "for a name the conversation, or the speaker themselves, already raised:\n"
            + "\n".join(seek_lines))
    if terminal and died:
        # #95 THE FALL + THE TESTAMENT (DEATH-TESTAMENT.md, Cx 422): the death receipt
        # owns the terminal render — a THIRD branch selected BEFORE the reckoning/
        # settling ternary is ever consulted. Honest, staged, never a gotcha or a score.
        _dcast = sorted({arc.protagonist}
                        | {e for e in arc_entities(arc, live_reads) if e.startswith("person:")})
        _dscope = [e for e in (set(arc_entities(arc, live_reads)) | set(scope or []))
                   if e.startswith(("person:", "place:", "obj:", "fact:"))
                   and live_reads.has_entity(e)]
        _dreveal = [f"{f['entity']} · {f['attribute']} · {f['value']}"
                    for f in _snap_or_empty(p, sorted(_dscope), as_of=_h).get("facts", [])
                    if f["entity"] != arc.protagonist][:20]
        briefing_parts.append(
            "\nTHE STORY ENDS HERE — THE PROTAGONIST FALLS. The staged mortal risk the "
            "player walked into has claimed them; render it truthfully, in TWO BEATS, "
            "separated by a line containing only '⸻':\n"
            "BEAT 1 — THE FALL: the death rendered honestly, in scene, at the pace of "
            "the moment — the world answers the player's last move as it truly falls. "
            "NO rescue invented, NO cutaway, NO scolding, NO miraculous reprieve.\n"
            "BEAT 2 — THE TESTAMENT: the world after them, and their effect on it. "
            "What they changed that STAYS changed; what they left undone; the promises "
            "and bonds left forever open — named as testament, not bookkeeping ('she "
            "waited at the rail end after close; he never came'). A fitting fate for "
            f"each of these, as the player's passing touches them: {_dcast}. "
            "Concealment lifts now (the story is over): name what was hidden, what "
            "they never learned. Close every thread; open nothing; this world's story "
            "ends with them.")
        if _dreveal:
            briefing_parts.append(
                "\nTHE TRUTH (revealed at the curtain — weave in what lands):\n"
                + "\n".join(_dreveal))
    elif terminal:
        # Phase 4 flavor: when the arc declares pillars, the ending's character is the
        # EFFECT of pillar coverage (STORY-SHAPES §0a) — the narrated consequence of the
        # causes, never "you won/lost". Falls back to the commitment grade for legacy
        # (pillar-less) arcs so existing worlds are unchanged.
        _shape_flavor = {
            "triumph": "triumphant and earned — the causes came together soundly",
            "costly_victory": "a hard-won, costly close — reached, but the toll shows",
            "bittersweet": "bittersweet and ironic — it lands, but on a flawed footing; "
                           "the truth the player missed festers",
            "partial": "partial and unfinished — some of it resolved, much left open",
            "failure": "a failure that lands as consequence — the causes never came together",
            "quiet_failure": "a quiet, muted close — the moment passed, the causes unmet",
        }
        if conc:
            _grade = conc["outcome"]
            flavor = _shape_flavor[conc["outcome"]] + f" ({conc['basis']})"
        else:
            # Legacy grade-aware flavor (pillar-less arcs): vindication / near-miss /
            # ironic-wrong / hollow-pyrrhic.
            _grade = commitment_grade or ("won" if outcome == "won" else "lost")
            flavor = {
                "vindicated": "triumphant and earned — they got it right",
                "partial": "bittersweet — right in the main, but incomplete",
                "wrong": "ironic and quietly devastating — they were confident and WRONG",
                "pyrrhic": "a hollow victory — right, but at a cost that outweighs it",
                "won": "triumphant but earned — the goal is reached",
                "lost": "somber — the goal is lost, the chance gone",
            }.get(_grade, "somber — the goal is lost")
        # The movie epilogue: name the cast for fates, lift concealment, and HAVE FUN
        # revealing the interesting bits the player never uncovered (the dessert course).
        fate_cast = sorted({arc.protagonist}
                           | {e for e in arc_entities(arc, live_reads) if e.startswith("person:")})
        reveal_scope = [e for e in (set(arc_entities(arc, live_reads)) | set(scope or []))
                        if e.startswith(("person:", "place:", "obj:", "fact:"))
                        and live_reads.has_entity(e)]
        reveal = [f"{f['entity']} · {f['attribute']} · {f['value']}"
                  for f in _snap_or_empty(p, sorted(reveal_scope), as_of=_h).get("facts", [])
                  if f["entity"] != arc.protagonist][:20]
        _ending_tag = conc["outcome"] if conc else f"{outcome}; grade: {_grade}"
        # S1 (#96, Cx 414 constraint 1): the ending voice BRANCHES on whether a player
        # commitment landed. A commitment-owned close gets the RECKONING scene; a silent /
        # world-event / authored-failure close gets a SETTLING beat — the world registering
        # the matter closing, with NO verdict, accusation, grade, or scene of judgment
        # (the invisible flip was the bug; a courtroom the player never convened is another).
        _commitment_landed = bool(commitment_grade)
        _beat1 = (
            "BEAT 1 — THE RECKONING SCENE: the player's decisive move LANDS where and as "
            "they staged it, and the world ANSWERS it, in scene — faces, voices, the "
            "moment turning. A wrong or failed move gets a SCENE too (the accusation "
            "landing on the wrong man, the room knowing it), never an explanation.\n"
            if _commitment_landed else
            "BEAT 1 — THE SETTLING: no decisive move was spoken, and none is invented — "
            "the world simply REGISTERS the matter closing, in scene: the thing found, "
            "the danger passed, the machinery of consequence starting to turn on its own "
            "(word carried, a door barred, men arriving). NO verdict, NO accusation, NO "
            "judgment scene — something completes and is SEEN to complete.\n")
        briefing_parts.append(
            f"\nTHE STORY ENDS HERE ({_ending_tag}). This conclusion is the EFFECT of what "
            f"the player did and left undone — narrate it as consequence, never as a "
            f"score. Render the close in TWO BEATS, separated by a line containing only "
            f"'⸻' (the close must breathe — never one compressed breath):\n"
            + _beat1 +
            f"BEAT 2 — THE AFTERMATH ({flavor}): the settled wake. For the protagonist "
            f"(you) AND each of these characters, a fitting FATE — where they end up, what "
            f"the outcome cost or won them: {fate_cast}. A loss may carry an unexpected BOON "
            f"(a door opened, a truth freed, hope for a next time); a victory may carry a "
            f"lasting WOUND — when the shape says both, say both. Concealment lifts now "
            f"(the story is over): name what was hidden, savor what the player never "
            f"uncovered — the secret walked past, the red herrings' truth. Close every "
            f"thread; apply NO new pressure, open NO new hooks.")
        # The twist fires when the player committed to a MISTAKEN case (a false-filled
        # required cause → conc["wrong_case"]), or, for legacy arcs, a 'wrong' grade. NB it
        # uses wrong_case, NOT `not sound`: a triumphant Farce is all-false (sound=False) but
        # NOT a wrong case, so it must not trip the twist (Cx 027 blocker 3). The wrong cause
        # lands, then the real truth surfaces at the curtain.
        _wrong_case = (conc["wrong_case"] if conc else commitment_grade == "wrong")
        if commitment and _wrong_case:
            briefing_parts.append(
                f"\nTHE TWIST (the player's case was not sound — land it like Sherlock going "
                f"over his notes): they concluded “{commitment}”, but the truth is "
                f"otherwise. Reveal the REAL answer and why their read was mistaken — the "
                f"clue they misread, what was really going on. This is the payoff, not a "
                f"scolding.")
        if reveal:
            briefing_parts.append(
                "\nTHE TRUTH (revealed at the curtain — the full picture, including what "
                "the player never learned; weave in what lands):\n" + "\n".join(reveal))
    elif concluded and not endless:
        _aftermath = "the world responds to the player in the settled wake of the " \
                     "story's end, applying no new dramatic pressure."
        if conc:  # the resolution's character is the EFFECT of pillar coverage
            _aftermath = (f"the close is {conc['outcome']} — {conc['basis']}. Render it as "
                          f"the consequence of the causes the player did and didn't "
                          f"establish, in the settled wake; apply no new pressure.")
        briefing_parts.append("\nTHE ARC HAS RESOLVED — render this turn as "
                              "aftermath/denouement: " + _aftermath)
    else:
        # CONVERGENCE (CONVERGENCE-TO-CONCLUSION.md; founder "all roads lead to the
        # conclusion"): act-aware pull toward the climax + relocate-the-beat-to-the-
        # player. Only while the arc is live (not terminal, not concluded — those own
        # the close). Dramatic pull only; never reveals the answer.
        # peril/thriller stories amplify the suspense build-up; everything else gets the gentler
        # general mounting-stakes (founder; Cx 113: a genre-HAZARD signal — survival/horror/combat
        # → 'peril' — NOT cost_disposition, which over-fired for mastery/contest/discovery).
        _act, _conv = _convergence_directive(current_phase(live_reads, arc),
                                             climax_ready(live_reads, arc),
                                             peril=(suspense == "peril"))
        trace.act = _act
        if _conv:
            briefing_parts.append(_conv)
        if _reckoning_ready:
            # THE DECISIVE MOMENT IS AT HAND (Cx 141; tone made story-agnostic): this commitment-
            # owned arc is ripe — what it was building toward is reachable now — but the CURTAIN is
            # the player's conclusory move, WHATEVER this story's "IT" is: a deduction's accusation,
            # a romance's confession, a bond's reconciliation, a choice owned or renounced. Phrase it
            # in THIS story's register, not a thriller's. Steer toward it without forcing or revealing.
            briefing_parts.append(
                "\nTHE DECISIVE MOMENT IS WITHIN REACH — what this story has been building toward is "
                "now available to the player; what remains is THEIR conclusory move (in this story's "
                "own register: a declaration, a confession, a choice, naming a truth, the decisive "
                "act). Bring the moment to a head and make it FEEL available and weighty — but do NOT "
                "make it for them, and do not reveal anything hidden. The curtain is theirs to draw. "
                "SAY IT ONCE: if your recent turns already voiced this pressure ('the case now comes "
                "down to…', 'the hour demands…'), do NOT restate it — hold it quietly instead (a "
                "detail, a look, a silence carries the same weight without the sermon).")
    if fallout_directives:
        # A side arc died/resolved this turn (LIVING-WORLD-GENERATOR §3): the
        # world acknowledges it as a real beat in the wake — never a silent stall,
        # never a game-over for the player. The standing consequence is already in
        # canon; this just renders the world noticing.
        briefing_parts.append(
            "\nA STORY THREAD HAS CLOSED (render diegetically, as the world "
            "reacting in passing — a real beat, NOT the end of YOUR story; "
            "acknowledge it and move on):\n"
            + "\n".join(f"- {d}" for d in fallout_directives))
    if gen_hooks:
        # A new development the living world threw up this turn (P2): surface it
        # as it ARRIVES in the scene — diegetic, never a system announcement.
        briefing_parts.append(
            "\nA NEW DEVELOPMENT ARRIVES (render diegetically, in the moment — a "
            "fresh hook entering the scene, not a menu):\n"
            + "\n".join(f"- {h}" for h in gen_hooks))
    # AUTHORITATIVE PLAYER IDENTITY (founder 2026-06-30: "player name wins, fully"). The player's
    # interview-set name/pronouns are the SINGLE source of truth — they must WIN over any authored-
    # default personal name/gender baked into premise/background prose or the entity id. State it
    # explicitly and instruct supersession, so the cast addresses the player by THEIR chosen identity,
    # not the authored "Clara Vale". (The whole interview propagates: name + pronouns + the you_lines
    # facts below carry background/role.)
    # Read identity through the FOLDED POINT READ (Cx 320): `name` is set-valued, so a stale
    # narrator-polluted `name="Miss Vale"` row coexists with the player's `name="Bradford Clemense"`;
    # the snapshot dict (`canon_table`) collapses to the LAST member, but `state()` serves the
    # authoritative winner. Carry pronouns + background + role from canon too (the Foyer writes them
    # there; the player-frame YOU block misses them).
    def _id_attr(a: str) -> str:
        try:
            v = live_reads.state(arc.protagonist, a)
        except Exception:
            v = None
        return str(v) if isinstance(v, str) else ""
    _pname = _id_attr("name") or protagonist_display
    _ppron = _id_attr("pronouns") or _id_attr("gender")
    _pbg = _id_attr("background")
    _prole = _id_attr("role")
    if _pname:
        _id_head = (f"\nTHE PLAYER CHARACTER IS {_pname}"
                    + (f" ({_ppron})" if _ppron else "")
                    + ". That is WHO they are — not how to address them every line (founder: the "
                      "full name in every reply reads canned). Refer to them the way people "
                      "actually would in this world and moment: plain 'you', a title ('sir', "
                      "'inspector'), a surname, or nothing at all — the full name only where a "
                      "person would naturally use it (a formal introduction, a pointed moment)"
                    + (f"; {_ppron} pronouns throughout" if _ppron else "")
                    + ". If any premise/background/context text uses a DIFFERENT personal name or "
                      "gender for the protagonist, that is a stale authored default for the SAME "
                      f"person — never use the other name."
                    + (f"\n- their role: {_prole}" if _prole else "")
                    + (f"\n- what brought them here: {_pbg}" if _pbg else ""))
        briefing_parts.append(_id_head)
    if you_lines:
        briefing_parts.append("\nYOU (the player character; never a third party):\n"
                              + "\n".join(you_lines))
    if terminal or (concluded and not endless):
        # CLOSE TURN (Cx 139 #2): the epilogue/aftermath directive above OWNS the render. The
        # player's act is the FINAL beat folding INTO the close — NOT "render exactly this, no
        # more", which fought and beat the epilogue (the narrator rendered the action, never the
        # curtain). Fold it in so the denouement is what lands.
        briefing_parts.append(
            f"\nTHE PLAYER'S LAST ACT (the move that brings the curtain down — render it as the "
            f"final beat that FOLDS INTO the epilogue/aftermath above, not as the whole turn; the "
            f"close owns the scene): {player_input}")
    else:
        briefing_parts.append(f"\nTHE PLAYER JUST DID (render exactly this, no more): "
                              f"{player_input}")
    if trace.movement_obstruction:
        seg = trace.movement_obstruction
        if trace.movement_status == "blocked":
            ev = seg.get("evidence") or []
            facts = "; ".join(
                f"{e.get('entity')} · {e.get('attribute')} · {e.get('value')}" for e in ev
            ) or "the way is obstructed"
            briefing_parts.append(
                f"\nMOVEMENT BLOCKED (render diegetically): the player tried to go there "
                f"but the way is barred — {facts}. Show the attempt and why it fails; "
                f"the player does NOT arrive.")
        else:  # obscured
            briefing_parts.append(
                "\nMOVEMENT UNCERTAIN (render diegetically): the state of the way can't be "
                "confirmed — render the passage as ambiguous; do NOT assert it is clearly open.")
    if trace.reveals:
        pairs = "; ".join(f"{a} is {b}" for a, b in trace.reveals)
        briefing_parts.append(
            f"\nREVEAL (render as the player's dawning recognition this turn): {pairs}. "
            f"Two figures the player took for separate are one. Dramatize the realization; "
            f"don't state it as a flat fact.")
    # WHAT THE PLAYER CARRIES (object permanence — founder: "a mug from the bar doesn't not
    # exist"): the objects in the protagonist's possession (taken or granted), so the narrator
    # grounds on what's in hand and never re-narrates a held thing back where it came from.
    # Read from canon contents; best-effort, never sinks a turn.
    try:
        _held = [h for h in p.contents(arc.protagonist, as_of=_h) if str(h).startswith("obj:")]
    except Exception:
        _held = []
    if _held:
        def _held_name(h: str) -> str:
            nm = canon_table.get((h, "name"))
            if not nm:
                try:
                    nm = live_reads.state(h, "name")
                except Exception:
                    nm = None
            return str(nm or _human_entity(h))
        briefing_parts.append(
            "\nWHAT YOU ARE CARRYING (in hand or on your person right now — honor this; never "
            "narrate one of these back where it was taken from). This list is EXCLUSIVE: it is "
            "everything on your person — anything NOT named here (incl. a thing you earlier set "
            "down/handed off/left behind) is NOT carried; do not narrate it as pocketed or in hand: "
            + ", ".join(_held_name(h) for h in _held))
    if trace.dropped:
        # DROP ACKNOWLEDGMENT (Cx 299 non-blocking): a thing set down THIS turn left the player's
        # hands and stays where it was left — so the narrator doesn't re-pocket it from transcript
        # memory next turn (the founder's "object follows me" family). Names the object + the place.
        _dropped_canon = canon_table.get((trace.dropped, "name"))
        if not _dropped_canon:
            try:
                _dropped_canon = live_reads.state(trace.dropped, "name")
            except Exception:
                _dropped_canon = None
        _dropped_nm = str(_dropped_canon or _human_entity(trace.dropped))
        _here_nm = str(canon_table.get((pre_scene, "name")) or _human_entity(pre_scene)) if pre_scene else "here"
        briefing_parts.append(
            f"\nJUST SET DOWN (no longer carried — it STAYS here, at {_here_nm}; do not narrate it "
            f"back in hand or pocket): {_dropped_nm}")
    if npcs:
        # WHO IS PRESENT (continuity guard — Cx 091 #1): name EVERY present character, not just
        # the ones who speak this turn. A silent present NPC (standing quietly, watching) was
        # surfacing only as raw fact triples and the narrator could erase them ("the doctor is
        # the only one here") — a coherence break against the cold open. Speakers carry their
        # wants; the rest are simply named as present so they can't vanish.
        # COMPANION TEXTURE (#82/#85): the standing `accompanying` state marks who is WITH the
        # player by their own agreement — a companion, not a bystander. Surfaced so the render
        # gives them living texture: they react, notice, and may interject unprompted.
        _companions = set(trace.npcs_joined)
        # THE HOMONYM TRIPWIRE (founder, 2026-07-12 — the park-forever
        # trigger made observable): two same-named cast CO-PRESENT is the
        # rare event the background-homonym park waits on, and the narrator
        # would resolve it silently rather than report it. Telemetry only —
        # zero prompt weight, zero narrative effect; fires the ledger/triage
        # review that builds the "known for X" epithet against a real scene.
        _by_name: dict = {}
        for _hn in npcs:
            _nm = str(canon_table.get((_hn, "name")) or "").strip().lower()
            if _nm:
                _by_name.setdefault(_nm, []).append(_hn)
        for _nm, _ids in _by_name.items():
            if len(_ids) > 1:
                trace.present_homonyms.append((_nm, sorted(_ids)))
                logger.warning("present homonyms in scene %s: %r share the "
                               "display name %r (the park-forever tripwire)",
                               scene, sorted(_ids), _nm)
        for n in npcs:
            if n in _companions:
                continue
            try:
                if live_reads.state(n, "accompanying") == arc.protagonist:
                    _companions.add(n)
            except Exception:  # noqa: BLE001
                pass
        present_lines = []
        from construct.arc.executor import person_can_act as _brief_can_act
        for n in npcs:
            nm = str(canon_table.get((n, "name")) or _human_entity(n))
            # NARRATOR LIVENESS (task #8, the D3 acceptance finding): the
            # authority layer already refuses a settled-dead person every
            # delivery/action channel, but the scene brief still listed them
            # as an interlocutor and the narrator improvised their dialogue.
            # Same shared predicate; the BODY stays present — it is a fact of
            # the scene — but it can never speak or act.
            if not _brief_can_act(live_reads, n):
                present_lines.append(
                    f"the body of {nm}: DEAD — present as a body only. The "
                    f"dead do not speak, move, gesture, or answer; render "
                    f"the body's stillness and the room around it.")
                continue
            # CAST IDENTITY (#87): the authored pronouns ride the presence line so the
            # narration can never drift a character's gender between scenes.
            _pn = canon_table.get((n, "pronouns"))
            if not _pn:
                try:
                    _pn = live_reads.state(n, "pronouns")
                except Exception:  # noqa: BLE001
                    _pn = None
            if _pn:
                nm += f" ({_pn})"
            _tag = " [COMPANION — with the player by agreement]" if n in _companions else ""
            intent = npc_turn_results.get(n)
            if intent and intent.get("speaks") and intent.get("intent"):
                line = f"{nm}{_tag}: wants {intent['intent']}"
                if intent.get("line_hint"):
                    line += f" (voice: {intent['line_hint']})"
                present_lines.append(line)
            else:
                present_lines.append(f"{nm}{_tag}: present, silent for now (do NOT remove them "
                                     f"from the scene — they remain here unless they visibly "
                                     f"leave)")
        _companion_note = (
            " A COMPANION travels with the player and lives in the scene: they react to what "
            "happens, notice things in their own competence, and may interject or murmur an "
            "aside UNPROMPTED — a quick beat, not a speech; they never narrate the player and "
            "never dominate the turn." if _companions else "")
        briefing_parts.append(
            "\nPRESENT CHARACTERS (ONLY these characters are here right now — keep every one in "
            "the scene; play the ones with wants, keep the rest present even if quiet; anyone else "
            "from earlier scenes is elsewhere — do not stage them here):"
            + _companion_note + "\n"
            + "\n".join(present_lines))
    else:
        # PRESENCE TRUTH WHEN ALONE (founder 2026-07-01 "why are nell and grieves here???" / Cx 354
        # B2): with an EMPTY colocated set the briefing used to say NOTHING about presence, so the
        # narrator rode the transcript window and resurrected departed cast. State the engine truth.
        briefing_parts.append(
            "\nPRESENT CHARACTERS: none besides you. Do not stage earlier characters here, and do "
            "not have an absent person arrive, speak, or be recalled doing things in this place — "
            "the world's map says who is where; if the player seeks someone absent, the way to "
            "them is going there or sending word, never their sudden appearance.")
    if nudge_directive:
        briefing_parts.append(f"\nPACING DIRECTIVE (weave in diegetically): {nudge_directive}")
    if trace.repair_directive:
        # DRIFT-HANDLING D3 (§3 R4): emitted ONLY after the replacement batch
        # receipt-confirmed — the new route exists in plot truth before the
        # narrator seeds it.
        briefing_parts.append(f"\n{trace.repair_directive}")
    if trace.relocate_directive:
        # DRIFT-HANDLING D1 (§3 R2 step 3): emitted ONLY after a confirmed carrier-move
        # commit (or no move needed at all) — presence truth already moved, so this
        # directive can never contradict canon.
        briefing_parts.append(f"\n{trace.relocate_directive}")
    return briefing_parts


def build_briefing_rulings(inp: BriefingInputs, trace: TurnTrace) -> list[str]:
    """The briefing's closing parts, after the consequence-callback slot: the grounding
    runway, the fallen-through question (withheld or improvised), the drawn resolution
    tier, the mortal-risk render, the tangent/reshape/fired-event directives and, in hold
    mode, the neutral-narrator discipline plus the destination card. Read-only over the
    world; records `trace.adjudication` on a deflected question."""
    from construct.turnloop import _destination_directive, _secret_tokens
    # The turn state this half reads, bound to the names run_turn used, so the
    # body below is the original run_turn text.
    live_reads = inp.live_reads
    arc = inp.arc
    endless = inp.endless
    death_policy = inp.death_policy
    names = inp.names
    terminal = inp.terminal
    died = inp.died
    concluded = inp.concluded
    _grounding_runway = inp.grounding_runway
    improv_query = inp.improv_query
    needs_test = inp.needs_test
    _resolved_tier = inp.resolved_tier
    uncertain_of = inp.uncertain_of
    _death_staged = inp.death_staged
    mortal_risk = inp.mortal_risk
    briefing_parts: list[str] = []
    if _grounding_runway and not (trace.clocks_fired or trace.beats_achieved
                                  or trace.terminal or trace.concluded):
        # ...unless a hand-authored turn-1 clock/beat/terminal genuinely fired — then the story
        # HAS arrived and the "settle a beat first" framing would contradict it (Cx 280 nit).
        briefing_parts.append(
            "\nGROUNDING RUNWAY (CHARACTER-GROUNDING, founder): this is the player's first beat — "
            "they are still settling into WHO and WHERE they are (their own space, their role, the "
            "ordinary texture of their world). Keep it GROUNDED and low-pressure; answer what they "
            "do. Do NOT introduce the inciting incident, the case, or any call-to-action this turn "
            "unless the PLAYER reaches for it — let them inhabit their world a moment first. The "
            "story arrives next beat.")
    deflect_secret = False
    if improv_query:
        public_name_toks = {t for nm in names.values()
                            for t in nm.lower().replace("-", " ").split()}
        secret_toks = _secret_tokens(arc, live_reads, public_name_toks)
        qtoks = set(improv_query.lower().replace("?", " ").replace(",", " ")
                    .replace(".", " ").split())
        deflect_secret = bool(secret_toks & qtoks)
    if improv_query and deflect_secret:
        # The fallen-through question probes the mystery's HIDDEN answer directly
        # (Cx 022 blocking #2). Do NOT improvise here — improvisation could brush the
        # secret. Deflect deterministically; the concealment block below names what's
        # protected, this just keeps the narrator from trying to answer it at all.
        trace.adjudication = "deflect: question probes a concealed arc fact"
        briefing_parts.append(
            f"\nWITHHELD QUESTION (do NOT improvise an answer): the player asked "
            f"“{improv_query}”, which reaches for something they have NOT uncovered. Do "
            f"not answer, confirm, deny, or hint at it — and do NOT invent a substitute "
            f"answer either. Deflect diegetically (the record is silent on that / it "
            f"isn't yours to know yet / that thread hasn't been pulled) and turn the "
            f"moment back to what is present and knowable. A deflection is NOT a flat "
            f"refusal: whoever fields it reacts as a person would — "
            f"an accusation lands with feeling before any procedure is cited. This is "
            f"earned only through play.")
    elif improv_query:
        briefing_parts.append(
            f"\nUNDER-DETERMINED QUESTION — IMPROVISE, but the WORLD'S INTEGRITY COMES "
            f"FIRST: the player asked “{improv_query}” and the record doesn't spell it out. "
            f"Answer as what THIS character would plainly know — a long-term resident knows "
            f"the local geography, where people eat, the neighbors, the routines.\n"
            f"  • If the thing plausibly EXISTS here but simply isn't written down yet, "
            f"AFFIRM it and invent consistent specifics (a name, a direction, a few streets "
            f"over) that fit this world.\n"
            f"  • BUT if the player names something that does NOT fit this world — an "
            f"anachronism or an out-of-setting thing (a 'pizza joint' in a rationed off-world "
            f"colony; a smartphone in a medieval vale) — do NOT fabricate it to match them. "
            f"Gently CORRECT in-world: there is no such thing here; name what this world has "
            f"in its place ('no pizza joint in Anchor — people eat at the ration canteen') "
            f"and let the player adapt to the world. Improvise the WORLD AS IT REALLY IS; "
            f"never bend its nature to the player's assumption.\n"
            f"Never a flat 'you can't say' for ordinary, knowable things; only a genuinely "
            f"SECRET answer is withheld (deflect diegetically). What you establish becomes "
            f"real (it will be remembered).")
    # Uncertain action → REUSE the tier drawn earlier (EVENT-OCCURS-FIRING reorder, Cx 115 — one
    # draw per turn, bound BEFORE beat firing) and tell the narrator WHAT happens (succeed/fail +
    # the twist); it improvises HOW. Assured actions never draw — they just succeed.
    if needs_test and _resolved_tier and _resolved_tier != "assured":
        briefing_parts.append("\n" + resolution.directive(_resolved_tier, uncertain_of))
    # ---- #95 mortal-risk render directives (DEATH-TESTAMENT.md, Cx 422) ---------------
    # Staged-never-a-gotcha: the first life-risking turn makes the stakes UNMISTAKABLE
    # and lands short of death; policy shields/premise-folds override a fatal draw.
    if _death_staged and not died:
        briefing_parts.append(
            "\nMORTAL STAKES (render, binding): this move risks the player character's "
            "LIFE, and they must SEE that plainly — make the lethal stakes unmistakable "
            "in the scene (the drop, the blade, the fire — concretely). This turn the "
            "move lands SHORT of death: a near-miss, a wound, pinned, thrown back — the "
            "world's honest warning shot. If they press on into this peril, it can kill.")
    elif (mortal_risk and _resolved_tier == "terrible_failure" and not died
          and death_policy in ("premise", "shielded")):
        # Cx 426: shielded/premise never stage a peril marker, so their fatal-draw
        # directives fire on the risk itself — the policy IS the contract, no
        # persistence needed (a mortal chapter's fatal draw is handled above/at death).
        if death_policy == "premise":
            briefing_parts.append(
                "\nDEATH, TRANSFORMED (render, binding): the move kills the player "
                "character — render the death honestly, and then the story's own "
                "premise transforms it (the loop resets, the ghost persists, the "
                "mechanism catches them) exactly as this story's premise established. "
                "The death is real and felt; the premise, not a rescue, is what answers "
                "it. The story continues.")
        else:  # shielded — the genre's contract caps the price below death
            briefing_parts.append(
                "\nTHE PRICE STOPS SHORT OF DEATH (render, binding): the failure lands "
                "hard — a wound, capture, ruin, a door slammed — in this genre's own "
                "conventions, but it does NOT kill the player character. Make the cost "
                "real and lasting; never a lethal beat.")
    if trace.tangent_directive:
        # G-A: the adoption landed this turn — the world answers the
        # player's declared story (spec: the hook is a wiring output)
        briefing_parts.append("\n" + trace.tangent_directive)
    if trace.reshape:
        # The act reshaped the world (committed pre-render). Tell the narrator the new
        # truth so prose matches canon; the sanctioned rows are licensed past the gate.
        briefing_parts.append(
            "\nWHAT THE ACT CHANGED (binding — the player's action reshaped the world; "
            "render this as real and match it exactly): " + trace.reshape)
    if trace.events_fired:
        # an authored act-beat fired this turn — it is now BINDING canon (Cx 115 #1); render it as
        # having happened, never contradict it.
        briefing_parts.append(
            "\nWHAT JUST HAPPENED (binding — the player's action brought this about; render it as "
            "real, do not walk it back): "
            + "; ".join(k.replace("_", " ") for k in trace.events_fired))
    # CONCEALMENT = STRUCTURAL ABSENCE (Kernos 076 Q2 / Cx 023 blocking #1): the narrator
    # is NOT handed the arc's hidden answer. It is briefed ONLY from the player frame, so
    # it cannot leak what it never sees. (Replaces the old _concealment_directive, which
    # fed the narrator the answer + "don't reveal" — the vault-with-a-sticky-note the mesh
    # ruled against, MORE leakable, not less. The strict promotion gate below stays as a
    # cheap backstop; the secret-question deflection guard above still fires.)
    # In HOLD-MODE (the story isn't concluding this turn) add the NEUTRAL-NARRATOR
    # discipline (Kernos Q4 / Cx blocking #2) — load-bearing for "the player may be
    # wrong": present evidence flatly, never weight a theory toward a verdict.
    hold_mode = not terminal and not (concluded and not endless)
    if hold_mode:
        briefing_parts.append(
            "\nNEUTRAL ON THE ANSWER (binding): stay neutral about the mystery's "
            "SOLUTION — present clues and misleading-but-true detail alike WITHOUT "
            "weighting them, and never confirm, deny, hint, wink at, or tonally tilt "
            "toward the player's theory or any conclusion; a leading question (“so it was "
            "X, right?”) gets only the observable facts, honest uncertainty, or an "
            "in-world deflection. This neutrality is EPISTEMIC — about the evidence and "
            "the verdict — and is NOT a flattening of human feeling: the characters still "
            "react with full emotion, they simply do not give the "
            "answer away. The player draws their own conclusions — let them, even when "
            "they are heading somewhere wrong. The truth is told only at the end, never "
            "coaxed out mid-play.")
        # The DM's CARD: the hidden destination to FORESHADOW toward (card model). Gives
        # the narrator the answer so it can lay a convergent trail; "weave, don't blurt".
        dest = _destination_directive(arc, live_reads)
        if dest:
            briefing_parts.append(dest)
    return briefing_parts
