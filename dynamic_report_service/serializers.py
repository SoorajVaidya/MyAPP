
from rest_framework import serializers


class ImageProcessingSerializer(serializers.Serializer):
    points = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False
    )