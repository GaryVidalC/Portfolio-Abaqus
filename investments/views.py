from django.shortcuts import render, get_object_or_404
from investments.models import Portfolio, Price
from investments.selectors import portfolio_time_series, last_price_date
from django.http import HttpResponseBadRequest
from datetime import datetime, date

def _parse_date(d):
    if isinstance(d, date):
        return d
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(d, fmt).date()
        except (TypeError, ValueError):
            continue
    raise ValueError(f"Fecha inválida: {d}")

def portfolio_charts(request, portfolio_id):
    """Con trades (por defecto)."""
    p = get_object_or_404(Portfolio, pk=portfolio_id)
    fi_str = request.GET.get('fecha_inicio', p.initial_date.isoformat())
    ff_str = request.GET.get('fecha_fin', p.initial_date.isoformat())
    fi = _parse_date(fi_str)
    ff = _parse_date(ff_str)
    
    last_date = last_price_date()
    if last_date and ff > last_date:
        return HttpResponseBadRequest(f"fecha_fin no puede ser mayor que {last_date.isoformat()}")

    data = portfolio_time_series(portfolio=p, start=fi, end=ff, use_trades=True)

    dates = [d.isoformat() for d in data["dates"]]
    vt = [float(v) for v in data["Vt"]]
    asset_names = sorted({k for day in data["weights"] for k in day.keys()})
    series = {name: [float(day.get(name, 0.0)) for day in data["weights"]] for name in asset_names}

    return render(request, "investments/portfolio_charts.html", {
        "portfolio": p, "dates": dates, "vt": vt, "assets": asset_names, "series": series,
    })

def portfolio_charts_no_trades(request, portfolio_id):
    """SIN trades (ignora Bonus 2)."""
    p = get_object_or_404(Portfolio, pk=portfolio_id)
    fi_str = request.GET.get('fecha_inicio', p.initial_date.isoformat())
    ff_str = request.GET.get('fecha_fin', p.initial_date.isoformat())
    fi = _parse_date(fi_str)
    ff = _parse_date(ff_str)

    last_date = last_price_date()
    if last_date and ff > last_date:
        return HttpResponseBadRequest(f"fecha_fin no puede ser mayor que {last_date.isoformat()}")
    
    data = portfolio_time_series(portfolio=p, start=fi, end=ff, use_trades=False)

    dates = [d.isoformat() for d in data["dates"]]
    vt = [float(v) for v in data["Vt"]]
    asset_names = sorted({k for day in data["weights"] for k in day.keys()})
    series = {name: [float(day.get(name, 0.0)) for day in data["weights"]] for name in asset_names}

    return render(request, "investments/portfolio_charts.html", {
        "portfolio": p, "dates": dates, "vt": vt, "assets": asset_names, "series": series,
    })

def home(request):
    # Defaults: primer portafolio, fecha inicial del portafolio y última fecha de precios
    p = Portfolio.objects.order_by('id').first()
    start_default = p.initial_date if p else date(2022, 1, 1)
    last_price = Price.objects.order_by('-date').first()
    end_default = last_price.date if last_price else start_default

    portfolios = Portfolio.objects.all().values('id', 'name')
    return render(request, "investments/home.html", {
        "portfolios": portfolios,
        "start_default": start_default.isoformat(),
        "end_default": end_default.isoformat(),
    })