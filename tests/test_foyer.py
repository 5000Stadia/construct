"""The Foyer tool loop (CHARACTER-CREATION.md) — stub-driven, no live model.
Verifies character details + free additions accumulate, defaults are carried,
and `done` ends the phase."""

import construct.game
from construct.foyer import (
    CharacterSheet, foyer_step, ingest_character, world_anchors)
from construct.provider import StubProvider


class _FakePorc:
    def __init__(self, facts=None):
        self.facts = facts or {}          # (entity, attribute) -> value
        self.ingested = []                # rows committed as stated canon

    def state(self, entity, attribute, frame="canon"):
        # Mirror the real porcelain shape: a structured {status, fact:{value}} dict.
        if (entity, attribute) in self.facts:
            return {"status": "known", "fact": {"value": self.facts[(entity, attribute)]}}
        return {"status": "unknown"}

    def ingest_structured(self, items, frame=None):
        self.ingested += items


class _FakeWorld:
    def __init__(self, facts=None):
        self.porcelain = _FakePorc(facts)


def _act(tool, field="", value=""):
    return {"tool": tool, "field": field, "value": value}


def _turn(reply, *actions):
    return {"reply": reply, "actions": list(actions)}


def _step(p, sheet, msg, **kw):
    return foyer_step(p, sheet, history="", user_msg=msg, **kw)


def test_set_details_accumulate():
    p = StubProvider([
        _turn("Wren it is.", _act("set_detail", "name", "Wren")),
        _turn("She/her, noted.", _act("set_detail", "pronouns", "she/her"))])
    s = CharacterSheet()
    _step(p, s, "call me Wren", role="a student of the Conservatory")
    _step(p, s, "she/her")
    assert s.details == {"name": "Wren", "pronouns": "she/her"}


def test_defer_lets_agent_set_the_value():
    # "you pick" → the agent invents and sets it (one tool call carries the value).
    p = StubProvider([_turn("Then: a fen-child who read weather-omens.",
                            _act("set_detail", "background",
                                 "a fen-child who read weather-omens"))])
    s = CharacterSheet()
    _step(p, s, "you pick my background")
    assert s.details["background"].startswith("a fen-child")


def test_free_addition_is_captured():
    p = StubProvider([_turn("A rival who's edged you out — noted.",
                            _act("add_element", value="a rivalry with the head of the rival house"))])
    s = CharacterSheet()
    _step(p, s, "I had a rivalry with the rival house head")
    assert s.additions == ["a rivalry with the head of the rival house"]


def test_rule_of_cool_negotiation_then_canon():
    # The guest's genre-straining request is negotiated over a couple of turns
    # (chat, no commit) and only the agreed, coherent canon is added.
    p = StubProvider([
        _turn("This realm is medieval — perhaps a card game?", _act("chat")),
        _turn("Then your grandfather's automata vision-box plays it.",
              _act("add_element", value=(
                   "grandfather's arch-artificer automata vision-box that plays "
                   "'rabble comrades', now called 'smash brothers'")))])
    s = CharacterSheet()
    r1 = _step(p, s, "start me playing Smash Bros with my neighbor Greg")
    assert r1.done is False and s.additions == []          # still negotiating
    _step(p, s, "no, keep it fantasy but I have the only working TV")
    assert any("vision-box" in a for a in s.additions)     # crafted canon captured


def test_done_ends_the_phase():
    p = StubProvider([_turn("Then let me weave it in.", _act("done"))])
    s = CharacterSheet(details={"name": "Wren", "pronouns": "they/them"})
    r = _step(p, s, "that's everything, let's start")
    assert r.done is True


def test_done_gated_until_required_fields_set():
    # Required-criteria gate (founder): never finish without name + pronouns, even
    # if the cohort says done — ask for the missing one and stay in the Foyer.
    p = StubProvider([_turn("Let's begin.", _act("done"))])
    s = CharacterSheet(details={"name": "Wren"})        # pronouns missing
    r = _step(p, s, "go")
    assert r.done is False
    assert "pronoun" in r.reply.lower()


def test_sheet_roundtrips():
    s = CharacterSheet(details={"name": "Wren"}, additions=["a rival"])
    assert CharacterSheet.from_dict(s.to_dict()).summary() == s.summary()


def test_summary_renders_details_and_additions():
    s = CharacterSheet(details={"name": "Wren", "pronouns": "she/her"},
                       additions=["a rivalry with the rival house"])
    text = s.summary()
    assert "name: Wren" in text and "she/her" in text
    assert "+ a rivalry with the rival house" in text


# ---- world-anchor read + character ingest --------------------------------

def test_state_value_unwraps_the_porcelain_shape():
    from construct.foyer import state_value
    p = _FakePorc({("person:x", "name"): "Xander"})
    assert state_value(p, "person:x", "name") == "Xander"
    assert state_value(p, "person:x", "missing") is None   # unknown → None


def test_world_anchors_reads_connected_entities():
    facts = {("person:maon", "kind"): "person", ("person:maon", "name"): "Maon",
             ("person:maon", "role"): "the severe master who taught your first sigil"}
    w = _FakeWorld(facts)
    anchors = world_anchors(w, ["person:maon", "person:wren"], "person:wren")
    assert len(anchors) == 1                      # protagonist excluded
    assert "Maon (person)" in anchors[0]
    assert "severe master" in anchors[0]


def test_ingest_character_writes_details_as_canon():
    w = _FakeWorld()
    sheet = CharacterSheet(details={"name": "Wren", "pronouns": "she/her",
                                    "gender": "woman", "favorite_color": "green"})
    ingest_character(w, StubProvider([]), "person:wren", sheet)
    got = {(r["entity"], r["attribute"], r["value"]) for r in w.porcelain.ingested}
    assert ("person:wren", "name", "Wren") in got
    assert ("person:wren", "pronouns", "she/her") in got
    # only the known detail fields write directly (not arbitrary keys)
    assert not any(r["attribute"] == "favorite_color" for r in w.porcelain.ingested)


def test_ingest_character_grounds_additions(monkeypatch):
    monkeypatch.setattr(construct.game, "_world_digest", lambda world: "(digest)")
    w = _FakeWorld()
    # The grounding cohort turns the addition into structured rows.
    p = StubProvider([{"items": [
        {"entity": "obj:vision_box", "attribute": "kind", "value": "artifact"},
        {"entity": "obj:vision_box", "attribute": "owned_by", "value": "person:wren"}]}])
    sheet = CharacterSheet(additions=["the only working TV in the kingdom"])
    ingest_character(w, p, "person:wren", sheet)
    got = {(r["entity"], r["attribute"]) for r in w.porcelain.ingested}
    assert ("obj:vision_box", "owned_by") in got


def test_ingest_character_failopen_keeps_additions_as_history(monkeypatch):
    monkeypatch.setattr(construct.game, "_world_digest", lambda world: "(digest)")
    w = _FakeWorld()
    p = StubProvider([])  # cohort call will raise (empty queue) → fail-open path
    sheet = CharacterSheet(additions=["a secret rivalry"])
    ingest_character(w, p, "person:wren", sheet)
    hist = [r for r in w.porcelain.ingested if r["attribute"] == "history"]
    assert hist and hist[0]["value"] == "a secret rivalry"
