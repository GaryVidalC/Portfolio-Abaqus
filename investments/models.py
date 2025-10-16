from django.db import models

# Create your models here.
from django.db import models


class Asset(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Portfolio(models.Model):
    name = models.CharField(max_length=100, unique=True)
    initial_value = models.DecimalField(max_digits=20, decimal_places=8)
    initial_date = models.DateField()

    def __str__(self):
        return self.name


class Price(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='prices')
    date = models.DateField()
    price = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        unique_together = ('asset', 'date')


class InitialWeight(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='initial_weights')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='initial_weights')
    weight = models.DecimalField(max_digits=10, decimal_places=8)

    class Meta:
        unique_together = ('portfolio', 'asset')


class HoldingAdjustment(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='holding_adjustments')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='holding_adjustments')
    effective_date = models.DateField()
    delta_units = models.DecimalField(max_digits=24, decimal_places=10)

    class Meta:
        indexes = [
            models.Index(fields=['portfolio', 'asset', 'effective_date'])
        ]
