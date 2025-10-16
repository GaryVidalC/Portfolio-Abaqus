from rest_framework import serializers

class InitialUnitsSerializer(serializers.Serializer):
    asset = serializers.CharField()
    units = serializers.DecimalField(max_digits=30, decimal_places=10)


class TimeSeriesRequestSerializer(serializers.Serializer):
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()