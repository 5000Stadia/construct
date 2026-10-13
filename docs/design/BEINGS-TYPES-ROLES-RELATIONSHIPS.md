# Beings, types, roles and relationships

**Status:** construct's proposal, r2, 2026-10-13 (r2 adopts pattern-buffer's derive-don't-move placement). Not built. It feeds pattern-buffer's R51 (beings) and R52 (role vs relationship), both in their Later list. Fresh views from two other model families come before anything is built, because the proposal changes R49's shipped gate rule.

**Source.** Kabe, 2026-10-13, after R49 recorded a dog as kind person, role dog:
- "If a dog is a kind of person and what is the point of identifying term person? Isn't it more of a 'sentient entity' have either type person or type dog"
- "In the future, this should be allowed as a hostile enemy if the engine actually develops into that direction"
- "So in many ways, the disposition of the entity matters as well"
- "Multiple titled dispositions should be compatible with individuals such as you would have multiple categorical tags available for an object. A person can both be a prisoner, a mayor, a father ... The intelligent and elegant nuance needs to be when you are choosing a tag of this sort, and when you are choosing a different mechanism that exists as actual architecture within pattern buffer such as relationships"
- "I am ignorant to the current infrastructure though. I propose that dilemma to you and trust you with the most elegant architecture."

## The rule: two questions, asked in order

For any word that describes a being ("dog", "prisoner", "mayor", "father", "hostile"):

1. **Does it need a second party to be true?** Father *of* someone, mayor *of* a town, captain *of* a ship, hostile *toward* someone.
   - **Yes:** it is a **relationship**, a dated, entity-valued fact from this being to that party. The title ("father", "the mayor") is derived from the edge when read, never stored beside it. Kabe's "disposition" (pattern-buffer's proposed name: **stance**) is one family of these: hostile, wary or loyal *toward* someone.
2. **If not, is it what the being is by nature, or what it is for a while?**
   - **By nature** (person, dog, wraith): its **type**, held in `kind`. Rarely changes; a story can change it (a werewolf, a ghost).
   - **For a while** (prisoner, widow, hero): a **role**, dated and set-valued, as R49 built it. Many at once.

The **being** itself is the class: anything that acts and knows, and can be met, friend or enemy. In construct that is the `person:` id space, which already holds every character. It is read as "being" and not renamed, because ids are written into every world.

## Why this is the elegant shape: almost everything already exists

| Layer | Pattern-buffer today | What is new |
|---|---|---|
| Being | the `person:` namespace; R49's person test (`ingest.py` `_is_person_role_move`) | read it as "being" |
| Type | `kind`, which identity already compares (`identity.py` `_kind_state`) | stop forcing `person`: keep a type word as given |
| Role | R49: set-valued, dated `role` | nothing |
| Relationship and stance | ordinary entity-valued rows; identity already treats a relating edge between two ids as evidence that they are two (`relating_edges_between`) | vocabulary, a read from the other side, and derived titles |

**Type vs role needs no word list, and no row is moved.** (Revised in r2, on pattern-buffer's pushback, m560af5.)
- r1 judged at the ingest gate and moved the row. That puts a synchronous model call on the write path (builds keep model calls out of it with begin_build/seal_build). A move decided at write time can't be undone by a better verdict later, because the log is append-only.
- r2 **derives instead of moving.** A being's `kind` rows are stored as written. The classifier, which is deferred, kept in its sidecar and rebuildable, judges each one CONSTITUTIVE or STATE. That lifts `kind`'s structural shortcut for beings only.
- The read serves the CONSTITUTIVE kinds as the type and the STATE ones as roles. Identity's kind check reads the type.
- Worlds already built, R49's and construct's, are fixed with no rewrite: "condemned man" is judged STATE, and the kind_conflict disappears.
- A wrong judgment is corrected by a new verdict, not a new row.
- Rules-only mode (no model) falls back to R49's behaviour: "person" is the type, anything else a role.
- The cost: a deeper engine change than R49. It touches the classifier's structural guardrail and the kind fold, and R49's gate move retires.
- To check: identity's build stages must read the type after the build's classification has run, not before.
- The fresh views get both placements, the gate and the sidecar.

**Identity gets its guard back.** `kind` holds the type again, so the existing kind check keeps a man and a dog both called Rex apart, with no new identity code. Two people's kinds are both `person` and still fold together, so R49's fix for run 8 (role noise splitting one person) is kept. A father-of edge between two ids already counts as evidence that they are two people.

**Titles are derived, not stored** (pattern-buffer's P3 and its membrane test). "Father" is read from the parent edge, so the tag and the edge can never disagree. A title the text gives with no party ("the Mayor", town never named) stays a role until the party is known: the conservative choice, and the one R49 makes today.

## What pattern-buffer would build (their design, our needs)

1. **The classifier and the kind fold:** a being's `kind` rows are judged CONSTITUTIVE (type) or STATE (role) in the deferred sidecar, and read accordingly. R49's gate move retires (r2; see above).
2. **The prompt (R52):** role is only what a being is on its own. A title that needs a party is a dated relationship to that party, chosen by the model.
3. **A read from the other side:** "who has X as the value of A" ("whose father is he?", "who is hostile to me?"). There is no porcelain read for it today; `incoming_refs` exists internally.
4. **Derived titles:** read a being's roles together with the titles of its relationships, so a host asks one question ("what is he?") and gets "prisoner; father of Nessa; mayor of Ironhold".
5. **Stance vocabulary:** a small built-in family (hostile toward, wary of, loyal to), set-valued and dated, readable from both sides. This is what makes a dog, a beast or a wraith an enemy rather than a type.

## What construct does with it

- Construct reads "what is he?" through the derived read (4), not through `role` alone.
- A being's stance toward the player can drive presence and conflict: an enemy is a being with a hostile stance toward the hero, of whatever type.
- Construct never writes a title beside an edge.

## Open, for when the work is brought forward

- Does a type change ever need its own era, like a role? A werewolf is a dated type. The proposal keeps `kind` timeless-by-default, with dated rows allowed.
- How many stance words are built in, and which stay domain words.
- Whether `person:` gains a `being:` alias for new non-human ids, or stays the one character namespace.
