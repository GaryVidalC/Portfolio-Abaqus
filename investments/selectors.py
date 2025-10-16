# investments/selectors.py
from __future__ import annotations

from datetime import datetime, timedelta, date
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

from django.db.models import Sum

from investments.models import Portfolio, Asset, Price, InitialWeight, HoldingAdjustment


# ---------- Helpers de fechas y decimales ----------

def _ensure_date(x) -> date:
    """Convierte str/fecha a date. Acepta YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY."""
    if isinstance(x, date):
        return x
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(x), fmt).date()
        except (TypeError, ValueError):
            continue
    raise ValueError(f"Fecha inválida: {x!r}")

def daterange(start, end):
    """Genera fechas día a día (incluye extremos)."""
    start = _ensure_date(start)
    end = _ensure_date(end)
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)

def _q(x) -> Decimal:
    """Convierte a Decimal de forma segura."""
    return x if isinstance(x, Decimal) else Decimal(str(x))


# ---------- Cálculo de unidades iniciales (C_{i,0}) ----------

def _compute_initial_units_once(portfolio: Portfolio) -> tuple[dict[int, Decimal], dict[int, str]]:
    """
    Devuelve:
      - base_units: {asset_id -> Decimal(unidades iniciales)}
      - asset_name: {asset_id -> nombre}
    Fórmula: C_{i,0} = w_{i,0} * V0 / P_{i,0}
    """
    t0 = portfolio.initial_date
    V0 = _q(portfolio.initial_value)

    # Pesos iniciales y sus assets en una query
    iweights = list(
        InitialWeight.objects.select_related("asset").filter(portfolio=portfolio)
    )
    if not iweights:
        raise ValueError(f"No hay pesos iniciales para el portafolio '{portfolio}'.")

    assets = [iw.asset for iw in iweights]
    asset_ids = [a.id for a in assets]

    # Precios al t0 para todos esos assets en una query
    p0_map = {
        p.asset_id: p.price
        for p in Price.objects.filter(asset_id__in=asset_ids, date=t0)
    }

    base_units: dict[int, Decimal] = {}
    asset_name: dict[int, str] = {a.id: a.name for a in assets}

    for iw in iweights:
        p0 = p0_map.get(iw.asset_id)
        if p0 is None:
            raise ValueError(f"Falta precio inicial (t0={t0}) para activo '{iw.asset.name}'.")
        units = (_q(iw.weight) * V0 / _q(p0)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        base_units[iw.asset_id] = units

    return base_units, asset_name


def initial_units_for_all_assets(*, portfolio: Portfolio) -> list[dict]:
    """
    Estructura para API: [{"asset": "EEUU", "units": Decimal(...)}, ...]
    Ordenada alfabéticamente por nombre de activo.
    """
    base_units, asset_name = _compute_initial_units_once(portfolio)
    rows = [{"asset": asset_name[aid], "units": base_units[aid]} for aid in base_units.keys()]
    rows.sort(key=lambda r: r["asset"])
    return rows


# ---------- Ajustes acumulados (trades) por rango ----------

def _adjustments_cumsum(portfolio: Portfolio, start: date, end: date) -> dict[tuple[int, date], Decimal]:
    """
    Para cada (asset_id, fecha del rango), retorna la suma acumulada de delta_units
    hasta esa fecha (incluida). Si no hubo ajustes para un par, no habrá key.
    """
    qs = (
        HoldingAdjustment.objects
        .filter(portfolio=portfolio, effective_date__lte=end)
        .values("asset_id", "effective_date")
        .annotate(total=Sum("delta_units"))
        .order_by("asset_id", "effective_date")
    )

    per_asset = defaultdict(list)
    for r in qs:
        per_asset[r["asset_id"]].append((r["effective_date"], _q(r["total"] or 0)))

    all_dates = list(daterange(start, end))
    out: dict[tuple[int, date], Decimal] = {}

    for aid, series in per_asset.items():
        cum = Decimal("0")
        idx = 0
        for d in all_dates:
            while idx < len(series) and series[idx][0] <= d:
                cum += series[idx][1]
                idx += 1
            out[(aid, d)] = cum

    return out


# ---------- Serie temporal (V_t y w_{i,t}) ----------

def portfolio_time_series(*, portfolio: Portfolio, start, end, use_trades: bool = True) -> dict:
    """
    Calcula para el rango [start, end]:
      - dates: [date, ...]
      - Vt: [Decimal, ...]
      - weights: [ {asset_name: Decimal(w_{i,t}), ...}, ... ]

    use_trades:
      True  -> incluye ajustes/operaciones (Bonus 2)
      False -> ignora ajustes (como si no existieran trades)
    """
    start = _ensure_date(start)
    end = _ensure_date(end)

    # 1) Unidades base al t0 y nombres
    base_units, asset_name = _compute_initial_units_once(portfolio)
    asset_ids = list(base_units.keys())

    # 2) Ajustes acumulados por día (según flag)
    adj_cum = _adjustments_cumsum(portfolio, start, end) if use_trades else {}

    # 3) Precios del rango (UNA consulta) -> mapa
    prices = (
        Price.objects
        .filter(asset_id__in=asset_ids, date__gte=start, date__lte=end)
        .values("asset_id", "date", "price")
    )
    price_map = {(p["asset_id"], p["date"]): p["price"] for p in prices}

    dates, vt, weights = [], [], []

    for d in daterange(start, end):
        total_v = Decimal("0")
        xi_by_asset = {}

        for aid in asset_ids:
            units = base_units[aid] + adj_cum.get((aid, d), Decimal("0"))
            price = price_map.get((aid, d))
            if price is None:
                continue
            xval = units * _q(price)
            xi_by_asset[aid] = xval
            total_v += xval

        total_v = total_v.quantize(Decimal("0.01"))

        wmap = {}
        if total_v > 0 and xi_by_asset:
            for aid, xval in xi_by_asset.items():
                wmap[asset_name[aid]] = (xval / total_v).quantize(Decimal("0.00000001"))

        dates.append(d)
        vt.append(total_v)
        weights.append(wmap)

    return {"dates": dates, "Vt": vt, "weights": weights}