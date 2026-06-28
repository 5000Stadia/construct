"""The turn loop — TURN-LOOP.md's DAG over the frozen porcelain.

Serial mutation spine → assembly fan-out → narrator render → post
(render ingested as canon + concealment audit). One call = one turn;
state lives in the playthrough world file.

Read pattern: atoms read live canon directly (per-key folds are ~0.2ms
after pattern-buffer 037 made folds closure-scoped). Snapshots are taken
only where a materialized fact LIST is genuinely needed — the player-
frame briefing and the canon mirror. The earlier SnapshotReads batching
existed only for the pre-037 per-read cost (seconds per fold) and was
retired once that cost vanished (PB catch-up, re-measured 2026-06-16).

Failure policy (TURN-LOOP §5): spine steps loud-fail; fan-out cohorts
fail open with the drop logged; the narrator failing is the turn
failing.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from construct import cohorts
from construct import resolution
from construct.adapter import PorcelainWorldReads
from construct.gauge import (
    apply_gauge_terminals, gauge_coloring, gauge_lines, gauge_pass,
)
from construct.reshape import apply_reshape
from construct.arc.executor import (
    LIFECYCLE_TERMINALS,
    PLOT,
    SESSION,
    arc_concluded,
    arc_entities,
    arc_lifecycle,
    arc_outcome,
    arc_protected_keys,
    beat_pass,
    clock_pass,
    climax_ready,
    conclusion_from_coverage,
    counters_from_session,
    coverage_summary,
    current_phase,
    emit_fallout,
    navigate,
    set_lifecycle,
    stored_lifecycle,
    turn_time,
)
from construct.arc.executor import _human as _human_entity
from construct.arc.generator import generate_from_fallout
from construct.arc.grammar import Arc, Phase, Weight
from construct.pins import resolve_active_pins
from construct.provider import Provider, ProviderError

logger = logging.getLogger(__name__)


import time as _time  # noqa: E402
from contextlib import contextmanager  # noqa: E402


def _destination_facts(arc: Arc, reads: Any) -> str:
    """The arc's hidden answer as newline-joined 'entity — attribute: value' lines (the
    protected (entity,attribute) → canon value set), or '' if the arc conceals nothing.
    Shared by the foreshadowing card and the commitment judge."""
    facts: list[str] = []
    for (e, a) in sorted(arc_protected_keys(arc)):
        try:
            v = reads.state(e, a)
        except Exception:
            v = None
        if isinstance(v, str) and v:
            disp = _human_entity(v) if ":" in v else v
            facts.append(f"{_human_entity(e)} — {a}: {disp}")
    return "\n".join(facts)


def _destination_directive(arc: Arc, reads: Any) -> str:
    """The narrator-as-DM's CARD (STORY-SHAPES.md card model — founder override of the
    earlier structural-absence ruling): the arc's hidden answer, framed as the
    destination to FORESHADOW toward, not a vault to guard. A DM must know the answer to
    lay a convergent trail — *you cannot foreshadow what you don't know* (the Joker-bomb
    argument). The discipline is "weave clues toward it, never blurt it, reveal only when
    earned." This re-introduces the answer the structural-absence pass removed; it no
    longer leaks because (a) the player frame is clean now (the seed bug that pre-loaded
    the answer is fixed), (b) the strict promotion gate backstops (a protected fact can't
    auto-promote from prose), (c) the neutral-narrator + brute-force deflection guards
    hold. Empty when the arc conceals nothing (genre-conditional)."""
    facts = _destination_facts(arc, reads)
    if not facts:
        return ""
    facts_block = "\n".join(f"  - {f}" for f in facts.split("\n"))
    return ("\nTHE HIDDEN DESTINATION (you, the narrator, KNOW this; the player does NOT "
            "— it is where the story is heading):\n"
            + facts_block
            + "\nFORESHADOW toward it like a good DM: plant ambiguous, observable clues "
            "that POINT here and let them accrete so the player can assemble it. But "
            "NEVER state, confirm, or hand it over — keep every clue deniable, reveal "
            "nothing until it is earned, and deflect any demand to be told. You hold the "
            "answer ONLY to lay the trail, never to give it away.")


_SECRET_STOP = {"the", "a", "an", "of", "to", "is", "in", "on", "and", "or", "by",
                "for", "with", "person", "place", "obj", "fact", "event", "true",
                "false", "none", "unknown", "yes", "no"}


def _secret_tokens(arc: Arc, reads: Any, public: set[str]) -> set[str]:
    """Distinctive vocabulary of the arc's HIDDEN answers — tokens drawn from each
    protected attribute and its canon value — MINUS tokens that are public names in
    play (a public NPC is not a secret just because they turn out to be the culprit;
    the player must be free to ask about them). Used to spot a question fishing
    directly for the solution (Cx 022 blocking #2) so the narrator deflects rather
    than improvises an answer that could brush the secret."""
    toks: set[str] = set()
    for (e, a) in arc_protected_keys(arc):
        try:
            v = reads.state(e, a)
        except Exception:
            v = None
        for src in (a, v if isinstance(v, str) else ""):
            for t in (str(src).replace(":", " ").replace("_", " ")
                      .replace("-", " ").lower().split()):
                if len(t) > 3 and t not in _SECRET_STOP:
                    toks.add(t)
    return toks - public


#: The 3-act overlay on the five dramatic phases (CONVERGENCE-TO-CONCLUSION.md;
#: founder "collapse into a three-part act"). Act is a host-side convergence frame,
#: never a player-facing banner.
_ACT_OF = {
    Phase.SETUP: "I", Phase.RISING: "I",
    Phase.CRISIS: "II", Phase.CLIMAX: "II",
    Phase.FALLING: "III",
}


def _convergence_directive(phase: Phase, ready: bool, peril: bool = False) -> tuple[str, str]:
    """The act label + a CONVERGENCE directive for the narrator (founder: "all roads
    should lead to the conclusion — gentle nudges, or relocate the conclusive scene to
    where the story has gone") PLUS a rising-STAKES/SUSPENSE build-up toward the conclusive
    scene (founder: "don't forget tension, raised stakes, suspense build-up before the
    conclusive scene — especially peril/thriller"). Convergence is WHERE it ends; the build-up
    is the RISING PRESSURE on the way. `peril` (a high-stakes/thriller story) amplifies the
    suspense clause. Dramatic pull + staging only — NEVER informational, never reveals the
    hidden answer. Returns ("" , "") in Act III, where the resolution/epilogue directives own it."""
    act = _ACT_OF.get(phase, "I")
    base = ("\nCONVERGENCE (this is live fiction with a destination — bend every road "
            "toward it, gently and diegetically; NEVER stall and NEVER railroad). ")
    # The suspense curve: stakes and pressure should MOUNT as the conclusive scene nears — never
    # coast flat into it. Amplified for peril/thriller (make the danger and the cost of failure
    # felt; tighten the clock; build dread). This is dramatic PRESSURE, never the answer.
    if peril:
        build_i = (" Begin to let the STAKES register — what stands to be lost is real and "
                   "the danger is not far off.")
        build_ii = (" BUILD THE SUSPENSE: raise the stakes and tighten the screws as the climax "
                    "nears — make the threat vivid and close, the clock louder, the cost of "
                    "failure unmistakable; let dread and urgency mount turn over turn. Do NOT "
                    "coast calmly into the conclusion — the player should FEEL the pressure crest.")
    else:
        build_i = (" Let the stakes begin to register — what matters here, and what it would "
                   "cost to lose it.")
        build_ii = (" Let the STAKES and significance MOUNT toward the conclusion — each beat "
                    "weightier than the last, the pressure rising; the player should feel the "
                    "story gathering to a head, not drifting to a stop.")
    if act == "I":
        return act, base + (
            "ACT I — establish the world and let it breathe, but keep a current under "
            "it: surface the hooks and let the central tension tug at the player. Plant, "
            "don't push." + build_i)
    if act == "II":
        relocate = (
            "If the player has wandered from where the pivotal beat was imagined, "
            "RELOCATE it: bring the confrontation/discovery TO them, re-woven to fit "
            "wherever they now are (the moment can land in any place — it turns on what "
            "is true, not on a room). Do not stall and do not march them back.")
        if ready:
            return act, base + (
                "ACT II, and the conclusion is AT HAND — steer every road into it now. "
                + relocate + " Tighten toward the climax; let it feel inevitable, not "
                "forced. Reveal nothing the player hasn't earned — converge the DRAMA, "
                "never the answer." + build_ii)
        return act, base + (
            "ACT II — converge: every thread should bend toward the pivotal beat now, "
            "pressure rising. " + relocate + " Converge the DRAMA, never the answer." + build_ii)
    return act, ""  # Act III: resolution/epilogue directives own the close


#: Honorifics/articles that don't identify a person on their own (so "the doctor" matches
#: by 'doctor', not by 'dr'); kept short — the goal is to drop noise, not over-filter.
_NAME_NOISE = frozenset({"the", "of", "a", "an", "and", "mr", "mrs", "ms", "dr",
                         "lord", "lady", "sir", "miss", "old", "young"})

# Pressure-gated clues should surface under ANY directed investigative engagement, not just
# overt hostility. The live whodunit run showed the agent questions politely ("ask Mara to
# describe what she saw") — that IS pressing a witness in an investigation, but the original
# narrow set (press/demand/threaten/force/insist) never tripped, so pressure clues never
# revealed (0 clues across 16 turns → quiet_failure). These two signal sets broaden it:
# overt pressure OR an investigative probe (a question, a confrontation, asking someone to
# account for / describe / explain). Founder: "directed questioning IS pressing them."
_PRESSURE_VERBS = frozenset({
    "press", "demand", "threaten", "force", "insist", "confront", "accuse", "interrogate",
    "grill", "challenge", "corner", "push", "pressure", "intimidate",
})
_PROBE_SIGNALS = frozenset({
    "ask", "question", "where", "what", "when", "why", "who", "whom", "how", "describe",
    "explain", "account", "alibi", "admit", "confess", "tell", "really", "actually",
    "lying", "lie", "hiding", "hide", "saw", "witness", "prove", "show", "reveal", "did",
    "were", "was", "know", "knew", "suspect", "doing", "claim", "story", "truth",
})


def _is_pressing(text_low: str, *, needs_test: bool) -> bool:
    """Does the player's input apply investigative pressure to a present cast member?

    True for overt pressure verbs, OR an investigative probe (interrogative / asking
    someone to account, describe, explain), OR when classify flagged the action as
    uncertain (needs_test) — directed questioning of a suspect IS pressing them in an
    investigation. v1 heuristic; a fuller intent read later."""
    if needs_test:
        return True
    if "?" in text_low:
        return True
    toks = set(text_low.replace("?", " ").replace(",", " ").replace(".", " ").split())
    return bool(toks & _PRESSURE_VERBS) or bool(toks & _PROBE_SIGNALS)


#: EXAMINE channel (EXAMINE-CHANNEL.md): verbs that mark the player INSPECTING a physical thing.
#: Inspecting a NAMED object is close inspection (scrutiny) — it earns the object's evidentiary
#: clue, not just a glance. A bare "look around" (no object) is NOT scrutiny (handled elsewhere).
_EXAMINE_VERBS = frozenset({
    "examine", "inspect", "search", "study", "check", "scrutinize", "scour", "comb",
    "investigate", "open", "compare", "measure", "probe", "read", "test", "feel", "smell",
    "turn", "lift", "pry",
})


#: Close-inspection adverbs: "look CLOSELY / CAREFULLY at X" is scrutiny even though "look" alone
#: is a glance (Cx 083 — the folded §8b spec named "look closely"). A bare "look around" is not.
_SCRUTINY_ADVERBS = ("closely", "carefully", "close at", "in detail", "minutely")


def _is_scrutiny(text_low: str) -> bool:
    """Is the player CLOSELY inspecting a physical thing this turn (the EXAMINE analogue of
    `_is_pressing`)? True when an examine/inspect/search-class verb is present, OR a close-
    inspection adverb ('look closely/carefully at …'). A bare 'look around'/'notice' is a glance,
    not scrutiny. Gates `scrutiny` object-clues; a glance earns only `examined`-level clues."""
    toks = set(text_low.replace(",", " ").replace(".", " ").replace("?", " ").split())
    if toks & _EXAMINE_VERBS:
        return True
    return any(adv in text_low for adv in _SCRUTINY_ADVERBS)


#: Role-address synonyms: the player-agent addresses a suspect by their ROLE, often with a
#: common synonym ('Doctor' for a 'family physician', 'Constable' for a 'policeman'). Map the
#: synonym a player would say → the role tokens the surface_role carries, so role-address
#: engages the right NPC. The live whodunit run failed a delivery when the agent said only
#: "Doctor" and the matcher (name/id 'orme' only) didn't engage Dr. Orme.
_ROLE_SYNONYMS = {
    "doctor": "physician", "doc": "physician", "physician": "physician",
    "nurse": "nurse", "constable": "policeman", "officer": "policeman",
    "inspector": "detective", "captain": "captain", "colonel": "officer",
    "reverend": "clergyman", "father": "priest", "vicar": "clergyman",
    "professor": "scholar", "maid": "housekeeper", "butler": "butler",
    "cook": "cook", "clerk": "clerk", "barkeep": "bartender",
}

#: The vocabulary of ROLE-NOUN heads that can stand in for a person's identity when the player
#: addresses them by occupation/station ("the valet", "Doctor"). Only these tokens of an NPC's
#: surface_role become addressable — NOT arbitrary descriptors (Cx 051): "Sir Julian's valet"
#: must NOT be addressable by the victim's name 'Julian'; "Market Dalling scandal" not by
#: 'Market'/'scandal'; "family physician" not by 'family'. A surface_role token counts as an
#: address head only if it is a known role noun here (or a canonical synonym target).
_ROLE_NOUNS = frozenset({
    "physician", "doctor", "surgeon", "nurse", "apothecary",
    "valet", "butler", "maid", "housekeeper", "governess", "cook", "footman",
    "gardener", "groom", "coachman", "steward", "servant", "porter",
    "clerk", "secretary", "solicitor", "lawyer", "banker", "merchant", "clergyman",
    "priest", "vicar", "sexton", "professor", "scholar", "tutor", "schoolmaster",
    "constable", "policeman", "detective", "inspector", "sergeant", "captain",
    "colonel", "major", "soldier", "sailor", "guard", "watchman",
    "innkeeper", "landlord", "bartender", "barkeep", "publican",
    "gentlewoman", "widow", "heir", "heiress", "nephew", "niece", "ward",
}) | frozenset(_ROLE_SYNONYMS.values())


def _words(s: str) -> list[str]:
    """Lowercased word tokens, punctuation stripped (so 'Dr. Ames,' → ['dr','ames'])."""
    for ch in ",.;:!?\"'()[]—-":
        s = s.replace(ch, " ")
    return s.lower().split()


def _names_entity(entity: str, text_low: str, name: str = "", role: str = "") -> bool:
    """Cheap heuristic: does the lowercased player input name this entity? Matches the id
    stem ('person:night_clerk' → 'clerk'/'night'), the significant tokens of the NPC's
    narrated `name` ('Hobbes, the butler' → 'hobbes'/'butler'; 'Dr. Ames' → 'ames'), AND
    its `role`/surface_role tokens ('family physician' → 'physician'; so addressing 'the
    physician' engages them). A small role-synonym map also catches the form a player
    actually says ('Doctor' → the 'physician' role).

    Matching is WHOLE-TOKEN, not substring (Cx 049): substring matching let 'doc' hit
    'documents'. And role tokens are ADDRESS-FILTERED, not blindly added (Cx 051): only an
    NPC's role-NOUN heads ('valet', 'physician') are addressable identity, never arbitrary
    descriptors — so "Sir Julian's valet" is not addressable by the victim's name 'Julian',
    nor "family physician" by 'family'. v1 — a fuller coreference resolver later."""
    text_toks = set(_words(text_low))
    cands: set[str] = set()
    # Name + id-stem tokens are fully addressable identity (they ARE the person's name).
    stem = entity.split(":", 1)[-1].replace("_", " ")
    for src_toks in (_words(stem), _words(name)):
        for tok in src_toks:
            if len(tok) > 2 and tok not in _NAME_NOISE:
                cands.add(tok)
    # Role tokens are addressable ONLY when they are recognized role-noun heads (Cx 051) —
    # not the descriptors a role string carries (a victim's name, a place, 'family').
    role_toks = set(_words(role))
    cands |= {t for t in role_toks if t in _ROLE_NOUNS}
    if cands & text_toks:
        return True
    # Role-synonym address ('Doctor' for a physician): the player SAID (as a whole token) a
    # role word whose canonical role noun this NPC carries.
    for spoken, canon in _ROLE_SYNONYMS.items():
        if spoken in text_toks and canon in role_toks:
            return True
    return False


def _colocated(npc_chain: list, scene: str, player_chain: list) -> bool:
    """Is an NPC present in the player's scene, CONTAINMENT-AWARE (founder bug: NPCs
    the cold open narrates as present were going inert under a brittle exact `in ==
    scene` match)? Present if the NPC is in the scene or anywhere WITHIN it (scene on
    the NPC's location chain), or their immediate place sits on the PLAYER's own chain
    (same area at a coarser grain). A person with NO location is never present."""
    return bool(npc_chain) and (scene in npc_chain or npc_chain[0] in player_chain)


@contextmanager
def _phase(trace: "TurnTrace", name: str):
    """Record a section's wall-clock into `trace.timings` (the optimization surface).
    Accumulates if a name recurs; negligible overhead, always on."""
    t = _time.perf_counter()
    try:
        yield
    finally:
        trace.timings[name] = round(trace.timings.get(name, 0.0)
                                    + (_time.perf_counter() - t), 2)


def _parallel(thunks: list) -> list:
    """Run independent, BLOCKING model-call thunks concurrently and return their
    results in the SAME order. Each cohort call does its own `asyncio.run` with a
    fresh per-call httpx client, so worker threads are safe; the win is collapsing
    the per-NPC calls (independent network I/O) from serial into one batch. A thunk
    that raises yields its exception object (callers already fail-open per NPC).
    Only the slow MODEL calls go in here — engine reads/commits stay on the main
    thread."""
    if not thunks:
        return []
    if len(thunks) == 1:
        try:
            return [thunks[0]()]
        except Exception as exc:  # noqa: BLE001 — mirror the per-call fail-open
            return [exc]
    out: list = [None] * len(thunks)
    with ThreadPoolExecutor(max_workers=min(len(thunks), 6)) as ex:
        futs = {ex.submit(t): i for i, t in enumerate(thunks)}
        for fut, i in futs.items():
            try:
                out[i] = fut.result()
            except Exception as exc:  # noqa: BLE001
                out[i] = exc
    return out

_ABSENT = object()
_PIN_CAP = 6  # max pins surfaced per turn (Cx 062: cap + stable order)
#: How many recent beats (player action + narration) to carry as the narrator's
#: short-term memory. The narrator is called STATELESS each turn (fresh prompt, no
#: persistent conversation), so this rolling window IS its memory — keep it RICH
#: (founder), not clipped to one beat. Bounded so the briefing can't grow forever.
import os as _os  # noqa: E402
_RECENT_TURNS = max(1, int(_os.getenv("CONSTRUCT_RECENT_TURNS", "8")))
#: Beats aging past the verbatim window are folded into a durable NARRATIVE MEMORY
#: (Kernos-style compaction at boundaries) — host-side, never canon. Compaction
#: runs in batches of this many aged beats, so the memory cohort fires occasionally
#: (not every turn). Fail-open: a miss never breaks the turn.
_COMPACT_BATCH = max(1, int(_os.getenv("CONSTRUCT_COMPACT_BATCH", "4")))
#: A conclusory commitment is "earned" once the player has had a real chance to play —
#: this many turns in, OR the arc is climax-ready. (Guards turn-1 abruptness WITHOUT
#: requiring the engine to have put the answer in the player frame — the card model.)
_MIN_COMMIT_TURN = max(1, int(_os.getenv("CONSTRUCT_MIN_COMMIT_TURN", "3")))
#: (Retired 2026-06-25, founder ruling / Cx 173: turns never force a conclusion. The post-climax
#: turn-count window `K_POSTCLIMAX` and the `session:reckoning_ready` turn-stamp are gone — a
#: commitment-owned arc stays ready indefinitely; only a landed commitment or an AUTHORED
#: diegetic-time/loss `failure_when` closes it. `_reckoning_ready` survives as a narrator nudge only.)
_TRANSCRIPT = "session:transcript"
_MEMORY = "session:narrative_memory"
#: The narrator's prose is staged here, NOT canon, so the ingest gate can
#: catch a contradiction of established canon before it overwrites it
#: (GATED-INGEST-COHORT; Cx round-robin). Non-contradicting rows promote to
#: canon; a row that changes an established value stays quarantined here for
#: arc review. Narrator-origin is stamped via `source` (PB 067).
_PROPOSED = "proposed:main"
_NARRATOR_SOURCE = "narrator"
#: Non-diegetic narrator "entities" the extraction must never canonize or use as a
#: container (the phantom `person:narrator` coreference bug — see the promotion gate).
_NARRATOR_PHANTOM = {"narrator", "person:narrator", _NARRATOR_SOURCE,
                     f"person:{_NARRATOR_SOURCE}"}


@dataclass
class TurnTrace:
    """The --debug emission: a formatting of session/audit rows, never a
    second bookkeeping (CLI.md)."""

    turn: int
    classified: str = ""
    briefing_frames: list[str] = field(default_factory=list)
    cohort_calls: list[str] = field(default_factory=list)
    clocks_fired: list[str] = field(default_factory=list)
    beats_achieved: list[str] = field(default_factory=list)
    beats_closed: list[str] = field(default_factory=list)
    pacing: str = "hold"
    act: str = "I"  # the 3-act convergence frame this turn (I|II|III) — CONVERGENCE-TO-CONCLUSION
    nudge: str | None = None
    irony_delta_size: int = -1
    concealment_audit: str = "not-run"
    player_boundary: str = "clean"
    adjudication: str = "allowed"
    concluded: bool = False
    dropped_cohorts: list[str] = field(default_factory=list)
    furnished: list[str] = field(default_factory=list)
    point_reads: int = 0  # fallback per-key reads (the expensive kind)
    movement_status: str = ""  # route() passability: clear|blocked|obscured
    took: str = ""             # object the player took into possession this turn (obj.in=player)
    movement_obstruction: dict | None = None  # the blocking facts, for narration
    reveals: list = field(default_factory=list)  # (a,b) pairs correlated this turn (AKA reveal beats)
    outcome: str | None = None  # arc_outcome this turn: won|lost|None
    commitment: str = ""        # the player's conclusory commitment this turn (if any)
    commitment_grade: str = ""  # vindicated|partial|wrong|pyrrhic — graded outcome (epilogue flavor)
    commitment_bounced: bool = False  # commit attempted but required coverage incomplete → non-terminal bounce (COMMITMENT-AS-EFFECT)
    main_fallout: list = field(default_factory=list)  # concrete canon consequences of a hollow/unjust main landing (caused_by the conclusion) — next-episode fuel
    events_fired: list = field(default_factory=list)  # authored event_occurs kinds that fired this turn (EVENT-OCCURS-FIRING) — the act-beats that achieved
    conclusion_shape: str = ""  # OUTCOME_SHAPE from pillar coverage (the EFFECT — STORY-SHAPES §0a)
    conclusion_basis: str = ""  # one-line why, for the epilogue + debug surface
    learned_clues: list = field(default_factory=list)  # clue ids surfaced into the player frame this turn
    discovered: list = field(default_factory=list)  # off-scene cast ids whose whereabouts the player learned this turn
    adapted: list = field(default_factory=list)  # (lane, pillar_id) the make-it-real doorway applied this turn (NARRATION-DISCIPLINE)
    weave_decision: str = ""    # story-governance: let_run|pepper_hook|deliver_card (CARD-WEAVING)
    weave_card: str = ""        # the card woven this turn (if any)
    floor_remaining: list = field(default_factory=list)  # floor-debt card ids still un-proposed
    terminal: bool = False  # this turn ended the scenario (win_loss mode + outcome)
    lifecycle: str = "active"  # main arc lifecycle this turn (won|lost|cancelled|incompletable|active)
    arc_fallout: list = field(default_factory=list)  # side arc ids that reached a terminal this turn
    generated: list = field(default_factory=list)  # arc ids minted by the DM generator this turn (P2)
    time_now: str = ""       # diegetic clock shown this turn (e.g. "Day 2, dusk")
    time_advanced: int = 0   # in-world minutes this turn consumed (DIEGETIC-TIME)
    pins: list = field(default_factory=list)  # (pin_id, scope_kind, salience) surfaced this turn
    gauge_levels: dict = field(default_factory=dict)  # gauge_id -> folded level after this turn's drain (GAUGE)
    contradictions: list = field(default_factory=list)  # narrator rows quarantined (changed established canon)
    quarantined: list = field(default_factory=list)  # narrator rows quarantined (unlicensed assertion of an arc key)
    reshape: str = ""  # WORLD-CHANGING AGENCY: the narrator directive for a canon reshape committed this turn (flag-gated)
    replanned: str = ""  # the new main arc id if a reshape re-aimed the arc mid-story (flag-gated)
    reshape_entities: list = field(default_factory=list)  # visible committed reshape entity ids (carried into next-turn scope)
    timings: dict = field(default_factory=dict)  # per-section wall-clock (s) this turn — optimization surface
    briefing: str = ""  # the FULL assembled narrator briefing (the directives that drove the prose) — mechanics log

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class TurnResult:
    prose: str
    trace: TurnTrace
    exit_requested: bool = False  # player asked (OOC) to leave/start over → transport confirms


def _player_frame(arc: Arc) -> str:
    return f"knows:{arc.protagonist}"


def _receipt_rows(receipt: Any) -> list[dict]:
    return receipt.to_dict()["rows"] if hasattr(receipt, "to_dict") else receipt["rows"]


def _snap_or_empty(p: Any, scope: list[str], frame: str = "canon",
                   *, as_of: float | None = None) -> dict:
    if not scope:
        return {"facts": []}
    ids = sorted(set(scope))
    snap = p.snapshot(ids, frame=frame, as_of=as_of)
    if "error" not in snap:
        return snap
    # The strict snapshot rejected the WHOLE batch because some id isn't a KNOWN entity (e.g.
    # an arc-scope `fact:*` beat target never asserted in canon, like fact:verdict). Don't lose
    # the whole table — that drops every NPC's narrated `name` and breaks interview delivery for
    # a player who addresses a suspect BY NAME (the live staged-whodunit bug). Recover the known
    # subset by probing per id (only on this failure path, so the happy path is unchanged).
    logger.warning("snapshot error for %s on %s: %s — recovering known subset per-id",
                   frame, ids, snap["error"])
    facts: list = []
    for e in ids:
        try:
            one = p.snapshot([e], frame=frame, as_of=as_of)
        except Exception:
            continue
        if "error" not in one:
            facts.extend(one.get("facts", []))
    return {"facts": facts}


def _route_obstruction(p: Any, origin: str | None, target: str | None,
                       *, as_of: float | None = None) -> dict | None:
    """First non-clear segment on origin->target via PB route() (RFC-003), or
    None. Fail-open: any route error => None => move proceeds unchecked. A
    `blocked` segment carries `evidence` (the portal's blocking fact); an
    `obscured` one a computed `unknown_basis`. `as_of` (Cx 255): read passability
    at the play horizon, so a future blocked/open portal can't alter movement now."""
    if not origin or not target or origin == target:
        return None
    try:
        r = p.route(origin, target, as_of=as_of)
    except Exception as exc:
        logger.warning("route() unavailable, movement unchecked: %s", exc)
        return None
    for seg in r.get("segments", []):
        if seg.get("status") in ("blocked", "obscured"):
            return seg
    return None


def _mirror_rows(p: Any, rows: list[dict], frame: str,
                 canon_table: dict[tuple[str, str], object], trace: TurnTrace,
                 *, as_of: float | None = None) -> None:
    """Mirror freshly-ingested canon facts into a knows: frame. Values
    come from the canon snapshot; point-read fallback for out-of-scope
    entities only. `as_of` (Cx 255): the fallback point-read honors the play
    horizon, so a future source winner can't be mirrored over the current value."""
    items = []
    for row in rows:
        if row.get("frame") not in (None, "canon"):
            continue
        key = (row["entity"], row["attribute"])
        value = canon_table.get(key, _ABSENT)
        if value is _ABSENT:
            st = p.state(row["entity"], row["attribute"], as_of=as_of)
            trace.point_reads += 1
            if st["status"] != "known":
                continue
            value = st["fact"]["value"]
        items.append({"entity": row["entity"], "attribute": row["attribute"],
                      "value": value})
    if items:
        # batch durability classification (one model call, not per-row) — the
        # per-turn latency fix (PB INGEST-HARDENING / letter 075).
        p.ingest_structured(items, frame=frame, classify="batch")


def furnish_scene(p: Any, scene: str | None, player_frame: str,
                  canon_table: dict, trace: TurnTrace,
                  *, as_of: float | None = None) -> None:
    """Fiction-mode scene furnishing (letter 020 finding B): seed the
    description thunk through the gate, force via `resolve()` (resolver
    authority, generated provenance, constraint inheritance), mirror to
    the player frame. Memoized — stable on return; lazy — current scene
    only. `as_of` (B' S3): check existing description as-of the play horizon, so an
    aftermath description for this scene never suppresses opening furnishing."""
    if scene is None or canon_table.get((scene, "description")) is not None:
        return
    st = p.state(scene, "description", as_of=as_of)
    trace.point_reads += 1
    if st["status"] != "unknown":
        return
    p.ingest_structured([{
        "entity": scene, "attribute": "description",
        "value": {"policy": "invent_under_canon"},
        "value_type": "unresolved",
    }])
    out = p.resolve(scene, "description")
    if out.get("status") != "resolved":
        logger.warning("scene furnish did not resolve: %s -> %s", scene, out.get("status"))
        return
    items = [{"entity": f["entity"], "attribute": f["attribute"], "value": f["value"]}
             for f in out.get("facts", []) if f.get("value") is not None]
    if items:
        p.ingest_structured(items, frame=player_frame, classify="batch")
        for item in items:
            canon_table[(item["entity"], item["attribute"])] = item["value"]
    trace.furnished.append(f"{scene}·description")
    logger.info("scene furnished: %s", scene)


def _table(snap: dict) -> dict[tuple[str, str], object]:
    return {(f["entity"], f["attribute"]): f["value"] for f in snap.get("facts", [])}


def _grant_equipment(world: Any, p: Any, protagonist: str, description: str,
                     scene: str | None, provider: Any) -> bool:
    """IMPROV-AND-AUTHORITY: an unresolved required item that is ORDINARY role/personal
    equipment (a physician's bag, a detective's notebook) is GRANTED — minted as the
    protagonist's possession and committed (the world adapts), so the action stands
    instead of being denied for a missing canon object. A specific/load-bearing object
    is NOT granted. Fail-safe: no provider, a 'no' verdict, or any error → False (deny)."""
    if provider is None:
        return False
    try:
        from construct import cohorts
        v = cohorts.equipment_check(provider, actor=protagonist, item=description,
                                    scene=scene or "")
        if not isinstance(v, dict) or not v.get("ordinary_equipment"):
            return False
        # HOST-OWNED, FRESH id (Cx 230): the cohort's `item_id` is at most a slug HINT, never
        # authority — a returned EXISTING id would pollute that object's location and falsely
        # allow. We mint a fresh obj id, never reusing/mutating an existing entity.
        words = (description or "").lower().split()
        while words and words[0] in {"my", "the", "a", "an", "your", "his", "her",
                                     "their", "its", "some"}:
            words.pop(0)
        slug = "".join(c if (c.isalnum() or c == "_") else "_"
                       for c in "_".join(words)).strip("_") or "kit"
        reads = PorcelainWorldReads(world)
        hint = (v.get("item_id") or "").strip()
        item_id = hint if (hint.startswith("obj:") and not reads.has_entity(hint)) else f"obj:{slug}"
        n = 1
        while reads.has_entity(item_id):   # never collide with an established entity
            item_id, n = f"obj:{slug}_{n}", n + 1
        world.porcelain.ingest_structured([
            {"entity": item_id, "attribute": "kind", "value": "object"},
            {"entity": item_id, "attribute": "in", "value": protagonist, "value_type": "entity"},
        ])
        # VERIFY the grant actually made it at-hand; never allow on a failed/conflicted write.
        if protagonist not in (PorcelainWorldReads(world).location_chain(item_id) or []):
            logger.warning("equipment grant for %r did not take (%s); denying", description, item_id)
            return False
        logger.info("adjudicate: granted ordinary equipment %r → %s (held by %s)",
                    description, item_id, protagonist)
        return True
    except Exception:
        logger.exception("equipment grant failed; denying")
        return False


def adjudicate(world: Any, p: Any, protagonist: str, scene: str | None,
               requires: list[str], provider: Any = None,
               *, as_of: float | None = None) -> str | None:
    """The Adjudicate faculty (letter 028, finding E): locate() is the
    rules lawyer. Each claimed item must resolve AND be at hand (its
    containment chain reaching the player or the current scene). Returns
    None if the action stands, else the denial reason. An unresolved item
    that is ordinary role equipment is GRANTED (improvise + commit) rather
    than denied (IMPROV-AND-AUTHORITY); load-bearing/specific objects still
    deny. Deterministic after refer() (+ one cheap grant check on a miss)."""
    for description in requires:
        res = world.refer(description, frame="canon", as_of=as_of)  # at-hand only at the horizon (Cx 257)
        if getattr(res, "status", None) != "resolved" or not getattr(res, "entity_id", None):
            if _grant_equipment(world, p, protagonist, description, scene, provider):
                continue  # ordinary role equipment — granted, action stands
            return (f"{description!r} is not a thing you are known to have — "
                    f"it has never been established in this world's canon")
        entity = res.entity_id
        chain = p.locate(entity, as_of=as_of)
        if protagonist not in chain and (scene is None or scene not in chain):
            where = chain[0] if chain else "nowhere known"
            return (f"{description!r} ({entity}) is not at hand — "
                    f"it is at {where}")
    return None


def _protagonist_tokens(protagonist: str) -> list[str]:
    """Name fragments that mark third-person rendering of the player
    ('person:marn' -> 'marn'). Deterministic guard input (letter 025)."""
    slug = protagonist.split(":", 1)[-1]
    return [t for t in slug.replace("-", "_").split("_") if len(t) > 2]


def names_protagonist(text: str, protagonist: str) -> bool:
    lowered = f" {text.lower()} "
    return any(f" {tok}" in lowered.replace("’", " ").replace("'", " ")
               .replace(",", " ").replace(".", " ").replace(";", " ")
               for tok in _protagonist_tokens(protagonist))


def _conclusion_recorded(reads: Any) -> bool:
    return bool(reads.events(kind="conclusion", frame=SESSION))


#: A shape's LITERAL external result — the Contest "scoreboard" axis (Cx 027), read ALONGSIDE
#: pillar coverage. CONSOLIDATED (letters 131/132): the result is an ordinary canon Occurred EVENT
#: (declared win/loss kinds), minted by EVENT-OCCURS like any beat — the bespoke `scoreboard:main`
#: entity + `_world_event` state read + `reads_world_event` flag are RETIRED. `result_events` =
#: {"win": (kinds,), "loss": (kinds,), "participants": (ids,)} declared per-arc (None/empty → no
#: literal-result axis, the common case). Collision-proofed by participant filtering (event `kind`
#: is global — EVENT-OCCURS-FIRING.md). Reads canon events, NEVER the internal won/lost receipt
#: (which would re-couple proof to score — Cx 027 blocker 2). Loss binds over win on a tie (the
#: real result the world delivered); otherwise most-recent by valid time.
def _literal_result(reads: Any, result_events: dict | None) -> str | None:
    if not result_events:
        return None
    parts = set(result_events.get("participants") or ())

    def _last_at(kinds) -> float | None:
        # Scope by participants ALL-of (matching PB's porcelain participant filter): the event must
        # involve EVERY declared scoping entity, across agents ∪ patients — EventRow exposes those,
        # NOT a `participants` attr (the v1 bug Cx 134 caught). Empty parts → unscoped. This is the
        # collision-proofing for the global event `kind` (Cx 132 #4).
        ats = []
        for k in (kinds or ()):
            for e in reads.events(kind=k):
                if e.at is None:
                    continue
                ev = set(getattr(e, "agents", ()) or ()) | set(getattr(e, "patients", ()) or ())
                if not parts or parts <= ev:
                    ats.append(e.at)
        return max(ats) if ats else None

    win_at, loss_at = _last_at(result_events.get("win")), _last_at(result_events.get("loss"))
    if win_at is None and loss_at is None:
        return None
    if loss_at is None:
        return "win"
    if win_at is None:
        return "loss"
    return "loss" if loss_at >= win_at else "win"


def _conclusion_effect(reads: Any, arc: Arc, cost_disposition: str,
                       result_events: dict | None) -> dict | None:
    """The coverage-derived conclusion EFFECT (`conclusion_from_coverage`) for a pillar arc, or
    None when the arc declares no required pillars. The SINGLE source of truth shared by the
    commitment grade (COMMITMENT-AS-EFFECT: the grade is the EFFECT, not an LLM judgment) and the
    epilogue. `cost_weight` is the false-coverage cost integral for NORMAL polarity, 0 for
    fail_forward (comedy: a false-fill is success, never a cost — Cx 027 blocker 3)."""
    if not arc.pillars:
        return None
    summary = coverage_summary(reads, arc)
    req = summary["required"] or []
    if not req:
        return None
    cost_weight = 0.0 if cost_disposition == "fail_forward" else (len(summary["false"]) / len(req))
    world_event = _literal_result(reads, result_events)
    return conclusion_from_coverage(summary, cost_disposition=cost_disposition,
                                    world_event=world_event, cost_weight=cost_weight)


def _fire_event_occurs(world: Any, p: Any, reads: Any, arcs: list, provider: Provider,
                       action: str, tier: str, turn: int, trace: "TurnTrace",
                       protagonist: str, only_kinds: set | None = None) -> list[str]:
    """EVENT-OCCURS-FIRING (EVENT-OCCURS-FIRING.md, Cx 115): fire any authored `event_occurs`
    act-beat whose act just HAPPENED in the player's RESOLVED action, so `beat_pass` achieves it
    this turn (the fix for the arc-stall: nothing else writes arbitrary-kind canon events). Gathers
    PENDING `Occurred`-kind candidates across the arcs (main + side), asks the CONSTRAINED detector
    which occurred, and mints the canon event(s) + an action-event anchor (`caused_by`). Fail-open;
    skipped (no cohort call) when there are no pending event_occurs kinds. Returns the fired kinds."""
    from construct.arc.conditions import Occurred
    cands: dict[str, str] = {}  # kind -> beat_id; PENDING beats only, deduped by kind
    for arc in arcs:
        for beat in getattr(arc, "beats", ()):
            cond = beat.achievable_via
            if not isinstance(cond, Occurred):
                continue  # v1: direct Occurred beats (the generator's event_occurs shape)
            try:
                status = reads.state(beat.beat_id, "status", frame=PLOT)
            except Exception:
                status = None
            if status not in (None, "pending"):
                continue  # already achieved/closed → no candidate, no duplicate event
            if only_kinds is not None and cond.kind not in only_kinds:
                continue  # restricted pass (failure-tier result-event minting — see caller)
            cands.setdefault(cond.kind, beat.beat_id)
    if not cands:
        return []
    candidates = [{"kind": k, "what": k.replace("_", " ")} for k in cands]
    try:
        out = cohorts.detect_events(provider, action, tier, candidates)
        trace.cohort_calls.append("detect_events:cheap")
    except Exception as exc:  # never sink the turn on the detector
        trace.dropped_cohorts.append(f"detect_events ({exc})")
        return []
    fired = [k for k in (out.get("occurred") or []) if k in cands]  # constrained to candidates
    if not fired:
        return []
    # Mint a real canon ACTION event to anchor caused_by (Cx 115 #2 — not a session marker), then
    # the authored event(s) it caused. events(kind=X) then sees them → Occurred(kind=X) is true.
    action_eid = f"event:action_{turn}"
    rows = [{"entity": action_eid, "attribute": "kind", "value": "player_action",
             "valid_from": turn_time(turn)},
            {"entity": action_eid, "attribute": "agent", "value": protagonist,
             "value_type": "entity", "valid_from": turn_time(turn)}]
    for k in fired:
        eid = f"event:{k}_{turn}"
        # caused_by must be an EVENT-ENTITY causality ROW (Cx 117) — item-level `caused_by` is PB
        # row metadata that `events().caused_by` does not surface. Write the explicit row.
        rows += [{"entity": eid, "attribute": "kind", "value": k, "valid_from": turn_time(turn)},
                 {"entity": eid, "attribute": "agent", "value": protagonist,
                  "value_type": "entity", "valid_from": turn_time(turn)},
                 {"entity": eid, "attribute": "caused_by", "value": action_eid,
                  "value_type": "entity", "valid_from": turn_time(turn)}]
    try:
        p.ingest_structured(rows)  # canon — a true world event; the membrane is unaffected
    except Exception as exc:  # fail-open
        trace.dropped_cohorts.append(f"event_fire ({exc})")
        return []
    trace.events_fired = fired
    logger.info("event_occurs fired: %s (caused_by %s)", fired, action_eid)
    return fired


def _episode_since(reads: Any) -> float | None:
    """The valid-time of the latest EPISODE boundary, or None for a first/only episode.
    Written by `game.continue_episode` when a concluded story continues into the next
    episode (CONCLUDE→CONTINUE). Scopes `terminal_outcome` so a PRIOR episode's win/loss
    receipt doesn't freeze the new one (PB is append-only — we can't delete the old
    receipt, so we read only receipts SINCE the boundary)."""
    starts = reads.events(kind="episode_start", frame=SESSION)
    ats = [e.at for e in starts if e.at is not None]
    return max(ats) if ats else None


def terminal_outcome(reads: Any) -> str | None:
    """The recorded win/loss terminal of a `win_loss` scenario, or None if it
    hasn't ended (WIN-LOSS §10). Reads the SESSION receipt via `events()` (the
    same pattern as `_conclusion_recorded` — SESSION event rows are read by kind,
    not folded by `state()`); the outcome is encoded in the kind. Lets a
    transport stop ticking an ended story instead of re-rendering aftermath.
    Scoped to the CURRENT episode (CONCLUDE→CONTINUE): only receipts since the latest
    episode boundary count, so a continued story isn't frozen by its prior ending."""
    since = _episode_since(reads)
    if reads.events(kind="arc_won", frame=SESSION, since=since):
        return "won"
    if reads.events(kind="arc_lost", frame=SESSION, since=since):
        return "lost"
    return None


def _has_time_deadline(arc: Arc) -> bool:
    """True if the arc authored a DIEGETIC-TIME deadline — a `Quantity` over
    `time:elapsed.elapsed_minutes` in `failure_when` (King's dinner, the bomb). Only such arcs
    need diegetic time advanced BEFORE the terminal check (Cx 173 #3); every other turn keeps the
    post-render time estimate (with narration) byte-for-byte unchanged."""
    fw = getattr(arc, "failure_when", None)
    if fw is None:
        return False
    from construct.arc.conditions import Quantity, atoms_of
    from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY
    return any(isinstance(a, Quantity) and a.entity == ELAPSED_ENTITY
               and a.attribute == ELAPSED_ATTR for a in atoms_of(fw))


def _advance_diegetic_time(world: Any, clock: Any, player_input: str, trace: "TurnTrace",
                           provider: Provider, *, narration: str) -> None:
    """Estimate how much in-world time this turn consumed and APPEND it to the accrue counter
    (DIEGETIC-TIME.md). Deterministic for ordinary turns (skips the model call); the model
    `estimate_elapsed` only for explicit temporal language (a wait/jump/rest/montage). Best-effort:
    time never sinks a turn. Called EARLY for time-deadline arcs (narration unavailable → "") so the
    deadline crosses same-turn; otherwise POST-RENDER with the narration for a richer estimate."""
    try:
        from construct.clock import commit_elapsed, delta_from_estimate, deterministic_elapsed
        with _phase(trace, "time_estimate"):
            _moved = trace.movement_status in ("clear", "obscured")
            est = deterministic_elapsed(player_input, moved=_moved)
            if est is None:
                est = cohorts.estimate_elapsed(
                    provider, now=clock.render(),
                    hours_per_day=clock.calendar.hours_per_day,
                    phases=clock.calendar.phase_names,
                    action=player_input, narration=narration)
                trace.cohort_calls.append("estimate_elapsed")
            else:
                trace.cohort_calls.append("time_estimate:deterministic")
        trace.time_advanced = delta_from_estimate(clock, est)
        commit_elapsed(world, trace.time_advanced)
    except Exception as exc:  # noqa: BLE001 — time never sinks a turn
        logger.warning("diegetic-time estimate failed: %s", exc)
        trace.dropped_cohorts.append(f"estimate_elapsed ({exc})")


def run_turn(world: Any, arc: Arc, provider: Provider, player_input: str,
             turn: int, scope: list[str] | None = None,
             mode: str = "pure", endless: bool = False,
             scenario_mode: str = "endless", style: str = "",
             play_style: str = "",
             judgment_type: str = "claim-vs-fact",
             cost_disposition: str = "peril_redemption",
             result_events: dict | None = None,
             suspense: str = "general",
             cast: dict | None = None,
             side_arcs: list[Arc] | None = None,
             terminal_owner: str = "world_event",
             generate: bool = True,
             horizon: float | None = None,
             on_scene: Callable[[], None] | None = None) -> TurnResult:
    """mode: 'pure' (canon-strict; the default for determined scenarios —
    declarations are refused, claimed items are adjudicated) or
    'coauthor' (the player may declare facts into the world).
    endless: when False (default) the arc concludes and the world settles
    into aftermath at its destination; when True the world has no terminal
    arc and carries on indefinitely (clocks/NPCs keep running).
    side_arcs: the rest of the portfolio (LIVING-WORLD-GENERATOR P1). `arc` is
    the MAIN arc — it alone bears the win/loss terminal and anchors the player
    frame, scope, pins and briefing voice. Side arcs tick (clocks/beats), are
    classified per-arc, and on a non-won terminal emit FALLOUT + a diegetic
    acknowledgment; they NEVER end the scenario."""
    side_arcs = side_arcs or []
    # Fold any terminal gauge floors into failure_when (GAUGE §5): the gauge
    # declaration is the source of truth; the loss terminal is derived each load.
    arc = apply_gauge_terminals(arc)
    p = world.porcelain
    # AS-OF PLAY HORIZON (B' S3): bind EVERY read this turn to the play horizon so beats/clocks
    # and presence/adjudication never see future source rows. None (legacy/single-timeframe) =
    # the timeline head — byte-for-byte unchanged. `_h` is the local alias threaded into the
    # direct p.locate/snapshot/state calls below (the adapter handles its own via `horizon`).
    _h = horizon
    live_reads = PorcelainWorldReads(world, horizon=horizon)
    trace = TurnTrace(turn=turn)
    player_frame = _player_frame(arc)

    # ---- SERIAL SPINE -----------------------------------------------------
    # 1. Classify (cheap; fail-open to action). Movement intent + the assured-vs-
    #    uncertain resolution judgment ride the same call (no extra latency).
    moves_to, requires = "", []
    needs_test, uncertain_of = False, ""
    uses_knowledge = False  # SCENE-CONTEXT-SHAPE: protagonist-competence gate (Cx 247)
    reshape_attempt = False
    commits, commitment = False, ""
    takes = ""
    examines_target = ""  # the ONE specific detail the player closely investigates (make-it-real gate)
    asserts_or_reveals = True  # conservative default (TURN-LATENCY A-lite): keep extraction
    # A brief actor descriptor so `classify` can wave off a test for things this
    # character is plainly proficient at (ACTION-RESOLUTION §1). Cheap point reads.
    actor = ""
    try:
        proto = arc.protagonist
        bits = [live_reads.state(proto, a) for a in ("role", "kind", "background")]
        actor = "; ".join(b for b in bits if isinstance(b, str) and b) \
            or proto.split(":")[-1].replace("_", " ")
    except Exception:
        actor = arc.protagonist.split(":")[-1].replace("_", " ")
    # BEAT-DELIVERY half 2 (topic-aware ASK delivery, Cx 125): assemble the ENTRY-scene
    # present clue-bearing cast's pursuable disclosures as OPAQUE candidates so `classify`
    # can match the player's QUESTION to the right one (the ASK twin of examines_target).
    # Opaque ids (clue ids can embed the answer); descriptor = the non-spoiling hook_text
    # (fallback: holder role). The deterministic reveal gate + presence stay authoritative at
    # delivery below — this only PICKS the topic. Pre-move (entry scene): a same-turn move+ask
    # falls back to authored order (Cx 125 v1 semantics).
    ask_candidates: list = []
    _ask_by_oid: dict = {}
    if cast:
        try:
            _entry_chain = p.locate(arc.protagonist, as_of=_h)
            _entry_scene = _entry_chain[0] if _entry_chain else None
        except Exception:
            _entry_chain, _entry_scene = [], None
        if _entry_scene:
            _citer = cast.items() if hasattr(cast, "items") else [(n.node_id, n) for n in cast]
            for _nid, _node in _citer:
                if not _nid.startswith("person:") or _nid == arc.protagonist:
                    continue
                _hc = getattr(_node, "holds_clues", ()) or ()
                if not _hc:
                    continue
                try:
                    _ncolocated = _colocated(p.locate(_nid, as_of=_h), _entry_scene, _entry_chain)
                except Exception:
                    _ncolocated = False
                if not _ncolocated:
                    continue
                for _clue in _hc:
                    _oid = f"ask_{len(_ask_by_oid)}"
                    _desc = (getattr(_clue, "hook_text", "") or "").strip() \
                        or (getattr(_node, "surface_role", "") or _nid.split(":")[-1])
                    ask_candidates.append((_oid, _desc))
                    _ask_by_oid[_oid] = _clue
    asks_targets: list = []
    try:
        with _phase(trace, "classify"):
            verdict = cohorts.classify(provider, player_input, actor=actor,
                                       ask_candidates=ask_candidates)
        kind = verdict["kind"]
        moves_to = verdict.get("moves_to", "") or ""
        requires = [r for r in verdict.get("requires", []) if r]
        needs_test = bool(verdict.get("needs_test")) and kind == "action"
        uncertain_of = (verdict.get("uncertain_of") or "").strip()
        reshape_attempt = bool(verdict.get("reshape_attempt")) and kind == "action"
        commits = bool(verdict.get("commits")) and kind in ("action", "declaration")
        commitment = (verdict.get("commitment") or "").strip() or player_input
        takes = (verdict.get("takes") or "").strip()
        examines_target = (verdict.get("examines_target") or "").strip()
        asks_targets = [t for t in (verdict.get("asks_targets") or []) if t]
        # Default TRUE on absence (old stubs / schema-less classify) so extraction is never
        # silently skipped where a fact could be asserted (protected-key licensing depends on it).
        asserts_or_reveals = bool(verdict.get("asserts_or_reveals", True))
        uses_knowledge = bool(verdict.get("uses_protagonist_knowledge")) and kind == "action"
        trace.cohort_calls.append("classify:cheap")
    except ProviderError as exc:
        kind = "action"
        trace.dropped_cohorts.append(f"classify ({exc})")
    trace.classified = kind
    improv_query = ""  # set when an unanswerable question falls through to narration

    if kind == "exit":
        # Out-of-character "let's do a new story / quit" — DON'T advance the world.
        # Signal the transport, which owns the start menu and the confirm step.
        return TurnResult(prose="", trace=trace, exit_requested=True)
    if kind == "question":
        # The engine's refer (HD 003 fix) strips determiners and resolves
        # against a knows:-derived scope, so "where is my brass spoon?"
        # binds engine-side — the old host-side normalize-and-retry is
        # retired (PB catch-up).
        a = p.ask(player_input, frame=player_frame, as_of=_h)  # answer at the play horizon (Cx 255)
        prose = a.get("prose") if isinstance(a, dict) else getattr(a, "prose", None)
        facts = a.get("facts") if isinstance(a, dict) else getattr(a, "facts", [])
        if prose or facts:
            answer = prose or "; ".join(
                f"{f['entity']} {f['attribute']}: {f['value']}" for f in facts)
            trace.concealment_audit = "n/a (ask path, frame-scoped)"
            return TurnResult(prose=answer, trace=trace)
        # Canon can't answer (e.g. "where's the closest pub?" — unestablished but
        # something this character would plainly KNOW). DON'T stonewall with "you
        # can't say for certain" — that's the absence of improvisation the founder
        # flagged. Fall through to the narrator and improvise an answer GROUNDED in
        # who the player is (a long-standing resident knows the local geography),
        # under canon + concealment.
        kind = "action"
        improv_query = player_input
        uses_knowledge = True  # improvising an answer the character would plainly know → competence
        trace.classified = "question→improv"
    if kind == "ooc":
        # Answered by CONDUIT, the host persona (not the narrator, not a character):
        # game state / what's possible / help — may say whether a win-loss terminal
        # is reached, never the hidden win mechanism (founder). Fail-open to a plain
        # host line.
        state_note = (
            f"Mode: {scenario_mode}. "
            f"Win/loss terminal reached: {terminal_outcome(live_reads) is not None}. "
            f"This is turn {turn} of live play. "
            f"The session auto-saves after every turn — there is no manual save; the "
            f"player can simply stop and resume later where they left off.")
        try:
            reply = cohorts.conduit_reply(provider, player_input, state_note).strip()
            trace.cohort_calls.append("conduit:cheap")
        except ProviderError as exc:
            trace.dropped_cohorts.append(f"conduit ({exc})")
            reply = "Noted — the world holds. Say the word to continue."
        return TurnResult(prose=f"Conduit: {reply}", trace=trace)

    if kind == "declaration" and mode == "pure" and not commits:
        # A declaration that tries to AUTHOR a new world-fact by fiat is denied in canon-strict
        # mode. But a CONCLUSORY COMMITMENT (commits=True) read as a declaration ("It was Julian —
        # he killed his uncle") is NOT fact-authoring — it's the player naming their conclusion,
        # the climax the commitment path judges/concludes/bounces (#2: a hedged accusation must
        # not be stonewalled as illegal authoring just because it parsed as a declaration).
        trace.adjudication = "denied: declarations are co-author moves; this scenario is canon-strict"
        return TurnResult(
            prose="(canon-strict) This world's facts are already written — "
                  "you can act in it, but not author it. State what you DO.",
            trace=trace)

    # 1b. Adjudication (letter 028, finding E): locate() is the rules
    #     lawyer. A failed precondition means the action DOES NOT COMMIT;
    #     the failure renders honestly and is receipted, never silent.
    pre_chain = p.locate(arc.protagonist, as_of=_h)
    pre_scene = pre_chain[0] if pre_chain else None
    if requires and mode == "pure":
        denial = adjudicate(world, p, arc.protagonist, pre_scene, requires, provider, as_of=_h)
        if denial:
            trace.adjudication = f"denied: {denial}"
            prose = cohorts.narrate(
                provider,
                f"SCENE: you are at {pre_scene or 'an unresolved place'}.\n"
                f"THE PLAYER ATTEMPTED: {player_input}\n"
                f"ADJUDICATION (binding): the attempt FAILS — {denial}. "
                f"Render the failure honestly and diegetically; the world "
                f"does not bend.",
                arc.protagonist, peopled=False, competence=False)  # brief denial render (Cx 247)
            trace.cohort_calls.append("narrate:main")
            p.ingest_structured([
                {"entity": f"event:turn_{turn}", "attribute": "kind",
                 "value": "turn", "valid_from": turn_time(turn)},
                {"entity": f"event:turn_{turn}", "attribute": "adjudication",
                 "value": trace.adjudication, "valid_from": turn_time(turn)},
            ], frame=SESSION, classify="batch")  # adjudication-denial receipt — bookkeeping
            return TurnResult(prose=prose, trace=trace)

    # 2. Ingest the player's effect. FAIL-OPEN on a text-extraction schema violation
    #    (the cheap extractor occasionally malforms its JSON and the provider raises
    #    after a re-ask): the render extraction below is the authoritative capture and
    #    movement rides moves_to/refer, so a failed player-input extraction must NOT
    #    sink the turn — degrade to no player-stated facts this turn (logged).
    # TURN-LATENCY Lever A-lite (Cx 077/079): SKIP the expensive player-input extraction on
    # turns that can't assert/reveal a new fact — pure look/ask/talk, and simple move/take
    # already captured deterministically by moves_to/takes below. classify flags this via
    # `asserts_or_reveals` (default TRUE → conservative: old stubs / uncertainty keep extraction,
    # so protected-key licensing via pre_keys is never silently lost). ~6s saved on those turns.
    receipt_rows = []
    if asserts_or_reveals:
        try:
            with _phase(trace, "player_ingest"):
                receipt_rows = _receipt_rows(
                    p.ingest(player_input, source=arc.protagonist, at=turn_time(turn),
                             classify="batch", extract="lean"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("player-input extraction failed; continuing: %s", exc)
            trace.dropped_cohorts.append(f"player_ingest ({exc})")
            receipt_rows = []
    else:
        trace.dropped_cohorts.append("player_ingest (skipped: no asserts/reveals)")

    # 2b. Movement (letter 026): the player's relocation commits
    #     deterministically — refer() resolves the destination as the
    #     player named it, the move goes through the gate as a stated
    #     item, and single-parent semantics supersede the old location.
    #     Unresolved destinations fall back to whatever extraction did,
    #     loudly logged.
    if moves_to:
        # Resolve the move destination at the play horizon (Cx 257 fresh-hunt): a HEAD refer
        # would resolve a place that only exists in the source AFTERMATH, and route()'s
        # `no_path` returns empty segments (seg is None) — so a future-only place would fall
        # through and commit as live movement. as_of=_h confines the candidate set.
        res = world.refer(moves_to, frame="canon", as_of=_h)
        status = getattr(res, "status", None)
        target = getattr(res, "entity_id", None)
        # Horizon-presence guard (Cx 257): `refer` resolves an entity by its registered NAME
        # even when that entity only EXISTS in the source AFTERMATH — tier-1 identity lookup
        # bypasses the as_of candidate filter. So confirm the target is present at the play
        # horizon (has_entity is horizon-bound) before treating it as a reachable destination;
        # a future-only place is not here yet. No-op for ordinary timeless geography.
        if status == "resolved" and target and not live_reads.has_entity(target):
            logger.info("move target %s absent at the play horizon; not resolving", target)
            status, target = None, None
        # Entitlement gate (INVESTIGATION-SHAPE.md §3c / Cx 061 #3): for OFFSCENE cast, canon
        # referability is NOT player entitlement. Movement to the person OR their authored
        # place is blocked until the player has LEARNED their whereabouts (a `whereabouts` row
        # in knows:<protagonist>, written by the discovery step). Otherwise a guessed name/
        # place skips the discovery chain and layer-1 topology collapses into layer-2.
        if status == "resolved" and target and cast:
            _cbi = cast if isinstance(cast, dict) else {n.node_id: n for n in cast}

            def _undiscovered_offscene(n) -> bool:
                return (getattr(n, "presence", "") == "offscene" and bool(getattr(n, "location", ""))
                        and not live_reads.assertion_in_frame(
                            player_frame, n.node_id, "whereabouts", n.location))
            _tnode = _cbi.get(target)
            _gate = (_tnode is not None and _undiscovered_offscene(_tnode)) or any(
                _undiscovered_offscene(n) for n in _cbi.values() if n.location == target)
            if _gate:
                trace.movement_status = "undiscovered"
                logger.info("movement to undiscovered offscene target %s blocked "
                            "(no learned whereabouts)", target)
                target = None
        # Movement guard (INVESTIGATION-SHAPE.md §3c / Cx 057): a route resolves to a
        # PLACE. If the player named a PERSON ("go to Parker"), travel to that person's
        # location — never set the protagonist `in` a person. If their whereabouts aren't
        # placed/known, don't teleport; the narrator handles it diegetically.
        if status == "resolved" and target and target.startswith("person:"):
            _pchain = p.locate(target, as_of=_h)
            _person_place = _pchain[0] if _pchain else None
            if _person_place:
                logger.info("route to person %s redirected to their place %s",
                            target, _person_place)
                target = _person_place
            else:
                logger.info("route to person %s has no known place; not moving", target)
                target = None
        if status == "resolved" and target:
            # Passability (PB route(), RFC-003): a `blocked` way (a portal with a
            # blocking state/relation under the declared traversal policy) is not
            # walked — the narrator explains why. `obscured` (state unknown) is
            # allowed but flagged so the prose can hedge; missing capture degrades
            # to obscured/clear, never a false hard-block.
            origin = pre_chain[0] if pre_chain else None
            seg = _route_obstruction(p, origin, target, as_of=_h)
            if seg and seg.get("status") == "blocked":
                trace.movement_status = "blocked"
                trace.movement_obstruction = seg
                logger.info("movement blocked: %s -> %s (%s)", arc.protagonist,
                            target, seg.get("evidence"))
            else:
                p.ingest_structured([{
                    "entity": arc.protagonist, "attribute": "in", "value": target,
                    "value_type": "entity", "valid_from": turn_time(turn),
                }], classify="batch")
                trace.movement_status = seg.get("status") if seg else "clear"
                if seg:
                    trace.movement_obstruction = seg
                logger.info("player moved: %s -> %s (%s)", arc.protagonist, target,
                            trace.movement_status)
        else:
            logger.warning("movement destination %r did not resolve (%s); "
                           "relying on extraction", moves_to, status)

    # 2c. Possession (parallel to movement): when the player TAKES an object, record it
    #     as HELD (obj.in = the protagonist) deterministically — so the adjudicator and
    #     the narrator agree the player has it. (Founder's ledger bug: the player tucked
    #     the ledger under their arm but canon never tracked possession, so a later "set
    #     it back" was wrongly denied. Host-side + coreference-proof: "I take X" → X is
    #     with you, never the pronoun-phantom the extraction sometimes invents.)
    if takes:
        ores = world.refer(takes, frame="canon", as_of=_h)  # take only a horizon-present object (Cx 257)
        otarget = getattr(ores, "entity_id", None)
        # Horizon-presence guard (Cx 257): don't grant possession of a future-only object that
        # `refer` matched purely by its registered name; it doesn't exist yet at the opening.
        if otarget and not live_reads.has_entity(otarget):
            logger.info("take target %s absent at the play horizon; not granting", otarget)
            otarget = None
        if (getattr(ores, "status", None) == "resolved" and otarget
                and otarget != arc.protagonist and otarget not in _NARRATOR_PHANTOM):
            p.ingest_structured([{
                "entity": otarget, "attribute": "in", "value": arc.protagonist,
                "value_type": "entity", "valid_from": turn_time(turn),
            }], classify="batch")
            trace.took = otarget
            logger.info("player took: %s -> held by %s", otarget, arc.protagonist)

    # 3. Scene + the canon materialization (ONE snapshot serves the tick).
    chain = p.locate(arc.protagonist, as_of=_h)
    scene = chain[0] if chain else None
    # Diegetic time (DIEGETIC-TIME.md): the current moment on the governing
    # calendar (the player's place → world default), read for the briefing now and
    # advanced after the render. Best-effort — the clock never sinks a turn.
    try:
        from construct.clock import read_clock
        _clock = read_clock(world, scene)
        trace.time_now = _clock.render()
    except Exception:
        logger.exception("clock read failed")
        _clock = None
    if scope is None:
        scope = sorted(e for e in arc_entities(arc) if live_reads.has_entity(e))
        trace.point_reads += len(arc_entities(arc))
    # The scene's structural FEATURES — its `part_of`-children (PLACE-FEATURE-
    # ABSTRACTION-V1, PB 070): a place's sub-features (a hatch in the dome, the
    # desk in the office) are pulled into scope so their facts (incl. `feel`)
    # surface, and listed for the narrator. Empty until `part_of` is authored.
    scene_features = []
    if scene:
        try:
            scene_features = list(p.features(scene, as_of=_h))
        except Exception:  # read unsupported / error — never break the turn
            scene_features = []
    snap_scope = list(scope) + ([scene] if scene else []) + scene_features
    canon_snap = _snap_or_empty(p, snap_scope, as_of=_h)
    canon_table = _table(canon_snap)

    _mirror_rows(p, receipt_rows, player_frame, canon_table, trace, as_of=_h)
    touched = {row["entity"] for row in receipt_rows}
    if touched & arc_entities(arc):
        p.ingest_structured([
            {"entity": f"event:arc_touch_{turn}", "attribute": "kind",
             "value": "arc_touch", "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # arc-touch marker — bookkeeping

    # 4. World tick (strict order; beats LAST). Atoms read LIVE canon
    #    directly: per-key folds are ~0.2ms post-engine-037 (were seconds
    #    pre-fix), so the SnapshotReads batching that existed only for the
    #    old cost is retired — and reading live is more correct (clocks
    #    and beats see this turn's own commits). Snapshots below are kept
    #    only where a materialized fact LIST is needed (briefing, mirror).
    # Gauge drain FIRST (GAUGE §3, Cx 150): commit each gauge's signed per-turn
    # delta before clocks/beats/outcome so a crossed floor is visible to terminal
    # and Quantity-driven-clock evaluation THIS turn (not the post-render time slot).
    trace.gauge_levels = gauge_pass(world, arc, player_input, as_of=_h)
    # For a TIME-DEADLINE arc only (Cx 173 #3): advance diegetic time HERE — before clocks/beats/
    # outcome — so a single big-jump action ("I wait three hours", "I go watch the movie") crosses
    # the authored deadline (`failure_when` = Quantity over time:elapsed) on the SAME turn it's taken
    # (obviously the bomb goes off). The render's `trace.time_now` was read pre-advance and is left
    # unchanged, so the narration's time-of-day is unaffected; only the terminal check sees it. Every
    # NON-deadline turn keeps the richer post-render estimate (with narration), byte-for-byte as before.
    _time_committed = False
    if _clock is not None and _has_time_deadline(arc):
        _advance_diegetic_time(world, _clock, player_input, trace, provider, narration="")
        _time_committed = True
    counters = counters_from_session(live_reads, arc)
    trace.clocks_fired = clock_pass(world, arc, live_reads, counters, turn)
    # Side arcs tick on the same shared pacing counters (whole-scene property,
    # P1 simplification): their clocks live in the same plot:main frame, keyed by
    # unique ids, so they fire independently without colliding with the main arc.
    for sa in side_arcs:
        if stored_lifecycle(live_reads, sa) in LIFECYCLE_TERMINALS:
            continue  # concluded arcs no longer tick
        trace.clocks_fired += clock_pass(world, sa, live_reads, counters, turn)

    with _phase(trace, "furnish"):
        furnish_scene(p, scene, player_frame, canon_table, trace, as_of=_h)
    # SCENE-IMAGERY (founder: start the image gen ASAP, in parallel): the scene's
    # description is committed now — fire the detection/render hook here so the
    # picture renders WHILE the NPC actions + narration below run, and is ready to
    # show just before this scene's prose. Best-effort; never affects the turn.
    if on_scene is not None:
        try:
            on_scene()
        except Exception:
            logger.debug("on_scene hook failed", exc_info=True)

    # NPCs PRESENT in the scene drive their own action + speech. Presence is
    # CONTAINMENT-AWARE, not an exact `in == scene` match (founder bug: NPCs the cold
    # open narrates as HERE were going inert and never acting). A person counts as
    # present if they share the player's immediate place, OR they are anywhere within
    # the player's scene, OR their room sits on the player's own location chain — so a
    # small authoring granularity gap (player at the colony level, the clerk in a room
    # within it) no longer silences them. A person with NO location is never present.
    def _present(e: str) -> bool:
        if not scene:
            return False
        if canon_table.get((e, "in")) == scene:  # fast path: exact same place
            return True
        npc_chain = p.locate(e, as_of=_h)
        trace.point_reads += 1
        return _colocated(npc_chain, scene, chain)

    npcs = [e for e in scope
            if e.startswith("person:") and e != arc.protagonist and _present(e)]
    # TURN-LATENCY Lever 4: the speak-intent half of each present NPC's folded
    # npc_turn call, stashed here and consumed at the briefing-assembly point.
    npc_turn_results: dict = {}
    if npcs:
        # Engine reads (sheets) stay on the main thread (fast, local); the slow
        # npc_turn MODEL calls run CONCURRENTLY (decisions against the same
        # entry scene). Commits stay SERIAL so canon order is preserved.
        # SEMANTICS (Cx 022, documented-not-reverted): parallelizing the DECISIONS
        # means each NPC decides against the SAME entry scene — they act
        # SIMULTANEOUSLY within the turn, not in a serial reaction chain (NPC B no
        # longer sees NPC A's commit before deciding). For a single beat this is the
        # intended reading (all present NPCs act in the same moment) and the latency
        # win is large; the COMMITS are still serialized so canon order is
        # deterministic. If serial reaction is ever needed, drop _parallel here.
        # Horizon-bind the character-sheet read (Cx 259 fresh-hunt): this sheet feeds
        # npc_turn, whose accepted action is ingested to canon before beat_pass + terminal —
        # so a future-stamped knows:<npc> row must NOT drive NPC behavior at the play horizon.
        sheets = {npc: json.dumps(p.snapshot(npc, frame=f"knows:{npc}",
                                             lens="character_sheet", as_of=_h))[:4000]
                  for npc in npcs}
        scene_json = json.dumps(canon_snap)[:4000]
        # TURN-LATENCY Lever 4: ONE folded npc_turn call per present NPC (was two —
        # npc_world_action here + npc_intent later). The world-action half commits
        # EARLY (below, unchanged); the speak-intent half is stashed in
        # `npc_turn_results` and consumed at the briefing-assembly point downstream.
        with _phase(trace, "npc_action"):
            decisions = _parallel([
                (lambda n=npc: cohorts.npc_turn(provider, n, sheets[n],
                                                scene_json, arc.protagonist))
                for npc in npcs])
        for npc, decision in zip(npcs, decisions):
            if isinstance(decision, Exception):
                trace.dropped_cohorts.append(f"npc_turn:{npc} ({decision})")
                continue
            trace.cohort_calls.append(f"npc_turn:{npc}:cheap")
            npc_turn_results[npc] = decision  # carry the speak-intent half forward
            if decision["acts"] and decision["action"]:
                p.ingest(decision["action"], source=npc, at=turn_time(turn),
                         classify="batch")
                canon_snap = _snap_or_empty(p, snap_scope, as_of=_h)  # refresh: canon moved
                canon_table = _table(canon_snap)

    # ---- INTERVIEW DELIVERY (STORY-SHAPES §8) ----------------------------
    # Questioning a present cast member surfaces its authorized clues into the player
    # frame — the moment that advances pillar coverage in real play. Earned + bounded:
    # only when the player ENGAGES that NPC this turn (names them, or they're the only one
    # present), at most one NEW clue per NPC, gated by reveal_condition (pressure inferred
    # from the action; trust/object_seen deferred to v2). Written BEFORE beat_pass so a
    # gated beat/pillar can fire the same turn. Fail-open per clue.
    learned: list = []
    if cast and kind == "action" and npcs:
        from construct.cast import learn_clue_items, revealable_clues
        low = player_input.lower()
        pressing = _is_pressing(low, needs_test=needs_test)
        only_one = len(npcs) == 1
        # Topic-aware selection (BEAT-DELIVERY half 2, Cx 125): the clue ids the classifier
        # judged the player's question to be PURSUING (mapped back from opaque ask_* ids). The
        # deterministic reveal gate below stays authoritative — `asks_targets` only PICKS among
        # already-eligible+fresh clues; empty/irrelevant → today's authored-order behavior.
        _target_clue_ids = {getattr(_ask_by_oid[o], "clue_id", None)
                            for o in asks_targets if o in _ask_by_oid}
        for npc in npcs:
            node = cast.get(npc)
            _name = str(canon_table.get((npc, "name")) or "")
            _role = getattr(node, "surface_role", "") if node else ""
            if node is None or not (only_one or _names_entity(npc, low, name=_name,
                                                              role=_role)):
                continue
            # Eligible = gate-passing (none always; pressure/examine when the lever is present)
            # AND not already in the player frame. The gate is the rigid, algorithmic filter.
            eligible = [c for c in revealable_clues(node, pressure=pressing)
                        if not live_reads.assertion_in_frame(player_frame, *c.surface_fact)]
            if not eligible:
                continue
            # Prefer an eligible clue the classifier flagged as the question's target; else
            # fall back to the first by genuine-first rank (legacy). One fresh clue per NPC.
            clue = next((c for c in eligible if c.clue_id in _target_clue_ids), eligible[0])
            try:
                p.ingest_structured(learn_clue_items(clue), frame=player_frame,
                                    classify="batch")
                learned.append((npc, clue))
            except Exception as exc:  # one clue must not sink the turn
                trace.dropped_cohorts.append(f"learn_clue:{clue.clue_id} ({exc})")

    # ---- EXAMINE DELIVERY (EXAMINE-CHANNEL.md) -----------------------------------------
    # Inspecting a present clue-bearing OBJECT/SITE surfaces its evidentiary fact into the
    # player frame — the EXAMINE-channel analogue of interview delivery. Earned (close
    # inspection = scrutiny; a glance = examined-level), present-gated (the object must be
    # in/within the scene), one fresh clue per object per turn. A PLAIN object (not a cast
    # node) matches nothing → no delivery, so the narrator renders it as atmosphere (never
    # fabricated evidence). Object holders carry NO knows:<obj> frame — their fact rides the
    # player frame only here (Cx 073). Fail-open per clue.
    if cast and kind == "action" and _is_scrutiny(player_input.lower()):
        from construct.cast import learn_clue_items as _lci
        from construct.cast import revealable_clues as _rc
        low_ex = player_input.lower()
        _cast_items = cast.items() if hasattr(cast, "items") else [(n.node_id, n) for n in cast]
        for oid, onode in _cast_items:
            if oid.startswith("person:"):
                continue  # people are the ASK channel, handled above
            _orole = getattr(onode, "surface_role", "")
            if not _names_entity(oid, low_ex, role=_orole) or not _present(oid):
                continue
            for clue in _rc(onode, examined=True, scrutiny=True):
                e, a, v = clue.surface_fact
                if live_reads.assertion_in_frame(player_frame, e, a, v):
                    continue  # already learned — don't re-surface
                try:
                    p.ingest_structured(_lci(clue), frame=player_frame, classify="batch")
                    learned.append((oid, clue))
                except Exception as exc:  # one clue must not sink the turn
                    trace.dropped_cohorts.append(f"examine_clue:{clue.clue_id} ({exc})")
                break  # one fresh clue per object per turn

    trace.learned_clues = [c.clue_id for (_npc, c) in learned]

    # ---- DISCOVERY → REACHABILITY (INVESTIGATION-SHAPE.md §3c) -----------------------
    # When a delivered clue NAMES an off-scene cast member (their id appears in the clue's
    # fact), the player has learned where to find them: write their whereabouts into the
    # player frame (layer 2, entitlement) so the route is now player-known, and brief that
    # they may be sought (layer 3, pacing). The suspect's `in` + their place were authored as
    # canon at build (layer 1). No `route_open` flag is ever stored. Fail-open per write.
    discovered: list = []
    if cast and learned:
        cast_by_id = cast if isinstance(cast, dict) else {n.node_id: n for n in cast}
        for (_npc, clue) in learned:
            e, _a, v = clue.surface_fact
            for ref in (e, v):
                tgt = cast_by_id.get(ref)
                if (tgt is None or getattr(tgt, "presence", "") != "offscene"
                        or not getattr(tgt, "location", "")):
                    continue
                if live_reads.assertion_in_frame(player_frame, ref, "whereabouts", tgt.location):
                    continue  # already discovered — don't re-surface
                try:
                    p.ingest_structured([{"entity": ref, "attribute": "whereabouts",
                                          "value": tgt.location, "value_type": "entity"}],
                                        frame=player_frame, classify="batch")
                    discovered.append((ref, tgt.location))
                except Exception as exc:  # discovery must not sink the turn
                    trace.dropped_cohorts.append(f"discover:{ref} ({exc})")
    trace.discovered = [ref for (ref, _loc) in discovered]

    # ---- MAKE-IT-REAL: a PURSUED off-script thread becomes THE path (NARRATION-DISCIPLINE.md) -
    # When the player pursued an investigative thread that delivered NO authored clue, and an
    # unfilled required cause remains, judge (cheap) whether the pursuit can HONESTLY serve that
    # cause. If so, REROUTE: write the cause's ALREADY-AUTHORED genuine clue through the same
    # learn-clue doorway — the narrator frames it as discovered via the player's OWN detail, so
    # the case solves by THEIR path, never railroaded back to the pre-written clue. Route-flex,
    # NEVER answer-flex: the hidden answer is never minted here (the host derives the fact from
    # the authored pillar; the cohort only ROUTES). Budgeted; fail-open. SKIPPED when the player
    # is engaging an authored holder (that is a reveal-condition gate, not an un-authored thread)
    # or nothing was authored to cover. The destructive lane is NOT here — a ruinous decisive act
    # is the resolution deck + world-reaction path, never a make-it-real rescue (Cx 086).
    adapt_directives: list[str] = []
    # PURSUIT SIGNAL (Cx 087): the player CLOSELY investigated ONE specific detail — not a
    # generic look-around. `examines_target` (from classify) carries it; empty = no make-it-real
    # (avoids adapting every atmospheric mention into structure).
    if (cast and kind == "action" and not learned and generate and arc.pillars
            and examines_target):
        try:
            from construct.arc.adapt import (ADAPT_BUDGET, adaptations_used,
                                             apply_adaptation)
            from construct.cast import all_clues as _all_clues_ad
            tgt_low = examines_target.lower()
            _cast_tuple = tuple(cast.values()) if isinstance(cast, dict) else tuple(cast)
            # If the pursued target IS an authored cast entity/holder, this is the ASK/EXAMINE
            # channel (and possibly a not-yet-met reveal condition) — NOT an un-authored thread.
            # Skip make-it-real so we never short-circuit an authored gate.
            names_authored = any(
                _names_entity(n.node_id, tgt_low,
                              name=str(canon_table.get((n.node_id, "name")) or ""),
                              role=getattr(n, "surface_role", ""))
                for n in _cast_tuple)
            summ = coverage_summary(live_reads, arc)
            if (not names_authored and summ["unfilled"]
                    and adaptations_used(live_reads) < ADAPT_BUDGET):
                # unfilled pillar id -> its authored GENUINE clue fact (the reroute target —
                # writing it satisfies the pillar's genuine_via, so the cause actually covers).
                by_pillar: dict = {}
                for c in _all_clues_ad(_cast_tuple):
                    if (c.pillar_id in summ["unfilled"] and c.coverage_effect == "genuine"
                            and not c.is_red_herring and c.pillar_id not in by_pillar):
                        by_pillar[c.pillar_id] = c.surface_fact
                labels = {pl.pillar_id: pl.label for pl in arc.pillars}
                offer = [(pid, labels.get(pid, pid)) for pid in summ["unfilled"]
                         if pid in by_pillar]
                if offer:
                    with _phase(trace, "adapt"):
                        # route on the PRECISE pursued detail (Cx 089 #2), not the full input
                        decision = cohorts.adapt_decision(
                            provider, examines_target, unfilled_pillars=offer, actor=actor)
                    trace.cohort_calls.append("adapt:cheap")
                    lane = (decision or {}).get("lane")
                    pid = (decision or {}).get("pillar_id") or ""
                    if lane == "genuine" and pid in by_pillar:
                        e, a, v = by_pillar[pid]
                        ar = apply_adaptation(
                            world, {"lane": "genuine", "pillar_id": pid, "fact": [e, a, v],
                                    "reason": (decision.get("reason") or "")},
                            protagonist=arc.protagonist, turn=turn, reads=live_reads)
                        if ar.get("applied"):
                            trace.adapted.append((ar["lane"], pid))
                            adapt_directives.append(
                                "\nMAKE IT REAL (the player's OWN line of inquiry pays off — "
                                "NARRATION-DISCIPLINE): their pursuit leads them, through their "
                                "own observation and reasoning RIGHT NOW, to a NEW realization — "
                                f"that {_human_entity(a)} of {_human_entity(e)} is "
                                f"{_human_entity(str(v))}. Render this as the detail they chose "
                                "yielding THIS realization FRESHLY, this turn ('the ring tells you "
                                "X', 'now you see that…') — NOT a witness reciting it, NEVER a "
                                "redirect to another object/person. CRUCIAL: do NOT lean on facts "
                                "the player has not actually established — never write 'as you "
                                "already knew' / 'the timeline you already fixed' for anything not "
                                "yet learned; the realization arises from THIS observation alone. "
                                f"({(decision.get('reason') or '').strip()})")
        except Exception as exc:  # make-it-real must never sink a turn
            trace.dropped_cohorts.append(f"adapt ({exc})")

    # ---- STORY GOVERNANCE: weave a card, or serve the live path (CARD-WEAVING.md) -------
    # Supersedes the passive cast-threads nudge (Cx 039 #5). When there are un-played cards
    # (cast clues carrying a hook) or floor debt, ask weave_pick whether to let_run /
    # pepper_hook / deliver_card, then weave the chosen card at its seam. A card is
    # 'delivered' once its fact is in the player frame (interview delivery did it);
    # 'hook_proposed' persists in session:main so the proposal floor accrues across turns.
    # The HOOK is never the fact (the safety seam) — peppering it informs choice only.
    # Fail-open: governance must never sink a turn.
    weave_directive = None
    if cast:
        from construct.cast import all_clues as _all_clues
        from construct.cast import floor_clues as _floor_clues
        try:
            nodes = tuple(cast.values())
            clues = [c for c in _all_clues(nodes) if c.hook_text]
            delivered = {c.clue_id for c in clues
                         if live_reads.assertion_in_frame(player_frame, *c.surface_fact)}
            proposed = set(delivered)
            for c in clues:
                if live_reads.state(f"card:{c.clue_id}", "weave_state",
                                    frame=SESSION) == "hook_proposed":
                    proposed.add(c.clue_id)
            unplayed = [c for c in clues if c.clue_id not in delivered]
            req_ids = [pl.pillar_id for pl in arc.pillars if pl.required]
            debt = [c for c in _floor_clues(nodes, req_ids) if c.clue_id not in proposed]
            trace.floor_remaining = [c.clue_id for c in debt]
            if unplayed or debt:
                present = ", ".join(str(canon_table.get((n, "name")) or _human_entity(n))
                                    for n in npcs) or "(no one in particular)"
                scene_desc = (f"Place: {_human_entity(scene) if scene else 'here'}. Present: "
                              f"{present}. The player just: {player_input}")
                # Momentum CONTEXT for the storytelling judgment (not a mechanical gate —
                # "appeal to good storytelling at a distance"): tell weave_pick whether the
                # moment is urgent, flowing, freshly-woven (let it breathe), or a calm one to
                # leave alone. The judgment paces itself from this; no hard cooldown.
                _last_weave = live_reads.state("weave:pacing", "last_turn", frame=SESSION)
                _wove_recently = isinstance(_last_weave, int) and (turn - _last_weave) <= 2
                if trace.clocks_fired:
                    momentum = "URGENT — a clock/pressure is live this turn; a beat is welcome"
                elif learned:
                    momentum = "flowing — the player just turned something up; likely let it ride"
                elif _wove_recently:
                    momentum = ("a thread was woven a turn or two ago — let this scene BREATHE; "
                                "weave again only if it has genuinely gone slack")
                else:
                    momentum = ("a calm, unhurried moment — serve the player's path; weave only "
                                "if the scene has truly gone slack")
                wv = cohorts.weave_pick(
                    provider, scene_desc,
                    [f"{c.clue_id} :: {c.hook_text}" for c in unplayed],
                    [f"{c.clue_id} :: {c.hook_text}" for c in debt],
                    momentum, arc.protagonist)
                trace.cohort_calls.append("weave_pick:cheap")
                dec = wv.get("decision", "let_run")
                card_id = wv.get("card_id", "")
                by_id = {c.clue_id: c for c in unplayed}
                if card_id not in by_id:  # a stray model id can't drive state (Cx 041 nit)
                    card_id = ""
                # `deliver_card` is only safe when the fact is ALREADY earned (in the player
                # frame). Un-played cards aren't earned by definition, so demote to pepper_hook
                # (Cx 041); earned cards are carried by the LEARNED THIS TURN block, not here.
                if dec == "deliver_card":
                    dec = "pepper_hook"
                trace.weave_decision, trace.weave_card = dec, card_id
                chosen = by_id.get(card_id)
                if dec == "pepper_hook" and chosen:
                    # Build the woven directive from ONLY the AUTHORED, non-spoiling
                    # `hook_text` — NO free model prose at all (not the model's `directive`,
                    # not its `seam_hint`), so a deliver-shaped response can't smuggle the
                    # underlying fact into the narrator prompt (Cx 043/045). The narrator
                    # finds the seam itself from the scene it already has in the briefing.
                    weave_directive = (
                        f"\nWEAVE THIS IN (woven naturally into the current scene): "
                        f"{chosen.hook_text}\nSurface this as a HOOK — why the thread is worth "
                        f"pursuing — woven into what is happening now; do NOT state the "
                        f"underlying fact, and never interrupt a good moment to force it.")
                    p.ingest_structured(
                        [{"entity": f"card:{card_id}", "attribute": "weave_state",
                          "value": "hook_proposed"},
                         {"entity": "weave:pacing", "attribute": "last_turn", "value": turn}],
                        frame=SESSION, classify="batch")
        except Exception as exc:  # governance must never sink the turn
            trace.dropped_cohorts.append(f"weave_pick ({exc})")

    player_snap = _snap_or_empty(p, snap_scope, frame=player_frame, as_of=_h)
    # EVENT-OCCURS-FIRING (Cx 115): resolve the action outcome NOW (before beat_pass) so an authored
    # `event_occurs` act-beat can fire on a SUCCESSFUL act and beat_pass achieves it THIS turn. The
    # tier is drawn ONCE here (deterministic deck) and REUSED by the narrator briefing (no 2nd draw).
    _resolved_tier = ""
    if kind == "action":
        if needs_test:
            try:
                _resolved_tier = resolution.draw_tier(live_reads, p)
                trace.adjudication = f"test:{_resolved_tier}"
            except Exception as exc:  # never sink a turn on a resolution hiccup
                logger.warning("resolution draw failed: %s", exc)
                trace.dropped_cohorts.append(f"resolution ({exc})")
        else:
            _resolved_tier = "assured"
        # fire authored act-beats only on a SUCCESS tier (never a failure — Cx 115 #1). Skip
        # TERMINAL side arcs (Cx 117): a dead side arc's pending Occurred beats offer no candidates.
        if _resolved_tier in ("assured", "success_cost", "complete_success"):
            _live_arcs = [arc] + [sa for sa in side_arcs
                                  if stored_lifecycle(live_reads, sa) not in LIFECYCLE_TERMINALS]
            _fire_event_occurs(world, p, live_reads, _live_arcs, provider,
                               player_input, _resolved_tier, turn, trace, arc.protagonist)
        elif (_resolved_tier in ("failure_opportunity", "terrible_failure")
              and result_events and result_events.get("loss")
              and (commits or current_phase(live_reads, arc)
                   in (Phase.CRISIS, Phase.CLIMAX, Phase.FALLING))):
            # The LOSS half of a literal-result axis (Contest, letters 131/132 + Cx 132 #2): a
            # FAILURE at the active RESULT MOMENT IS the loss — mint the declared loss-kind
            # result-event. Gated to the result moment (a conclusory commit, OR the arc in its
            # late CRISIS/CLIMAX/FALLING phase — NOT climax_ready, which would deadlock since the
            # loss-beat can't both BE a climax beat and require climax already-achieved) so an
            # early failed action can't canonize the loss; RESTRICTED to the declared loss-kinds
            # (`only_kinds`) so ordinary beats keep the success-only rule. Main arc only (the
            # literal result is the protagonist's). The gate's exact shape is validated against a
            # real Contest arc in the #33 pass; dormant until an arc declares result_events.
            _fire_event_occurs(world, p, live_reads, [arc], provider,
                               player_input, _resolved_tier, turn, trace, arc.protagonist,
                               only_kinds=set(result_events.get("loss") or ()))
    # WORLD-CHANGING AGENCY (flag-gated, default OFF — WORLD-CHANGING-AGENCY.md): an
    # earned, uncertain act may RESHAPE canon. Commit PRE-beat_pass (so the arc reacts
    # THIS turn) through the host doorway, then patch the local materialization the
    # post-render gate reads (canon_table is a stale snapshot — Cx 204/205 #1) and
    # license the exact sanctioned rows so the narrator may restate them past the
    # protected-key gate (Cx 204/205 #2). Inert when off: apply_reshape returns None →
    # no patch, no license, no briefing change. Private witness frames are NOT licensed.
    _reshape_license: set[tuple[str, str, str]] = set()
    # The reshape judge (a model call) runs ONLY when classify flagged a genuine miraculous
    # attempt — so an ordinary uncertain action (pick a lock, search) never pays for it. This
    # cheap pre-filter is what lets world-changing be ON by default without taxing every turn.
    if reshape_attempt and needs_test and _resolved_tier not in ("", "assured"):
        _snap = set(snap_scope)
        _scene_facts = "; ".join(
            f"{e.split(':', 1)[-1]}.{a}={v}"
            for (e, a), v in list(canon_table.items()) if e in _snap)[:1200]
        _rr = apply_reshape(world, provider, action=player_input,
                            scene=(scene or arc.protagonist),
                            canon=f"{uncertain_of}. {_scene_facts}".strip(),
                            tier=_resolved_tier, turn=turn)
        if _rr is not None:
            trace.reshape = _rr.summary
            for _row in _rr.canon_rows:
                if _row["entity"] == _rr.event_id:
                    continue  # the reshape EVENT anchor, not a player-visible world fact
                canon_table[(_row["entity"], _row["attribute"])] = _row["value"]
                _reshape_license.add((_row["entity"], _row["attribute"], _row["value"]))
            # Carry the visible reshape entities so the Session can keep them in NEXT-turn
            # scope (Cx 221): a revived NPC the replacement arc doesn't reference must not
            # drop out of scene awareness after the re-plan.
            trace.reshape_entities = sorted({r["entity"] for r in _rr.canon_rows
                                             if r["entity"] != _rr.event_id})
            logger.info("world reshape committed: %s (%d visible rows licensed)",
                        _rr.event_id, len(_reshape_license))
            # The reshape may have made the destination stale → re-aim the MAIN arc
            # (first cut: re-evaluate on every LANDED reshape; the cohort judges staleness
            # and can keep the through-line). Same-turn swap so beat_pass + briefing + gate +
            # outcome all run from the new arc (Cx 210/212). Flag-gated via apply_reshape above.
            if _rr.landed:
                from construct.arc import io as arc_io
                from construct.game import author_replan
                _ro = author_replan(world, arc, provider, reshape_summary=_rr.summary, turn=turn)
                if _ro.reason == "replanned" and _ro.arc is not None:
                    arc_io.replan_main_arc(world, _ro.arc, turn=turn)
                    arc = _ro.arc                       # swap the LIVE arc — all downstream uses it
                    trace.replanned = arc.arc_id
                    # Refresh scope + snapshots from the NEW arc. CRUCIAL (Cx 215 #2): also
                    # include the VISIBLE committed reshape entities (landed state/restage/
                    # consequence rows, not the event anchor) — a coherent replacement arc may
                    # not reference a restaged entity (e.g. a revived NPC) via arc_entities, and
                    # a fresh PB read only carries rows whose entities are in the requested scope.
                    _reshaped_ents = [r["entity"] for r in _rr.canon_rows
                                      if r["entity"] != _rr.event_id and live_reads.has_entity(r["entity"])]
                    _new_scope = sorted(set(e for e in arc_entities(arc) if live_reads.has_entity(e))
                                        | set(_reshaped_ents))
                    snap_scope = _new_scope + ([scene] if scene else []) + scene_features
                    canon_snap = _snap_or_empty(p, snap_scope, as_of=_h)
                    canon_table = _table(canon_snap)
                    player_snap = _snap_or_empty(p, snap_scope, frame=player_frame, as_of=_h)
                    logger.info("arc re-planned mid-story -> %s", arc.arc_id)
                elif _ro.reason == "no_replacement":
                    # The old destination is gone and nothing coherent replaces it → EXPLICIT
                    # old-main-arc fallout (never a silent stale arc, never a broken install).
                    try:
                        _fo = emit_fallout(world, arc, "incompletable", turn)
                        trace.arc_fallout.append(arc.arc_id)
                        trace.reshape = (trace.reshape + " " + _fo.directive).strip()
                    except Exception:
                        logger.exception("reshape no_replacement fallout failed")
                # provider_error → keep the current arc + the committed reshape (fail-open)
    achieved, closed, revealed = beat_pass(world, arc, live_reads, turn)
    trace.beats_achieved, trace.beats_closed = achieved, closed
    trace.reveals = revealed
    # Side-arc beats tick too (their statuses drive side-arc lifecycle below).
    # Folded into the trace lists for the debug surface; main-arc `achieved`
    # alone drives pacing/pins (the player is the main protagonist).
    for sa in side_arcs:
        if stored_lifecycle(live_reads, sa) in LIFECYCLE_TERMINALS:
            continue
        sa_ach, sa_closed, sa_rev = beat_pass(world, sa, live_reads, turn)
        trace.beats_achieved += sa_ach
        trace.beats_closed += sa_closed
        trace.reveals += sa_rev

    # ---- PINNED AWARENESS (PINNED-AWARENESS spec; reviews 060/062/063) ---
    # One awareness coordinate for the WHOLE assembly (Kernos 060 #2 / Cx #2):
    # region ancestry (the turn's current chain), the scene's present entities,
    # and the temporal window all resolve as-of the same `now`. Candidates come
    # from the arc's pin set (the host index, never a log scan).
    awareness_as_of = turn_time(turn)
    pin_subjects: set[tuple] = set()
    active_pins: list = []
    if arc.pins:
        present_entities = {e for (e, a), v in canon_table.items()
                            if a == "in" and v == scene}
        present_entities.add(arc.protagonist)
        try:  # `spent` pins recede permanently (Kernos 060 #6); none normally
            spent = {a for ev in live_reads.events(kind="pin_spent", frame=SESSION)
                     for a in ev.agents}
        except Exception:
            spent = set()
        # Arc progress drives foreshadowing escalation: fraction of REQUIRED
        # beats achieved → an `escalates` pin's clue gets louder as the reveal
        # nears (v2 clue-trail).
        required = [b for b in arc.beats if b.weight is Weight.REQUIRED]
        done = sum(1 for b in required
                   if live_reads.assertion_in_frame("plot:main", b.beat_id, "status", "achieved"))
        progress = (done / len(required)) if required else 0.0
        active_pins = resolve_active_pins(
            arc.pins, ancestry=set(chain), present_entities=present_entities,
            as_of=awareness_as_of, spent=spent, progress=progress)
        pin_subjects = {ap.subject_key for ap in active_pins}
        trace.pins = [(ap.pin.pin_id, ap.pin.scope_kind, round(ap.salience, 3))
                      for ap in active_pins]

    # ---- ASSEMBLY FAN-OUT (reuses the tick's materializations) -----------
    # The protagonist's facts are recast as "you" and segregated — the
    # narrator must never see the player listed as a scene entity
    # (letter 025: the briefing itself was inviting third-person Marn).
    # A pinned subject is suppressed from the plain scene list and surfaced
    # ONLY in the PINS block, with its directive (dedupe, Kernos 060 #5).
    # Render grounding BY NAME, never raw ids — cleaner for the narrator and it
    # closes an id-leak (the narrator must speak the world's names, not 'person:x').
    # Names are resolved from the player frame (so still frame-scoped, no leak); an
    # entity with no established name falls back to a humanized id.
    _NAME_ATTRS = ("name", "alias", "title")
    names = {}
    for f in player_snap.get("facts", []):
        if f["attribute"] in _NAME_ATTRS and f["entity"] not in names:
            names[f["entity"]] = str(f["value"])

    def _disp(x: Any) -> str:
        s = str(x)
        if s in names:
            return names[s]
        if ":" in s and s.split(":", 1)[0] in ("person", "place", "obj", "fact", "event"):
            return s.split(":", 1)[-1].replace("_", " ")
        return s

    scene_lines, you_lines = [], []
    for f in player_snap.get("facts", []):
        if f["attribute"] in _NAME_ATTRS:
            continue  # names feed the resolver above, not shown as bare facts
        if f["entity"] == arc.protagonist:
            you_lines.append(f"you · {f['attribute']} · {_disp(f['value'])}")
        elif (f["entity"], f["attribute"]) in pin_subjects:
            continue
        else:
            scene_lines.append(f"{_disp(f['entity'])} · {f['attribute']} · {_disp(f['value'])}")
    trace.briefing_frames = [player_frame]

    # Irony delta via the designed sixth read (frame_diff) — restored
    # after PB's indexed read path landed (letter 024; measured 0.68s on
    # the live world vs >250s pre-fix).
    player_table = _table(player_snap)
    diff = p.frame_diff("canon", player_frame, sorted(set(snap_scope)), as_of=_h)  # Cx 255
    threads = [f"{f['entity']} · {f['attribute']} · {f['value']}" for f in diff][:12]
    trace.irony_delta_size = len(diff)

    # Conclusion detection (endless mode). Bounded worlds settle into
    # aftermath once the arc reaches its destination — the navigator
    # stops pushing toward an end already reached. Endless worlds note
    # the milestone but keep their pressure/clocks running indefinitely.
    # TERMINAL OWNER (Cx 141): for COMMITMENT-owned shapes (deduction/contest/…), world_condition
    # being met is READINESS for the reckoning, NOT the conclusion — the player's conclusory
    # commitment owns the curtain (the audit-office falter: seizing evidence ended the story before
    # the accusation could land). Such an arc concludes only on (a) refusal, (b) a landed commitment
    # [below], or (c) the post-climax window expiring (the reckoning never came). WORLD-EVENT-owned
    # shapes (endurance/farce) keep the direct world_condition terminal — unchanged.
    from construct.arc.conditions import Truth as _Truth
    from construct.arc.conditions import evaluate as _evaluate
    _commitment_owned = terminal_owner == "commitment"
    # DIEGETIC-CLOCK CONCLUSION (founder ruling 2026-06-25; Cx 173): turns are FREE — NO turn-count
    # ever forces a conclusion. A commitment-owned arc with no authored deadline stays READY forever;
    # it concludes ONLY on the player's commitment [below] or a crossed AUTHORED `failure_when`
    # (a fiction deadline = Quantity over time:elapsed, or an authored loss event). `_reckoning_ready`
    # remains, but ONLY as the narrator nudge ("THE RECKONING IS AT HAND") — never a countdown.
    # Gated on win_loss too (story-agnostic scoping): the nudge steers toward a CONCLUSORY move,
    # which only exists when the story has a win/loss destination. An endless/sandbox story (idle
    # family dynamics, open-ended romance, slice-of-life) has no conclusion to steer toward, so it
    # never gets the nudge — it just plays on.
    _reckoning_ready = _commitment_owned and scenario_mode == "win_loss" and (
        climax_ready(live_reads, arc)
        or _evaluate(arc.shape.world_condition, live_reads) is _Truth.TRUE)
    _authored_failure = (arc.failure_when is not None
                         and _evaluate(arc.failure_when, live_reads) is _Truth.TRUE)
    concluded = arc_concluded(live_reads, arc)
    if _commitment_owned:
        # world_condition is READINESS, not a conclusion. The only forced close is an authored
        # failure (deadline/loss event); the commitment's own terminal is handled below.
        concluded = _authored_failure
    trace.concluded = concluded
    if concluded and not _conclusion_recorded(live_reads):
        p.ingest_structured([
            {"entity": f"event:conclusion_{turn}", "attribute": "kind",
             "value": "conclusion", "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # conclusion marker — bookkeeping

    # Win/loss termination (WIN-LOSS §10): STRICTLY in `win_loss` mode (founder
    # ruling) — endless/freeplay never terminate. On the first won/lost, write
    # the one-time SESSION receipt; this turn renders the flavored aftermath, and
    # the transport stops ticking thereafter (Session reads terminal_outcome).
    # Main-arc lifecycle (LIVING-WORLD-GENERATOR §3): won/lost via arc_outcome,
    # plus incompletable/cancelled. For the MAIN arc in win_loss, a non-won
    # terminal ends the story as a loss (the win is foreclosed) — mapped to the
    # one-time `arc_lost` receipt. The main arc never emits fallout (its ending
    # IS the story's ending — the epilogue handles it); only side arcs regenerate.
    # CONCLUSORY COMMITMENT (STORY-SHAPES.md win-model): the player's decisive climactic
    # move ENDS the story — when it's EARNED (climax-ready, never turn 1). Capture +
    # JUDGE it ONCE (host call, not per-turn) → a graded outcome (vindicated / partial /
    # wrong / pyrrhic). The grade is EPILOGUE FLAVOR, not a pass/fail gate: a WRONG
    # accusation still concludes the story (the wrong person goes down; the twist lands
    # at the curtain). `knows:player` stays the evidence store — the held answer never
    # had to enter it. In endless mode the commitment is recorded + reflected, not terminal.
    # EARNED gate: a commitment concludes once the player has genuinely PLAYED — either
    # the arc is climax-ready, OR enough turns have passed (the card model means the
    # engine never just hands the answer into the player frame, so we must NOT require
    # that; "earned" = they've had the chance to investigate, not "the engine told them").
    # A turn-1 accusation is too abrupt — it stays an ordinary action until then.
    earned = climax_ready(live_reads, arc) or turn >= _MIN_COMMIT_TURN
    commitment_grade = ""
    commitment_bounced = False
    if commits and earned and terminal_outcome(live_reads) is None:
        # COMMITMENT-AS-EFFECT slice 1 (Cx 105): a voluntary conclusive commitment LANDS only when
        # the payoff is EARNED — for an arc with REQUIRED pillars, required coverage must be
        # `complete` (genuine OR false; false counts, so a hollow case can still land). An INCOMPLETE
        # attempt BOUNCES, non-terminal — BEFORE the judge and BEFORE any commitment rows: no judge
        # call, no claim/grade, no event:commitment, no terminal; the narrator nudges "not yet
        # proven" and play continues. Scoped to the VOLUNTARY-commitment path only — forced closes
        # (clocks/refusal/scoreboard/arc_concluded) are untouched. No required pillars (legacy/
        # optional-only) → keep the existing judge/terminate path (gate on `required`, not arc.pillars).
        _csum = coverage_summary(live_reads, arc)
        if _csum.get("required") and not _csum.get("complete"):
            commitment_bounced = True
            logger.info("commitment bounced (not yet proven): unfilled required pillars %s",
                        _csum.get("unfilled"))
    if commits and earned and not commitment_bounced and terminal_outcome(live_reads) is None:
        # COMMITMENT-AS-EFFECT slice 2 (Cx 105/107): for a PILLAR arc the grade IS the coverage
        # EFFECT — computed ALGORITHMICALLY from `conclusion_from_coverage` (cost_disposition-aware),
        # never an LLM judgment (the model did this rigid-criteria work and got it WRONG live). The
        # accusation follows the evidence the player actually gathered, so coverage already encodes
        # just-vs-hollow: `wrong_case` (a required cause covered by a FALSE clue — a red herring
        # believed → an unjust/mistaken conviction) → 'wrong'; the intended/sound effect →
        # 'vindicated'; otherwise 'partial'. fail_forward (comedy) is honored (a live blowup is
        # effect-sound, never wrong_case). LEGACY pillar-less arcs keep the LLM judge — extracting a
        # verdict from open language with no coverage to read is genuinely its job.
        if _csum.get("required"):
            _eff = _conclusion_effect(live_reads, arc, cost_disposition, result_events)
            if _eff and _eff.get("wrong_case"):
                commitment_grade = "wrong"
            elif _eff and _eff.get("effect_sound"):
                commitment_grade = "vindicated"
            else:
                commitment_grade = "partial"
        else:
            destination = _destination_facts(arc, live_reads)
            try:
                jv = cohorts.judge_commitment(provider, commitment, judgment_type, destination)
                commitment_grade = jv.get("grade", "") or "partial"
                trace.cohort_calls.append("judge_commitment:cheap")
            except Exception as exc:  # never sink the turn on the judge
                logger.warning("judge_commitment failed: %s", exc)
                commitment_grade = "partial"
                trace.dropped_cohorts.append(f"judge_commitment ({exc})")
        p.ingest_structured([
            {"entity": f"claim:{arc.protagonist}", "attribute": "committed",
             "value": commitment[:300]},
            {"entity": f"claim:{arc.protagonist}", "attribute": "grade",
             "value": commitment_grade},
        ], classify="batch")
        p.ingest_structured([
            {"entity": f"event:commitment_{turn}", "attribute": "kind",
             "value": "commitment", "valid_from": turn_time(turn)},
            {"entity": f"event:commitment_{turn}", "attribute": "grade",
             "value": commitment_grade, "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # commitment marker — bookkeeping
    trace.commitment = commitment if commits else ""
    trace.commitment_grade = commitment_grade
    trace.commitment_bounced = commitment_bounced

    main_life = arc_lifecycle(live_reads, arc)
    trace.lifecycle = main_life
    outcome = arc_outcome(live_reads, arc)
    if _commitment_owned:
        # For a commitment shape, `world_condition` is READINESS, not victory, so don't let
        # arc_outcome's won-first mask an authored deadline (Cx 173 #4): evaluate `failure_when`
        # DIRECTLY. Only an authored failure (a crossed fiction deadline / loss event) can close a
        # ready arc; turn-count refusal/post-climax expiry no longer terminate. The commitment
        # [below] owns the win.
        outcome = "lost" if _authored_failure else None
    if outcome is None and main_life in ("incompletable", "cancelled"):
        outcome = "lost"
    # The commitment IS the conclusion (convergence): it terminates regardless of the
    # world_condition. The grade maps to the binary terminal receipt (wrong → lost; all else →
    # won) while the EFFECT (conclusion_from_coverage) is what the player feels. For pillar arcs
    # the grade is now derived FROM that effect (slice 2), so receipt + epilogue can't contradict:
    # an unjust/hollow conviction → 'wrong' → lost → terminal → a wrong_case epilogue (the
    # conviction still concluded, on a hollow note); a sound case → 'vindicated' → won → triumph.
    if commitment_grade and outcome is None:
        outcome = "lost" if commitment_grade == "wrong" else "won"
    trace.outcome = outcome
    terminal = scenario_mode == "win_loss" and outcome is not None
    trace.terminal = terminal
    # CONCLUSION AS EFFECT (STORY-SHAPES §0a): when the arc declares pillars, the conclusory
    # scene's CHARACTER is the narrated effect of pillar COVERAGE, not a win/lost verdict. The
    # won/lost receipt above stays as the "episode concluded, stop ticking" plumbing; this is what
    # the player feels. Uses the SAME `_conclusion_effect` the commitment grade derives from (slice
    # 2), so the receipt, the grade, and the epilogue can never disagree.
    conc = None
    if terminal or (concluded and not endless):
        conc = _conclusion_effect(live_reads, arc, cost_disposition, result_events)
        if _commitment_owned and _authored_failure and not commitment_grade:
            # AUTHORED DEADLINE/FAILURE closed a ready arc with no commitment (Cx 173): the fiction's
            # clock ran out (or its loss event fired) before the player drew the curtain. Force a
            # quiet-failure close — NOT the positive coverage effect — so the rendered shape matches
            # the `lost` receipt. (Only fires when the story AUTHORED a deadline/failure; a
            # no-deadline arc never reaches here — it just stays ready.)
            conc = {"outcome": "quiet_failure", "sound": False, "effect_sound": False,
                    "wrong_case": False,
                    # Agnostic basis: an authored failure_when fired with no commitment — a missed
                    # deadline (King's dinner), a decisive loss event (the protectee killed), etc.
                    # The narrator's epilogue renders the SPECIFIC event from world-state; this is the
                    # neutral fallback so it fits any story's "IT", not just a time deadline.
                    "basis": "the story's decisive turn came and went unmet"}
        # GAUGE coloring (GAUGE §5): a WIN earned on the last of the reserve is a COSTLY
        # victory, not a clean triumph — the gauge supplies the number, the shape the meaning.
        if conc and outcome == "won" and conc.get("outcome") == "triumph" \
                and gauge_coloring(arc, world, as_of=_h) == "costly":
            conc = dict(conc, outcome="costly_victory",
                        basis=conc.get("basis", "") +
                        " — but it was won on the last of the reserve, at the edge of disaster")
        if conc:
            trace.conclusion_shape = conc["outcome"]
            trace.conclusion_basis = conc["basis"]
    if terminal and terminal_outcome(live_reads) is None:
        p.ingest_structured([
            {"entity": f"event:arc_outcome_{turn}", "attribute": "kind",
             "value": f"arc_{outcome}", "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # terminal receipt — bookkeeping
        set_lifecycle(world, arc, main_life, turn)
        # COMMITMENT-AS-EFFECT slice 3 (Cx 105 #5): a HOLLOW/unjust main landing writes a CONCRETE
        # canon consequence — the fallout the next episode grows from — anchored via `caused_by` to
        # the conclusion event. NOT a derived label ('hollow'/'irony'), NOT side-arc emit_fallout.
        # Deduction worked example: the case convicted on a red herring → the REAL culprit was never
        # brought to justice → they walk free (a true world fact, the book-2 hook). The protagonist-
        # knowledge gap is STRUCTURAL: this is CANON (the world knows the culprit is at large);
        # knows:<protagonist> does NOT get it — the protagonist believes they convicted rightly,
        # unless/until it surfaces. Fail-open; never sinks the terminal turn.
        if conc and conc.get("wrong_case") and cast:
            _cast_items = cast.items() if isinstance(cast, dict) else [(n.node_id, n) for n in cast]
            _culprit = next((cid for cid, n in _cast_items if getattr(n, "is_culprit", False)), None)
            if _culprit:
                try:
                    p.ingest_structured([
                        {"entity": _culprit, "attribute": "brought_to_justice", "value": "false",
                         "caused_by": f"event:arc_outcome_{turn}", "valid_from": turn_time(turn)},
                    ])  # canon (default frame) — the real culprit walks free; generator/next-episode fuel
                    trace.main_fallout.append((_culprit, "brought_to_justice", "false"))
                    logger.info("hollow landing: %s at large (caused_by the botched case)", _culprit)
                except Exception as exc:  # fallout must never sink the terminal turn
                    trace.dropped_cohorts.append(f"main_fallout ({exc})")

    # Side-arc lifecycle: classify each, and on the FIRST transition to a
    # terminal (guarded by the persisted lifecycle row so re-entry never re-fires)
    # acknowledge it diegetically and — for a non-won terminal — emit FALLOUT
    # (a standing canon consequence, generator fuel). Side arcs NEVER terminate
    # the scenario (no arc_won/arc_lost receipt, `ended` stays False).
    fallout_directives: list[str] = []
    fallouts = []  # the Fallout records (non-won terminals) — fuel for the generator
    for sa in side_arcs:
        if stored_lifecycle(live_reads, sa) in LIFECYCLE_TERMINALS:
            continue
        life = arc_lifecycle(live_reads, sa)
        if life == "active":
            continue
        set_lifecycle(world, sa, life, turn)
        trace.arc_fallout.append(sa.arc_id)
        if life == "won":
            fallout_directives.append(
                f"A side thread resolved in the world's favor — "
                f"{_human_entity(sa.protagonist)}'s matter came good. Note it in "
                f"passing; it is not the player's victory.")
        else:
            fo = emit_fallout(world, sa, life, turn)
            fallout_directives.append(fo.directive)
            fallouts.append(fo)

    # ---- THE OPPORTUNISTIC DM GENERATOR (LIVING-WORLD-GENERATOR P2a) ------
    # A dead arc seeds the next one. Paced, gated, fail-open; mints into the
    # hidden plot frame, surfaces only as a diegetic hook. One mint per turn.
    gen_hooks: list[str] = []
    if generate and fallouts:
        ctx = {
            "style": style,
            "available_ids": sorted(set(scope or []) | set(npcs) | {arc.protagonist}),
            "present_characters": "\n".join(
                f"{n}: drive={canon_table.get((n, 'drive'))} "
                f"fear={canon_table.get((n, 'fear'))}" for n in npcs) or "(none in scene)",
        }
        try:
            minted = generate_from_fallout(world, live_reads, provider,
                                           fallouts[0], side_arcs, ctx, turn)
        except Exception as exc:  # the generator NEVER breaks the turn
            logger.warning("DM generator failed: %s", exc)
            minted = None
        if minted is not None:
            new_arc, hook = minted
            side_arcs.append(new_arc)  # ticks from next turn; also in the portfolio
            trace.generated.append(new_arc.arc_id)
            if hook:
                gen_hooks.append(hook)

    counters = counters_from_session(live_reads, arc)
    rung = navigate(counters, len(diff), bool(achieved))
    if concluded and not endless:
        rung = None  # the arc has resolved; do not escalate toward a reached end
    trace.pacing = ("concluded" if (concluded and not endless)
                    else (rung.value if rung else "hold"))

    nudge_directive = None
    # Card weaving (CARD-WEAVING.md) SUBSUMES the legacy thread-nudge for cast worlds (Cx
    # 039 #2) — don't double-fire. The nudge remains for pillar/cast-less worlds.
    if rung and threads and not cast:
        try:
            with _phase(trace, "nudge"):
                pick = cohorts.nudge_pick(provider, rung.value, threads,
                                          "\n".join(scene_lines), arc.protagonist)
                trace.cohort_calls.append("nudge_pick:cheap")
                # Deterministic player-boundary guard (letter 025): a
                # directive that names the protagonist is re-asked once,
                # then DROPPED (fail-open) — pressure, never puppetry.
                if names_protagonist(pick["directive"], arc.protagonist):
                    pick = cohorts.nudge_pick(provider, rung.value, threads,
                                              "\n".join(scene_lines), arc.protagonist)
                    trace.cohort_calls.append("nudge_pick:cheap(re-ask)")
            if names_protagonist(pick["directive"], arc.protagonist):
                trace.dropped_cohorts.append("nudge (named the protagonist twice)")
            else:
                nudge_directive = pick["directive"]
                trace.nudge = nudge_directive
        except ProviderError as exc:
            trace.dropped_cohorts.append(f"nudge_pick ({exc})")

    npc_intents: list[str] = []
    if npcs:
        # TURN-LATENCY Lever 4: the speak-intent was already decided in the folded
        # npc_turn call at the early npc phase (one call per NPC). Consume the stashed
        # results here for the briefing — no second model call.
        for npc in npcs:
            intent = npc_turn_results.get(npc)
            if intent is None:  # the folded call failed-open for this NPC
                continue
            if intent["speaks"]:
                npc_intents.append(f"{npc}: wants {intent['intent']}"
                                   + (f" (voice: {intent['line_hint']})"
                                      if intent.get("line_hint") else ""))

    # ---- BRIEFING (no plot:, structurally — player-frame reads only) ----
    # Continuity: the recent story (player actions + the narrator's own beats) as a
    # rolling window — the narrator's short-term memory, since each turn is a fresh
    # stateless call. Rich but bounded to the last `_RECENT_TURNS`.
    try:
        _raw_tr = live_reads.state(_TRANSCRIPT, "recent", frame=SESSION)
        _recent = json.loads(_raw_tr) if _raw_tr else []
    except Exception:
        _recent = []
    # The compacted long-arc memory (themes/dynamics/threads beneath the recent
    # beats) — Kernos-style, host-side, never canon. Empty until beats age out.
    narrative_memory = live_reads.state(_MEMORY, "text", frame=SESSION) or ""
    # Out-of-character creative suggestions the engine agreed to TRY (`/ooc`):
    # soft aspirations, never canon — weave one in only where it fits.
    try:
        wishes = json.loads(live_reads.state("session:wishes", "list", frame=SESSION) or "[]")
    except (ValueError, TypeError):
        wishes = []
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
            "to them):\n" + "\n".join(seek_lines))
    if terminal:
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
        cast = sorted({arc.protagonist}
                      | {e for e in arc_entities(arc) if e.startswith("person:")})
        reveal_scope = [e for e in (set(arc_entities(arc)) | set(scope or []))
                        if e.startswith(("person:", "place:", "obj:", "fact:"))
                        and live_reads.has_entity(e)]
        reveal = [f"{f['entity']} · {f['attribute']} · {f['value']}"
                  for f in _snap_or_empty(p, sorted(reveal_scope), as_of=_h).get("facts", [])
                  if f["entity"] != arc.protagonist][:20]
        _ending_tag = conc["outcome"] if conc else f"{outcome}; grade: {_grade}"
        briefing_parts.append(
            f"\nTHE STORY ENDS HERE ({_ending_tag}). This conclusion is the EFFECT of what "
            f"the player did and left undone — narrate it as consequence, never as a "
            f"score. Render a final, buttoned-up EPILOGUE — {flavor}. Like a film's "
            f"closing: for the protagonist "
            f"(you) AND each of these characters, give a fitting FATE — where they end up, "
            f"what the outcome cost or won them: {cast}. Concealment lifts now (the story "
            f"is over): name what was hidden. And HAVE FUN with it — savor the interesting "
            f"things the player never uncovered: the secret they walked past, the "
            f"connection they missed, what the red herrings really were. Close every "
            f"thread in the settled wake; apply NO new pressure, open NO new hooks.")
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
                "make it for them, and do not reveal anything hidden. The curtain is theirs to draw.")
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
    if npcs:
        # WHO IS PRESENT (continuity guard — Cx 091 #1): name EVERY present character, not just
        # the ones who speak this turn. A silent present NPC (standing quietly, watching) was
        # surfacing only as raw fact triples and the narrator could erase them ("the doctor is
        # the only one here") — a coherence break against the cold open. Speakers carry their
        # wants; the rest are simply named as present so they can't vanish.
        present_lines = []
        for n in npcs:
            nm = str(canon_table.get((n, "name")) or _human_entity(n))
            intent = npc_turn_results.get(n)
            if intent and intent.get("speaks") and intent.get("intent"):
                line = f"{nm}: wants {intent['intent']}"
                if intent.get("line_hint"):
                    line += f" (voice: {intent['line_hint']})"
                present_lines.append(line)
            else:
                present_lines.append(f"{nm}: present, silent for now (do NOT remove them from "
                                     f"the scene — they remain here unless they visibly leave)")
        briefing_parts.append(
            "\nPRESENT CHARACTERS (all of them are HERE right now — keep every one in the scene; "
            "play the ones with wants, keep the rest present even if quiet):\n"
            + "\n".join(present_lines))
    if nudge_directive:
        briefing_parts.append(f"\nPACING DIRECTIVE (weave in diegetically): {nudge_directive}")
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
            f"refusal: whoever fields it reacts as a person would (see A PEOPLED WORLD) — "
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
            "react with full emotion (see A PEOPLED WORLD), they simply do not give the "
            "answer away. The player draws their own conclusions — let them, even when "
            "they are heading somewhere wrong. The truth is told only at the end, never "
            "coaxed out mid-play.")
        # The DM's CARD: the hidden destination to FORESHADOW toward (card model). Gives
        # the narrator the answer so it can lay a convergent trail; "weave, don't blurt".
        dest = _destination_directive(arc, live_reads)
        if dest:
            briefing_parts.append(dest)
    briefing = "\n".join(briefing_parts)
    trace.briefing = briefing  # captured for the mechanics log (the directives → the prose)

    # ---- RENDER (loud-fail) ----------------------------------------------
    # SCENE-CONTEXT-SHAPE Stage 2: the peopled / competence directives ride the window
    # ONLY when this turn triggers them — present cast (containment-aware npcs), and a
    # capability-dependent protagonist-knowledge move (classify's uses_protagonist_knowledge,
    # or the question→improv ordinary-knowledge fallthrough). Cx 247 / K 080.
    _peopled, _competence = bool(npcs), uses_knowledge
    # RULE OF COOL (founder 2026-06-27): inject the improv-serves-the-thread directive when there
    # is a rich live thread to gravitate toward — present cast, unwalked threads, or an authored
    # cast/pillar surface. Keeps the narrator's improv enriching the core, not inventing hollow
    # tangents (the castdemo rabbit-hole). Off on a genuinely empty scene (no always-on mass).
    _serve_thread = bool(npcs or threads or cast)
    with _phase(trace, "narrate"):
        prose = cohorts.narrate(provider, briefing, arc.protagonist,
                                peopled=_peopled, competence=_competence,
                                serve_thread=_serve_thread)
    trace.cohort_calls.append("narrate:main")
    # Deterministic player-boundary guard on the render: prose naming
    # the protagonist in third person gets ONE re-ask with the violation
    # named; a second violation ships but is flagged in the trace and
    # session receipts (visible to the live tester, never silent).
    if names_protagonist(prose, arc.protagonist):
        prose = cohorts.narrate(
            provider,
            briefing + f"\n\nVIOLATION TO FIX: your previous render named "
            f"{arc.protagonist} as a third-person character. They are 'you'. "
            f"Re-render without naming them.",
            arc.protagonist, peopled=_peopled, competence=_competence,
            serve_thread=_serve_thread)  # same flags (Cx 247)
        trace.cohort_calls.append("narrate:main(re-ask)")
    if names_protagonist(prose, arc.protagonist):
        trace.player_boundary = "FLAGGED: protagonist named in third person"

    # ---- POST: INGEST GATE (GATED-INGEST-COHORT) --------------------------
    # The licensed narrator improvises freely WITHIN its grounding, but its
    # prose is not trusted straight to canon. Stage it in a quarantine frame,
    # then promote everything EXCEPT a row that overwrites an established canon
    # value (a contradiction) — those stay quarantined for arc review. New
    # facts and same-value restatements promote (so good improv — the drawer's
    # papers, the paperclip — is never blocked). Narrator-origin is stamped.
    pre_keys = {(row["entity"], row["attribute"]) for row in receipt_rows}
    pre_entities = {row["entity"] for row in receipt_rows}
    briefing_keys = set(player_table)
    license_tokens = set(
        f"{briefing}\n{player_input}".lower()
        .replace("’", "").replace("'", "")
        .replace(",", " ").replace(".", " ").replace(";", " ").replace(":", " ")
        .split())

    def _licensed(entity: str, attribute: str) -> bool:
        # Licensed = the narrator was GIVEN it: a briefing/player key, an entity
        # already in play, the scene, or an entity whose every name-token came
        # from the briefing+input (possessives normalized).
        if (entity, attribute) in briefing_keys or (entity, attribute) in pre_keys:
            return True
        if entity in pre_entities or entity == scene:
            return True
        name_tokens = entity.split(":", 1)[-1].replace("-", "_").split("_")
        return all(tok in license_tokens for tok in name_tokens if tok)

    canon_before = dict(canon_table)  # established values BEFORE this render
    # `defer`: don't durability-classify the QUARANTINE staging — these rows are
    # only here to diff against canon for contradictions; the survivors get a single
    # batch classification on PROMOTION below. Kills the per-turn double-classify.
    # FAIL-OPEN: the PROSE is the player-facing deliverable and is already rendered;
    # the post-render extraction is bookkeeping (staging for the canon-commit gate). A
    # schema violation here (the cheap extractor malforming its JSON, raising after a
    # re-ask) must NOT sink an already-delivered turn — the harness caught this sinking
    # turns. Ship the prose; skip this turn's canon-commit (logged). (Turn-loop policy:
    # "the narrator failing is the turn failing" — this is POST-narrator.)
    try:
        with _phase(trace, "post_extract"):
            staged = _receipt_rows(p.ingest(prose, scene=scene, at=turn_time(turn),
                                            source=_NARRATOR_SOURCE, frame=_PROPOSED,
                                            classify="defer", extract="lean"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("render extraction failed; shipping prose, skipping commit: %s", exc)
        trace.dropped_cohorts.append(f"post_extract ({exc})")
        staged = []
    # the entities the narrator's prose touched (drop meta/assertion ids); read
    # their proposed-frame values (snapshot facts are fact-only — no meta noise)
    staged_entities = sorted({
        r["entity"] for r in staged
        if ":" in r["entity"] and not r["entity"].startswith(("a:", "attr:"))})
    proposed_vals = _table(_snap_or_empty(p, staged_entities, frame=_PROPOSED))

    # EPILOGUE-NO-CANON (Cx 189): on a TERMINAL / conclusion-curtain turn the narrator renders
    # FATE/SUMMARY prose ("walks back into the rain with his name cleared", "keeps his pride but not
    # his clean hands") — it must mint NOTHING into canon. Promoting it canonized descriptive ALIASES
    # onto the cast, which the next episode then surfaced as character NAMES ("With His Name Cleared").
    # The prose is still archived in session:main (the transcript below); any real consequence is
    # written BEFORE narration via the explicit conclusion/consequence paths, never mined back out of
    # curtain prose. So drop all promotion candidates on the epilogue turn.
    if trace.terminal or (trace.concluded and not endless):
        proposed_vals = {}

    protected_keys = arc_protected_keys(arc)  # the arc's load-bearing (hidden) facts
    promote: list[dict] = []
    contradictions: list[tuple] = []
    quarantined: list[tuple] = []
    for (entity, attribute), newv in proposed_vals.items():
        # The narrator is NOT a diegetic entity (harness bug): the extraction sometimes
        # mints a phantom `person:narrator` from second/first-person pronouns ("you",
        # "I", "under my arm") and even conflates the held object into it, then locates
        # things IN it — breaking adjudication ("the ledger is at person:narrator"). Drop
        # any row that IS the narrator phantom or LOCATES something in it; it never enters
        # canon. ("you"/"I" should be the protagonist, never a narrator entity.)
        if entity in _NARRATOR_PHANTOM or str(newv) in _NARRATOR_PHANTOM:
            quarantined.append((entity, attribute))
            continue
        key = (entity, attribute)
        established = canon_before.get(key, _ABSENT)
        # STRICT license for a PROTECTED arc fact (Cx 022 blocking #1): the mystery's
        # answer may enter canon AND the player frame ONLY if the player legitimately
        # surfaced it THIS turn — it is in their own action receipt (pre_keys) or
        # already in their knowledge frame (briefing_keys = the player-frame snapshot,
        # i.e. earned by prior play). Token matching (_licensed) is too loose here: a
        # narrator that merely RESTATES a hidden canon fact (SAME value) would otherwise
        # slip past the contradiction check and promote+mirror it into knows:<player>,
        # handing over the solution. So a protected key the player didn't earn this turn
        # is QUARANTINED — new OR same-value. A legitimately discovered arc fact is in
        # the player frame → licensed_strict → promotes normally (discovery still works).
        licensed_strict = (key in pre_keys or key in briefing_keys
                           or (entity, attribute, newv) in _reshape_license)
        # Promoted rows carry their narrator PROVENANCE (Cx 022 non-blocking): the
        # promote path is structured-ingest, which drops the `source` the staging
        # ingest stamped — re-stamp via `source_doc` so a promoted improv fact is
        # auditable as narrator-origin (vs player/author/canon-seed).
        if key in protected_keys:
            if licensed_strict:
                promote.append({"entity": entity, "attribute": attribute,
                                "value": newv, "source_doc": _NARRATOR_SOURCE})
            else:
                quarantined.append(key)
            continue
        if established is not _ABSENT and established != newv and not licensed_strict:
            contradictions.append(key)  # narrator overwrote established truth
        else:
            promote.append({"entity": entity, "attribute": attribute,
                            "value": newv, "source_doc": _NARRATOR_SOURCE})
    if promote:
        with _phase(trace, "promote"):
            p.ingest_structured(promote, frame="canon", classify="batch")
            canon_table.update(_table(_snap_or_empty(p, snap_scope, as_of=_h)))
            _mirror_rows(p, promote, player_frame, canon_table, trace, as_of=_h)
    trace.contradictions = sorted(contradictions)
    trace.quarantined = sorted(quarantined)

    leaked = [(it["entity"], it["attribute"]) for it in promote
              if not _licensed(it["entity"], it["attribute"])]
    audit = []
    if leaked:
        audit.append(f"unlicensed:{leaked[:5]}")
    if contradictions:
        audit.append(f"contradiction:{sorted(contradictions)[:5]}")
    if quarantined:
        audit.append(f"momentous:{sorted(quarantined)[:5]}")
    trace.concealment_audit = "clean" if not audit else "FLAGGED: " + " ".join(audit)

    p.ingest_structured([
        {"entity": f"event:turn_{turn}", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "pacing", "value": trace.pacing,
         "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "concealment_audit",
         "value": trace.concealment_audit, "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "player_boundary",
         "value": trace.player_boundary, "valid_from": turn_time(turn)},
        # The append-only ARCHIVE (Kernos Ledger discipline): every beat preserved,
        # lossless at its own resolution, so the compacted memory is RECOVERABLE/
        # regenerable against it — never a lone drifting summary. On a plain
        # `arch:turn_N` entity (NOT an event: id, which is read via the event log,
        # not key-folds), so it is retrievable by `state()`. Host frame — narrative,
        # never canon fact.
        {"entity": f"arch:turn_{turn}", "attribute": "player_said",
         "value": player_input[:600], "valid_from": turn_time(turn)},
        {"entity": f"arch:turn_{turn}", "attribute": "prose",
         "value": prose[:2400], "valid_from": turn_time(turn)},
    ], frame=SESSION, classify="batch")  # bookkeeping (receipts/archive) — no durability (K 077)

    # Append this beat to the rolling transcript (the narrator's short-term memory).
    # Beats past the verbatim window age out; once a BATCH has accumulated, fold
    # them into the durable NARRATIVE MEMORY via the memory cohort (Kernos-style
    # compaction at a boundary, reconciled in one call). Fail-open: a compaction
    # miss leaves the aged beats in place to retry next turn — never breaks the
    # turn. Stored literal so the classifier never mistypes the JSON blob.
    _recent.append({"turn": turn, "player": player_input[:400], "prose": prose[:1600]})
    if len(_recent) > _RECENT_TURNS + _COMPACT_BATCH:
        aged = _recent[: len(_recent) - _RECENT_TURNS]
        aged_text = "\n\n".join(
            (f"› You: {b['player']}\n" if b.get("player") else "") + (b.get("prose") or "")
            for b in aged)
        try:
            with _phase(trace, "compact_memory"):
                updated = cohorts.compact_memory(provider, narrative_memory, aged_text)
            p.ingest_structured([
                {"entity": _MEMORY, "attribute": "text", "value": updated["memory"][:6000],
                 "value_type": "literal", "valid_from": turn_time(turn)},
            ], frame=SESSION, classify="batch")  # narrative memory literal — no durability
            _recent = _recent[-_RECENT_TURNS:]  # aged beats now live in memory
            trace.cohort_calls.append("compact_memory:main")
        except Exception as exc:  # noqa: BLE001 — never break the turn on memory
            logger.warning("narrative-memory compaction failed: %s", exc)
            trace.dropped_cohorts.append(f"compact_memory ({exc})")
            _recent = _recent[-(_RECENT_TURNS + _COMPACT_BATCH):]  # cap unbounded growth
    p.ingest_structured([
        {"entity": _TRANSCRIPT, "attribute": "recent",
         "value": json.dumps(_recent), "value_type": "literal",
         "valid_from": turn_time(turn)},
    ], frame=SESSION, classify="batch")  # transcript literal — no durability

    # Advance diegetic time POST-RENDER for the normal case (richer estimate — it can use the
    # narration), UNLESS a time-deadline arc already advanced it early (Cx 173 #3) so the deadline
    # could cross same-turn. Best-effort; never blocks or breaks a turn.
    if _clock is not None and not _time_committed:
        _advance_diegetic_time(world, _clock, player_input, trace, provider, narration=prose)

    _write_mechanics_log(arc, turn, player_input, prose, trace)
    return TurnResult(prose=prose, trace=trace)


def _write_mechanics_log(arc: Arc, turn: int, player_input: str, prose: str,
                         trace: "TurnTrace") -> None:
    """Per-turn MECHANICS LOG (founder: read the machinery, not just the fiction — anticipate how
    each shape SHOULD behave). Env-gated by CONSTRUCT_MECHANICS_LOG (a path, or "1" → logs/
    mechanics-<arc>.md). Dumps, per turn: the classify→tick→arc→governance signals, which cohorts
    fired, and — the key — the FULL assembled BRIEFING (the directives that produced the prose) +
    the prose itself, so the mechanics→prose link is legible. OFF by default; never sinks a turn."""
    import os
    dest = os.environ.get("CONSTRUCT_MECHANICS_LOG")
    if not dest:
        return
    try:
        from pathlib import Path
        slug = arc.arc_id.replace(":", "_")
        path = (Path("logs") / f"mechanics-{slug}.md") if dest in ("1", "true", "yes") else Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        d = trace.to_dict() if hasattr(trace, "to_dict") else {}
        def _g(k, default=""):
            return d.get(k, getattr(trace, k, default))
        lines = [
            f"\n\n{'='*78}\n## Turn {turn} — {player_input!r}",
            f"- classify: kind={_g('classified')}  pacing={_g('pacing')}  "
            f"resolution_tier={_g('adjudication')}",
            f"- delivery: learned={_g('learned_clues') or '-'}  discovered={_g('discovered') or '-'}",
            f"- world tick: clocks_fired={_g('clocks_fired') or '-'}  beats_achieved="
            f"{_g('beats_achieved') or '-'}  beats_closed={_g('beats_closed') or '-'}  "
            f"events_fired={_g('events_fired') or '-'}  reveals={_g('reveals') or '-'}",
            f"- arc: act={_g('act')}  lifecycle={_g('lifecycle')}  concluded={_g('concluded')}  "
            f"conclusion={_g('conclusion_shape') or '-'}  terminal={_g('terminal')}  "
            f"outcome={_g('outcome') or '-'}  bounced={_g('commitment_bounced')}",
            f"- governance: weave={_g('weave_decision') or '-'}/{_g('weave_card') or '-'}  "
            f"adapted={_g('adapted') or '-'}  fallout={_g('arc_fallout') or '-'}  "
            f"generated={_g('generated') or '-'}",
            f"- cohorts fired: {_g('cohort_calls') or '-'}",
            f"- dropped: {_g('dropped_cohorts') or '-'}",
            f"- time: {_g('time_now')} (+{_g('time_advanced')}m)  "
            f"pins={_g('pins') or '-'}  quarantined={_g('quarantined') or '-'}",
            f"- timings(s): {_g('timings') or '-'}",
            "\n### BRIEFING (the directives that drove the prose)\n" + (trace.briefing or "(none)"),
            "\n### PROSE\n" + (prose or "(empty)"),
        ]
        with path.open("a") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:  # a debug log must NEVER affect a turn
        logger.exception("mechanics log write failed")


run_turn_sync = run_turn  # the v0 loop is synchronous end to end
