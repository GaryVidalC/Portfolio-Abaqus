from decimal import Decimal, ROUND_HALF_UP
from django.db import models, transaction
from investments.models import Portfolio, Asset, Price, InitialWeight, HoldingAdjustment

def _q(x): 
    return x if isinstance(x, Decimal) else Decimal(str(x))

def _price(asset: Asset, d):
    return Price.objects.get(asset=asset, date=d).price

def compute_initial_units_for_portfolio(*, portfolio: Portfolio):
    t0 = portfolio.initial_date
    V0 = _q(portfolio.initial_value)
    out = {}
    for iw in portfolio.initial_weights.select_related('asset'):
        w = _q(iw.weight)
        p = _price(iw.asset, t0)
        units = (w * V0 / p).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
        out[iw.asset] = units
    return out

def get_units_on_date(*, portfolio: Portfolio, asset: Asset, d):
    base = compute_initial_units_for_portfolio(portfolio=portfolio)[asset]
    delta = (HoldingAdjustment.objects
             .filter(portfolio=portfolio, asset=asset, effective_date__lte=d)
             .aggregate(total=models.Sum('delta_units'))['total'] or Decimal('0'))
    return (base + delta).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

def portfolio_value_on_date(*, portfolio: Portfolio, d):
    total = Decimal('0')
    for iw in portfolio.initial_weights.select_related('asset'):
        c = get_units_on_date(portfolio=portfolio, asset=iw.asset, d=d)
        p = _price(iw.asset, d)
        total += c * p
    return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def portfolio_weights_on_date(*, portfolio: Portfolio, d):
    Vt = portfolio_value_on_date(portfolio=portfolio, d=d)
    if Vt == 0:
        return {}
    res = {}
    for iw in portfolio.initial_weights.select_related('asset'):
        c = get_units_on_date(portfolio=portfolio, asset=iw.asset, d=d)
        p = _price(iw.asset, d)
        res[iw.asset.name] = (c * p / Vt).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
    return res

@transaction.atomic
def apply_trade(*, portfolio: Portfolio, d, asset_sell: Asset, value_sell: Decimal, asset_buy: Asset, value_buy: Decimal):
    ps = _price(asset_sell, d)
    pb = _price(asset_buy, d)
    HoldingAdjustment.objects.create(portfolio=portfolio, asset=asset_sell, effective_date=d, delta_units=-_q(value_sell)/ps)
    HoldingAdjustment.objects.create(portfolio=portfolio, asset=asset_buy,  effective_date=d, delta_units= _q(value_buy)/pb)
