from medfuel.models.schemas import OFFICIAL_RANK, CompanyIdentity, SourceType


def test_canonical_cik_zero_pads_and_strips_non_digits():
    identity = CompanyIdentity(name="Example", cik="0001234567")
    assert identity.canonical_cik() == "0001234567"

    identity2 = CompanyIdentity(name="Example", cik="1234567")
    assert identity2.canonical_cik() == "0001234567"

    identity3 = CompanyIdentity(name="Example", cik="CIK0001234567")
    assert identity3.canonical_cik() == "0001234567"

    identity4 = CompanyIdentity(name="Example")
    assert identity4.canonical_cik() is None


def test_official_rank_orders_regulator_above_company():
    assert OFFICIAL_RANK[SourceType.FDA] < OFFICIAL_RANK[SourceType.COMPANY]
    assert OFFICIAL_RANK[SourceType.SEC] < OFFICIAL_RANK[SourceType.INVESTOR_DECK]
    assert OFFICIAL_RANK[SourceType.PMDA] == OFFICIAL_RANK[SourceType.FDA]
