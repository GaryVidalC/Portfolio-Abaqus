from rest_framework import views, response
from django.shortcuts import get_object_or_404
from investments.models import Portfolio, Asset
from investments.services import apply_trade
from investments.selectors import portfolio_time_series
from .serializers import TimeSeriesRequestSerializer
from investments.selectors import initial_units_for_all_assets
from .serializers import InitialUnitsSerializer

class HealthApi(views.APIView):
    def get(self, request):
        return response.Response({"status": "ok"})

class PortfolioInitialUnitsApi(views.APIView):
    def get(self, request, portfolio_id):
        p = get_object_or_404(Portfolio, pk=portfolio_id)
        data = initial_units_for_all_assets(portfolio=p)
        ser = InitialUnitsSerializer(data, many=True)
        return response.Response(ser.data)
        
class PortfolioTimeSeriesApi(views.APIView):
    def get(self, request, portfolio_id):
        p = get_object_or_404(Portfolio, pk=portfolio_id)
        ser = TimeSeriesRequestSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        data = portfolio_time_series(
            portfolio=p,
            start=ser.validated_data['fecha_inicio'],
            end=ser.validated_data['fecha_fin']
        )
        return response.Response({
            "dates": [d.isoformat() for d in data["dates"]],
            "Vt": data["Vt"],
            "weights": data["weights"]
        })

class TradeApi(views.APIView):
    def post(self, request, portfolio_id):
        p = get_object_or_404(Portfolio, pk=portfolio_id)
        data = request.data
        a_sell = Asset.objects.get(name=data['asset_sell'])
        a_buy = Asset.objects.get(name=data['asset_buy'])
        apply_trade(
            portfolio=p, d=data['fecha'],
            asset_sell=a_sell, value_sell=data['value_sell'],
            asset_buy=a_buy, value_buy=data['value_buy']
        )
        return response.Response({"status": "ok"})
