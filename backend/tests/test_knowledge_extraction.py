"""Engineering rule coverage; these assertions are not expert clinical labels."""

from tcm_platform.knowledge_extraction import scan_candidates


def test_original_unicode_offsets_longest_terms_and_no_markup_normalization():
    original = "🙂桂枝去芍藥加附子湯，自汗出。桂枝去桂加茯苓白-{朮}-湯。"
    mentions, relations = scan_candidates(original)
    assert [(m.surface_text, m.start_offset) for m in mentions] == [
        ("桂枝去芍藥加附子湯", 1), ("自汗出", 11),
    ]
    assert all(original[m.start_offset:m.end_offset] == m.surface_text for m in mentions)
    assert relations == []


def test_naming_preserves_full_condition_and_does_not_infer_treatment():
    original = "太陽病，發熱，汗出，惡風，脈緩者，名為中風。若酒客病，不可與桂枝湯。"
    mentions, relations = scan_candidates(original)
    assert len(relations) == 1
    relation = relations[0]
    assert relation.relation_type == "NAMED_AS"
    assert original[relation.start_offset:relation.end_offset] == relation.assertion_text
    assert relation.assertion_text == original.split("。", 1)[0] + "。"
    assert original[relation.subject_start:].startswith("太陽病")
    assert original[relation.object_start:].startswith("中風")
    assert any(m.surface_text == "桂枝湯" for m in mentions)


def test_no_alias_inference_no_cross_sentence_subject_and_unknown_terms_remain_unknown():
    mentions, relations = scan_candidates("太陽病。若發汗已，身灼熱者，名曰風溫。太阳病，发热。未知方。")
    assert [m.surface_text for m in mentions] == ["太陽病", "風溫"]
    assert relations == []


def test_repeated_exact_mentions_preserve_each_location():
    mentions, _ = scan_candidates("桂枝湯，桂枝湯。")
    assert [m.start_offset for m in mentions] == [0, 4]


def test_multiple_types_keep_independent_mentions_and_suppress_ambiguous_relation(monkeypatch):
    from tcm_platform import knowledge_extraction

    monkeypatch.setattr(knowledge_extraction, "TERMS", {
        "CONDITION": ("甲病", "乙病"), "PATTERN": ("乙病",),
    })
    mentions, relations = scan_candidates("甲病，名曰乙病。")
    assert [(m.surface_text, m.entity_type, m.start_offset) for m in mentions] == [
        ("甲病", "CONDITION", 0), ("乙病", "CONDITION", 5), ("乙病", "PATTERN", 5),
    ]
    assert relations == []
