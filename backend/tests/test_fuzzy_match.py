from app.services.fuzzy_match import MATCH_THRESHOLD, match_score, pick_matches, trigram_similarity


def test_trigram_similarity_identical_is_1():
    assert trigram_similarity("nam nguyen", "nam nguyen") == 1.0


def test_trigram_similarity_unrelated_is_low():
    assert trigram_similarity("nam nguyen", "ha tran") < MATCH_THRESHOLD


def test_match_score_exact_after_normalize_is_1():
    assert match_score("duy pham", "Duy Phạm") == 1.0


def test_match_score_whole_word_first_name_is_high_tier():
    assert match_score("Duy", "Duy Phạm") >= 0.9


def test_match_score_unrelated_name_is_low():
    assert match_score("Duy", "Hà Trần") < 0.9


def test_pick_matches_returns_single_tier_a_ignoring_weak_trigram_noise():
    scored = [
        ("duy_pham", match_score("Duy", "Duy Phạm")),
        ("ha_tran", match_score("Duy", "Hà Trần")),
    ]
    picked = pick_matches(scored)
    assert [item for item, _ in picked] == ["duy_pham"]


def test_pick_matches_returns_both_when_tier_a_ties():
    scored = [
        ("nam_nguyen", match_score("Nam", "Nam Nguyễn")),
        ("nam_tran", match_score("Nam", "Nam Trần")),
    ]
    picked = pick_matches(scored)
    assert {item for item, _ in picked} == {"nam_nguyen", "nam_tran"}


def test_pick_matches_empty_when_nothing_clears_threshold():
    scored = [("ha_tran", match_score("xyz123", "Hà Trần"))]
    assert pick_matches(scored) == []
