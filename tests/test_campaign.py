from decimal import Decimal as D

import pytest

from arcelikSalesHelper.domain.campaign import (
    CampaignLine,
    calibrate,
    solve_campaign_prices,
    verify_campaign_prices,
)
from arcelikSalesHelper.domain.models import CampaignProfile


def test_calibrate_measures_percentage_discount() -> None:
    profile = calibrate(lambda price: price * D("0.10"), D(100), D(200))

    assert profile.rate == D("0.10")
    assert profile.fixed_amount == D("0")


def test_solve_scales_only_editable_lines_in_net_space() -> None:
    lines = (
        CampaignLine("editable", D(100), CampaignProfile(D("0.10"))),
        CampaignLine(
            "fixed",
            D(200),
            CampaignProfile(D(0), D(20), editable=False),
        ),
    )

    prices = solve_campaign_prices(lines, D(280))

    assert prices[0].line_id == "editable"
    assert abs(prices[0].net - D(100)) < D("0.0001")
    assert prices[0].price == D("111.11")


def test_verify_corrects_last_editable_line_and_reports_convergence() -> None:
    lines = (
        CampaignLine("editable", D(100), CampaignProfile(D("0.10"))),
    )
    initial = solve_campaign_prices(lines, D(120))

    result = verify_campaign_prices(
        initial,
        lines,
        D(120),
        lambda prices: prices[0].price * D("0.90"),
    )

    assert result.converged
    assert result.difference == D(0)
    assert result.rounds == 1


def test_calibrate_rejects_equal_points() -> None:
    with pytest.raises(ValueError, match="farklı"):
        calibrate(lambda price: price, D(10), D(10))
