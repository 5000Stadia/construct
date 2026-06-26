"""The public session API (letter 034).

One surface that every interface — the REPL, the Discord bot, a future
web/MCP client — is a thin client of. It is a small wrapper around the
SAME `run_turn` the one-shot CLI uses: no change to the turn loop,
cohorts, or engine. A session holds one open world for its lifetime and
persists every turn to the player's slot.

    session = Session.open("anchor", player_id="discord:42")
    reply = session.turn("I look around the council tier")
    print(reply.prose)
    session.close()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from construct.game import (
    next_turn_number,
    open_playthrough,
    slot_path,
    start_playthrough,
)
from construct.provider import Provider
from construct.adapter import PorcelainWorldReads
from construct.turnloop import TurnTrace, run_turn, terminal_outcome

logger = logging.getLogger(__name__)


@dataclass
class Reply:
    """What a turn returns to any transport: the prose to show, and the
    trace for debug surfaces. `ok` is False only for a failed turn that
    the transport should surface without tearing the session down."""

    prose: str
    trace: TurnTrace | None
    ok: bool = True
    ended: bool = False  # the scenario reached its win/loss terminal (win_loss mode)
    exit_requested: bool = False  # player asked (OOC) to leave/start over


class Session:
    """An open holonovel for one player. Construct does all the model
    work inside `turn`; transports carry text in and out, nothing more."""

    def __init__(self, scenario: str, world: Any, arc: Any, meta: dict,
                 provider: Provider, player_id: str | None,
                 entry_as_of: float | None = None,
                 mode_override: str | None = None) -> None:
        self.scenario = scenario
        self.player_id = player_id
        self.entry_as_of = entry_as_of
        self._world = world
        self._arc = arc
        # The rest of the arc portfolio (LIVING-WORLD-GENERATOR P1): side arcs
        # tick and conclude alongside the main arc but never end the scenario.
        self._side_arcs = meta.get("_side_arcs") or []
        self._provider = provider
        self._scope = meta.get("arc_scope") or None
        # Prefer the PER-PLAYER episode scope persisted in THIS slot's session frame (written by
        # game.continue_episode on a CONCLUDE→CONTINUE) over the shared, build-time scenario meta
        # (Cx 191): the live reopen reloads the stale scenario .meta.json, so without this EP2 would
        # cold-open with EP1's scope (the old cast + any polluted aliases). Mirrors the entry_epoch fix.
        try:
            _slot_scope = PorcelainWorldReads(self._world).state(
                "session:episode", "arc_scope", frame="session:main")
            if _slot_scope:
                self._scope = json.loads(_slot_scope) if isinstance(_slot_scope, str) else _slot_scope
        except Exception:
            logger.exception("episode scope read failed; falling back to scenario meta")
        self._mode = meta.get("mode", "pure")
        # The PLAYER's chosen experience (session-zero interview) overrides the
        # scenario's authored default. Three states:
        #   win_loss — a story that builds to an ending (has an aim; can terminate);
        #   endless  — freeplay, the world carries on and never settles;
        #   bounded  — the default: the arc concludes and the world settles into a
        #              "concluded" pacing, but no win/loss aim and no termination.
        # In the live transport the player ALWAYS supplies mode_override (the
        # session-zero interview), so this default only governs CLI/tests/legacy.
        # `_endless` honors both the mode and the legacy `meta["endless"]` flag.
        self._scenario_mode = mode_override or meta.get("scenario_mode", "bounded")
        self._endless = self._scenario_mode == "endless" or bool(meta.get("endless"))
        # The game-type directive (GAME-TYPES.md): the maintained narrative
        # instruction for THIS kind of game (hand-wave vs dramatize, tension).
        # None for an unset/unknown type → free improvised narrative.
        from construct.play_styles import directive_for
        self._play_style = directive_for(meta.get("game_type")) or ""
        # The STORY-SHAPE discipline (STORY-SHAPES.md): the per-shape "earn the payoff"
        # guidance (generalizes concealment to every genre — romance builds intimacy,
        # not clues). Rides in the briefing alongside the play-style flavor directive.
        from construct.story_shapes import shape_directive, shapes_for
        _shape = shape_directive(meta.get("game_type"))
        if _shape:
            self._play_style = f"{self._play_style}\n\n{_shape}" if self._play_style else _shape
        # The shape's judgment type — how a conclusory commitment is graded (claim-vs-fact
        # for deduction, relationship-vs-consequence for bond, …). Default deduction.
        _prof = shapes_for(meta.get("game_type"))
        self._judgment_type = (_prof or {}).get("judgment_type", "claim-vs-fact")
        # The shape's cost_disposition — how pillar coverage is READ at the conclusion
        # (peril_redemption is the normal polarity; fail_forward inverts it for comedy).
        from construct.story_shapes import conclusion_profile, suspense_profile
        _cprof = conclusion_profile(meta.get("game_type")) or {}
        self._cost_disposition = _cprof.get("cost_disposition", "peril_redemption")
        # Who CLOSES the story (Cx 141): 'commitment' shapes (reckoning — deduction/contest/…) reach
        # climax-READY on world_condition but the player's conclusory commitment owns the curtain;
        # 'world_event' shapes (endurance/farce) end on the decisive event directly. Default
        # world_event so legacy/unmapped arcs are byte-for-byte unchanged.
        self._terminal_owner = _cprof.get("terminal_owner", "world_event")
        # Suspense intensity for the pre-conclusion build-up (Cx 113): a genre-HAZARD signal
        # (survival/horror/combat → 'peril' → amplified), not cost_disposition.
        self._suspense = suspense_profile(meta.get("game_type"))
        # The LITERAL external-result axis (Contest's "scoreboard", Cx 027) read ALONGSIDE
        # coverage — now expressed as declared canon Occurred result-events, not a bespoke
        # scoreboard entity (letters 131/132). `result_events` = {win:(kinds,), loss:(kinds,),
        # participants:(ids,)} authored per-arc; None for shapes with no literal-result axis.
        self._result_events = meta.get("result_events")
        # The populated cast (STORY-SHAPES §8), rebuilt once from the seal for interview
        # delivery (node_id → CastNode). Absent → a pillar-less world (legacy path).
        self._cast: dict = {}
        _castblob = meta.get("cast")
        if _castblob:
            try:
                from construct.cast import cast_from_proposal
                _nodes, _ = cast_from_proposal(_castblob)
                self._cast = {n.node_id: n for n in _nodes}
            except Exception:  # a bad cast blob must never break the session
                self._cast = {}
        # The scenario entry epoch (obs #3 half 3): the live-play time origin, ABOVE every
        # pre-play valid_from. Re-established on the executor contextvar at every turn so
        # turn_time (staging supersession + pacing fold) sits on the entry axis. Absent →
        # TURN_EPOCH (one-timeframe / legacy worlds — unchanged behavior).
        from construct.arc.executor import TURN_EPOCH, set_entry_epoch
        # Prefer the PER-PLAYER episode epoch persisted in THIS slot's session frame (written by
        # game.continue_episode on a CONCLUDE→CONTINUE) over the shared, build-time scenario meta
        # (Cx 138 #2): a continued episode raised the epoch for its boundary, and turns must stamp
        # ABOVE it or terminal_outcome (scoped since the episode_start) won't see the new ending.
        _slot_epoch = None
        try:
            _slot_epoch = PorcelainWorldReads(self._world).state(
                "session:episode", "entry_epoch", frame="session:main")
        except Exception:
            logger.exception("episode epoch read failed; falling back to scenario meta")
        self._entry_epoch = float(_slot_epoch if _slot_epoch is not None
                                  else (meta.get("entry_epoch", TURN_EPOCH) or TURN_EPOCH))
        set_entry_epoch(self._entry_epoch)
        self._meta = meta
        self._closed = False

    @classmethod
    def open(cls, scenario: str, player_id: str | None = None,
             *, fresh: bool = False, provider: Provider | None = None,
             as_of: float | None = None,
             mode_override: str | None = None) -> "Session":
        """Load or resume `scenario` for `player_id` (its own slot) and
        return a ready session. fresh=True restarts from the pristine
        scenario; otherwise it resumes where the player left off.

        `mode_override` (session-zero interview) is the PLAYER's chosen
        experience — "win_loss" (a story that builds to an ending) or
        "endless" (freeplay) — overriding the scenario's authored default.
        The transport interprets the player's first message into one of
        these before the world opens.

        `as_of` (ENTRY:WHERE, SESSION-ZERO design) is the timeline
        coordinate the player ENTERS at — the establishing view is
        materialized as-of t ("enter before the meter went dark"). It is
        recorded on the playthrough at fresh start and read back on
        resume; it governs the establishing entry, not ongoing turn
        stamping (turns run forward at TURN_EPOCH as ever)."""
        if provider is None:
            from construct.provider import CodexProvider
            provider = CodexProvider()
        start_playthrough(scenario, fresh=fresh, player_id=player_id)
        world, arc, meta = open_playthrough(scenario, provider, player_id=player_id)
        entry = _entry_as_of(world, requested=as_of, fresh=fresh)
        return cls(scenario, world, arc, meta, provider, player_id, entry_as_of=entry,
                   mode_override=mode_override)

    @property
    def title(self) -> str:
        return self._meta.get("title", self.scenario)

    @property
    def protagonist(self) -> str:
        return self._arc.protagonist

    def location(self) -> str | None:
        """Current scene id (deterministic; no model call)."""
        chain = self._world.porcelain.locate(self._arc.protagonist)
        return chain[0] if chain else None

    def status_line(self) -> str:
        """A one-line `time | location` status — the diegetic clock on the
        governing calendar + the current place's name. Pure reads (no model, no
        time progression), so it's safe for an at-any-time `/status` and for the
        transport to prepend to a reply. The narrator never sees this — it's a
        host-injected header, outside the agent's context."""
        from construct.clock import read_clock
        from construct.foyer import state_value
        loc = self.location()
        when = read_clock(self._world, loc).render()
        where = ""
        if loc:
            where = (state_value(self._world.porcelain, loc, "name")
                     or loc.split(":", 1)[-1].replace("_", " "))
        return f"{when} | {where}" if where else when

    def character_setup(self) -> dict | None:
        """Inputs for the Foyer character-creation phase (CHARACTER-CREATION.md):
        the protagonist's role, the authored DEFAULT personal details (to keep or
        change), and the world anchors tied to them. Returns None if unavailable
        (then the transport skips the Foyer and goes straight to the cold open)."""
        try:
            from construct.foyer import world_anchors, state_value, _DETAIL_ATTRS
            proto = self._arc.protagonist
            p = self._world.porcelain
            name = state_value(p, proto, "name") or proto.split(":")[-1].replace("_", " ")
            role = state_value(p, proto, "role") or state_value(p, proto, "kind") or ""
            defaults = {a: v for a in _DETAIL_ATTRS
                        if (v := state_value(p, proto, a))}
            genre = (self._meta.get("genre") or self._meta.get("genre_era")
                     or "").strip()
            gt = self._meta.get("game_type") or []
            gt_str = ", ".join(gt) if isinstance(gt, list) else str(gt or "")
            theme = " · ".join(p for p in (self._meta.get("title", ""), genre, gt_str)
                               if p).strip(" ·")
            # The back-of-book brief for the Foyer's world-intro. PREFER the authored
            # `premise` (a concrete, canon-faithful where/when/what-system blurb,
            # authored from the digest at build) — that's the durable source. Fall
            # back to the thematic `intro`, then style+theme, so older/thin worlds
            # still get grounding. We stop DEPENDING on `style` (a prose-voice field)
            # to describe the world (founder).
            world_brief = (self._meta.get("premise") or "").strip()
            if not world_brief:
                style_brief = (self._meta.get("style") or "").strip()
                heart = (self._meta.get("theme")
                         or self._meta.get("goal_statement") or "").strip()
                world_brief = (self._meta.get("intro") or "").strip() \
                    or ". ".join(s for s in (style_brief, heart) if s)
            return {"protagonist": proto,
                    "role": name + (f" — {role}" if role else ""),
                    "defaults": defaults,
                    "theme": theme,  # title · genre · game-type — to color the Foyer voice
                    "world_brief": world_brief,  # the authored premise — to establish the world
                    "anchors": world_anchors(self._world, self._scope, proto)}
        except Exception:
            logger.exception("character_setup failed for %s", self.scenario)
            return None

    def apply_character(self, sheet: Any) -> None:
        """Commit the Foyer's finished character sheet as canon BEFORE turn one."""
        from construct.foyer import ingest_character
        ingest_character(self._world, self._provider, self._arc.protagonist, sheet)

    def concealed_truths(self) -> str:
        """A host-side digest of the story's HIDDEN answers — the conclusion's
        shape/premise/win-state and any reveal-beat correlations ('X and Y are
        secretly one'). The engine knows these; the player does not. Fed to the
        `/ooc` host so protection fires PROPORTIONAL to how close a guess comes to
        the real secret (grounded protection) — NEVER surfaced to the player. Empty
        when there's no meaningful concealed answer to guard."""
        try:
            arc = self._arc
            sh = arc.shape
            lines = [
                f"Destination (delta): {sh.delta_type}; dramatic tension: {sh.tension}",
                f"Premise (hidden): {sh.premise}",
                f"The win-state condition: {sh.world_condition}",
            ]
            for b in arc.beats:
                if getattr(b, "correlates", None):
                    a, c = b.correlates
                    lines.append(f"REVEAL twist: {a} and {c} are secretly the same / linked")
            loss = getattr(arc, "failure_when", None)
            if loss:
                lines.append(f"Loss condition: {loss}")
            return "\n".join(str(x) for x in lines)
        except Exception:
            logger.exception("concealed_truths failed for %s", self.scenario)
            return ""

    def note_wish(self, text: str) -> None:
        """Record an out-of-character creative suggestion the engine agreed to try
        (`/ooc`). A soft host aspiration in the SESSION frame — never canon — that
        the narrator may weave in IF it fits the trajectory (turn loop surfaces it).
        Append-only with a small cap; deduped by text."""
        import json
        from construct.foyer import state_value
        text = (text or "").strip()
        if not text:
            return
        p = self._world.porcelain
        raw = state_value(p, "session:wishes", "list")
        try:
            wishes = json.loads(raw) if raw else []
        except (ValueError, TypeError):
            wishes = []
        if text not in wishes:
            wishes = (wishes + [text])[-6:]
            p.ingest_structured([{"entity": "session:wishes", "attribute": "list",
                                  "value": json.dumps(wishes), "value_type": "literal"}],
                                frame="session:main")

    def goal_statement(self) -> str | None:
        """The non-spoiling player-facing aim, shown only in win_loss mode.
        Freeplay/endless has no fixed aim, so this returns None there. The
        line is a leak-checked derivative authored at session-zero and
        sealed on the scenario meta (never a plot:/canon row)."""
        if self._scenario_mode != "win_loss":
            return None
        goal = self._meta.get("goal_statement")
        return str(goal) if goal else None

    def opening(self) -> str:
        """The cold open the player steps into — an ELEGANT NARRATED scene, not a
        structure dump. The establishing facts ('the world at rest') are anchors
        the narrator renders FROM, in the world's voice and by name; they are never
        shown raw (founder: this front end is live fiction, not pattern-buffer
        retrieval). Layout: title · the authored thematic intro · the narrated cold
        open. NO forced 'aim'/objective banner — the call to action arises in the
        fiction (founder). Falls back to a clean (id-free, triple-free) banner only
        if narration is unavailable."""
        title = self.title
        intro = (self._meta.get("intro") or "").strip()
        scene = self._opening_narration(intro)
        parts = [title]
        if intro:
            parts.append(intro)
        if scene:
            parts.append(scene)
        elif not intro:  # clean last resort — never raw triples/ids
            who = self._display_name(self._arc.protagonist)
            where = self._display_name(self.location())
            parts.append(f"You are {who}" + (f", at {where}." if where else "."))
        # NO forced 'aim'/objective banner (founder 2026-06-22: "no forced goal —
        # the fiction needs to carry it"). The call to action ARISES diegetically
        # over the cold open + first beats, like a detective story that begins
        # before the case lands — never a game-y objective line stapled on top.
        return "\n\n".join(p for p in parts if p)

    def _display_name(self, entity) -> str:
        """An entity's established name/alias/title (player frame, then canon), else
        a humanized id — never a raw `kind:slug`."""
        if not entity:
            return ""
        try:
            snap = self._world.porcelain.snapshot(
                [entity], frame=f"knows:{self._arc.protagonist}")
            facts = snap.get("facts", []) or \
                self._world.porcelain.snapshot([entity]).get("facts", [])
        except Exception:
            facts = []
        for attr in ("name", "alias", "title"):
            for f in facts:
                if f["entity"] == entity and f["attribute"] == attr:
                    return str(f["value"])
        s = str(entity)
        return s.split(":", 1)[-1].replace("_", " ") if ":" in s else s

    def _opening_narration(self, intro: str) -> str:
        """Render the cold open from the establishing anchors (by name, in voice).
        Fail-open: returns '' so opening() degrades to a clean banner."""
        from construct import cohorts
        anchors, names = self._establishing_anchors()
        # COLD-OPEN LOCKSTEP (INVESTIGATION-SHAPE.md §3b / Cx 059): the opening must foreground
        # EXACTLY the people the engine considers present, computed with the SAME _colocated the
        # turn loop uses (no second presence definition). Computed BEFORE the render gate so a
        # populated scene ALWAYS renders an opening that introduces the cast — the live staged
        # whodunit run failed because the opening bailed to a bare banner (empty anchors) and the
        # spoon-fed cast was never introduced, so the player wandered into the architecture.
        present, absent_known = self._present_people(names)
        if not (anchors or intro or present):
            return ""
        prot = self._arc.protagonist
        who = names.get(prot) or self._display_name(prot)
        where = self.location()
        where_name = (names.get(where) or self._display_name(where)) if where else ""
        brief = [f"YOU ARE VOICING: {who}"
                 + (f", who stands at {where_name}." if where_name else ".")]
        style = self._meta.get("style", "")
        if style:
            brief.insert(0, f"VOICE (write in this): {style}")
        # CONCLUDE→CONTINUE: a continued episode opens on time-pass + the protagonist's earned
        # reputation for the last case ("you made a name on that one…"), THEN the new case
        # surfaces (founder). One-shot: consumed and cleared so it never re-frames a later open.
        cont = (self._meta.pop("continuation_intro", "") or "").strip()
        if cont:
            brief.append(cont)
        if intro:
            brief.append(f"THEMATIC FRAME (the stakes — do not quote verbatim):\n{intro}")
        if anchors:
            brief.append("WHAT IS TRUE AND PRESENT (anchors — weave in by name, "
                         "never list):\n" + "\n".join(anchors))
        if present:
            # the FIRST WITNESS leads the spoon-fed opening (genre-faithful: the one who found/
            # reported it introduces the cast). INVESTIGATION-SHAPE.md §3b.
            fw = next((nid for nid, n in (self._cast or {}).items()
                       if getattr(n, "first_witness", False)), None)
            fw_name = (names.get(fw) or self._display_name(fw)) if fw else ""
            lead = (f" {fw_name} is the one who found/reported it — let THEM speak first and "
                    f"introduce the others by name." if fw_name and fw_name in present else "")
            brief.append(
                "PRESENT WITH YOU RIGHT NOW (these people — and ONLY these — are in the opening "
                "scene; name and introduce each so the player knows who is here to question;"
                + lead + " do NOT bring anyone not listed here into the room):\n"
                + "\n".join(f"- {n}" for n in present))
        if absent_known:
            brief.append(
                "EXISTS BUT NOT HERE (mention only as people one might later seek out; NEVER "
                "narrate them as present in this scene):\n"
                + "\n".join(f"- {n}" for n in absent_known))
        threads = self.live_threads()
        if threads:
            brief.append("STILL LIVE (unresolved, in the air):\n"
                         + "\n".join(f"- {t}" for t in threads))
        try:
            return cohorts.open_scene(self._provider, "\n\n".join(brief), prot).strip()
        except Exception:
            logger.warning("opening narration unavailable; clean-banner fallback",
                           exc_info=True)
            return ""

    def _present_people(self, names: dict):
        """Split the in-scope people into (present, absent-but-known) by the SAME presence
        rule the turn loop applies (`turnloop._colocated`) — so the cold open foregrounds
        exactly who is colocated with the protagonist and treats the rest as elsewhere. Reuses
        the turn-loop helper (no second 'present' definition; Cx 059). Returns display names."""
        scope = self._scope or []
        prot = self._arc.protagonist
        try:
            from construct.turnloop import _colocated
            chain = self._world.porcelain.locate(prot)
            scene = chain[0] if chain else None
        except Exception:
            return [], []
        if not scene:
            return [], []

        def _disp(e):
            return names.get(e) or self._display_name(e)

        present, absent = [], []
        for e in sorted(scope):
            if not e.startswith("person:") or e == prot:
                continue
            try:
                npc_chain = self._world.porcelain.locate(e)
            except Exception:
                continue
            if _colocated(npc_chain, scene, chain):
                present.append(_disp(e))
            elif npc_chain:  # placed somewhere else — known to exist, not here
                absent.append(_disp(e))
        return present, absent

    def _establishing_anchors(self, limit: int = 10):
        """By-NAME establishing facts + an entity→name map — grounding for the cold
        open, never shown raw. (Replaces the triple dump the player used to see.)"""
        scope = self._scope
        if not scope:
            return [], {}
        # The establishing snapshot is strict: one unknown arc-scope id (e.g. a `fact:*` beat
        # target never asserted, like fact:verdict) makes the WHOLE snapshot fail → an empty
        # (banner) cold open. Recover the known subset by probing per id on the failure path so
        # a real opening still renders with anchors (the live staged-whodunit bug).
        ids = sorted(set(scope))
        try:
            snap = self._world.porcelain.snapshot(
                ids, lens="establishing_set", as_of=self.entry_as_of)
        except Exception:
            return [], {}
        if "error" in snap:
            facts_acc: list = []
            for e in ids:
                try:
                    one = self._world.porcelain.snapshot(
                        [e], lens="establishing_set", as_of=self.entry_as_of)
                except Exception:
                    continue
                if "error" not in one:
                    facts_acc.extend(one.get("facts", []))
            snap = {"facts": facts_acc}
        facts = snap.get("facts", [])
        # Display name: prefer an explicit `name` over any `alias`/`title`, regardless of fact order
        # (Cx 189 #3). The old last-wins comprehension let a LATE descriptive alias (a narrator-origin
        # phrase like "with his name cleared") override the real name on the cold-open screen. A
        # `name` always wins; an alias/title only fills in when no name is present.
        names: dict[str, str] = {}
        for f in facts:
            if f["attribute"] not in ("name", "alias", "title"):
                continue
            if f["attribute"] == "name" or f["entity"] not in names:
                names[f["entity"]] = str(f["value"])

        def disp(x):
            s = str(x)
            if s in names:
                return names[s]
            if ":" in s and s.split(":", 1)[0] in ("person", "place", "obj", "fact", "event"):
                return s.split(":", 1)[-1].replace("_", " ")
            return s

        # CONCEAL the arc's load-bearing facts from the cold open — the same
        # (entity, attribute) keys the turn loop protects (the beats' conditions,
        # the destination, the premise). These are the mystery's EVIDENCE (Cray
        # signed the order; the phantom-reserve ledgers): the player DISCOVERS them
        # in play, and the open must not recite them (founder: the open was handing
        # away the whole solution, then play said "you can't say for certain").
        try:
            from construct.arc.executor import arc_protected_keys
            protected = arc_protected_keys(self._arc)
        except Exception:
            protected = set()
        lines = [f"{disp(f['entity'])} · {f['attribute']} · {disp(f['value'])}"
                 for f in facts
                 if f["attribute"] not in ("name", "alias", "title")
                 and f["entity"] != self._arc.protagonist
                 and (f["entity"], f["attribute"]) not in protected]
        return lines[:limit], names

    def live_threads(self, limit: int = 6) -> list[str]:
        """Re-entry awareness: the LIVE threads anchored to scope, via the
        `situation` lens (standing-truth ∪ live events, dead history dropped —
        PB SITUATION-LENS-V1, letter 058). Additive to the establishing set,
        which stays the tuned 'world at rest' cold-open. Fail-safe: with no
        `caused_by`-linked live events it returns empty, so a fresh/quiet world
        shows no section. Renders each live event by its alias or kind."""
        scope = self._scope
        if not scope:
            return []
        try:
            snap = self._world.porcelain.snapshot(
                sorted(scope), lens="situation", as_of=self.entry_as_of)
        except Exception:  # lens unsupported / read error — never break the open
            return []
        # The lens adds live EVENT rows on top of standing truth; surface those
        # as threads (alias preferred, else kind), one line per distinct event.
        threads: dict[str, str] = {}
        for f in snap.get("facts", []):
            e = f["entity"]
            if not e.startswith("event:"):
                continue
            if f["attribute"] == "alias":
                threads[e] = str(f["value"])
            elif f["attribute"] == "kind" and e not in threads:
                threads[e] = str(f["value"])
        # CONCEAL (Cx 022 #3): an event's alias/kind is freeform text, so it bypasses
        # the (entity,attribute) protected-key filter — an event named after the
        # mystery's answer would otherwise leak it in the cold open's STILL-LIVE list.
        # Drop any thread whose text or event id brushes the arc's concealed vocabulary.
        concealed = self._concealed_tokens()

        def _leaks(text: str, ev: str) -> bool:
            blob = (f"{text} {ev.split(':', 1)[-1]}"
                    .replace("_", " ").replace("-", " ").replace(":", " ").lower())
            words = set(blob.split())
            return bool(concealed & words)

        return [t for e, t in threads.items() if not _leaks(t, e)][:limit]

    def _concealed_tokens(self) -> set[str]:
        """Distinctive tokens of the arc's HIDDEN facts — drawn from each protected
        entity id and attribute (NOT the value: a protected fact's value is often a
        public name, which is not itself secret). Used to filter the cold open's
        freeform live-thread aliases against the concealment set (Cx 022 #3)."""
        try:
            from construct.arc.executor import arc_protected_keys
            keys = arc_protected_keys(self._arc)
        except Exception:
            return set()
        stop = {"the", "a", "an", "of", "to", "is", "in", "on", "status", "kind",
                "name", "alias", "title", "fact", "event", "obj", "person", "place"}
        toks: set[str] = set()
        for (e, a) in keys:
            for src in (e.split(":", 1)[-1], a):
                for t in src.replace("_", " ").replace("-", " ").lower().split():
                    if len(t) > 3 and t not in stop:
                        toks.add(t)
        return toks

    def establishing_lines(self, limit: int = 8) -> list[str]:
        """The establishing-set facts in scope, as of the entry
        coordinate — `materialize(establishing_set, as_of=t)`, the ENTRY
        design's literal shape. Deterministic; no model."""
        scope = self._scope
        if not scope:
            return []
        snap = self._world.porcelain.snapshot(
            sorted(scope), lens="establishing_set", as_of=self.entry_as_of)
        lines = [f"{f['entity']} · {f['attribute']} · {f['value']}"
                 for f in snap.get("facts", [])
                 if f["entity"] != self.protagonist]
        return lines[:limit]

    def turn(self, text: str) -> Reply:
        """Run exactly one player turn and persist it. Never raises for
        an in-world failure — returns ok=False with an honest message so
        a long-lived transport (REPL/bot) survives the turn."""
        if self._closed:
            raise RuntimeError("session is closed")
        # Re-establish the scenario entry epoch on the contextvar for THIS turn's context
        # (obs #3 half 3) — turn_time stamping must sit above all pre-play valid_from.
        from construct.arc.executor import set_entry_epoch
        set_entry_epoch(self._entry_epoch)
        # Only a WIN_LOSS scenario ends; endless/freeplay never short-circuits
        # (a stale terminal receipt from a prior mode must not freeze open play).
        if self._scenario_mode == "win_loss":
            ended = terminal_outcome(PorcelainWorldReads(self._world))
            if ended:
                return Reply(prose=f"(The story has ended — you {ended}. "
                                   f"Start fresh to play again.)", trace=None, ended=True)
        n = next_turn_number(self._world)
        try:
            result = run_turn(self._world, self._arc, self._provider, text, n,
                              scope=self._scope, mode=self._mode, endless=self._endless,
                              scenario_mode=self._scenario_mode,
                              style=self._meta.get("style", ""),
                              play_style=self._play_style,
                              judgment_type=self._judgment_type,
                              cost_disposition=self._cost_disposition,
                              result_events=self._result_events,
                              terminal_owner=self._terminal_owner,
                              suspense=self._suspense,
                              cast=self._cast or None,
                              side_arcs=self._side_arcs)
        except Exception as exc:  # loud, but the session lives
            logger.exception("turn failed for %s/%s", self.scenario, self.player_id)
            return Reply(prose=f"(the turn could not complete: {exc})",
                         trace=None, ok=False)
        # WORLD-CHANGING AGENCY (Cx 215 #1): a mid-story reshape may have RE-PLANNED the main
        # arc in PB this turn. run_turn swapped only its local arc; reload the live portfolio so
        # the NEXT turn enters run_turn with the new main arc + scope, not the stale ones held
        # since open — else "revive → re-aim → the case keeps going" breaks across turns.
        if result.trace and getattr(result.trace, "replanned", ""):
            self._reload_arc_portfolio(
                extra_scope=getattr(result.trace, "reshape_entities", None))
        return Reply(prose=result.prose, trace=result.trace,
                     ended=bool(result.trace and result.trace.terminal),
                     exit_requested=getattr(result, "exit_requested", False))

    def _reload_arc_portfolio(self, extra_scope: list | None = None) -> None:
        """Refresh the live arc portfolio from PB after a mid-story re-plan, so subsequent
        turns run the new main arc. `extra_scope` carries the visible reshaped/restaged
        entities (Cx 221) so a revived NPC the replacement arc doesn't reference stays in
        NEXT-turn scene scope. Best-effort: a reload hiccup keeps the current arc."""
        from construct.arc import io as arc_io
        from construct.arc.executor import arc_entities
        try:
            reads = PorcelainWorldReads(self._world)
            main_id = arc_io.main_arc_from_frame(reads)
            portfolio = arc_io.portfolio_from_frame(reads)
            self._arc = next((a for a in portfolio if a.arc_id == main_id), self._arc)
            self._side_arcs = [a for a in portfolio if a.arc_id != main_id]
            scope = set(arc_entities(self._arc)) | set(extra_scope or [])
            self._scope = sorted(e for e in scope if reads.has_entity(e))
            logger.info("session arc reloaded after replan: main=%s (+%d reshape entities)",
                        self._arc.arc_id, len(extra_scope or []))
        except Exception:
            logger.exception("arc portfolio reload after replan failed; keeping current arc")

    def close(self) -> None:
        if not self._closed:
            self._world.close()
            self._closed = True

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def slot_exists(scenario: str, player_id: str | None = None) -> bool:
    return slot_path(scenario, player_id).exists()


_ENTRY = "event:entry"
_SESSION_FRAME = "session:main"


def _entry_as_of(world: Any, requested: float | None, fresh: bool) -> float | None:
    """Resolve the entry coordinate: on a fresh start, record the
    requested coordinate (if any) into the session frame; on resume,
    read back whatever was recorded. None = entered at the timeline head
    (current state). Stored as a session:main row so it's inspectable and
    survives across one-shot turns."""
    p = world.porcelain
    if fresh:
        if requested is not None:
            # Record the entry as an EVENT whose valid-time IS the
            # coordinate — read back via events() (the proven session:main
            # read path; state() doesn't fold no-valid-time frame rows).
            p.ingest_structured(
                [{"entity": _ENTRY, "attribute": "kind", "value": "entry",
                  "valid_from": float(requested)}],
                frame=_SESSION_FRAME)
        return requested
    for ev in p.events(kind="entry", frame=_SESSION_FRAME):
        t = ev.get("t")
        if t is not None:
            return float(t)
    return None
