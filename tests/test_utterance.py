"""UTTERANCE-NOT-FACT (docs/design/UTTERANCE-NOT-FACT.md r3, R42 first slice; ruleset IR-5).

What the player's character SAYS never becomes canon by being said: speech is not extracted;
the speech act is recorded as a reserved `player_speech` event."""
import dataclasses

import pytest

from construct.adapter import PorcelainWorldReads
from construct.provider import _SILENT_DEFAULTS
from construct.provider import StubProvider as _Stub
from construct.speech import strip_speech
from tests.test_integration import PLAYER, make_arc, run_turn, seed_arc, world  # noqa: F401

_BASE = {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""}


def StubProvider(responses):  # noqa: N802
    return _Stub(responses, silent_defaults={
        **_SILENT_DEFAULTS, "ndg": ("directive", {"thread": "", "directive": ""}),
        "npt": ("acts", {"acts": False, "action": "", "speaks": False, "intent": "",
                         "line_hint": ""})})


def _spy_extract(world, monkeypatch):
    seen: list[str] = []
    real = world.porcelain.extract

    def spy(text, *a, **kw):
        seen.append(str(text))
        return real(text, *a, **kw)
    monkeypatch.setattr(world.porcelain, "extract", spy)
    return seen


def _said(world):
    return PorcelainWorldReads(world).events(kind="player_speech")


def _seed_people(world, *names):
    rows = []
    for n in names:
        pid = f"person:{n.lower()}"
        rows += [{"entity": pid, "attribute": "kind", "value": "person", "timeless": True},
                 {"entity": pid, "attribute": "name", "value": n},
                 {"entity": pid, "attribute": "in", "value": "place:study",
                  "value_type": "entity"}]
    world.ingest_structured(rows)


def _turn(world, verdict, text, *, scope=None, turn=3, extra_extraction=None):
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([extra_extraction or {"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, **verdict}, {"prose": "The words land."}])
    return run_turn(world, arc, prov, text, turn=turn,
                    scope=scope or [PLAYER, "place:study"])


# ------------------------------------------------------------- 1-2. speech is not fact

def test_bare_spoken_claim_is_not_extracted(world, monkeypatch):
    _seed_people(world, "Warden")
    seen = _spy_extract(world, monkeypatch)
    r = _turn(world, {"claims_are": "speech", "asserts_or_reveals": True},
              "'Tovan didn't steal anything,' I tell the warden.",
              scope=[PLAYER, "place:study", "person:warden"])
    assert not any("Tovan" in t for t in seen)
    ev = _said(world)
    assert len(ev) == 1 and "person:warden" in ev[0].patients
    content = PorcelainWorldReads(world).state(ev[0].event_id, "content")
    assert "Tovan didn't steal anything" in content
    assert any("utterance, not a fact" in d for d in r.trace.dropped_cohorts)


def test_a_lie_never_lands(world, monkeypatch):
    seen = _spy_extract(world, monkeypatch)
    _turn(world, {"claims_are": "speech"},
          "I tell Quincy, 'Ellis was at the docks that night.'",
          extra_extraction={"items": [{"entity": "person:ellis", "attribute": "in",
                                       "value": "place:docks", "value_type": "entity"}]})
    assert not any("Ellis was at the docks" in t for t in seen)
    assert _said(world)


# --------------------------------------------------------------------- 3. mixed lines

def test_mixed_line_extracts_only_the_unspoken_part(world, monkeypatch):
    seen = _spy_extract(world, monkeypatch)
    _turn(world, {"claims_are": "mixed"},
          "I slide the ledger to Quincy. \"Ellis cooked these numbers.\"")
    assert seen and all("Ellis cooked" not in t for t in seen)
    assert any("I slide the ledger to Quincy." in t for t in seen)


# ------------------------------------------------------------------- 4. act unchanged

def test_act_line_extracts_as_today(world, monkeypatch):
    seen = _spy_extract(world, monkeypatch)
    _turn(world, {"claims_are": "act"}, "I bar the door with the plank.")
    assert any("I bar the door with the plank." in t for t in seen)
    assert not _said(world)


# ----------------------------------------------------------- 5. unknown fails closed

@pytest.mark.parametrize("line", ["Tovan did not steal anything",
                                  "I tell Quincy Ellis was at the docks",
                                  "I bar the door with the plank."])
def test_unknown_classification_extracts_nothing(world, monkeypatch, line):
    seen = _spy_extract(world, monkeypatch)
    _turn(world, {}, line)                      # an old-shaped verdict: no claims_are
    assert not any(line in t for t in seen)


# ---------------------------------------------------------------------- 5b. the scanner

@pytest.mark.parametrize("text,rest,spans", [
    ("I hand Quincy the ledger and say 'Ellis cooked the numbers.'",
     "I hand Quincy the ledger and say", ["Ellis cooked the numbers."]),
    ("I take Quincy's ledger; don't move", "I take Quincy's ledger; don't move", []),
    ('He said "wait for me', "He said", ["wait for me"]),          # unmatched: to the end
    ("\"he said 'no' twice\" I add", "I add", ["he said 'no' twice"]),  # outermost wins
    ('"Where were you at nine?"', "", ["Where were you at nine?"]),
    ("“Tovan didn’t steal anything,” I tell the warden.", "I tell the warden.",
     ["Tovan didn’t steal anything,"]),
    ("«Leave,» I say, and bar the door.", "I say, and bar the door.", ["Leave,"]),
])
def test_strip_speech(text, rest, spans):
    got_rest, got_spans = strip_speech(text)
    assert got_rest == " ".join(rest.split()) and got_spans == spans


def test_quote_only_line_makes_no_extraction_call(world, monkeypatch):
    seen = _spy_extract(world, monkeypatch)
    _turn(world, {"claims_are": "mixed"}, "\"Hand over the ledger, Cray.\"")
    assert not any("ledger" in t for t in seen)
    assert _said(world)


def test_quotes_around_an_action_with_act_take_todays_path(world, monkeypatch):
    seen = _spy_extract(world, monkeypatch)
    _turn(world, {"claims_are": "act"}, "\"I bar the door,\" I mutter, and I do.")
    assert any("I bar the door" in t for t in seen)


# ------------------------------------------------------ 5c. addressees and delivery

def test_patients_are_the_addressed_set(world):
    _seed_people(world, "Quincy", "Mara")
    _turn(world, {"claims_are": "speech"}, "'It was Ellis,' I tell Quincy.",
          scope=[PLAYER, "place:study", "person:quincy", "person:mara"])
    ev = _said(world)
    assert ev and list(ev[0].patients) == ["person:quincy"]


def test_no_addressee_no_patient(world):
    _turn(world, {"claims_are": "speech", "addresses_present": False},
          "'Nobody listens anyway,' I mutter.")
    ev = _said(world)
    assert ev and not ev[0].patients


def test_interrogation_still_delivers_a_clue(world):
    """Only factual EXTRACTION of speech is prohibited: ASK delivery runs as today."""
    from construct.cast import CastNode, Clue
    _seed_people(world, "Clerk")
    arc = make_arc()
    seed_arc(world, arc)
    clue = Clue("clue:nine", "pillar:p", ("fact:secret", "culprit", "person:rival"))
    cast = {"person:clerk": CastNode("person:clerk", holds_clues=(clue,),
                                     presence="at_scene", location="place:study")}
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, "claims_are": "speech", "addresses_present": True},
                         {"prose": "The clerk swallows. 'The rival.'"}])
    run_turn(world, arc, prov, "'Who was it, clerk?' I ask the clerk.", turn=4,
             scope=[PLAYER, "place:study", "person:clerk"], cast=cast)
    known = PorcelainWorldReads(world).assertion_in_frame(
        f"knows:{PLAYER}", "fact:secret", "culprit", "person:rival")
    assert known


# ------------------------------------------------------------------ 5d. no collision

def test_speech_event_never_collides_or_satisfies(world):
    from construct.arc.conditions import Occurred
    from construct.arc.grammar import Beat, Phase, Weight
    from construct.game import _build_arc
    base = make_arc()
    arc = dataclasses.replace(base, beats=(*base.beats, Beat(
        "beat:utter", Phase.RISING, Weight.OPTIONAL, achievable_via=Occurred("utterance"))))
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, "claims_are": "speech"}, {"occurred": ["utterance"]},
                         {"prose": "You speak."}])
    run_turn(world, arc, prov, "'I know what you did,' I say.", turn=4,
             scope=[PLAYER, "place:study"])
    R = PorcelainWorldReads(world)
    said = {e.event_id for e in R.events(kind="player_speech")}
    authored = {e.event_id for e in R.events(kind="utterance")}
    assert said == {"event:said_4"} and authored == {"event:utterance_4"}
    with pytest.raises(Exception):
        _build_arc({"protagonist": PLAYER, "delta_type": "desire_at_cost",
                    "tension": [PLAYER, "drive:a", "drive:b"],
                    "beats": [{"id": "beat:x", "phase": "climax", "weight": "required",
                               "kind": "event_occurs", "entity": "player_speech",
                               "attribute": "", "value": ""}]})


# ------------------------------------------------------- 5e. the named gap, pinned

def test_named_gap_unquoted_reported_speech_in_a_mixed_line(world, monkeypatch):
    """PINNED residual gap: unquoted reported speech inside a mixed line still reaches
    extraction today. When a later slice closes it, this test should flip."""
    seen = _spy_extract(world, monkeypatch)
    _turn(world, {"claims_are": "mixed"},
          "I hand Quincy the ledger and tell him Ellis cooked it.")
    assert any("Ellis cooked it" in t for t in seen)
