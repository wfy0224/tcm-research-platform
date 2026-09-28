from types import SimpleNamespace

from tcm_platform.claim_normalization import _fingerprint


def test_canonical_key_preserves_source_era_and_school_boundaries():
    claim = SimpleNamespace(claim_type="HISTORICAL_FACT", assertion_text="同 一 断 言")
    same_text = SimpleNamespace(claim_type="HISTORICAL_FACT", assertion_text="同 一 断 言")
    han = [{"source_revision_id": "revision-1", "era": "汉", "school": "经方"}]
    ming = [{"source_revision_id": "revision-2", "era": "明", "school": "温补"}]

    assert _fingerprint(claim, han) == _fingerprint(same_text, han)
    assert _fingerprint(claim, han) != _fingerprint(same_text, ming)
    assert _fingerprint(claim, han) != _fingerprint(
        SimpleNamespace(claim_type="THEORETICAL_INFERENCE", assertion_text="同 一 断 言"), han
    )
