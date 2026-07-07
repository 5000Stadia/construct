"""Founder-approved clean rebuild of Minutes Before Bullets (#107): the same
brief, on the fixed code — the play_as figure is staged, never swapped, and
her identity carries the gender the original capture dropped."""
import logging
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_generated
from construct.provider import CodexProvider

SEED = """A post-apocalyptic survival story of a small community in good standing which receives information from the remaining government — details regarding continuous outsiders attempting to raid sanctioned, government-approved encampments like the one the character starts in. There is an assignment of basic sectional leads in the encampment — defense, food, retrieval, etc — with apprentices supporting leads as future replacements. This structure is as recommended by the government, which provides minor supplies from time to time but is otherwise distant; understanding of government plans and the future-as-planned-for-prosperity is informed over radio, mostly. Besides the government military robot that caravans supplies in and provides rare info to the encampment — and, rarer yet, people who have been vetted to join — there is no real contact with the government.

The encampment is well hidden, and they haven't had contact with anyone outside other than the rare person brought in by the caravan robot. When they have, outsiders are assumed to be raiders and given one chance to turn back or be killed. There has been controversy over whether this is the most intelligent way of doing things, but the risk of violent people is much higher than in the past. It's assumed that if people aren't in a safe settled community, it's because they are too dangerous to enter one.

Warnings have come in on the radio for a while now about a disease infecting communities and raiders alike — guaranteed after some time, and highly contagious. Proximity seems to be the only deterrent, and the encampment has new guidelines: warn outsiders from a much farther distance, and shoot to kill at a distance from adjusted defense locations if they don't comply.

An outsider group will be coming soon. They will stop when they hear the encampment's warning, then decide to slowly proceed, shouting something that in the moment is difficult to make out. They will cross the line and be shot dead.

The main character is the defense apprentice — a young woman, daughter of the defense lead. She is deeply bothered by the killing of this group; it nags at her what they were shouting. She grows suspicious of what she hears on the radio, sees the conviction the promises of a better tomorrow have given her father, and also sees how those promises may have proven false. She questions the motives behind the costs of the supplies coming in, distrusts that it is simply government humanitarianism, and wonders whether they are puppets — and if so, what the puppet show is all about. The secrecy behind the government makes little sense. Where IS the government? WHAT is the government? It may not be the government at all; the disease may not be real; and the people who were killed may have been trying to inform the encampment of the truth.

The encampment has multiple categories of needs sectioned into groups, each group with a lead and an apprentice; decisions are made by democratic voting in a nighttime group setting around dinner time."""

meta = create_scenario_from_generated(
    "live_telegram_8786956263_3",
    CodexProvider(),
    seed=SEED,
    endless=False,
    win_direction="",
    play_as=("the defense apprentice — a young woman, daughter of the defense "
             "lead; deeply bothered by the killing of the shouting outsider "
             "group, nagged by what they were shouting, growing suspicious of "
             "the radio government and its promises"),
    game_types=["wilderness_survival"],
    reality_register="alternate",
    on_stage=lambda m: print(f"STAGE: {m}", flush=True),
)
print("SEALED:", meta.get("title"), "| protagonist:", meta.get("protagonist"))
print("laws:", [l.get("name") for l in (meta.get("laws") or [])])
