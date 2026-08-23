from signal_engine.dedup import resolve_hn_text


def test_resolves_unambiguous_exact_mention():
    assert resolve_hn_text("Anthropic acquires Bun") is None  # no entity in our list at all
    assert resolve_hn_text("Cloudflare launches a new edge product") == "NET"


def test_word_boundary_prevents_substring_false_positive():
    # "Elastic" must not match inside an unrelated longer word.
    assert resolve_hn_text("The elasticity of demand for cloud compute") is None
    assert resolve_hn_text("Show HN: an inelastic-collision physics demo") is None


def test_alias_variant_still_resolves_to_canonical_ticker():
    assert resolve_hn_text("Elasticsearch releases a new query planner") == "ESTC"


def test_multiple_aliases_of_same_entity_do_not_double_count_as_ambiguous():
    # "Elastic" and "Elasticsearch" both appearing shouldn't look like two
    # different companies matched.
    assert resolve_hn_text("Elastic ships Elasticsearch 9.0") == "ESTC"


def test_two_distinct_entities_in_one_story_is_dropped_not_guessed():
    assert resolve_hn_text("Okta and Cloudflare partner on zero trust") is None


def test_no_match_returns_none():
    assert resolve_hn_text("A completely unrelated story about gardening") is None
