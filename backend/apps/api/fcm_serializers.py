from rest_framework import serializers


class FcmTokenRegisterSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512, trim_whitespace=True, allow_blank=False)

    def validate_token(self, value: str) -> str:
        token = value.strip()
        if not token:
            raise serializers.ValidationError("FCM token is required.")
        if len(token) < 20:
            raise serializers.ValidationError("FCM token looks too short.")
        return token
