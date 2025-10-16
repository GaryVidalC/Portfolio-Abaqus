"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from investments.views import portfolio_charts, portfolio_charts_no_trades, home

urlpatterns = [
    path('', home),
    path('admin/', admin.site.urls),
    path('api/', include('investments.api.urls')),
    path('charts/portfolios/<int:portfolio_id>/', portfolio_charts, name = "chart_con_trades"),
    path('charts/portfolios/<int:portfolio_id>/no-trades/', portfolio_charts_no_trades, name = "chart_sin_trades"),
]
