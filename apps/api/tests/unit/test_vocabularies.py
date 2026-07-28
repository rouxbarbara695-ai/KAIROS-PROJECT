from app.identity.domain import vocabularies as vocab


def test_normalize_recognizes_exact_value() -> None:
    assert (
        vocab.normalize(
            "functional", vocab.MECHANICAL_CONDITIONS, vocab.MECHANICAL_FALLBACK
        )
        == "functional"
    )


def test_normalize_is_case_and_separator_insensitive() -> None:
    assert (
        vocab.normalize("Very Good", vocab.COSMETIC_CONDITIONS, vocab.COSMETIC_FALLBACK)
        == "very_good"
    )
    assert (
        vocab.normalize("very-good", vocab.COSMETIC_CONDITIONS, vocab.COSMETIC_FALLBACK)
        == "very_good"
    )


def test_normalize_absent_mechanical_becomes_unknown_not_defect() -> None:
    # « inconnu » (40 pts) est honnête ; « défaut » (10 pts) affirmerait à
    # tort qu'un défaut a été constaté (calculation-spec.md §6).
    assert (
        vocab.normalize(None, vocab.MECHANICAL_CONDITIONS, vocab.MECHANICAL_FALLBACK)
        == "unknown"
    )


def test_normalize_unrecognized_cosmetic_falls_back_to_worst_not_favorable() -> None:
    # Aucune case « inconnu » pour cosmetic dans le ruleset 1.0.0 : le repli
    # est le niveau le plus prudent, jamais une hypothèse favorable
    # (principles.md #6).
    assert (
        vocab.normalize("mint", vocab.COSMETIC_CONDITIONS, vocab.COSMETIC_FALLBACK)
        == "poor"
    )


def test_completeness_level_full_set() -> None:
    assert vocab.completeness_level(True, True) == "full_set"


def test_completeness_level_partial() -> None:
    assert vocab.completeness_level(True, False) == "box_or_papers"
    assert vocab.completeness_level(False, True) == "box_or_papers"


def test_completeness_level_watch_only() -> None:
    assert vocab.completeness_level(False, False) == "watch_only"


def test_completeness_level_absent_falls_back() -> None:
    assert vocab.completeness_level(None, None) == vocab.COMPLETENESS_FALLBACK
