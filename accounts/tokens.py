from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password


class PasswordAwareRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        token = self.token_class(attrs["refresh"])
        user = (
            get_user_model()
            .objects.filter(pk=token.get(api_settings.USER_ID_CLAIM))
            .first()
        )
        if (
            not user
            or not user.is_active
            or token.get(api_settings.REVOKE_TOKEN_CLAIM)
            != get_md5_hash_password(user.password)
        ):
            raise AuthenticationFailed(
                "Your credentials have changed. Please sign in again."
            )
        return super().validate(attrs)
