"""The text toolkit: word tokenizers, slugs, and entity-id humanizing in one place.

Before this module the same jobs were done by clones scattered across construct (audit
2026-10 tier 2 #3: turnloop findings 4 and 9, arc F11, world F6). Each function here is ONE
distinct mechanism, and its docstring states it exactly: the character class, case
handling, how `_`, `-`, `:` and apostrophes are treated, and what happens to non-ASCII
text. The clones did NOT all agree, and they still don't: the per-site differences (the
separator set, the length floor, the stopwords, the empty-result fallback) are passed as
explicit arguments at each call site, so every caller keeps exactly the behaviour it had.
Unifying two of these mechanisms is a behaviour change, and is the founder's call.

Shared rules:
- The word tokenizers lowercase with `str.lower()` (Python's full Unicode lowering, so 'İ'
  becomes 'i' + U+0307 and the Kelvin sign 'K' becomes 'k'). Lowering is idempotent, so
  passing text that is already lowercased gives the same result. `id_stem_parts` keeps
  case, and `split_words`/`respace` say WHEN they lower (`lower="first"`, `"last"` or
  `"never"`): the order is observable through the Greek final sigma (see `respace`).
- `min_len` keeps a token only when `len(token) >= min_len` (so the old `len(t) > 3` is
  `min_len=4`); `stop` drops any token in that collection. Neither ever produces an empty
  token: the default `min_len=1` drops empties.
- Inputs are not coerced: a caller that used `text or ""` or `str(text)` still does.

The name readers at the end take a duck-typed `reads` (anything with
`.state(entity, attribute)`), so this module imports nothing from construct.
"""

from __future__ import annotations

import functools
import re
from typing import Any, Collection

# ---------------------------------------------------------------------------
# Word tokenizers
# ---------------------------------------------------------------------------

#: Runs of ASCII lowercase letters and digits.
_ALNUM_RUN = re.compile(r"[a-z0-9]+")

#: Runs of Unicode letters and digits (`\w` minus the underscore).
UNICODE_WORD = re.compile(r"[^\W_]+")

#: Runs of the separators an entity id or kind string uses: the ASCII space, `_`, `-`,
#: `/` and `:`.
_SEPARATOR_RUN = re.compile(r"[ _\-/:]+")

#: Separator sets that more than one tokenizer copy shares (pass to `split_words(seps=)`).
#: The id separators: `:`, `_` and `-` read as spaces.
ID_SEPARATORS = ":_-"
#: Comma, period and question mark read as spaces (the intent heuristics' split).
CLAUSE_PUNCT = ",.?"
#: The address matcher's split: these punctuation marks (including the em dash and the
#: hyphen) read as spaces.
WORD_PUNCT = ",.;:!?\"'()[]—-"
#: Edge punctuation stripped off a destination phrase's words.
EDGE_PUNCT = ".,;:!?'\""


def _keep(tokens: Any, min_len: int, stop: Collection[str]) -> list[str]:
    return [t for t in tokens if len(t) >= min_len and t not in stop]


def alnum_words(text: str, *, min_len: int = 1, stop: Collection[str] = ()) -> list[str]:
    """The lowercased runs of ASCII letters and digits in `text`, in order (duplicates kept).

    Everything else separates words: punctuation, whitespace, `_`, `-`, `:`, apostrophes
    (so "don't" gives ['don', 't']), and every non-ASCII character after lowering (so
    'josé' gives ['jos'] and 'café' gives ['caf']). This is the "total" tokenizer: no
    punctuation can stay attached to a word ('the map!' gives ['the', 'map']).
    `re.split(r"[^a-z0-9]+", ...)` with empties dropped is the same thing."""
    return _keep(_ALNUM_RUN.findall(text.lower()), min_len, stop)


def unicode_words(text: str, *, min_len: int = 1, stop: Collection[str] = ()) -> list[str]:
    """The lowercased runs of Unicode letters and digits in `text`, in order.

    Like `alnum_words`, but accented and non-Latin letters stay inside the word ('josé'
    is one word). The underscore separates, as do `-`, `:`, apostrophes, punctuation and
    whitespace."""
    return _keep(UNICODE_WORD.findall(text.lower()), min_len, stop)


@functools.lru_cache(maxsize=None)
def _space_table(seps: str, drop: str) -> dict[int, Any]:
    table: dict[int, Any] = {ord(c): " " for c in seps}
    table.update({ord(c): None for c in drop})
    return table


def respace(text: str, *, seps: str = "", drop: str = "", lower: str = "first") -> str:
    """`text` with every character of `drop` deleted and every character of `seps` turned
    into a space (the same as chaining `.replace(c, "")` / `.replace(c, " ")` per
    character, in any order), and lowercased:

    - `lower="first"`: lowercase, then respace;
    - `lower="last"`: respace, then lowercase;
    - `lower="never"`: keep case (for callers handed text that is already lowercased).

    "first" and "last" differ only through `str.lower()`'s one context rule, the Greek
    final sigma: ':', '.', and the apostrophes are case-ignorable, so 'ΛΟΓΟΣ:ΤΙ' lowers
    its 'Σ' to 'σ' when the colon is still there ("first") but to the final 'ς' once the
    colon has become a space ("last")."""
    if lower == "first":
        return text.lower().translate(_space_table(seps, drop))
    if lower == "last":
        return text.translate(_space_table(seps, drop)).lower()
    if lower == "never":
        return text.translate(_space_table(seps, drop))
    raise ValueError(f"lower must be 'first', 'last' or 'never', not {lower!r}")


def split_words(text: str, *, seps: str = "", drop: str = "", strip: str = "",
                lower: str = "first", min_len: int = 1,
                stop: Collection[str] = ()) -> list[str]:
    """Whitespace words of `respace(text, seps=seps, drop=drop, lower=lower)`, in order.

    Only the characters in `seps` become separators (on top of all Unicode whitespace,
    which `str.split()` splits on); every other character stays inside its word, so with
    `seps=""` 'culprit,' stays one word with its comma, and 'josé' stays whole. Each word
    then has the characters in `strip` stripped from both ends (none when `strip` is
    empty), and words left empty are dropped."""
    words = respace(text, seps=seps, drop=drop, lower=lower).split()
    if strip:
        words = [w.strip(strip) for w in words]
    return _keep(words, min_len, stop)


def separator_words(text: str, *, min_len: int = 1, stop: Collection[str] = ()) -> list[str]:
    """`text` lowercased and split on runs of the ASCII space, `_`, `-`, `/` and `:`.

    Only those five characters separate: tabs, newlines and punctuation stay inside a
    word ('kind,' and 'a\\tb' are single words). Non-ASCII letters are kept."""
    return _keep(_SEPARATOR_RUN.split(text.lower()), min_len, stop)


def id_stem_parts(eid: str, *, hyphens: bool = False, min_len: int = 1,
                  stop: Collection[str] = ()) -> list[str]:
    """The parts of an entity id's local part (`id_local`) split on `_`, in order.

    With `hyphens=True` a `-` splits too. Case is KEPT (nothing is lowercased), and no
    other character separates."""
    local = id_local(eid)
    if hyphens:
        local = local.replace("-", "_")
    return _keep(local.split("_"), min_len, stop)


# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------

_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")
_NON_ALNUM_UNDERSCORE_RUN = re.compile(r"[^a-z0-9_]+")
_NOT_FILE_SAFE_RUN = re.compile(r"[^A-Za-z0-9_-]+")


def slugify(text: str, *, sep: str = "_") -> str:
    """`text` lowercased, every run of characters outside ASCII `[a-z0-9]` replaced by one
    `sep`, and `sep` stripped from both ends.

    Existing underscores are separators too, so a run like '__' or '-_-' collapses to one
    `sep`. Non-ASCII letters are separators ('café bar' gives 'caf_bar'). The result can
    be empty; callers supply their own fallback."""
    return _NON_ALNUM_RUN.sub(sep, text.lower()).strip(sep)


def slugify_keep_underscores(text: str) -> str:
    """`text` lowercased, every run of characters outside ASCII `[a-z0-9_]` replaced by
    one `_`, and `_` stripped from both ends.

    Unlike `slugify`, existing underscores are kept as they are (never collapsed): 'a__b'
    stays 'a__b', and 'a-_-b' becomes 'a___b'. Non-ASCII letters are replaced."""
    return _NON_ALNUM_UNDERSCORE_RUN.sub("_", text.lower()).strip("_")


def slugify_per_char(text: str) -> str:
    """`text` lowercased, then EACH character that is neither Unicode alphanumeric
    (`str.isalnum`) nor `_` replaced by its own `_`, and `_` stripped from both ends.

    Runs are not collapsed ('a, b' gives 'a__b'), and accented or non-Latin letters and
    digits are kept ('café' stays 'café')."""
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in text.lower()).strip("_")


def file_safe(text: str) -> str:
    """`text` with every run of characters outside ASCII `[A-Za-z0-9_-]` replaced by one
    `_`, and `_` stripped from both ends (a filesystem-safe name segment).

    Case is kept, and `-` survives. The result can be empty."""
    return _NOT_FILE_SAFE_RUN.sub("_", text).strip("_")


# ---------------------------------------------------------------------------
# Entity ids as readable text
# ---------------------------------------------------------------------------

#: The id kinds the display helpers treat as entity ids.
TYPED_ID_KINDS = ("person", "place", "obj", "fact", "event")


def id_local(eid: str) -> str:
    """The id's local part: everything after the FIRST `:` ('person:clara_vale' gives
    'clara_vale'; 'a:b:c' gives 'b:c'); the whole string when there is no `:`."""
    return eid.split(":", 1)[-1]


def humanize_id(eid: str) -> str:
    """`id_local(eid)` with every `_` turned into a space; case kept ('person:clara_vale'
    gives 'clara vale'). `-` and any later `:` are left as they are."""
    return id_local(eid).replace("_", " ")


def humanize_id_title(eid: str) -> str:
    """`humanize_id(eid)` title-cased with `str.title()`, whatever the id's kind
    ('obj:brass_token' gives 'Brass Token')."""
    return humanize_id(eid).title()


def humanize_id_last(eid: str) -> str:
    """The text after the LAST `:` with every `_` turned into a space ('a:b:c_d' gives
    'c d', where `humanize_id` gives 'b:c d'); case kept."""
    return eid.split(":")[-1].replace("_", " ")


def human_name(eid: str) -> str:
    """`humanize_id(eid)`, title-cased only for a `person:` id: a person's slug is a
    proper name ('person:clara_vale' gives 'Clara Vale'), while objects and places stay
    lowercase so prose reads naturally ('obj:brass_token' gives 'brass token')."""
    local = humanize_id(eid)
    return local.title() if str(eid).startswith("person:") else local


def is_typed_id(s: str) -> bool:
    """True when `s` has a `:` and its kind prefix (before the first `:`) is one of
    `TYPED_ID_KINDS`."""
    return ":" in s and s.split(":", 1)[0] in TYPED_ID_KINDS


def humanize_typed_id(s: str) -> str:
    """`humanize_id(s)` for a typed id (`is_typed_id`), else `s` unchanged. Never
    title-cases."""
    return humanize_id(s) if is_typed_id(s) else s


def human_name_typed_id(s: str) -> str:
    """`human_name(s)` for a typed id (`is_typed_id`), else `s` unchanged. A person's
    name is title-cased."""
    return human_name(s) if is_typed_id(s) else s


# ---------------------------------------------------------------------------
# Display-name readers (duck-typed `reads`: anything with `.state(entity, attribute)`)
# ---------------------------------------------------------------------------

def read_str(reads: Any, entity: str, attribute: str = "name") -> str:
    """`reads.state(entity, attribute)` when it is a string, else ''. A read that raises
    gives '' too."""
    try:
        v = reads.state(entity, attribute)
    except Exception:  # noqa: BLE001 — an unreadable value reads as absent
        return ""
    return v if isinstance(v, str) else ""


def name_or_humanized_id(reads: Any, eid: str) -> str:
    """The entity's `name` when it is a non-empty string, else `humanize_id(eid)`. A read
    that raises, or a name that is not a string, falls back to the humanized id."""
    try:
        v = reads.state(eid, "name")
    except Exception:  # noqa: BLE001
        v = None
    return v if isinstance(v, str) and v else humanize_id(eid)


def name_text_or_humanized_id(reads: Any, eid: str) -> str:
    """`str()` of the entity's `name` when it is truthy, else `humanize_id(eid)`.

    Unlike `name_or_humanized_id`, a truthy name that is not a string (a number, say) is
    shown as its `str()` instead of falling back. A read that raises falls back."""
    try:
        nm = str(reads.state(eid, "name") or "")
    except Exception:  # noqa: BLE001
        nm = ""
    return nm or humanize_id(eid)


def table_or_read_name(table: Any, reads: Any, eid: str) -> str:
    """The `name` from a snapshot `table` (`{(entity, attribute): value}`) when it is a
    string, else a live `reads.state(eid, "name")` when that is a string, else ''.

    An empty string in the table counts as a name (the live read is skipped). A live read
    that raises gives ''."""
    v = table.get((eid, "name"))
    if not isinstance(v, str):
        try:
            v = reads.state(eid, "name")
        except Exception:  # noqa: BLE001
            v = None
    return v if isinstance(v, str) else ""


def table_or_read_name_or_human(table: Any, reads: Any, eid: str) -> str:
    """`str()` of the first TRUTHY of: the `name` in the snapshot `table`, the live
    `reads.state(eid, "name")`, and `human_name(eid)`.

    Unlike `table_or_read_name`, truthiness decides (an empty table name falls through to
    the live read, and a truthy non-string is shown as its `str()`), and the last resort
    is the humanized id, never ''. A live read that raises falls through."""
    nm = table.get((eid, "name"))
    if not nm:
        try:
            nm = reads.state(eid, "name")
        except Exception:  # noqa: BLE001
            nm = None
    return str(nm or human_name(eid))
