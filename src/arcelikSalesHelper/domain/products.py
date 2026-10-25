from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
from decimal import Decimal

from .validation import ValidationError

MAX_NAME_LENGTH = 200


@dataclass(frozen=True)
class ProductDraft:
    name: str
    regular_price: Decimal
    website_price: Decimal
    default_gift_name: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    regular_price: Decimal
    website_price: Decimal
    default_gift_name: str | None
    notes: str | None
    archived: bool
    created_at: str  # UTC ISO-8601, e.g. 2026-10-24T09:30:00Z
    updated_at: str
    quantity: int | None = None  # manually counted; None = never counted
    quantity_updated_at: str | None = None


def name_key(name: str) -> str:
    """Uniqueness / search key: collapse whitespace, casefold, NFC-normalise.

    Shared by the product repository and (in M7) the CSV importer.
    Not Turkish-aware: 'I' folds to 'i', and 'ı' / 'İ' stay distinct.
    """
    collapsed = " ".join(name.split())
    return unicodedata.normalize("NFC", collapsed.casefold())


def _blank_to_none(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def normalize_draft(draft: ProductDraft) -> ProductDraft:
    return replace(
        draft,
        name=" ".join(draft.name.split()),
        default_gift_name=_blank_to_none(draft.default_gift_name),
        notes=_blank_to_none(draft.notes),
    )


def _bad_money(d: Decimal) -> bool:
    return (not d.is_finite()) or d < 0


def validate_draft(draft: ProductDraft) -> tuple[ValidationError, ...]:
    """Expects a normalised draft."""
    errors: list[ValidationError] = []
    if not draft.name:
        errors.append(
            ValidationError(
                "name_required", "name", "Product name is required."
            )
        )
    elif len(draft.name) > MAX_NAME_LENGTH:
        errors.append(
            ValidationError(
                "name_too_long",
                "name",
                f"Name must be at most {MAX_NAME_LENGTH} characters.",
            )
        )
    if _bad_money(draft.regular_price):
        errors.append(
            ValidationError(
                "regular_price_invalid",
                "regular_price",
                "Regular price must be zero or more.",
            )
        )
    if _bad_money(draft.website_price):
        errors.append(
            ValidationError(
                "website_price_invalid",
                "website_price",
                "Website price must be zero or more.",
            )
        )
    return tuple(errors)
