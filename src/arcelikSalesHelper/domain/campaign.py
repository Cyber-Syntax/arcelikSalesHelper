from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .arith import ZERO
from .models import CampaignProfile


@dataclass(frozen=True)
class CampaignLine:
    line_id: str
    current_price: Decimal
    profile: CampaignProfile


@dataclass(frozen=True)
class CampaignPrice:
    line_id: str
    net: Decimal
    price: Decimal


@dataclass(frozen=True)
class VerificationResult:
    prices: tuple[CampaignPrice, ...]
    actual_total: Decimal
    target: Decimal
    difference: Decimal
    rounds: int
    converged: bool


def _round_price(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(60, len(value.as_tuple().digits) + max(value.adjusted(), 0) + 3)
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calibrate(
    price_fn: Callable[[Decimal], Decimal],
    p1: Decimal,
    p2: Decimal,
) -> CampaignProfile:
    if p1 == p2:
        raise ValueError("Kalibrasyon fiyatları birbirinden farklı olmalıdır")
    if p1 < ZERO or p2 < ZERO:
        raise ValueError("Kalibrasyon fiyatları negatif olamaz")
    d1, d2 = price_fn(p1), price_fn(p2)
    rate = (d2 - d1) / (p2 - p1)
    fixed_amount = d1 - rate * p1
    return CampaignProfile(rate=rate, fixed_amount=fixed_amount)


def net_amount(price: Decimal, profile: CampaignProfile) -> Decimal:
    return price * (Decimal(1) - profile.rate) - profile.fixed_amount


def solve_campaign_prices(
    lines: Sequence[CampaignLine],
    target: Decimal,
) -> tuple[CampaignPrice, ...]:
    if not lines:
        raise ValueError("En az bir kampanya satırı gereklidir")
    editable = [line for line in lines if line.profile.editable]
    if not editable:
        raise ValueError("Hedef için düzenlenebilir kampanya satırı yok")
    current_nets = {
        line.line_id: net_amount(line.current_price, line.profile)
        for line in lines
    }
    editable_net = sum(
        (current_nets[line.line_id] for line in editable), ZERO
    )
    if editable_net <= ZERO:
        raise ValueError("Düzenlenebilir satırların net toplamı pozitif olmalıdır")
    if any(
        Decimal(1) - line.profile.rate == ZERO
        for line in editable
    ):
        raise ValueError("Düzenlenebilir satırın etkin oranı %100 olamaz")
    current_total = sum(current_nets.values(), ZERO)
    scale = (editable_net + target - current_total) / editable_net
    if scale <= ZERO:
        raise ValueError("Hedef, sabit satırlar korunarak karşılanamıyor")
    return tuple(
        CampaignPrice(
            line_id=line.line_id,
            net=current_nets[line.line_id] * scale,
            price=_round_price(
                (
                    current_nets[line.line_id] * scale
                    + line.profile.fixed_amount
                )
                / (Decimal(1) - line.profile.rate)
            ),
        )
        for line in editable
    )


def verify_campaign_prices(
    prices: Sequence[CampaignPrice],
    lines: Sequence[CampaignLine],
    target: Decimal,
    actual_total_fn: Callable[[Sequence[CampaignPrice]], Decimal],
    max_rounds: int = 3,
) -> VerificationResult:
    if max_rounds < 1:
        raise ValueError("Doğrulama turu en az bir olmalıdır")
    if not prices:
        raise ValueError("Doğrulama için en az bir fiyat gereklidir")
    by_id = {line.line_id: line for line in lines}
    current = tuple(prices)
    for round_number in range(1, max_rounds + 1):
        actual = actual_total_fn(current)
        difference = target - actual
        if difference == ZERO:
            return VerificationResult(
                current, actual, target, difference, round_number - 1, True
            )
        last = current[-1]
        profile = by_id[last.line_id].profile
        denominator = Decimal(1) - profile.rate
        if denominator == ZERO:
            raise ValueError("Son düzenlenebilir satırın etkin oranı %100 olamaz")
        correction = difference / denominator
        current = tuple(
            CampaignPrice(
                line_id=price.line_id,
                net=price.net + (
                    difference if price.line_id == last.line_id else ZERO
                ),
                price=(
                    _round_price(
                        price.price
                        + (
                            correction
                            if price.line_id == last.line_id
                            else ZERO
                        )
                    )
                ),
            )
            for price in current
        )
    actual = actual_total_fn(current)
    difference = target - actual
    return VerificationResult(
        current, actual, target, difference, max_rounds, difference == ZERO
    )
