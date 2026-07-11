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


def _is_namelike(value: str) -> bool:
    """Whether a string reads as a NAME/handle rather than a descriptive clause (#4 host
    slice). A proper name is short and not article-led ("Administrator Cray", "Hobbes"); a
    descriptive alias is a clause ("deaf on the left side", "the clerk with the tin ear") — those
    should NOT be used AS a display name. Heuristic: ≤3 words and not starting with an article."""
    v = (value or "").strip()
    if not v:
        return False
    words = v.split()
    if len(words) > 3:
        return False
    first = words[0].lower().strip(".,;:!?")
    # not article-led, and not a clause fragment that starts with a pronoun/contraction (a
    # dialogue line like "I'm carrying it" can be mis-extracted as an entity — never a name).
    if first in ("the", "a", "an"):
        return False
    if first in ("i", "you", "he", "she", "it", "they", "we", "i'm", "i'll", "i've",
                 "we're", "they're", "he's", "she's", "it's", "that", "this", "there"):
        return False
    # a bare adverb/filler mis-extracted as an entity ("here", "now") is never a name (the
    # spurious-entity ROOT is extraction quality — PB/#56 — but keep these out of the display).
    if v.lower() in ("here", "there", "now", "then", "yes", "no", "ok", "okay", "this", "that",
                     "it", "them", "us", "him", "her", "everyone", "someone", "no one", "nobody"):
        return False
    return True


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
    image: Any = None  # SceneImage for this turn's location (SCENE-IMAGERY), or None
    # #95 (Cx 422): transports must never infer "ended means continueable" — a death
    # terminal ends the world's story for this player, no next chapter.
    can_continue: bool = True


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
        # AS-OF PLAY HORIZON (B' S3): a HORIZON world (ingested fiction with a spaced source
        # axis) binds every canon read to `opening_as_of + turns-so-far`, so beats/conditions
        # and scene/presence reads see the opening state and never the source aftermath.
        # Absent (legacy/interview/single-timeframe) → reads run at the timeline head, unchanged.
        self._opening_as_of = meta.get("opening_as_of")
        self._next_source_as_of = meta.get("next_source_as_of")
        if self._opening_as_of is not None and self.entry_as_of is None:
            # The establishing/situation snapshots read as-of the opening coordinate.
            self.entry_as_of = float(self._opening_as_of)
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
        # DRIFT D3 (cr re-review blocker 5): the beat-DERIVED subset of scope,
        # tracked separately so a committed repair can SUBTRACT superseded-only
        # referents (never independently-played scope) before adding the live
        # set. Baselined against the live beat overlay at open.
        self._beat_scope: set[str] = set()
        try:
            from construct.arc.executor import arc_entities as _ae
            _reads0 = PorcelainWorldReads(self._world, horizon=self._horizon())
            for _a in [self._arc] + list(self._side_arcs or []):
                self._beat_scope |= _ae(_a, _reads0)
        except Exception:
            logger.exception("beat-scope baseline failed; removal disabled until refresh")
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
        # WORLD LAWS (#105): the sealed law objects off meta — one read; run_turn
        # renders the same block for the briefing lane + every adjudication feed.
        from construct.laws import laws_from_meta
        self._laws = laws_from_meta(meta)
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
        # TURN-LATENCY dumbfire: the prior turn's deferred bookkeeping (the post-narrate
        # `settle` closure — extract→canon, mirror, transcript, compact, time). It runs
        # POST-SEND (the adapter triggers it so it overlaps the player reading), and is
        # JOINED defensively at the START of the next turn so a back-to-back message can
        # never read canon before the prior turn finished writing it. None = nothing pending.
        self._pending_settle: Any = None

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

    def _horizon(self, turn: int | None = None) -> float | None:
        """The current play horizon (B' as-of): `opening_as_of + turns-so-far`, fail-closed
        STRICTLY below the next source coordinate (Cx 253 §1) so future source canon can never
        enter by turn-count arithmetic. None for legacy/single-timeframe worlds (head reads)."""
        if self._opening_as_of is None:
            return None
        n = next_turn_number(self._world) if turn is None else turn
        h = float(self._opening_as_of) + float(n)
        if self._next_source_as_of is not None:
            h = min(h, float(self._next_source_as_of) - 1.0)
        return h

    def location(self) -> str | None:
        """Current scene id (deterministic; no model call)."""
        chain = self._world.porcelain.locate(self._arc.protagonist, as_of=self._horizon())
        return chain[0] if chain else None

    def carrying(self) -> list[str]:
        """Object ids currently held by the protagonist (obj.in == protagonist) at
        the play horizon. Diagnostic accessor for the cohesion harness — pure reads,
        no model call. Mirrors the WHAT YOU ARE CARRYING briefing's source."""
        proto = self._arc.protagonist
        try:
            return [h for h in self._world.porcelain.contents(proto, as_of=self._horizon())
                    if str(h).startswith("obj:")]
        except Exception:
            return []

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
            where = (state_value(self._world.porcelain, loc, "name", as_of=self._horizon())
                     or loc.split(":", 1)[-1].replace("_", " "))
        return f"{when} | {where}" if where else when

    def journal(self) -> str:
        """The case-board notebook (#83): the protagonist's own `knows:` frame rendered
        as their diegetic notebook. Pure reads at the play horizon (no model call, no
        time progression) — safe for an at-any-time `/journal`. Own frame only, so the
        surface can never spoil what the character hasn't learned."""
        from construct.arc.executor import (
            arc_protected_keys, concealed_tokens, turn_time, value_leaks,
        )
        from construct.foyer import state_value
        from construct.journal import render_journal
        proto = self._arc.protagonist
        h = self._horizon()
        # THE CONCEALMENT SCREEN, BY PROVENANCE (Cx 337 pattern): the authored frame can
        # carry load-bearing answer rows (build residue — e.g. the culprit's own drives,
        # written at build) that every render surface screens; the notebook must never be
        # the back door to them. But a row LEARNED IN PLAY (valid_from above the opening
        # stamp) reached the frame through the gated paths — the authorized clue delivery
        # or the promote gate — so it is EARNED by construction and shows as-is (learned
        # pillar clues sit on protected keys on purpose; screening those would hide the
        # notebook's core content). Build-stamped rows get the full key + token screen.
        _protected = arc_protected_keys(
            self._arc, PorcelainWorldReads(self._world, horizon=h))
        _ctoks = concealed_tokens(_protected)
        _stamp = turn_time(0)

        def _shows(r: Any) -> bool:
            vf = getattr(r, "valid_from", None)
            if h is not None and vf is not None and float(vf) > h:
                return False  # beyond the play horizon
            if vf is not None and float(vf) > _stamp:
                return True   # learned in play — earned through the gated writes
            return ((str(r.entity), str(r.attribute)) not in _protected
                    and not value_leaks(str(getattr(r, "value", "")), _ctoks))

        from construct.adapter import frame_facts
        rows = [r for r in frame_facts(self._world, f"knows:{proto}") if _shows(r)]

        def _name_of(ent: str) -> str | None:
            try:
                v = state_value(self._world.porcelain, ent, "name", as_of=h)
                return str(v) if v else None
            except Exception:  # noqa: BLE001
                return None

        try:
            header = self.status_line()
        except Exception:  # noqa: BLE001
            header = ""
        # #96 S3 (Cx 414): settled-history markers — a past chapter's answered entities
        # render as closed knowledge, never as active leads.
        _settled_ids: set = set()
        try:
            from construct.adapter import frame_facts
            for r in frame_facts(self._world, "session:main"):
                if (str(r.entity).startswith("settled:episode_")
                        and str(r.attribute) == "record"):
                    rec = json.loads(str(r.value))
                    for line in rec.get("settled", []):
                        tok = str(line).split(" · ", 1)[0].strip()
                        if ":" in tok:
                            _settled_ids.add(tok)
        except Exception:  # noqa: BLE001
            _settled_ids = set()
        return render_journal(rows, proto, name_of=_name_of, header=header,
                              settled=_settled_ids)

    def character_setup(self) -> dict | None:
        """Inputs for the Foyer character-creation phase (CHARACTER-CREATION.md):
        the protagonist's role, the authored DEFAULT personal details (to keep or
        change), and the world anchors tied to them. Returns None if unavailable
        (then the transport skips the Foyer and goes straight to the cold open)."""
        try:
            from construct.foyer import world_anchors, state_value, _DETAIL_ATTRS
            proto = self._arc.protagonist
            p = self._world.porcelain
            _h = self._horizon()  # the opening horizon (Cx 255): role/name/defaults at the start
            name = state_value(p, proto, "name", as_of=_h) or proto.split(":")[-1].replace("_", " ")
            role = (state_value(p, proto, "role", as_of=_h)
                    or state_value(p, proto, "kind", as_of=_h) or "")
            defaults = {a: v for a in _DETAIL_ATTRS
                        if (v := state_value(p, proto, a, as_of=_h))}
            # NAME IS THE PLAYER'S TO CHOOSE (founder): the protagonist is presented by
            # ROLE with the name To-Be-Determined, chosen at game start and canonized.
            # The authored name rides as a SUGGESTED default, never the imposed identity,
            # so the Foyer never says "you're Lionel Pym — now rename yourself".
            defaults.pop("name", None)
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
                    "role": role or "the figure at the heart of this story",
                    "suggested_name": name,  # offered as a default to keep, not imposed
                    "defaults": defaults,
                    "theme": theme,  # title · genre · game-type — to color the Foyer voice
                    "world_brief": world_brief,  # the authored premise — to establish the world
                    "anchors": world_anchors(self._world, self._scope, proto, as_of=_h)}
        except Exception:
            logger.exception("character_setup failed for %s", self.scenario)
            return None

    def apply_character(self, sheet: Any) -> None:
        """Commit the Foyer's finished character sheet as canon BEFORE turn one, then GROUND
        the character (CHARACTER-GROUNDING P2): the engine completes a concrete role + inhabited
        place so the player knows who/where they are. Both run ONCE here at Foyer-done — NOT
        per-turn (zero added play latency)."""
        from construct.foyer import ground_character, ingest_character
        proto = self._arc.protagonist
        ingest_character(self._world, self._provider, proto, sheet)
        ground_character(self._world, self._provider, proto,
                         world_brief=self._meta.get("premise", ""),
                         theme=self._meta.get("theme", ""),
                         as_of=self._horizon())  # bind reads to the OPENING horizon (Cx 280)

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
            from construct.adapter import PorcelainWorldReads as _PWR
            from construct.arc.executor import active_beats as _active_beats
            for b in _active_beats(_PWR(self._world), arc):  # D3: live beat set
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

    def opening_parts(self) -> tuple[str, str]:
        """The cold open SPLIT for the founder's scene-image layout: `(framing, scene)`.
        `framing` = the story TITLE only, shown BEFORE the picture (a chapter heading, not
        exposition); `scene` = the localized cold-open ROOM narration ('you stand in your
        office…'), shown AFTER the picture so the painting introduces the room and the
        prose walks you into it. NO premise/exposition crawl — the founder's rule (2026-06-29):
        do NOT dump the back-of-book premise upfront (it spoils the case — 'Harrow has been
        found dead…' — and pre-empts discovery); introduce the world DIEGETICALLY, through the
        character's own experience. The `intro` still flavors the scene render as a non-verbatim
        THEMATIC tone hint, but is never shown to the player as a crawl. Starts the scene-image
        render UP FRONT so it generates while the (slow) narration is composed. NO forced
        'aim'/objective banner — the call to action arises in the fiction (founder)."""
        title = self.title
        intro = (self._meta.get("intro") or "").strip()  # tone hint for the scene render ONLY
        # SCENE-IMAGERY: furnish + START the render now (furnish otherwise runs only
        # during a turn), before narration, so the picture renders in parallel.
        self._ensure_scene_description()
        self._note_scene_image()
        scene = self._opening_narration(intro)
        if not scene and not intro:  # clean last resort — never raw triples/ids
            who = self._display_name(self._arc.protagonist)
            where = self._display_name(self.location())
            scene = f"You are {who}" + (f", at {where}." if where else ".")
        return title, scene

    def opening(self) -> str:
        """The cold open as ONE string (CLI / non-image transports / tests): framing +
        scene joined. Image-capable transports use :meth:`opening_parts` to place the
        picture between the framing and the room."""
        framing, scene = self.opening_parts()
        return "\n\n".join(p for p in (framing, scene) if p)

    def _display_name(self, entity) -> str:
        """An entity's established name/alias/title (player frame, then canon), else
        a humanized id — never a raw `kind:slug`."""
        if not entity:
            return ""
        _h = self._horizon()
        try:
            snap = self._world.porcelain.snapshot(
                [entity], frame=f"knows:{self._arc.protagonist}", as_of=_h)
            facts = snap.get("facts", []) or \
                self._world.porcelain.snapshot([entity], as_of=_h).get("facts", [])
        except Exception:
            facts = []
        # Prefer a proper `name`; if there is none, prefer a NAME-LIKE alias/title over a
        # descriptive clause (#4 host slice): an unnamed entity often carries a descriptive
        # alias ("deaf on the left side", "the clerk with the tin ear") that reads terribly AS
        # a name. Fall back to the humanized id ("clerk") before resorting to such a phrase.
        vals = {a: [str(f["value"]) for f in facts
                    if f["entity"] == entity and f["attribute"] == a]
                for a in ("name", "alias", "title")}
        if vals["name"]:
            return vals["name"][0]
        namelike = [v for v in (vals["alias"] + vals["title"]) if _is_namelike(v)]
        if namelike:
            return min(namelike, key=len)            # the tightest name-like handle
        s = str(entity)
        if ":" in s:
            local = s.split(":", 1)[-1].replace("_", " ")   # humanized id beats a descriptive clause
            return local.title() if s.startswith("person:") else local  # person slug = a proper name
        return (vals["alias"] + vals["title"] + [s])[0]

    def _opening_narration(self, intro: str) -> str:
        """Render the cold open from the establishing anchors (by name, in voice).
        Fail-open: returns '' so opening() degrades to a clean banner."""
        from construct import cohorts
        from construct.foyer import state_value
        anchors, names = self._establishing_anchors()
        # COLD-OPEN LOCKSTEP (INVESTIGATION-SHAPE.md §3b / Cx 059): the opening must foreground
        # EXACTLY the people the engine considers present, computed with the SAME _colocated the
        # turn loop uses (no second presence definition). Computed BEFORE the render gate so a
        # populated scene ALWAYS renders an opening that introduces the cast — the live staged
        # whodunit run failed because the opening bailed to a bare banner (empty anchors) and the
        # spoon-fed cast was never introduced, so the player wandered into the architecture.
        present, absent_known, present_ids, absent_ids = self._present_people(names)
        if not (anchors or intro or present):
            return ""
        prot = self._arc.protagonist
        # AUTHORITATIVE NAME via the folded point read (Cx 320): a stale narrator-polluted `name`
        # row can sit in `names`/`_display_name`; `state()` serves the player's winning name.
        who = (state_value(self._world.porcelain, prot, "name", as_of=self._horizon())
               or names.get(prot) or self._display_name(prot))
        where = self.location()
        where_name = (names.get(where) or self._display_name(where)) if where else ""
        # THE GEOGRAPHY OF SELF (founder live, 2026-07-03 — "whose house is this?"): the flat
        # scene name hid the containment truth (the parlor IS Bobby's rooms WITHIN Brackenmere
        # Hall), so the player inferred a separate house and read the true render as drift. Name
        # the location CHAIN and instruct the open to make the roof-relationship unmistakable.
        _chain = []
        try:
            _chain = [c for c in (self._world.porcelain.locate(
                self._arc.protagonist, as_of=self._horizon()) or [])
                if str(c).startswith("place:")]
        except Exception:  # noqa: BLE001
            _chain = []
        _chain_names = [str(names.get(c) or self._display_name(c)) for c in _chain]
        brief = [f"YOU ARE VOICING: {who}"
                 + (f", who stands at {where_name}." if where_name else ".")]
        # THE INTIMATE VERSION (founder 2026-07-03): the build authors the player's lived
        # relationship to their starting ground (relationship_to_<place> rows in their own
        # frame) — the causes, motivation, and history that brought them HERE. Surface it
        # with the chain so the open explains the roof, not just names it.
        _place_rel_lines: list[str] = []
        from construct.adapter import PorcelainWorldReads as _PWR
        _krd = _PWR(self._world, horizon=self._horizon())
        for _pid, _pnm in zip(_chain, _chain_names):
            try:
                _rv = _krd.state(self._arc.protagonist, f"relationship_to_{_pid}",
                                 frame=f"knows:{self._arc.protagonist}")
            except Exception:  # noqa: BLE001
                _rv = None
            if _rv:
                _place_rel_lines.append(f"- {_pnm}: {str(_rv)}")
        if len(_chain_names) > 1 or _place_rel_lines:
            brief.append(
                "WHERE YOU ARE (geography of the player's own position — make it unmistakable "
                "in the open)"
                + (f": {_chain_names[0]} sits within {_chain_names[-1]}."
                   if len(_chain_names) > 1 else ".")
                + " If the larger place belongs to someone else, say so plainly — living or "
                  "working under another's roof is a fact the character carries daily, never "
                  "a puzzle left for the player to assemble."
                + (("\nYOUR HISTORY WITH THIS GROUND (the causes and motivation that brought "
                    "the player to live here — weave the intimacy in, never recite):\n"
                    + "\n".join(_place_rel_lines)) if _place_rel_lines else ""))
        # AUTHORITATIVE PLAYER IDENTITY (founder 2026-06-30, "player name wins, fully"): the player's
        # interview-set name/pronouns supersede any authored-default personal name/gender embedded in
        # the THEMATIC FRAME or anchors below (e.g. a build that hard-authored "Clara Vale"). The cast
        # must address the player by THEIR chosen identity.
        _ppron = (state_value(self._world.porcelain, prot, "pronouns", as_of=self._horizon())
                  or state_value(self._world.porcelain, prot, "gender", as_of=self._horizon()) or "")
        _pbg = state_value(self._world.porcelain, prot, "background", as_of=self._horizon()) or ""
        _prole = state_value(self._world.porcelain, prot, "role", as_of=self._horizon()) or ""
        brief.append(
            f"THE PLAYER CHARACTER IS {who}" + (f" ({_ppron})" if _ppron else "")
            + ". That is WHO they are — not how to address them every line: characters refer to "
              "them naturally ('you', 'sir', a surname, nothing at all), the full name only where "
              "a person would really use it"
            + (f"; {_ppron} pronouns throughout" if _ppron else "")
            + ". If the THEMATIC FRAME or any anchor below uses a DIFFERENT personal name or gender "
              "for the protagonist, that is a stale authored default for the SAME person — never "
              "use the other name."
            + (f"\nTheir role: {_prole}" if _prole else "")
            + (f"\nWhat brought them here (their own words): {_pbg}" if _pbg else ""))
        # CHARACTER-GROUNDING P3 (Cx 280): hand the narrator the player's OWN place — its grounded
        # description (the grounding step set this at seal) — so the cold open zooms into a concrete
        # inhabited space, not a bare room.
        if where:
            _wd = state_value(self._world.porcelain, where, "description", as_of=self._horizon())
            if _wd:
                brief.append(f"YOUR PLACE (their own space — ground the open IN this, "
                             f"weave it in, never quote raw): {where_name or where}: {_wd}")
        style = self._meta.get("style", "")
        if style:
            brief.insert(0, f"VOICE (write in this): {style}")
        # CONCLUDE→CONTINUE: a continued episode opens on a CREATIVE bridge between where the last
        # story landed and where this one is headed (founder 2026-06-26 — not a fixed time-pass +
        # reputation formula). One-shot: consumed and cleared so it never re-frames a later open.
        cont = (self._meta.pop("continuation_intro", "") or "").strip()
        if cont:
            brief.append(cont)
        # WHAT THE PLAYER ALREADY KNOWS (founder 2026-06-30): the player's lived context — why
        # they are here, the series of events, their standing, their relationships to the people
        # present — read from their own knowledge frame. A character is NOT a stranger to their
        # own life; the open must orient them in what they already know, woven into the prose.
        situation, rels, absent_rels = self._player_grounding(names, present_ids, absent_ids)
        # The STANDING GROUNDING DIRECTIVE — clean and singular (agent-prompt-elegance), governs
        # EVERY game's open: orient the player in their character's lived knowledge so they can
        # step in informed, never as a stranger to their own situation.
        brief.append(
            "GROUND THE PLAYER (every opening, before they take their turn): write the open so the "
            "player understands their own situation as the character already would — woven into the "
            "prose, never as a briefing or a list. Make clear who they are, the history and "
            "circumstances they carry into this moment, who the people present are TO THEM, and why "
            "one would speak with them. The character is not arriving as a stranger to their own "
            "life — render the world as they already understand it (in plain terms a newcomer can "
            "follow, not unglossed insider jargon), then hand them the turn. (The "
            "active call-to-action surfaces on its own timing per the scene's pacing below; "
            "grounding is the lived context they walk in with, not a plot summary.)")
        if situation:
            brief.append(
                "WHAT YOU ALREADY KNOW (your own lived situation as you walk in — the background and "
                "state of things; weave in, never recite as facts):\n"
                + "\n".join(f"- {s}" for s in situation))
        if intro:
            brief.append(f"THEMATIC FRAME (the stakes — do not quote verbatim):\n{intro}")
        if anchors:
            brief.append("WHAT IS TRUE AND PRESENT (anchors — weave in by name, "
                         "never list):\n" + "\n".join(anchors))
        if present:
            # UNVEIL INTELLIGENTLY, DON'T SCRIPT (founder 2026-07-01): the old rule forced the first
            # WITNESS to "speak first and introduce the others" — which had a costermonger marshalling
            # the room and voicing the investigator's agenda. Beware such rules. Instead hand the
            # agent each present person's own ROLE + standing (+ who found the body, + the player's
            # relationship) as clean SITUATION, and ONE principle — each speaks from their own role —
            # then trust it to open the scene sensibly.
            # ALIGNED (id, name) pairs (Cx 333 #4) — a name→id dict collapses duplicate display names.
            def _line(nid, n):
                node = (self._cast or {}).get(nid)
                role = str(getattr(node, "surface_role", "") or "").strip() if node else ""
                found = getattr(node, "first_witness", False) if node else False
                bits = []
                if role:
                    bits.append(role)
                if found:
                    bits.append("found and reported the body")
                if rels.get(nid):
                    bits.append(f"to you: {rels[nid]}")
                return f"- {n}" + (" — " + "; ".join(bits) if bits else "")
            brief.append(
                "PRESENT WITH YOU RIGHT NOW (these people — and ONLY these — are in the opening "
                "scene; name and introduce each so the player knows who is here, who they are to "
                "the player, and why one would speak with them. Let the scene UNVEIL INTELLIGENTLY "
                "rather than by a fixed script: each person speaks and acts only from their OWN role "
                "and standing — the investigative authority naturally frames why everyone is here, a "
                "witness gives their own firsthand account — and no one voices another's agenda or "
                "orders. Do NOT bring anyone not listed here into the room):\n"
                + "\n".join(_line(nid, n) for nid, n in zip(present_ids, present)))
        if absent_rels:
            brief.append(
                "OTHERS YOU KNOW (people in your life not in this room — context for who the player "
                "is, mention only naturally, do NOT stage them here):\n"
                + "\n".join(f"- {r}" for r in absent_rels))
        if absent_known:
            brief.append(
                "EXISTS BUT NOT HERE (mention only as people one might later seek out; NEVER "
                "narrate them as present in this scene):\n"
                + "\n".join(f"- {n}" for n in absent_known))
        threads = self.live_threads()
        if threads:
            brief.append("STILL LIVE (unresolved, in the air):\n"
                         + "\n".join(f"- {t}" for t in threads))
        # CHARACTER-GROUNDING P3: a FRESH first entry (just out of the Foyer, no turns played,
        # not a continuation) zooms into the player's inhabited space and HOLDS the call-to-action
        # for a beat; a resume mid-story or a continued episode opens normally (already grounded).
        # HOLD ONLY WHEN SOLO (Cx 333 #5): the held "zoom into your empty space, no one else, no
        # hook" framing contradicts a staged open where cast is already present (the briefing-room
        # whodunit open — founder feedback 2026-06-30). When people are in the room the case scene
        # is already in motion; use the "ground first, then let the call arise" mode, which is
        # compatible with the present cast and the lived-context grounding above.
        from construct.game import next_turn_number
        try:
            _fresh = not cont and not present and next_turn_number(self._world) <= 1
        except Exception:
            _fresh = False
        try:
            return cohorts.open_scene(self._provider, "\n\n".join(brief), prot,
                                      grounding=_fresh).strip()
        except Exception:
            logger.warning("opening narration unavailable; clean-banner fallback",
                           exc_info=True)
            return ""

    def _present_people(self, names: dict):
        """Split the in-scope people into (present, absent-but-known) by the SAME presence
        rule the turn loop applies (`turnloop._colocated`) — so the cold open foregrounds
        exactly who is colocated with the protagonist and treats the rest as elsewhere. Reuses
        the turn-loop helper (no second 'present' definition; Cx 059). Returns display names,
        plus the matching entity-id lists (the grounding pass needs ids to read relationships)."""
        scope = self._scope or []
        prot = self._arc.protagonist
        _h = self._horizon()
        try:
            from construct.adapter import PorcelainWorldReads
            from construct.turnloop import _colocated, _departed_from
            chain = self._world.porcelain.locate(prot, as_of=_h)
            scene = chain[0] if chain else None
            _dep_reads = PorcelainWorldReads(self._world, horizon=_h)
        except Exception:
            return [], [], [], []
        if not scene:
            return [], [], [], []

        def _disp(e):
            return names.get(e) or self._display_name(e)

        present, absent, present_ids, absent_ids = [], [], [], []
        for e in sorted(scope):
            if not e.startswith("person:") or e == prot:
                continue
            try:
                npc_chain = self._world.porcelain.locate(e, as_of=_h)
            except Exception:
                continue
            if _colocated(npc_chain, scene, chain) and not _departed_from(
                    self._world.porcelain, _dep_reads, e, scene, as_of=_h):
                present.append(_disp(e))
                present_ids.append(e)
            elif npc_chain:  # placed somewhere else — known to exist, not here
                absent.append(_disp(e))
                absent_ids.append(e)
        return present, absent, present_ids, absent_ids

    # identity attrs the open already voices elsewhere (the PLAYER CHARACTER block) — never
    # re-listed as lived "situation" context.
    _GROUNDING_SKIP_ATTRS = frozenset({
        "name", "alias", "title", "pronouns", "gender", "background", "role", "kind", "in"})

    def _player_grounding(self, names: dict, present_ids: list, absent_ids: list):
        """The protagonist's LIVED CONTEXT for the cold open — read straight from the player's
        knowledge frame (`knows:<prot>`), which IS 'what the player walks in already knowing':
        their own situation (assignment, operating context, standing, the series of events that
        put them here) and their established relationships to the people in the room. Generic
        across games — surfaces whatever grounding the build/ingest wrote into the protagonist's
        frame, minus the identity attrs voiced elsewhere and the arc's protected SOLUTION keys
        (no spoilers in the open). Returns (situation_lines, {entity_id: relationship_phrase})."""
        prot = self._arc.protagonist
        _h = self._horizon()
        p = self._world.porcelain
        try:
            from construct.arc.executor import arc_protected_keys
            protected = arc_protected_keys(
                self._arc, PorcelainWorldReads(self._world, horizon=_h))
        except Exception:
            protected = set()
        try:
            snap = p.snapshot([prot], frame=f"knows:{prot}", as_of=_h)
            facts = snap.get("facts", []) or []
        except Exception:
            facts = []

        def _disp(e):
            return names.get(e) or self._display_name(e)

        # Screen freeform VALUES against the concealed vocabulary (Cx 333 #3): a relationship
        # or situation value naming the hidden answer would bypass the (entity,attribute)
        # protected-key filter, exactly as a live-thread alias does. Drop any such line.
        concealed = self._concealed_tokens()
        absent_set = set(absent_ids)
        present_set = set(present_ids)
        situation: list[str] = []
        rels: dict[str, str] = {}          # present-cast id -> relationship phrase
        absent_rels: list[str] = []        # known-elsewhere relationships, lower priority
        for f in facts:
            if f["entity"] != prot:
                continue
            attr, val = f["attribute"], str(f["value"]).strip()
            if not val or (prot, attr) in protected or self._value_leaks(val, concealed):
                continue
            if attr.startswith("relationship_to_"):
                target = attr[len("relationship_to_"):]      # an entity id, e.g. person:edmund_reed
                if target in present_set:
                    rels[target] = val
                else:                                         # absent or out-of-scope acquaintance
                    absent_rels.append(f"{_disp(target)} — {val}")
            elif attr not in self._GROUNDING_SKIP_ATTRS:
                situation.append(f"{attr.replace('_', ' ')}: {val}")
        return situation, rels, absent_rels

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
            val = str(f["value"])
            # a `name` always wins; an alias/title only fills when no name is present AND it
            # reads like a name, not a descriptive clause (#4: keep "deaf on the left side" out
            # of the cold-open's present-cast list — disp() humanizes the id instead).
            if f["attribute"] == "name":
                names[f["entity"]] = val
            elif f["entity"] not in names and _is_namelike(val):
                names[f["entity"]] = val

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
            protected = arc_protected_keys(
                self._arc, PorcelainWorldReads(self._world, horizon=self._horizon()))
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
            if e.startswith("event:tick_"):
                # DISCOVERY GATING (#84, Cx 395/396): an off-screen world-tick event is
                # not re-entry awareness — the player discovers the changed world through
                # presence and scene reads, never an omniscient "meanwhile" recital.
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
        """The arc's concealment vocabulary — delegates to the shared
        `executor.concealed_tokens` so the render + build leak screens cannot drift
        (Cx 337). Fail-open to empty on any arc read error."""
        try:
            from construct.arc.executor import arc_protected_keys, concealed_tokens
            return concealed_tokens(arc_protected_keys(
                self._arc, PorcelainWorldReads(self._world, horizon=self._horizon())))
        except Exception:
            return set()

    def _value_leaks(self, text: str, concealed: set[str] | None = None) -> bool:
        """True if freeform text brushes the arc's concealed vocabulary (Cx 333 #3) — the
        same screen `live_threads` applies to freeform event aliases, reused for the grounding
        block's freeform situation/relationship VALUES. Delegates to the shared
        `executor.value_leaks` (Cx 337)."""
        from construct.arc.executor import value_leaks
        if concealed is None:
            concealed = self._concealed_tokens()
        return value_leaks(text, concealed)

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
        # BACK-TO-BACK JOIN (TURN-LATENCY dumbfire): complete the PRIOR turn's deferred
        # bookkeeping before THIS turn reads canon. The adapter normally already ran it
        # post-send; this is the defensive join so a fast second message can't start a
        # turn on stale canon (single PB connection → ordering is mandatory). Idempotent.
        self._flush_settle()
        # Re-establish the scenario entry epoch on the contextvar for THIS turn's context
        # (obs #3 half 3) — turn_time stamping must sit above all pre-play valid_from.
        from construct.arc.executor import set_entry_epoch
        set_entry_epoch(self._entry_epoch)
        n = next_turn_number(self._world)
        # AS-OF PLAY HORIZON (B' S3): bind this turn's reads (terminal check + the whole turn
        # loop) to opening_as_of + n. None for legacy worlds — the head read, unchanged.
        horizon = self._horizon(n)
        # #95 (Cx 422): death ends BOTH scenario modes — permanence. Checked before the
        # win_loss-only gate so an endless world's death still stops, and no next-chapter
        # offer ever arms (can_continue=False).
        _t_kind = terminal_outcome(PorcelainWorldReads(self._world, horizon=horizon))
        if _t_kind == "died":
            return Reply(prose="(This story ended at its close — the world remembers.)",
                         trace=None, ended=True, can_continue=False)
        # Only a WIN_LOSS scenario ends; endless/freeplay never short-circuits
        # (a stale terminal receipt from a prior mode must not freeze open play).
        if self._scenario_mode == "win_loss":
            if _t_kind:
                # NO WIN/LOSE LANGUAGE (founder 2026-07-02 "no winning or losing please"):
                # the conclusion's QUALITY lives in the epilogue prose (conclusion-as-effect);
                # the ended-guard says only that the chapter closed. ended=True lets the
                # transport offer the next chapter (auto-continue flow).
                return Reply(prose="(This chapter has closed.)", trace=None, ended=True)
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
                              side_arcs=self._side_arcs,
                              horizon=horizon,
                              death_policy=self._meta.get("death_policy", "shielded"),
                              laws=self._laws,
                              reality=self._meta.get("reality_register", ""),
                              on_scene=self._note_scene_image)
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
        elif result.trace and getattr(result.trace, "repairs", None):
            self._refresh_beat_scope()
        # Post-turn safety net: the mid-turn `on_scene` hook already started the
        # render for the common move-to-a-new-room case; re-checking here (idempotent
        # via the in-flight guard) also catches a description that CHANGED in place
        # (a reshape, a fire) where furnish didn't re-fire.
        self._note_scene_image()
        # Hold the post-narrate bookkeeping; the adapter runs it post-send (see _flush_settle).
        self._pending_settle = getattr(result, "settle", None)
        return Reply(prose=result.prose, trace=result.trace,
                     ended=bool(result.trace and result.trace.terminal),
                     can_continue=not bool(
                         result.trace
                         and getattr(result.trace, "terminal_kind", "") == "died"),
                     exit_requested=getattr(result, "exit_requested", False),
                     image=self.last_image)

    def flush_settle(self) -> None:
        """Run the prior turn's deferred bookkeeping NOW (TURN-LATENCY dumbfire). The
        transport calls this AFTER it has sent the reply, so the PB writes (extract→canon,
        mirror, transcript, compact, time) overlap the player reading instead of padding
        the turn the player waited on. Idempotent (runs a pending settle at most once),
        exception-safe (a settle hiccup never tears down the session), and a no-op when
        nothing is pending. Also called defensively at the start of the next turn and on
        close() so the deferred work is never silently dropped."""
        self._flush_settle()

    def _flush_settle(self) -> None:
        settle = self._pending_settle
        self._pending_settle = None
        if settle is None:
            return
        try:
            settle()
        except Exception:  # never let deferred bookkeeping break the live session
            logger.exception("deferred settle failed for %s/%s",
                             self.scenario, self.player_id)

    def _note_scene_image(self) -> Any:
        """SCENE-IMAGERY hook: DETECT whether the location is new/changed (a fast hash
        check) and, if so, START rendering its image in the BACKGROUND so the generation
        overlaps the rest of the turn (founder: fire ASAP, text-only meanwhile). The
        transport hands off via `take_pending_image()` and shows the image just before the
        new scene's prose (or LATE if the render is slow). Usually no model call — but if the
        location has NO committed description (an improv place reached by narrating a trip),
        it furnishes one ONCE so the image has a paint source. Fail-open; idempotent per scene."""
        try:
            from construct import imagery
            from construct.foyer import state_value
            if not imagery.enabled():
                return None
            loc = self.location()
            if not loc:
                return None
            desc = state_value(self._world.porcelain, loc, "description",
                               as_of=self._horizon()) or ""
            if not desc:
                # A location reached by NARRATING a trip (an improvised place) may have no
                # committed description yet — and the image paints from the description, not the
                # prose. Furnish one now so a new location always gets a picture (founder: "should
                # I have gotten a new image for this new location?"). Memoized → fires at most once.
                self._ensure_scene_description()
                desc = state_value(self._world.porcelain, loc, "description",
                                   as_of=self._horizon()) or ""
            contents = self._scene_contents(loc)
            if not (desc or contents):
                return None
            rec = imagery.plan_scene(self.scenario, loc,
                                     self._display_name(loc) or loc, desc,
                                     world_brief=self._meta.get("premise", ""),
                                     genre=self._scene_genre(),
                                     contents=contents)
            self._last_image = rec
            if rec and rec.fresh and not self._render_in_flight(rec):
                self._start_render(rec)
            return rec
        except Exception:
            logger.debug("scene-image hook failed", exc_info=True)
            return None

    def _scene_genre(self) -> str:
        """The world's listed genre / game-type, humanized — dumped into the image
        style for per-story visual variety (founder). E.g. 'mystery whodunnit, social
        drama relationship web'. Empty when the world declares none."""
        parts: list[str] = []
        gt = self._meta.get("game_type") or self._meta.get("game_types") or []
        if isinstance(gt, str):
            gt = [gt]
        parts.extend(str(g) for g in gt if g)
        for key in ("genre", "genre_era"):
            v = (self._meta.get(key) or "").strip()
            if v:
                parts.append(v)
        seen, out = set(), []
        for p in parts:
            p = p.replace("_", " ").strip()
            if p and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        return ", ".join(out[:3])

    def _ensure_scene_description(self) -> None:
        """Mint the current scene's `description` if it's never been furnished — so the
        OPENING has an image source (furnish_scene otherwise runs only inside a turn).
        Best-effort; a furnish hiccup just means the opening leans on scene contents."""
        try:
            from construct.turnloop import TurnTrace, furnish_scene
            scene = self.location()
            if not scene:
                return
            furnish_scene(self._world.porcelain, scene,
                          f"knows:{self._arc.protagonist}", {}, TurnTrace(turn=0),
                          as_of=self._horizon())
        except Exception:
            logger.debug("opening scene furnish failed", exc_info=True)

    def _scene_contents(self, scene: str) -> str:
        """The notable canon things ACTUALLY in the scene — objects/clues and any
        corpse — so the image depicts the real, furnished room (founder: not a bare
        hall). LIVING people are deliberately excluded (theatre of the mind); a dead
        body IS included. Read from the arc scope (the cast + key objects); best-effort."""
        from construct.foyer import state_value
        p = self._world.porcelain
        proto = self._arc.protagonist
        _h = self._horizon()
        items: list[str] = []
        try:
            here = p.locate(scene, as_of=_h) or []
        except Exception:
            here = []
        for e in (self._scope or []):
            if e in (proto, scene):
                continue
            try:
                loc = state_value(p, e, "in", as_of=_h)
                if loc != scene:
                    chain = p.locate(e, as_of=_h) or []
                    if scene not in chain and not (set(chain) & {scene, *here}):
                        continue
            except Exception:
                continue
            name = state_value(p, e, "name", as_of=_h) or e.split(":", 1)[-1].replace("_", " ")
            kind = (state_value(p, e, "kind", as_of=_h) or "").strip()
            if e.startswith("person:"):
                cond = " ".join(filter(None, (
                    state_value(p, e, "state", as_of=_h), state_value(p, e, "condition", as_of=_h),
                    state_value(p, e, "status", as_of=_h), kind))).lower()
                if any(w in cond for w in ("dead", "slain", "corpse", "killed",
                                           "lifeless", "murdered", "body")):
                    items.append(f"the body of {name}")
                continue  # living people stay theatre-of-the-mind
            label = name if (not kind or kind.lower() in name.lower()) else f"{name} ({kind})"
            items.append(label)
        # stable order so the hash is deterministic for an unchanged room
        return ", ".join(sorted(dict.fromkeys(items))[:8])

    def _render_in_flight(self, rec: Any) -> bool:
        h = getattr(self, "_pending_image", None)
        return bool(h and h["rec"].description_hash == rec.description_hash)

    def _start_render(self, rec: Any) -> None:
        """Kick the (slow) prompt-cohort + image generation on a daemon thread, so a
        fresh location's picture is being made while the turn's prose is composed."""
        import threading
        from construct import imagery
        holder: dict[str, Any] = {"rec": rec, "done": threading.Event()}

        def _run() -> None:
            try:
                imagery.render(self.scenario, rec, provider=self._provider)
            finally:
                holder["done"].set()

        threading.Thread(target=_run, daemon=True, name="scene-image").start()
        self._pending_image = holder

    def take_pending_image(self) -> Any:
        """Hand off the in-flight render HOLDER ({'rec', 'done'}) and clear the slot WITHOUT
        waiting — the transport decides whether to join briefly (image-before-text) or send it
        LATE when the render finishes, so the text reply is never blocked on a slow render and a
        slow-but-successful image is delivered late instead of dropped (founder image fix). One-shot."""
        holder = getattr(self, "_pending_image", None)
        self._pending_image = None
        return holder

    def pending_image(self, timeout: float = 75.0) -> Any:
        """Block (bounded) for the in-flight scene render and return the rendered
        SceneImage iff its asset file is ready, else None. One-shot — clears the slot,
        so a fresh image is delivered exactly once, just before its scene's prose."""
        holder = getattr(self, "_pending_image", None)
        self._pending_image = None
        if not holder:
            return None
        holder["done"].wait(timeout)
        rec = holder["rec"]
        from pathlib import Path
        if rec and rec.asset_path and Path(rec.asset_path).exists():
            return rec
        return None

    @property
    def last_image(self) -> Any:
        """The most recently planned SceneImage (fresh/cached), or None."""
        return getattr(self, "_last_image", None)

    def _refresh_beat_scope(self) -> None:
        """DRIFT D3 (cr blockers 3 + re-review 5): a committed repair changed
        the live beat set; refresh the beat-derived session scope so the
        replacement's referents enter scene scope AND superseded-only
        referents stop driving it. The tracked `_beat_scope` subset is
        subtracted (never independently-played scope — an entity the story
        put in play through scenes/canon stays visible) and the fresh live
        set added, at the play horizon. Best-effort."""
        try:
            from construct.arc.executor import arc_entities
            reads = PorcelainWorldReads(self._world, horizon=self._horizon())
            live: set[str] = set()
            for _a in [self._arc] + list(self._side_arcs or []):
                live |= arc_entities(_a, reads)
            scope = (set(self._scope or []) - self._beat_scope) | live
            self._scope = sorted(e for e in scope if reads.has_entity(e))
            self._beat_scope = live
        except Exception:
            logger.exception("scope refresh after repair failed; keeping current scope")

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
            scope = set(arc_entities(self._arc, reads)) | set(extra_scope or [])
            self._scope = sorted(e for e in scope if reads.has_entity(e))
            self._beat_scope = set(arc_entities(self._arc, reads))
            for _sa in self._side_arcs or []:
                self._beat_scope |= arc_entities(_sa, reads)
            logger.info("session arc reloaded after replan: main=%s (+%d reshape entities)",
                        self._arc.arc_id, len(extra_scope or []))
        except Exception:
            logger.exception("arc portfolio reload after replan failed; keeping current arc")

    def close(self) -> None:
        if not self._closed:
            # Flush any deferred bookkeeping before the world closes, so the last turn's
            # facts/transcript/time are never lost when a session ends without a next turn.
            self._flush_settle()
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
