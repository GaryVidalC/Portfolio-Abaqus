from rest_framework import views, response, status
from django.shortcuts import get_object_or_404
from investments.models import Portfolio, Asset
from investments.services import apply_trade
from investments.selectors import portfolio_time_series
from .serializers import TimeSeriesRequestSerializer
from investments.selectors import initial_units_for_all_assets, last_price_date
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

        fecha_inicio = ser.validated_data['fecha_inicio']
        fecha_fin = ser.validated_data['fecha_fin']

        # Validación contra última fecha disponible
        last_date = last_price_date()
        if last_date and fecha_fin > last_date:
            return response.Response(
                {"detail": f"fecha_fin no puede ser mayor que {last_date.isoformat()}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        use_trades = request.query_params.get('use_trades', '1') in ('1', 'true', 'True')

        data = portfolio_time_series(
            portfolio=p, start=fecha_inicio, end=fecha_fin, use_trades=use_trades
        )
        return response.Response({
            "dates": [d.isoformat() for d in data["dates"]],
            "Vt": data["Vt"],
            "weights": data["weights"],
            "use_trades": use_trades,
        })

class TradeApi(views.APIView):
    def post(self, request, portfolio_id):
        p = get_object_or_404(Portfolio, pk=portfolio_id)
        data = request.data
        a_sell = Asset.objects.get(name=data['asset_sell'])
        a_buy  = Asset.objects.get(name=data['asset_buy'])
        apply_trade(
            portfolio=p, d=data['fecha'],
            asset_sell=a_sell, value_sell=data['value_sell'],
            asset_buy=a_buy,  value_buy=data['value_buy'],
        )
        return response.Response({"status": "ok"})
