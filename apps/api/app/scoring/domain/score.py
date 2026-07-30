from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.scoring.domain.curves import curve, interpolate
from app.scoring.domain.gates import GateCode, GateReport, GateStatus
from app.shared.domain.errors import DomainError
from app.shared.rules.ruleset import Ruleset

_SUBSCORE = Decimal("0.0001")
_EXPOSED = Decimal("0.01")

_WEIGHTS = ("scoring", "pillar_weights")
_CAPS = ("scoring", "caps")
_CONDITION_SCORES = ("scoring", "condition_scores")
_EVIDENCE_SCORES = ("scoring", "evidence_scores")


class Verdict(StrEnum):
    BUY = "buy"
    WATCH = "watch"
    PASS = "pass"
    ANALYSIS_IMPOSSIBLE = "analysis_impossible"


# Ordre de prudence : en cas de règles concurrentes, le verdict le plus prudent
# l'emporte (scoring-engine.md § 3). L'index bas gagne.
_PRECEDENCE = (
    Verdict.PASS,
    Verdict.ANALYSIS_IMPOSSIBLE,
    Verdict.WATCH,
    Verdict.BUY,
)


def most_cautious(*verdicts: Verdict) -> Verdict:
    return min(verdicts, key=_PRECEDENCE.index)


@dataclass(frozen=True, slots=True)
class AppliedCap:
    name: str
    value: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    """Entrées du score, toutes déjà calculées en amont.

    Le moteur n'interroge rien : portes, valorisation et pricing ont déjà
    tranché. Il ne fait qu'appliquer un barème à des faits établis.
    """

    central_profit_eur: Decimal
    central_roi: Decimal | None

    sale_delay_days: int
    active_comparable_depth: int
    dispersion_subscore: Decimal

    allocation_rate: Decimal
    brand_concentration_rate: Decimal
    capital_immobilization_rate: Decimal
    maximum_allocation_rate: Decimal

    mechanical: str
    cosmetic: str
    completeness: str
    originality: str

    listing_quality_score: Decimal
    valuation_confidence: Decimal
    seller_reliability: str
    transaction_protections: str


@dataclass(frozen=True, slots=True)
class ScoreResult:
    raw_score: Decimal
    final_score: Decimal
    verdict: Verdict
    profitability: Decimal
    liquidity: Decimal
    portfolio: Decimal
    condition: Decimal
    evidence_quality: Decimal
    subscores: dict[str, Decimal]
    applied_caps: tuple[AppliedCap, ...]
    blocking_conditions: tuple[str, ...]
    ruleset_version: str


def _weighted(parts: list[tuple[Decimal, Decimal]]) -> Decimal:
    total = sum((score * weight for score, weight in parts), Decimal("0"))
    return total.quantize(_SUBSCORE, rounding=ROUND_HALF_UP)


def compute_score(
    inputs: ScoreInputs, gates: GateReport, ruleset: Ruleset
) -> ScoreResult:
    """Score sur cinq piliers, plafonds cumulatifs et verdict.

    Le score n'est calculé qu'après les portes : une porte bloquante rend
    l'analyse impossible ou justifie un refus, et aucune note ne doit pouvoir
    le contredire (scoring-engine.md § en-tête).
    """

    if not gates.analysis_possible:
        return _impossible(gates, ruleset)

    subscores: dict[str, Decimal] = {}
    caps: list[AppliedCap] = []
    blocking: list[str] = []

    # --- Rentabilité ---
    profit_score = interpolate(curve(ruleset, "profit_eur"), inputs.central_profit_eur)
    roi_score = (
        interpolate(curve(ruleset, "roi"), inputs.central_roi)
        if inputs.central_roi is not None
        else Decimal("0")
    )
    subscores["profit"] = profit_score
    subscores["roi"] = roi_score

    profitability = _weighted(
        [
            (
                profit_score,
                ruleset.decimal("scoring", "profitability_subweights", "profit"),
            ),
            (roi_score, ruleset.decimal("scoring", "profitability_subweights", "roi")),
        ]
    )

    # Un profit central négatif ne se compense pas : la rentabilité tombe à
    # zéro et le verdict est `pass`, quelle que soit la qualité du reste.
    negative_profit = inputs.central_profit_eur < 0
    if negative_profit:
        profitability = Decimal("0")
        blocking.append("central_profit_negative")

    # --- Liquidité ---
    delay_score = interpolate(
        curve(ruleset, "delay_days"), Decimal(inputs.sale_delay_days)
    )
    depth_score = interpolate(
        curve(ruleset, "depth"), Decimal(inputs.active_comparable_depth)
    )
    subscores["delay"] = delay_score
    subscores["depth"] = depth_score
    subscores["consistency"] = inputs.dispersion_subscore

    liquidity = _weighted(
        [
            (delay_score, ruleset.decimal("scoring", "liquidity_subweights", "delay")),
            (depth_score, ruleset.decimal("scoring", "liquidity_subweights", "depth")),
            (
                inputs.dispersion_subscore,
                ruleset.decimal("scoring", "liquidity_subweights", "consistency"),
            ),
        ]
    )

    # --- Capital et portefeuille ---
    cash_score = interpolate(curve(ruleset, "cash_impact"), inputs.allocation_rate)
    diversification_score = interpolate(
        curve(ruleset, "brand_concentration"), inputs.brand_concentration_rate
    )
    immobilization_score = interpolate(
        curve(ruleset, "capital_immobilization"), inputs.capital_immobilization_rate
    )

    # Règle 1 : une liquidité faible plafonne la diversification *avant* le
    # calcul du pilier, pas après — un portefeuille bien réparti mais illiquide
    # ne doit pas paraître sain.
    illiquid = ruleset.mapping("scoring", "illiquid_diversification_cap")
    if liquidity < Decimal(str(illiquid["liquidity_below"])):
        capped = Decimal(str(illiquid["cap"]))
        if diversification_score > capped:
            diversification_score = capped
            caps.append(
                AppliedCap(
                    "illiquid_diversification",
                    capped,
                    "Liquidité faible : diversification plafonnée avant calcul.",
                )
            )

    subscores["cash_impact"] = cash_score
    subscores["diversification"] = diversification_score
    subscores["immobilization"] = immobilization_score

    portfolio = _weighted(
        [
            (
                cash_score,
                ruleset.decimal("scoring", "portfolio_subweights", "cash_impact"),
            ),
            (
                diversification_score,
                ruleset.decimal("scoring", "portfolio_subweights", "diversification"),
            ),
            (
                immobilization_score,
                ruleset.decimal("scoring", "portfolio_subweights", "immobilization"),
            ),
        ]
    )

    # --- État ---
    for dimension, value in (
        ("mechanical", inputs.mechanical),
        ("cosmetic", inputs.cosmetic),
        ("completeness", inputs.completeness),
        ("originality", inputs.originality),
    ):
        subscores[dimension] = ruleset.decimal(*_CONDITION_SCORES, dimension, value)

    condition = _weighted(
        [
            (
                subscores[dimension],
                ruleset.decimal("scoring", "condition_subweights", dimension),
            )
            for dimension in ("mechanical", "cosmetic", "completeness", "originality")
        ]
    )

    # --- Qualité des preuves ---
    subscores["listing"] = inputs.listing_quality_score
    subscores["comparables"] = inputs.valuation_confidence
    subscores["seller"] = ruleset.decimal(
        *_EVIDENCE_SCORES, "seller", inputs.seller_reliability
    )
    subscores["protections"] = ruleset.decimal(
        *_EVIDENCE_SCORES, "protections", inputs.transaction_protections
    )

    evidence_quality = _weighted(
        [
            (
                subscores[key],
                ruleset.decimal("scoring", "evidence_subweights", key),
            )
            for key in ("listing", "comparables", "seller", "protections")
        ]
    )

    # --- Score brut, sans arrondi intermédiaire ---
    raw = (
        profitability * ruleset.decimal(*_WEIGHTS, "profitability")
        + liquidity * ruleset.decimal(*_WEIGHTS, "liquidity")
        + portfolio * ruleset.decimal(*_WEIGHTS, "portfolio")
        + condition * ruleset.decimal(*_WEIGHTS, "condition")
        + evidence_quality * ruleset.decimal(*_WEIGHTS, "evidence_quality")
    )

    caps.extend(_score_caps(inputs, evidence_quality, liquidity, ruleset))

    final = raw
    for cap in caps:
        if cap.name == "illiquid_diversification":
            continue  # déjà appliqué au sous-score
        final = min(final, cap.value)

    verdict, verdict_blocking = _decide(
        inputs=inputs,
        gates=gates,
        final_score=final,
        evidence_quality=evidence_quality,
        negative_profit=negative_profit,
        ruleset=ruleset,
    )
    blocking.extend(verdict_blocking)

    return ScoreResult(
        raw_score=raw.quantize(_EXPOSED, rounding=ROUND_HALF_UP),
        final_score=final.quantize(_EXPOSED, rounding=ROUND_HALF_UP),
        verdict=verdict,
        profitability=profitability,
        liquidity=liquidity,
        portfolio=portfolio,
        condition=condition,
        evidence_quality=evidence_quality,
        subscores=subscores,
        applied_caps=tuple(caps),
        blocking_conditions=tuple(dict.fromkeys(blocking)),
        ruleset_version=ruleset.version,
    )


def _score_caps(
    inputs: ScoreInputs,
    evidence_quality: Decimal,
    liquidity: Decimal,
    ruleset: Ruleset,
) -> list[AppliedCap]:
    """Plafonds de score, tous conservés. Le plus contraignant l'emporte, mais
    chacun reste visible : savoir *pourquoi* un score est bridé importe autant
    que le score lui-même."""

    caps: list[AppliedCap] = []
    confidence = inputs.valuation_confidence

    if confidence < 40:
        caps.append(
            AppliedCap(
                "valuation_below_40",
                ruleset.decimal(*_CAPS, "valuation_below_40"),
                "Confiance de valorisation inférieure à 40.",
            )
        )
    elif confidence < 60:
        caps.append(
            AppliedCap(
                "valuation_below_60",
                ruleset.decimal(*_CAPS, "valuation_below_60"),
                "Confiance de valorisation inférieure à 60.",
            )
        )

    if evidence_quality < 40:
        caps.append(
            AppliedCap(
                "evidence_below_40",
                ruleset.decimal(*_CAPS, "evidence_below_40"),
                "Qualité des preuves inférieure à 40.",
            )
        )

    if inputs.allocation_rate > inputs.maximum_allocation_rate:
        caps.append(
            AppliedCap(
                "allocation_exceeded",
                ruleset.decimal(*_CAPS, "allocation_exceeded"),
                "Allocation après achat au-delà du maximum de la stratégie.",
            )
        )

    immobilization_threshold = ruleset.decimal("scoring", "immobilization_threshold")
    strict_start = ruleset.decimal("scoring", "strict_allocation", "starts_at")
    if (
        inputs.capital_immobilization_rate >= immobilization_threshold
        and inputs.allocation_rate > strict_start
    ):
        relief = _exceptional_deal_relief(inputs, evidence_quality, liquidity, ruleset)
        caps.append(
            relief
            or AppliedCap(
                "immobilization_and_allocation",
                ruleset.decimal(*_CAPS, "immobilization_and_allocation"),
                "Capital immobilisé et allocation élevée simultanément.",
            )
        )

    return caps


def _exceptional_deal_relief(
    inputs: ScoreInputs,
    evidence_quality: Decimal,
    liquidity: Decimal,
    ruleset: Ruleset,
) -> AppliedCap | None:
    """Dérogation au plafond d'immobilisation pour une affaire exceptionnelle.

    Conditionnée d'abord à la liquidité : le plafond existe parce qu'un capital
    bloqué le reste longtemps, or une pièce qui se revend vite ne prolonge pas
    ce blocage. Une forte marge sur une pièce illiquide aggraverait au
    contraire la situation, d'où le refus de la déclencher sur le seul profit.

    Le plafond est relevé, jamais supprimé : une position immobilisée reste
    tendue. Absente du ruleset, la dérogation n'existe simplement pas — elle ne
    peut donc pas s'activer par défaut sur un barème antérieur (Q-13).
    """

    try:
        rule = ruleset.mapping("scoring", "exceptional_deal_relief")
    except DomainError:
        return None

    conditions = {
        "liquidité": (liquidity, Decimal(str(rule["minimum_liquidity"]))),
        "ROI": (
            inputs.central_roi if inputs.central_roi is not None else Decimal("-1"),
            Decimal(str(rule["minimum_roi"])),
        ),
        "profit": (inputs.central_profit_eur, Decimal(str(rule["minimum_profit_eur"]))),
        "confiance": (
            inputs.valuation_confidence,
            Decimal(str(rule["minimum_valuation_confidence"])),
        ),
        "preuves": (
            evidence_quality,
            Decimal(str(rule["minimum_evidence_quality"])),
        ),
    }

    if any(observed < required for observed, required in conditions.values()):
        return None

    detail = ", ".join(
        f"{name} {observed} ≥ {required}"
        for name, (observed, required) in conditions.items()
    )
    return AppliedCap(
        "immobilization_relieved_exceptional_deal",
        Decimal(str(rule["cap"])),
        f"Dérogation, affaire exceptionnelle : {detail}.",
    )


def _decide(
    *,
    inputs: ScoreInputs,
    gates: GateReport,
    final_score: Decimal,
    evidence_quality: Decimal,
    negative_profit: bool,
    ruleset: Ruleset,
) -> tuple[Verdict, list[str]]:
    blocking: list[str] = []

    buy_threshold = ruleset.decimal("verdict", "buy_score")
    watch_threshold = ruleset.decimal("verdict", "watch_score")
    minimum_confidence = ruleset.decimal(
        "verdict", "minimum_valuation_confidence_for_buy"
    )

    # Seuils comparés sur la valeur non arrondie (scoring-engine.md § 4).
    if final_score >= buy_threshold:
        verdict = Verdict.BUY
    elif final_score >= watch_threshold:
        verdict = Verdict.WATCH
    else:
        verdict = Verdict.PASS

    if inputs.valuation_confidence < minimum_confidence:
        verdict = most_cautious(verdict, Verdict.WATCH)
        blocking.append("valuation_confidence_below_buy_minimum")

    identification = gates.get(GateCode.IDENTIFICATION)
    if identification and identification.status is GateStatus.PASSED_WITH_WARNING:
        verdict = most_cautious(verdict, Verdict.WATCH)
        blocking.append("identification_only_suggested")

    strict = ruleset.mapping("scoring", "strict_allocation")
    strict_start = Decimal(str(strict["starts_at"]))
    if strict_start < inputs.allocation_rate <= inputs.maximum_allocation_rate and (
        inputs.valuation_confidence
        < Decimal(str(strict["minimum_valuation_confidence"]))
        or evidence_quality < Decimal(str(strict["minimum_evidence_quality"]))
    ):
        verdict = most_cautious(verdict, Verdict.WATCH)
        blocking.append("strict_allocation_requirements_unmet")

    long_delay = ruleset.integer("scoring", "long_delay_days")
    long_delay_allocation = ruleset.decimal("scoring", "long_delay_allocation")
    if (
        inputs.sale_delay_days > long_delay
        and inputs.allocation_rate > long_delay_allocation
    ):
        verdict = most_cautious(verdict, Verdict.PASS)
        blocking.append("long_delay_with_high_allocation")

    if negative_profit:
        verdict = most_cautious(verdict, Verdict.PASS)

    # Une porte non bloquante pour l'analyse mais échouée — authenticité,
    # risque vendeur — justifie l'abandon quoi qu'en dise le score.
    if not gates.passed:
        verdict = most_cautious(verdict, Verdict.PASS)
        blocking.extend(f"gate_failed_{code.value}" for code in gates.failed_codes)

    return verdict, blocking


def _impossible(gates: GateReport, ruleset: Ruleset) -> ScoreResult:
    return ScoreResult(
        raw_score=Decimal("0.00"),
        final_score=Decimal("0.00"),
        verdict=Verdict.ANALYSIS_IMPOSSIBLE,
        profitability=Decimal("0"),
        liquidity=Decimal("0"),
        portfolio=Decimal("0"),
        condition=Decimal("0"),
        evidence_quality=Decimal("0"),
        subscores={},
        applied_caps=(),
        blocking_conditions=tuple(
            f"gate_failed_{code.value}" for code in gates.failed_codes
        ),
        ruleset_version=ruleset.version,
    )
