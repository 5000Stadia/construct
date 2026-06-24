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
from typing import Any

from construct import cohorts
from construct import resolution
from construct.adapter import PorcelainWorldReads
from construct.arc.executor import (
    LIFECYCLE_TERMINALS,
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


def _convergence_directive(phase: Phase, ready: bool) -> tuple[str, str]:
    """The act label + a CONVERGENCE directive for the narrator (founder: "all roads
    should lead to the conclusion — gentle nudges, or relocate the conclusive scene to
    where the story has gone"). Dramatic pull + staging only — NEVER informational, so
    it never reveals the hidden answer (the concealment block still governs). Returns
    ("" , "") in Act III, where the existing resolution/epilogue directives take over."""
    act = _ACT_OF.get(phase, "I")
    base = ("\nCONVERGENCE (this is live fiction with a destination — bend every road "
            "toward it, gently and diegetically; NEVER stall and NEVER railroad). ")
    if act == "I":
        return act, base + (
            "ACT I — establish the world and let it breathe, but keep a current under "
            "it: surface the hooks and let the central tension tug at the player. Plant, "
            "don't push.")
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
                "never the answer.")
        return act, base + (
            "ACT II — converge: every thread should bend toward the pivotal beat now, "
            "pressure rising. " + relocate + " Converge the DRAMA, never the answer.")
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
    contradictions: list = field(default_factory=list)  # narrator rows quarantined (changed established canon)
    quarantined: list = field(default_factory=list)  # narrator rows quarantined (unlicensed assertion of an arc key)
    timings: dict = field(default_factory=dict)  # per-section wall-clock (s) this turn — optimization surface

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


def _snap_or_empty(p: Any, scope: list[str], frame: str = "canon") -> dict:
    if not scope:
        return {"facts": []}
    ids = sorted(set(scope))
    snap = p.snapshot(ids, frame=frame)
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
            one = p.snapshot([e], frame=frame)
        except Exception:
            continue
        if "error" not in one:
            facts.extend(one.get("facts", []))
    return {"facts": facts}


def _route_obstruction(p: Any, origin: str | None, target: str | None) -> dict | None:
    """First non-clear segment on origin->target via PB route() (RFC-003), or
    None. Fail-open: any route error => None => move proceeds unchecked. A
    `blocked` segment carries `evidence` (the portal's blocking fact); an
    `obscured` one a computed `unknown_basis`."""
    if not origin or not target or origin == target:
        return None
    try:
        r = p.route(origin, target)
    except Exception as exc:
        logger.warning("route() unavailable, movement unchecked: %s", exc)
        return None
    for seg in r.get("segments", []):
        if seg.get("status") in ("blocked", "obscured"):
            return seg
    return None


def _mirror_rows(p: Any, rows: list[dict], frame: str,
                 canon_table: dict[tuple[str, str], object], trace: TurnTrace) -> None:
    """Mirror freshly-ingested canon facts into a knows: frame. Values
    come from the canon snapshot; point-read fallback for out-of-scope
    entities only."""
    items = []
    for row in rows:
        if row.get("frame") not in (None, "canon"):
            continue
        key = (row["entity"], row["attribute"])
        value = canon_table.get(key, _ABSENT)
        if value is _ABSENT:
            st = p.state(row["entity"], row["attribute"])
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
                  canon_table: dict, trace: TurnTrace) -> None:
    """Fiction-mode scene furnishing (letter 020 finding B): seed the
    description thunk through the gate, force via `resolve()` (resolver
    authority, generated provenance, constraint inheritance), mirror to
    the player frame. Memoized — stable on return; lazy — current scene
    only."""
    if scene is None or canon_table.get((scene, "description")) is not None:
        return
    st = p.state(scene, "description")
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


def adjudicate(world: Any, p: Any, protagonist: str, scene: str | None,
               requires: list[str]) -> str | None:
    """The Adjudicate faculty (letter 028, finding E): locate() is the
    rules lawyer. Each claimed item must resolve AND be at hand (its
    containment chain reaching the player or the current scene). Returns
    None if the action stands, else the denial reason. Deterministic
    after refer()."""
    for description in requires:
        res = world.refer(description, frame="canon")
        if getattr(res, "status", None) != "resolved" or not getattr(res, "entity_id", None):
            return (f"{description!r} is not a thing you are known to have — "
                    f"it has never been established in this world's canon")
        entity = res.entity_id
        chain = p.locate(entity)
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


#: The conventional canon source of a shape's external result (the scoreboard), read
#: ALONGSIDE pillar coverage by shapes whose profile sets `reads_world_event` (Contest).
#: Authored as ordinary canon when the contest resolves (`scoreboard:main / outcome /
#: win|loss`); host reads it, never the internal won/lost receipt (which would re-couple
#: proof to score — Cx 027 blocker 2). None until/unless authored.
def _world_event(reads: Any) -> str | None:
    val = reads.state("scoreboard:main", "outcome", frame="canon")
    return val if val in ("win", "loss") else None


def terminal_outcome(reads: Any) -> str | None:
    """The recorded win/loss terminal of a `win_loss` scenario, or None if it
    hasn't ended (WIN-LOSS §10). Reads the SESSION receipt via `events()` (the
    same pattern as `_conclusion_recorded` — SESSION event rows are read by kind,
    not folded by `state()`); the outcome is encoded in the kind. Lets a
    transport stop ticking an ended story instead of re-rendering aftermath."""
    if reads.events(kind="arc_won", frame=SESSION):
        return "won"
    if reads.events(kind="arc_lost", frame=SESSION):
        return "lost"
    return None


def run_turn(world: Any, arc: Arc, provider: Provider, player_input: str,
             turn: int, scope: list[str] | None = None,
             mode: str = "pure", endless: bool = False,
             scenario_mode: str = "endless", style: str = "",
             play_style: str = "",
             judgment_type: str = "claim-vs-fact",
             cost_disposition: str = "peril_redemption",
             reads_world_event: bool = False,
             cast: dict | None = None,
             side_arcs: list[Arc] | None = None,
             generate: bool = True) -> TurnResult:
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
    p = world.porcelain
    live_reads = PorcelainWorldReads(world)
    trace = TurnTrace(turn=turn)
    player_frame = _player_frame(arc)

    # ---- SERIAL SPINE -----------------------------------------------------
    # 1. Classify (cheap; fail-open to action). Movement intent + the assured-vs-
    #    uncertain resolution judgment ride the same call (no extra latency).
    moves_to, requires = "", []
    needs_test, uncertain_of = False, ""
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
    try:
        with _phase(trace, "classify"):
            verdict = cohorts.classify(provider, player_input, actor=actor)
        kind = verdict["kind"]
        moves_to = verdict.get("moves_to", "") or ""
        requires = [r for r in verdict.get("requires", []) if r]
        needs_test = bool(verdict.get("needs_test")) and kind == "action"
        uncertain_of = (verdict.get("uncertain_of") or "").strip()
        commits = bool(verdict.get("commits")) and kind in ("action", "declaration")
        commitment = (verdict.get("commitment") or "").strip() or player_input
        takes = (verdict.get("takes") or "").strip()
        examines_target = (verdict.get("examines_target") or "").strip()
        # Default TRUE on absence (old stubs / schema-less classify) so extraction is never
        # silently skipped where a fact could be asserted (protected-key licensing depends on it).
        asserts_or_reveals = bool(verdict.get("asserts_or_reveals", True))
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
        a = p.ask(player_input, frame=player_frame)
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

    if kind == "declaration" and mode == "pure":
        trace.adjudication = "denied: declarations are co-author moves; this scenario is canon-strict"
        return TurnResult(
            prose="(canon-strict) This world's facts are already written — "
                  "you can act in it, but not author it. State what you DO.",
            trace=trace)

    # 1b. Adjudication (letter 028, finding E): locate() is the rules
    #     lawyer. A failed precondition means the action DOES NOT COMMIT;
    #     the failure renders honestly and is receipted, never silent.
    pre_chain = p.locate(arc.protagonist)
    pre_scene = pre_chain[0] if pre_chain else None
    if requires and mode == "pure":
        denial = adjudicate(world, p, arc.protagonist, pre_scene, requires)
        if denial:
            trace.adjudication = f"denied: {denial}"
            prose = cohorts.narrate(
                provider,
                f"SCENE: you are at {pre_scene or 'an unresolved place'}.\n"
                f"THE PLAYER ATTEMPTED: {player_input}\n"
                f"ADJUDICATION (binding): the attempt FAILS — {denial}. "
                f"Render the failure honestly and diegetically; the world "
                f"does not bend.",
                arc.protagonist)
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
        res = world.refer(moves_to, frame="canon")
        status = getattr(res, "status", None)
        target = getattr(res, "entity_id", None)
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
            _pchain = p.locate(target)
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
            seg = _route_obstruction(p, origin, target)
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
        ores = world.refer(takes, frame="canon")
        otarget = getattr(ores, "entity_id", None)
        if (getattr(ores, "status", None) == "resolved" and otarget
                and otarget != arc.protagonist and otarget not in _NARRATOR_PHANTOM):
            p.ingest_structured([{
                "entity": otarget, "attribute": "in", "value": arc.protagonist,
                "value_type": "entity", "valid_from": turn_time(turn),
            }], classify="batch")
            trace.took = otarget
            logger.info("player took: %s -> held by %s", otarget, arc.protagonist)

    # 3. Scene + the canon materialization (ONE snapshot serves the tick).
    chain = p.locate(arc.protagonist)
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
            scene_features = list(p.features(scene))
        except Exception:  # read unsupported / error — never break the turn
            scene_features = []
    snap_scope = list(scope) + ([scene] if scene else []) + scene_features
    canon_snap = _snap_or_empty(p, snap_scope)
    canon_table = _table(canon_snap)

    _mirror_rows(p, receipt_rows, player_frame, canon_table, trace)
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
        furnish_scene(p, scene, player_frame, canon_table, trace)

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
        npc_chain = p.locate(e)
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
        sheets = {npc: json.dumps(p.snapshot(npc, frame=f"knows:{npc}",
                                             lens="character_sheet"))[:4000]
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
                canon_snap = _snap_or_empty(p, snap_scope)  # refresh: canon moved
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
        for npc in npcs:
            node = cast.get(npc)
            _name = str(canon_table.get((npc, "name")) or "")
            _role = getattr(node, "surface_role", "") if node else ""
            if node is None or not (only_one or _names_entity(npc, low, name=_name,
                                                              role=_role)):
                continue
            for clue in revealable_clues(node, pressure=pressing):
                e, a, v = clue.surface_fact
                if live_reads.assertion_in_frame(player_frame, e, a, v):
                    continue  # already learned — don't re-surface
                try:
                    p.ingest_structured(learn_clue_items(clue), frame=player_frame,
                                        classify="batch")
                    learned.append((npc, clue))
                except Exception as exc:  # one clue must not sink the turn
                    trace.dropped_cohorts.append(f"learn_clue:{clue.clue_id} ({exc})")
                break  # one fresh clue per NPC per turn (an earned trickle, not a dump)

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
                                "own observation and reasoning, to establish that "
                                f"{_human_entity(a)} of {_human_entity(e)} is "
                                f"{_human_entity(str(v))}. Render this as THEIR pursued detail "
                                "genuinely yielding it — not a witness reciting it, and NEVER a "
                                "redirect to some other object or person. "
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

    player_snap = _snap_or_empty(p, snap_scope, frame=player_frame)
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
    diff = p.frame_diff("canon", player_frame, sorted(set(snap_scope)))
    threads = [f"{f['entity']} · {f['attribute']} · {f['value']}" for f in diff][:12]
    trace.irony_delta_size = len(diff)

    # Conclusion detection (endless mode). Bounded worlds settle into
    # aftermath once the arc reaches its destination — the navigator
    # stops pushing toward an end already reached. Endless worlds note
    # the milestone but keep their pressure/clocks running indefinitely.
    concluded = arc_concluded(live_reads, arc)
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
    if commits and earned and terminal_outcome(live_reads) is None:
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

    main_life = arc_lifecycle(live_reads, arc)
    trace.lifecycle = main_life
    outcome = arc_outcome(live_reads, arc)
    if outcome is None and main_life in ("incompletable", "cancelled"):
        outcome = "lost"
    # The commitment IS the conclusion (convergence): it terminates regardless of the
    # world_condition. The grade maps to the binary terminal receipt (wrong → lost; all
    # else → won) while the grade itself flavors the epilogue.
    if commitment_grade and outcome is None:
        outcome = "lost" if commitment_grade == "wrong" else "won"
    trace.outcome = outcome
    terminal = scenario_mode == "win_loss" and outcome is not None
    trace.terminal = terminal
    # CONCLUSION AS EFFECT (STORY-SHAPES §0a): when the arc declares pillars, the
    # conclusory scene's CHARACTER is the narrated effect of pillar COVERAGE, not a
    # win/lost verdict. The won/lost receipt above stays as the "episode concluded, stop
    # ticking" plumbing; this is what the player feels. cost_weight ties the ending's toll
    # to the run — more false-filled (wrong) causes = a costlier close (the §0a integral).
    conc = None
    if arc.pillars and (terminal or (concluded and not endless)):
        summary = coverage_summary(live_reads, arc)
        req = summary["required"] or []
        # cost_weight is a v1 placeholder for the run's cost integral. For NORMAL polarity a
        # false-filled cause is a cost; for fail_forward (comedy) a false-fill is SUCCESS, so
        # it must NOT count as cost — else warm comic triumph is unreachable (Cx 027 blocker
        # 3). Until the real residue (collateral/ruptures/botched draws) is wired, comedy
        # gets 0.0 (warm by default; comeuppance later from genuine collateral).
        if cost_disposition == "fail_forward":
            cost_weight = 0.0
        else:
            cost_weight = (len(summary["false"]) / len(req)) if req else 0.0
        # An external result read ALONGSIDE coverage for shapes whose ending also reads a
        # world EVENT (Cx 027 blocker 2 — Contest's scoreboard: sound coverage + a 'loss'
        # = "proved himself, lost the decision"). The scoreboard is authored canon
        # (`scoreboard:main / outcome / win|loss`), NOT the internal won/lost receipt —
        # deriving it from the receipt would re-couple proof to score.
        world_event = _world_event(live_reads) if reads_world_event else None
        conc = conclusion_from_coverage(summary, cost_disposition=cost_disposition,
                                        world_event=world_event, cost_weight=cost_weight)
        if conc:
            trace.conclusion_shape = conc["outcome"]
            trace.conclusion_basis = conc["basis"]
    if terminal and terminal_outcome(live_reads) is None:
        p.ingest_structured([
            {"entity": f"event:arc_outcome_{turn}", "attribute": "kind",
             "value": f"arc_{outcome}", "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # terminal receipt — bookkeeping
        set_lifecycle(world, arc, main_life, turn)

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
                  for f in _snap_or_empty(p, sorted(reveal_scope)).get("facts", [])
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
        _act, _conv = _convergence_directive(current_phase(live_reads, arc),
                                             climax_ready(live_reads, arc))
        trace.act = _act
        if _conv:
            briefing_parts.append(_conv)
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
    if npc_intents:
        briefing_parts.append("\nPRESENT CHARACTERS (play them by their wants):\n"
                              + "\n".join(npc_intents))
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
    # Uncertain action → draw the next outcome tier from the pre-rolled deck (no model
    # call) and tell the narrator WHAT happens (succeed/fail + the twist); it improvises
    # HOW. Assured actions never draw — they just succeed (ACTION-RESOLUTION.md).
    if needs_test:
        try:
            tier = resolution.draw_tier(live_reads, p)
            briefing_parts.append("\n" + resolution.directive(tier, uncertain_of))
            trace.adjudication = f"test:{tier}"
        except Exception as exc:  # never sink a turn on a resolution hiccup
            logger.warning("resolution draw failed: %s", exc)
            trace.dropped_cohorts.append(f"resolution ({exc})")
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

    # ---- RENDER (loud-fail) ----------------------------------------------
    with _phase(trace, "narrate"):
        prose = cohorts.narrate(provider, briefing, arc.protagonist)
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
            arc.protagonist)
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
        licensed_strict = key in pre_keys or key in briefing_keys
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
            canon_table.update(_table(_snap_or_empty(p, snap_scope)))
            _mirror_rows(p, promote, player_frame, canon_table, trace)
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

    # Advance diegetic time by what happened (DIEGETIC-TIME.md): estimate how much
    # in-world time this turn consumed (relative to the events, honoring this
    # world's day length + player waits) and APPEND it to the accrue counter.
    # Best-effort + after the render, so it never blocks or breaks a turn.
    if _clock is not None:
        try:
            from construct.clock import (
                commit_elapsed,
                delta_from_estimate,
                deterministic_elapsed,
            )
            with _phase(trace, "time_estimate"):
                # TURN-LATENCY Lever C (Cx 077): most turns advance time predictably by action
                # kind — use a DETERMINISTIC estimate and skip the ~6s model call. Fall back to
                # the model `estimate_elapsed` ONLY when the input carries explicit temporal
                # language (a wait/jump/rest/montage that may cross a phase/day boundary).
                _moved = trace.movement_status in ("clear", "obscured")
                est = deterministic_elapsed(player_input, moved=_moved)
                if est is None:
                    est = cohorts.estimate_elapsed(
                        provider, now=_clock.render(),
                        hours_per_day=_clock.calendar.hours_per_day,
                        phases=_clock.calendar.phase_names,
                        action=player_input, narration=prose)
                    trace.cohort_calls.append("estimate_elapsed")
                else:
                    trace.cohort_calls.append("time_estimate:deterministic")
            trace.time_advanced = delta_from_estimate(_clock, est)
            commit_elapsed(world, trace.time_advanced)
        except Exception as exc:  # noqa: BLE001 — time never sinks a turn
            logger.warning("diegetic-time estimate failed: %s", exc)
            trace.dropped_cohorts.append(f"estimate_elapsed ({exc})")

    return TurnResult(prose=prose, trace=trace)


run_turn_sync = run_turn  # the v0 loop is synchronous end to end
