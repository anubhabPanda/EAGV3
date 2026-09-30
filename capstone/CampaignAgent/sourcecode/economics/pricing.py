"""Per-model pricing, loaded from config.

No price appears in Python. ``pricing.yaml`` owns the table; an unlisted model
falls back to the file's own ``default`` row so an unknown model is never
silently free (the failure mode that makes a metering layer useless).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelPrice:
    """What one model costs per ``unit_tokens`` tokens."""

    input: float
    output: float


@dataclass(frozen=True)
class Pricing:
    """The priced table. ``cost`` is the only way money is ever computed."""

    currency: str
    unit_tokens: int
    default: ModelPrice
    models: dict[str, ModelPrice] = field(default_factory=dict)
    cache_read_multiplier: float = 1.0
    cache_write_multiplier: float = 1.0

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Pricing:
        def price(row: Any) -> ModelPrice:
            row = row or {}
            return ModelPrice(float(row.get("input", 0.0)), float(row.get("output", 0.0)))

        unit = int(data.get("unit_tokens", 1_000_000))
        if unit <= 0:
            raise ValueError("pricing.unit_tokens must be positive")
        return cls(
            currency=str(data.get("currency", "USD")),
            unit_tokens=unit,
            default=price(data.get("default")),
            models={str(name): price(row) for name, row in (data.get("models") or {}).items()},
            cache_read_multiplier=float(data.get("cache_read_multiplier", 1.0)),
            cache_write_multiplier=float(data.get("cache_write_multiplier", 1.0)),
        )

    def price_for(self, model: str | None) -> ModelPrice:
        """The row for ``model``, falling back to the configured default row.

        Matching is exact first, then longest configured prefix, so a gateway
        that decorates a model id (``gemini-3.1-flash-lite-002``) still prices.
        """
        if model:
            if model in self.models:
                return self.models[model]
            candidates = [name for name in self.models if model.startswith(name)]
            if candidates:
                return self.models[max(candidates, key=len)]
        return self.default

    def is_priced(self, model: str | None) -> bool:
        """True when the model has its own row (rather than the default row)."""
        return bool(model) and self.price_for(model) is not self.default

    def cost(
        self,
        model: str | None,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """Cost of one call, in ``self.currency``.

        Cached input is billed at the configured read/write multipliers; the
        gateway reports those token counts separately from fresh input.
        """
        row = self.price_for(model)
        per_token_in = row.input / self.unit_tokens
        per_token_out = row.output / self.unit_tokens
        return (
            max(0, int(input_tokens)) * per_token_in
            + max(0, int(output_tokens)) * per_token_out
            + max(0, int(cache_read_tokens)) * per_token_in * self.cache_read_multiplier
            + max(0, int(cache_write_tokens)) * per_token_in * self.cache_write_multiplier
        )
