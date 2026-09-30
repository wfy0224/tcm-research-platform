"""Synthetic grammar tests; these texts are not a real corpus or dose standard."""

import pytest

from tcm_platform.knowledge_formula_extraction import scan_formula_candidates


def test_full_block_preserves_unicode_raw_doses_processing_and_all_spans():
    paragraphs = ["😀合成说明。\n合成測試湯方：", "桂枝三兩（去皮）；芍藥三兩半。",
                  "右二味，以水七升，煮取三升。", "分溫再服。禁忌原文待考。"]
    candidate, = scan_formula_candidates(paragraphs)
    assert candidate.original_name == "合成測試湯"
    assert candidate.segment_indices == (0, 1, 2, 3)
    assert candidate.method == "\n".join(paragraphs[2:])
    first, second = candidate.ingredients
    assert (first.original_name, first.amount_original, first.unit, first.processing) == (
        "桂枝", "三兩", "兩", "去皮",
    )
    assert second.amount_original == "三兩半" and second.processing is None
    for ingredient in candidate.ingredients:
        assert (ingredient.herb_id, ingredient.amount_normalized, ingredient.dose_ratio,
                ingredient.role) == (None,) * 4
    values = {"original_name": candidate.original_name, "method": candidate.method}
    for i, ingredient in enumerate(candidate.ingredients):
        for key in ("original_name", "amount_original", "unit", "processing"):
            if getattr(ingredient, key) is not None:
                values[f"ingredients.{i}.{key}"] = getattr(ingredient, key)
    assert {s.field_key for s in candidate.spans} == set(values)
    for span in candidate.spans:
        quote = paragraphs[span.segment_index][span.start_offset:span.end_offset]
        assert quote == values[span.field_key] or (span.field_key == "method" and span.basis)


@pytest.mark.parametrize("text", [
    "桂枝湯主之。",  # A name mention cannot supply missing ingredients.
    "桂枝湯：桂枝三兩；芍藥三兩。右二味，以水七升，煎服。",  # No explicit 方 heading.
    "桂枝湯方：桂枝；芍藥三兩。右二味，以水七升，煎服。",
    "桂枝湯方：桂枝三兩；芍藥三兩。右三味，以水七升，煎服。",
    "桂枝湯方：桂枝、芍藥各三兩。右二味，以水七升，煎服。",
    "桂枝湯方：桂枝三兩，去皮；芍藥三兩。右二味，以水七升，煎服。",
    "桂枝湯方：桂枝三兩；未知藥適量。右二味，以水七升，煎服。",
    "桂枝湯方：桂枝三兩；芍藥三兩。以水七升，煎服。",  # Missing count.
    "桂枝湯方：桂枝三兩；芍藥三兩。右二味，以水七升，煮取三升。",  # No administration.
    "桂枝湯方：桂枝三兩；芍藥三兩。右二味，含糊方法，服之。",
    "桂枝湯方：桂枝三兩；芍藥三兩；另加生薑。右二味，以水七升，煎服。",
    "桂枝湯方：桂枝三兩；桂枝三兩。右二味，以水七升，煎服。",
    "桂枝湯方：桂枝或芍藥三兩。右一味，以水七升，煎服。",
    "桂枝湯方：桂枝三兩（去皮或生用）。右一味，以水七升，煎服。",
    "若用桂枝湯方：桂枝三兩。右一味，以水七升，煎服。",
    "不可用桂枝湯方：桂枝三兩。右一味，以水七升，煎服。",
    "或服桂枝湯方：桂枝三兩。右一味，以水七升，煎服。",
    "桂枝湯方：桂枝零兩。右一味，以水七升，煎服。",
    "桂枝湯方：桂枝三三兩。右一味，以水七升，煎服。",
    "桂枝湯方：桂枝一0兩。右一味，以水七升，煎服。",
    "桂枝湯方：桂枝三兩。右一味，以水七升，煎服。右一味，以水七升，煎服。",
])
def test_unclear_or_incomplete_block_is_rejected_whole(text):
    assert scan_formula_candidates([text]) == []


def test_two_formula_blocks_keep_distinct_identity_and_support_arabic_count():
    text = "合成甲散方：桂枝二分。上1味，用水煎服。\n合成乙丸方：芍藥三錢。右一味，以水煎服。"
    candidates = scan_formula_candidates([text])
    assert [c.original_name for c in candidates] == ["合成甲散", "合成乙丸"]
    assert [c.method for c in candidates] == ["上1味，用水煎服。", "右一味，以水煎服。"]
    assert [c.ingredients[0].unit for c in candidates] == ["分", "錢"]


def test_no_partial_formula_when_later_block_is_incomplete():
    paragraphs = ["合成甲湯方：桂枝三兩。右一味，以水煎服。", "合成乙湯方：芍藥。"]
    candidates = scan_formula_candidates(paragraphs)
    assert len(candidates) == 1 and candidates[0].method == "右一味，以水煎服。"
