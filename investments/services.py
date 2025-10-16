from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date

from django.db import models, transaction

from investments.models import Portfolio, Asset, Price, HoldingAdjustment


# ---------- helpers ----------
def _q(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))

def _ensure_date(x) -> date:
    if isinstance(x, date):
        return x
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(x), fmt).date()
        except (TypeError, ValueError):
            continue
    raise ValueError(f"Fecha inválida: {x!r}")

def _price(asset: Asset, d: date) -> Decimal:
    return Price.objects.get(asset=asset, date=d).price


# ---------- core ----------
def compute_initial_units_for_portfolio(*, portfolio: Portfolio) -> dict[int, Decimal]:
    """
    Devuelve {asset_id: unidades_iniciales} usando C_{i,0} = w_i0 * V0 / P_i0.
    Usamos asset_id como clave (no la instancia) para evitar mismatches.
    """
    t0 = portfolio.initial_date
    V0 = _q(portfolio.initial_value)
    out: dict[int, Decimal] = {}
    for iw in portfolio.initial_weights.select_related("asset"):
        w = _q(iw.weight)
        p = _price(iw.asset, t0)
        units = (w * V0 / p).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        out[iw.asset_id] = units
    return out

def get_units_on_date(*, portfolio: Portfolio, asset: Asset, d) -> Decimal:
    """
    Unidades = unidades_iniciales + sum(delta_units hasta d)
    """
    d = _ensure_date(d)
    base_by_id = compute_initial_units_for_portfolio(portfolio=portfolio)
    base = base_by_id.get(asset.id, Decimal("0"))
    delta = (
        HoldingAdjustment.objects
        .filter(portfolio=portfolio, asset=asset, effective_date__lte=d)
        .aggregate(total=models.Sum("delta_units"))["total"] or Decimal("0")
    )
    return (base + _q(delta)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

def portfolio_value_on_date(*, portfolio: Portfolio, d) -> Decimal:
    d = _ensure_date(d)
    total = Decimal("0")
    for iw in portfolio.initial_weights.select_related("asset"):
        c = get_units_on_date(portfolio=portfolio, asset=iw.asset, d=d)
        p = _price(iw.asset, d)
        total += c * p
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def portfolio_weights_on_date(*, portfolio: Portfolio, d) -> dict[str, Decimal]:
    d = _ensure_date(d)
    Vt = portfolio_value_on_date(portfolio=portfolio, d=d)
    if Vt == 0:
        return {}
    res: dict[str, Decimal] = {}
    for iw in portfolio.initial_weights.select_related("asset"):
        c = get_units_on_date(portfolio=portfolio, asset=iw.asset, d=d)
        p = _price(iw.asset, d)
        res[iw.asset.name] = (c * p / Vt).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    return res

@transaction.atomic
def apply_trade(*, portfolio: Portfolio, d, asset_sell: Asset, value_sell, asset_buy: Asset, value_buy) -> None:
    """
    Aplica un trade en fecha d:
      - vende 'value_sell' USD de asset_sell  -> delta_units NEGATIVO
      - compra 'value_buy'  USD de asset_buy  -> delta_units POSITIVO
    Usa precios de ese día y cuantiza unidades a 8 decimales.
    """
    d = _ensure_date(d)
    ps = _price(asset_sell, d)  # puede levantar DoesNotExist (correcto)
    pb = _price(asset_buy,  d)

    units_sell = (_q(value_sell) / ps).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    units_buy = (_q(value_buy) / pb).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    # Evita duplicados: si ya existe un ajuste idéntico no lo recreamos.
    # Esto hace que la operación sea idempotente frente a reintentos/duplicados de la petición.
    sell_kwargs = dict(portfolio=portfolio, asset=asset_sell, effective_date=d, delta_units=-units_sell)
    buy_kwargs = dict(portfolio=portfolio, asset=asset_buy, effective_date=d, delta_units=units_buy)

    if not HoldingAdjustment.objects.filter(**sell_kwargs).exists():
        HoldingAdjustment.objects.create(**sell_kwargs)

    if not HoldingAdjustment.objects.filter(**buy_kwargs).exists():
        HoldingAdjustment.objects.create(**buy_kwargs)

    # Retornamos las unidades calculadas por si el llamador quiere usarlas (útil para tests/manual checks)
    return {'units_sell': units_sell, 'units_buy': units_buy}
