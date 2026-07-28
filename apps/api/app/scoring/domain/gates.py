from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.shared.rules.ruleset import Ruleset

_GATES = ("gates",)


class GateCode(StrEnum):
    """Identifiants publics stables. Un code n'est jamais recyclé pour un autre
    sens (docs/product/gates.md)."""

    AUTHENTICITY = "G1_AUTHENTICITY"
    IDENTIFICATION = "G2_IDENTIFICATION"
    DATA_QUALITY = "G3_DATA_QUALITY"
    MARKET_SUPPORT = "G4_MARKET_SUPPORT"
    SELLER_RISK = "G5_SELLER_RISK"


class GateStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNING = "passed_with_warning"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


# Portes dont l'échec rend l'analyse impossible, par opposition à celles qui
# concluent à `pass` : l'un signifie « on ne peut pas se prononcer », l'autre
# « on se prononce, et c'est non » (gates.md).
_BLOCKS_ANALYSIS = frozenset(
    {GateCode.IDENTIFICATION, GateCode.DATA_QUALITY, GateCode.MARKET_SUPPORT}
)


@dataclass(frozen=True, slots=True)
class GateResult:
    code: GateCode
    status: GateStatus
    reason_codes: tuple[str, ...] = ()

    @property
    def blocking(self) -> bool:
        return self.status is GateStatus.FAILED


@dataclass(frozen=True, slots=True)
class GateInputs:
    """Ce que les portes observent. Chaque champ est un fait constaté, jamais
    une appréciation : l'arbitrage appartient au ruleset et aux règles."""

    reference_status: str
    identification_confidence: Decimal | None

    has_price: bool
    has_currency: bool
    has_condition: bool
    has_completeness: bool
    has_seller_country: bool

    comparable_count: int
    total_weight: Decimal

    authenticity_signals: tuple[str, ...] = ()
    seller_risk_level: str = "unknown"


@dataclass(frozen=True, slots=True)
class GateReport:
    results: tuple[GateResult, ...] = field(default=())

    @property
    def analysis_possible(self) -> bool:
        return not any(
            result.blocking and result.code in _BLOCKS_ANALYSIS
            for result in self.results
        )

    @property
    def passed(self) -> bool:
        return not any(result.blocking for result in self.results)

    @property
    def failed_codes(self) -> tuple[GateCode, ...]:
        return tuple(result.code for result in self.results if result.blocking)

    def get(self, code: GateCode) -> GateResult | None:
        return next((r for r in self.results if r.code == code), None)


def _authenticity(inputs: GateInputs) -> GateResult:
    if inputs.authenticity_signals:
        return GateResult(
            GateCode.AUTHENTICITY,
            GateStatus.FAILED,
            tuple(inputs.authenticity_signals),
        )
    return GateResult(GateCode.AUTHENTICITY, GateStatus.PASSED)


def _identification(inputs: GateInputs, ruleset: Ruleset) -> GateResult:
    if inputs.reference_status in ("confirmed", "corrected"):
        return GateResult(GateCode.IDENTIFICATION, GateStatus.PASSED)

    minimum = ruleset.decimal(*_GATES, "indicative_identification_min")
    confidence = inputs.identification_confidence

    # Une suggestion suffisamment sûre laisse l'analyse se poursuivre, mais
    # l'avertissement subsiste : la référence n'a pas été confirmée par un
    # humain.
    if (
        inputs.reference_status == "suggested"
        and confidence is not None
        and confidence >= minimum
    ):
        return GateResult(
            GateCode.IDENTIFICATION,
            GateStatus.PASSED_WITH_WARNING,
            ("reference_suggested_not_confirmed",),
        )

    reasons = ["reference_not_confirmed"]
    if confidence is not None and confidence < minimum:
        reasons.append("identification_confidence_below_threshold")
    return GateResult(GateCode.IDENTIFICATION, GateStatus.FAILED, tuple(reasons))


def _data_quality(inputs: GateInputs) -> GateResult:
    missing = [
        code
        for present, code in (
            (inputs.has_price, "price_missing"),
            (inputs.has_currency, "currency_missing"),
            (inputs.has_condition, "condition_missing"),
            (inputs.has_completeness, "completeness_missing"),
            (inputs.has_seller_country, "seller_country_missing"),
        )
        if not present
    ]
    if missing:
        return GateResult(GateCode.DATA_QUALITY, GateStatus.FAILED, tuple(missing))
    return GateResult(GateCode.DATA_QUALITY, GateStatus.PASSED)


def _market_support(inputs: GateInputs, ruleset: Ruleset) -> GateResult:
    minimum = ruleset.integer(*_GATES, "valuation_min_comparables")

    reasons: list[str] = []
    if inputs.comparable_count < minimum:
        reasons.append("insufficient_comparables")
    if inputs.total_weight <= 0:
        reasons.append("total_weight_not_positive")

    if reasons:
        return GateResult(GateCode.MARKET_SUPPORT, GateStatus.FAILED, tuple(reasons))
    return GateResult(GateCode.MARKET_SUPPORT, GateStatus.PASSED)


def _seller_risk(inputs: GateInputs) -> GateResult:
    if inputs.seller_risk_level == "high":
        return GateResult(
            GateCode.SELLER_RISK, GateStatus.FAILED, ("seller_risk_high",)
        )
    if inputs.seller_risk_level in ("medium", "unknown"):
        # Un risque moyen n'interdit pas d'acheter, mais il est signalé et
        # peut plafonner le verdict selon le ruleset (gates.md).
        return GateResult(
            GateCode.SELLER_RISK,
            GateStatus.PASSED_WITH_WARNING,
            (f"seller_risk_{inputs.seller_risk_level}",),
        )
    return GateResult(GateCode.SELLER_RISK, GateStatus.PASSED)


def evaluate_gates(inputs: GateInputs, ruleset: Ruleset) -> GateReport:
    """Évalue les cinq portes dans l'ordre.

    Toutes sont évaluées même après un échec : `not_evaluated` est réservé aux
    portes qu'on ne peut pas juger, pas à celles qu'on renonce à regarder. Un
    échec déjà connu doit rester visible, et masquer les suivants priverait
    l'utilisateur de la liste complète de ce qu'il a à corriger (gates.md).
    """

    return GateReport(
        results=(
            _authenticity(inputs),
            _identification(inputs, ruleset),
            _data_quality(inputs),
            _market_support(inputs, ruleset),
            _seller_risk(inputs),
        )
    )
