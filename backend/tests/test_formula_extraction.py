"""Rule tests, including PROPOSED source evidence; none is a medical truth label."""

from pathlib import Path

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


@pytest.mark.parametrize(("filename", "name", "herbs"), [
    ("guizhi_tang.txt", "桂枝湯", ("桂枝", "芍藥", "甘草", "生薑", "大棗")),
    ("guizhi_jia_ge_gen_tang.txt", "桂枝加葛根湯",
     ("葛根", "麻黄", "芍藥", "生薑", "甘草", "大棗", "桂枝")),
    ("guizhi_jia_fu_zi_tang.txt", "桂枝加附子湯",
     ("桂枝", "芍藥", "甘草", "生薑", "大棗", "附子")),
])
def test_proposed_archived_formula_preserves_all_literal_fields_and_spans(filename, name, herbs):
    # A successful grammar parse does not qualify or approve the source/labels.
    text = (Path(__file__).parents[1] / "fixtures" / "c02_candidate" / filename).read_text(encoding="utf-8")
    paragraphs = text.split("\n")
    candidate, = scan_formula_candidates(paragraphs)
    assert candidate.original_name == name
    assert tuple(i.original_name for i in candidate.ingredients) == herbs
    method_start = text.index("上", text.index("\n\n") + 2)
    assert candidate.method == text[method_start:].rstrip()
    assert "服" in candidate.method
    values = {"original_name": candidate.original_name, "method": candidate.method}
    for sequence, ingredient in enumerate(candidate.ingredients):
        assert (ingredient.herb_id, ingredient.amount_normalized,
                ingredient.dose_ratio, ingredient.role) == (None,) * 4
        for key in ("original_name", "amount_original", "unit", "processing"):
            if getattr(ingredient, key) is not None:
                values[f"ingredients.{sequence}.{key}"] = getattr(ingredient, key)
    assert {s.field_key for s in candidate.spans} == set(values)
    for key, value in values.items():
        spans = [s for s in candidate.spans if s.field_key == key]
        assert "\n".join(paragraphs[s.segment_index][s.start_offset:s.end_offset] for s in spans) == value


def test_space_delimiters_do_not_confuse_internal_dose_or_processing_whitespace():
    text = "合成空白湯方：桂枝 三兩 （去皮）　芍藥\t三兩　甘草 一斗。上三味，以水煎服。"
    candidate, = scan_formula_candidates([text])
    assert [(i.original_name, i.amount_original, i.processing) for i in candidate.ingredients] == [
        ("桂枝", "三兩", "去皮"), ("芍藥", "三兩", None), ("甘草", "一斗", None),
    ]
    assert candidate.ingredients[-1].unit == "斗"
    for span in candidate.spans:
        if span.field_key.startswith("ingredients."):
            _, number, key = span.field_key.split(".")
            assert text[span.start_offset:span.end_offset] == getattr(candidate.ingredients[int(number)], key)


@pytest.mark.parametrize("ingredients", [
    "桂枝三兩芍藥三兩",  # Adjacent doses without a delimiter cannot be split by guessing.
    "桂枝三兩　芍藥",  # Every herb must carry its own explicit dose.
    "桂枝三兩　芍藥各三兩",  # Shared-dose marker remains ambiguous.
    "桂枝、芍藥 三兩",  # Whitespace cannot cure a shared dose.
    "桂枝三兩　未知藥適量",
    "桂枝三兩　或芍藥三兩",
    "桂枝三兩　芍藥三兩（去皮或生用）",
    "桂枝三兩　芍藥三兩　另加生薑",
    "桂枝三兩　芍藥三兩 以上酌加",  # No trailing unparsed prose may be dropped.
    "桂枝三兩　芍藥三兩　甘草一兩",  # Extra fully parsed herb still fails the declared count.
    "桂枝三兩　桂枝三兩",
    "桂 枝三兩　芍藥三兩",  # Internal herb-name whitespace is not silently normalized.
    "桂枝一斗二升　芍藥三兩",  # Compound dose is outside this narrow grammar.
])
def test_spaced_ingredients_require_full_consumption_and_exact_count(ingredients):
    assert scan_formula_candidates([f"合成空白湯方：{ingredients}。上二味，以水煎服。"]) == []


@pytest.mark.parametrize("method", [
    "右五味，㕮咀三味，以水七升，煎服。",  # Only the actual observed literal prefix is supported.
    "上五味，㕮咀四味，以水七升，煎服。",
    "上五味，㕮咀三味，用水七升，煎服。",
    "上五味，先另加藥，再以水七升，煎服。",
    "上五味，㕮咀三味，以水七升，煮取三升。",  # Administration remains mandatory.
])
def test_unobserved_preparation_prefix_is_rejected(method):
    herbs = "桂枝三兩　芍藥三兩　甘草二兩　生薑三兩　大棗十二枚。"
    assert scan_formula_candidates(["合成預備湯方：" + herbs + method]) == []
