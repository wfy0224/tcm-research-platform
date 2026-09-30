"""Bounded spelling candidates; never a medical synonym or identity resolver."""

import unicodedata
from itertools import product

QUERY_POLICY = "explicit-orthography/v1"

# Deliberately finite, reviewable groups. The first glyph is a matching key only.
# Many-to-one simplifications (發/髮/发, 後/后, 臟/髒/脏, etc.) are excluded.
# New groups require a new policy version. Source text and stored FTS stay intact.
GLYPH_GROUPS = (
    "医醫", "证證", "汤湯", "药藥", "阴陰", "阳陽", "气氣", "脉脈",
    "伤傷", "论論", "经經", "络絡", "营營", "卫衛", "风風",
    "湿濕", "热熱", "虚虛", "实實", "补補", "泻瀉", "温溫", "凉涼",
    "恶惡", "头頭", "项項", "颈頸", "胁脅", "满滿", "呕嘔", "剂劑",
    "归歸", "黄黃", "连連", "芦蘆", "龙龍",
    "两兩", "钱錢", "饮飲", "盐鹽", "检檢", "词詞", "别別",
    "规規", "见見", "说說", "数數", "迟遲", "涩澀", "紧緊",
    "细細", "长長", "独獨", "关關", "门門",
    "学學", "书書", "节節", "与與", "内內",
    "读讀", "问問", "闻聞", "变變", "异異", "泽澤", "麦麥", "齿齒", "较較",
    "群羣", "峰峯",
)
GLYPH_FROM = "".join(group[1:] for group in GLYPH_GROUPS)
GLYPH_TO = "".join(group[0] * (len(group) - 1) for group in GLYPH_GROUPS)
_KEYS = str.maketrans(GLYPH_FROM, GLYPH_TO)
_ALTERNATIVES = {glyph: group for group in GLYPH_GROUPS for glyph in group}


def spelling_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower().translate(_KEYS)


def spelling_sql(expression: str) -> str:
    """Expression is internal SQL, never user text; glyph data are bound parameters."""
    return f"translate(lower(normalize({expression}, NFKC)), :glyph_from, :glyph_to)"


def spelling_params(query: str) -> dict:
    return {"query_key": spelling_key(query), "glyph_from": GLYPH_FROM, "glyph_to": GLYPH_TO}


def expanded_fts_query(tokens: list[str]) -> str:
    """AND original tokens, OR spellings of each char/bigram; no phrase explosion.

    Existing indexes store Han chars/bigrams and Latin alphanumerics. A two-glyph
    token has at most four alternatives with this policy. Mixed spelling works
    without changing a frozen chunk's search vector or vector embedding.
    """
    groups = []
    for token in dict.fromkeys(tokens):
        if not token or not all(
            "\u3400" <= char <= "\u9fff" or char.isascii() and char.isalnum()
            for char in token
        ):
            raise ValueError("FTS candidate token is outside the tokenizer alphabet")
        variants = ([token] if len(token) > 2 else sorted({
            "".join(chars) for chars in product(*(_ALTERNATIVES.get(c, c) for c in token))
        }))
        groups.append("(" + " | ".join(f"'{value}'" for value in variants) + ")")
    return " & ".join(groups)


def query_metadata(query: str) -> dict:
    normalized = unicodedata.normalize("NFKC", query).strip()
    return {"policy": QUERY_POLICY, "normalized_query": normalized,
            "spelling_key": spelling_key(normalized), "alias_policy": "published-own-terms"}
