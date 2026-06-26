"""Surgical live test of the ONE remaining unproven link in topic-aware delivery: does the live
`classify` model populate `asks_targets` correctly from real ask_candidates? Everything downstream
(select among gate-eligible, fire the beat) is already proven at the integration level by
test_topic_aware_delivery_picks_the_questioned_clue_and_fires_the_beat (real run_turn, stub
narrator). So we isolate just classify here — cheap calls, no build, no narrate timeout.

Run:  PYTHONPATH=. .venv/bin/python scripts/classify_asks_probe.py
"""
from __future__ import annotations

import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct import cohorts
from construct.provider import CodexProvider

# (label, player_input, ask_candidates [(oid, non_spoiling_descriptor)], expected_oids)
CASES = [
    ("press-on-topic (Mara/Carl money)",
     "I turn to Mara and press her hard — how bad does she think my money troubles are, the "
     "contracts, the house?",
     [("ask_0", "Mara knows Carl is one failed contract from selling his house in Fairbanks"),
      ("ask_1", "Hal saw only white out the windscreen before the crash"),
      ("ask_2", "the cargo manifest lists the core boxes")],
     {"ask_0"}),
    ("press-on-topic (clerk/vault)",
     "I ask the old clerk about the vault — what is it he keeps and maintains down here?",
     [("ask_0", "the old clerk maintains the vault and guards what is inside"),
      ("ask_1", "Administrator Cray wrote a phantom reserve into the ledgers")],
     {"ask_0"}),
    ("press-on-topic (Cray/reserve)",
     "I press Administrator Cray hard about the phantom reserve in the ledgers — who wrote it in?",
     [("ask_0", "the old clerk maintains the vault"),
      ("ask_1", "Cray wrote the phantom reserve into the ledgers"),
      ("ask_2", "Cray signed the decommission order")],
     {"ask_1"}),
    ("generic look-around → empty",
     "I take a slow look around the room and let it settle.",
     [("ask_0", "the old clerk maintains the vault"),
      ("ask_1", "Cray wrote the phantom reserve")],
     set()),
]


def main() -> None:
    prov = CodexProvider()
    print("# classify asks_targets probe\n")
    passed = 0
    for label, inp, cands, expected in CASES:
        try:
            out = cohorts.classify(prov, inp, ask_candidates=cands)
            got = set(out.get("asks_targets") or [])
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {label}: {exc}")
            continue
        ok = got == expected
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        print(f"        input: {inp[:70]}...")
        print(f"        expected={sorted(expected)}  got={sorted(got)}  kind={out.get('kind')}")
    print(f"\n{passed}/{len(CASES)} cases passed")


if __name__ == "__main__":
    main()
