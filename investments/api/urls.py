from django.urls import path
from .views import HealthApi,PortfolioTimeSeriesApi, PortfolioInitialUnitsApi, TradeApi

# De momento no hay endpoints; definimos la lista vacía
urlpatterns = [
    path('health', HealthApi.as_view()),
    path('portfolios/<int:portfolio_id>/initial-units', PortfolioInitialUnitsApi.as_view()),
    path('portfolios/<int:portfolio_id>/time-series', PortfolioTimeSeriesApi.as_view()),
    path('portfolios/<int:portfolio_id>/trade',    TradeApi.as_view()),
]
