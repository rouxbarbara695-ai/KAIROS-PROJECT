from app.shared.domain.errors import DomainError, ErrorCode

# Statuts HTTP exacts de docs/architecture/api-contract.md. Certains codes
# (RULESET_MISSING, COLLECTOR_UNAVAILABLE, ...) ne sont pas encore atteints
# par une route réelle dans ce lot (moteurs/collecteurs = épics futures) ;
# ce test fige au moins la correspondance code -> statut HTTP du catalogue.
_EXPECTED_STATUS = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.OPPORTUNITY_DUPLICATE: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.RESOURCE_VERSION_CONFLICT: 409,
    ErrorCode.IMMUTABLE_RESOURCE: 409,
    ErrorCode.INVALID_TRANSITION: 409,
    ErrorCode.REFERENCE_UNCONFIRMED: 422,
    ErrorCode.GATE_FAILED: 422,
    ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES: 422,
    ErrorCode.FX_RATE_UNAVAILABLE: 503,
    ErrorCode.COLLECTOR_NOT_AUTHORIZED: 403,
    ErrorCode.COLLECTOR_UNAVAILABLE: 503,
    ErrorCode.RULESET_MISSING: 500,
}


def test_every_error_code_has_expected_http_status() -> None:
    assert set(_EXPECTED_STATUS) == set(ErrorCode)
    for code, expected_status in _EXPECTED_STATUS.items():
        assert DomainError(code, "message").http_status == expected_status


def test_domain_error_carries_field_and_details() -> None:
    error = DomainError(
        ErrorCode.VALIDATION_ERROR,
        "message",
        field="price.amount",
        details={"eligible": 1},
    )
    assert error.field == "price.amount"
    assert error.details == {"eligible": 1}
