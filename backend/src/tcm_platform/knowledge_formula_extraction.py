"""Narrow local formula grammar; reject an incomplete block instead of dropping a herb.

This is an engineering rule, not a historical collation or dose normalization.
Input paragraphs must be contiguous citable siblings from one frozen source.
"""

import re
from dataclasses import dataclass

from tcm_platform.knowledge_service import IngredientSpec

_NUMBER = r"[一二三四五六七八九十百兩两〇零0-9]+"
_DOSE_NUMBER = r"(?:[1-9][0-9]*|一?百|[一二三四五六七八九]?十[一二三四五六七八九]?|[一二三四五六七八九兩两])"
_UNIT = r"兩|两|錢|钱|分|升|合|枚|斤|銖|铢|斗"
_HEADING = re.compile(r"(?m)^[ \t]*(?P<name>[\u3400-\u9fff]{1,40}(?:湯|汤|散|丸|飲|饮|方))方[：:]?[ \t]*")
_TAIL = re.compile(r"(?:右|上)(?P<count>" + _NUMBER + r")味[，,。]")
_INGREDIENT = re.compile(
    r"(?P<name>[\u3400-\u9fff]{1,20}?)\s*"
    r"(?P<amount>" + _DOSE_NUMBER + r"(?P<unit>" + _UNIT + r")(?:半)?)"
    r"(?:\s*(?:（(?P<full_processing>[^（）\n]+)）|\((?P<processing>[^()\n]+)\)))?"
)


@dataclass(frozen=True)
class FormulaSpan:
    field_key: str
    segment_index: int
    start_offset: int
    end_offset: int
    basis: str | None = None


@dataclass(frozen=True)
class FormulaCandidate:
    original_name: str
    ingredients: tuple[IngredientSpec, ...]
    method: str
    spans: tuple[FormulaSpan, ...]
    segment_indices: tuple[int, ...]


def _count(value: str) -> int | None:
    if value.isascii() and value.isdigit():
        return int(value)
    digits = {char: i for i, char in enumerate("〇一二三四五六七八九")}
    digits.update({"兩": 2, "两": 2, "零": 0})
    if value in digits:
        return digits[value]
    if value == "百":
        return 100
    if value.count("十") == 1:
        left, right = value.split("十")
        if (not left or left in digits) and (not right or right in digits):
            return digits.get(left, 1) * 10 + digits.get(right, 0)
    return None


def scan_formula_candidates(paragraphs: list[str]) -> list[FormulaCandidate]:
    """Accept explicit NAME方 blocks with fully parsed doses, count, and administration.

    Parenthetical processing is copied literally. Shared doses, substitutions,
    unparsed prose, missing doses/counts, and name mentions yield no full formula.
    No seed herb vocabulary, inferred modern units, ratios, roles, or aliases.
    """
    original = "\n".join(paragraphs)
    starts = []
    offset = 0
    for paragraph in paragraphs:
        starts.append(offset)
        offset += len(paragraph) + 1

    def spans_for(key, start, end):
        pieces = []
        for index, (base, paragraph) in enumerate(zip(starts, paragraphs, strict=True)):
            lower, upper = max(start, base), min(end, base + len(paragraph))
            if lower < upper:
                pieces.append(FormulaSpan(key, index, lower - base, upper - base))
        if len(pieces) > 1:
            # The copied method uses the same newline between frozen paragraphs.
            pieces = [FormulaSpan(p.field_key, p.segment_index, p.start_offset, p.end_offset,
                                  "按原片段顺序以换行连接完整煎服原文，未换算或改写") for p in pieces]
        return pieces

    headings = list(_HEADING.finditer(original))
    result = []
    for index, heading in enumerate(headings):
        if re.search(r"若|或|如|宜|用|服|主之|不可|禁忌", heading["name"]):
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(original)
        tails = list(_TAIL.finditer(original, heading.end(), end))
        if len(tails) != 1:
            continue
        tail = tails[0]
        count = _count(tail["count"])
        if count is None or not 1 <= count <= 100:
            continue
        method_end = end
        while method_end > tail.end() and original[method_end - 1].isspace():
            method_end -= 1
        # Only a clear water preparation prefix with explicit administration is accepted.
        instructions = original[tail.end():method_end].lstrip()
        # The only additional preparation prefix is copied from the archived
        # PROPOSED C02 block. Do not infer other chopping/preparation prose.
        observed_preparation = tail.group() == "上五味，" and instructions.startswith("㕮咀三味，以水")
        if not (instructions.startswith(("以水", "用水", "水煎")) or observed_preparation) or "服" not in instructions:
            continue
        ingredients, field_spans = [], spans_for("original_name", *heading.span("name"))
        valid = True
        for item in re.finditer(r"[^；;、\n]+", original[heading.end():tail.start()]):
            start = heading.end() + item.start()
            content = item.group()
            stripped = content.strip(" \t\r\u3000。．.")
            if not stripped:
                continue
            start += len(content) - len(content.lstrip(" \t\r\u3000。．."))
            cursor = 0
            while cursor < len(stripped):
                # Match a complete herb/dose first; whitespace before its dose
                # belongs to that herb. Only then may space delimit another herb.
                match = _INGREDIENT.match(stripped, cursor)
                if match is None or re.search(_NUMBER, match["name"]) or re.search(
                    r"[或若各及另缺待加減减去取共等用不無无]", match["name"]
                ):
                    valid = False
                    break
                sequence = len(ingredients)
                processing_group = "full_processing" if match["full_processing"] else "processing"
                if match[processing_group] and re.search(r"或|若|酌|適量|适量|加減|加减", match[processing_group]):
                    valid = False
                    break
                ingredients.append(IngredientSpec(
                    original_name=match["name"], amount_original=match["amount"],
                    unit=match["unit"], processing=match[processing_group],
                ))
                for field, group in (("original_name", "name"), ("amount_original", "amount"),
                                     ("unit", "unit"), ("processing", processing_group)):
                    if match[group] is not None:
                        a, b = match.span(group)
                        field_spans.extend(spans_for(f"ingredients.{sequence}.{field}", start + a, start + b))
                cursor = match.end()
                if cursor < len(stripped):
                    separator = re.match(r"[ \t\r\u3000]+", stripped[cursor:])
                    if separator is None:
                        valid = False
                        break
                    cursor += separator.end()
            if not valid:
                break
        if not valid or len(ingredients) != count or len({i.original_name for i in ingredients}) != count:
            continue
        field_spans.extend(spans_for("method", tail.start(), method_end))
        indices = tuple(range(min(s.segment_index for s in field_spans),
                              max(s.segment_index for s in field_spans) + 1))
        if len(indices) > 100:
            continue
        result.append(FormulaCandidate(heading["name"], tuple(ingredients),
                                       original[tail.start():method_end], tuple(field_spans), indices))
    return result
