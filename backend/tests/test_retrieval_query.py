import pytest

from tcm_platform.retrieval import tokenize
from tcm_platform.retrieval_query import expanded_fts_query, spelling_key


def test_spelling_candidates_keep_unknowns_and_ambiguous_simplifications():
    assert spelling_key("醫药脈羣峯 ＡＢＣ") == "医药脉群峰 abc"
    for left, right in (("發", "发"), ("髮", "发"), ("後", "后"),
                        ("臟", "脏"), ("朮", "术"), ("參", "参"), ("範", "范")):
        assert spelling_key(left) != spelling_key(right)
    assert spelling_key("𠮷罕见词") == "𠮷罕见词"


def test_fts_candidates_are_linear_and_preserve_latin_token_boundaries():
    expression = expanded_fts_query(tokenize("醫脈ABC").split())
    assert "'abc'" in expression and "'醫脉'" in expression and "'医脈'" in expression
    assert len(expanded_fts_query(tokenize("醫脈" * 1000).split())) < 200
    with pytest.raises(ValueError, match="alphabet"):
        expanded_fts_query(["x') | TRUE"])
