from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.authentication import api_settings
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings as simplejwt_api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from django.utils.translation import gettext_lazy as _

from api.profiling import profile_timer
from users.auth_cache import get_cached_auth_user, load_auth_user_from_database


class ProfiledJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        with profile_timer("auth_time"):
            return super().authenticate(request)

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken(_("Token contained no recognizable user identification")) from exc

        user = None
        if not simplejwt_api_settings.CHECK_REVOKE_TOKEN:
            user = get_cached_auth_user(user_id)
        if user is None:
            try:
                user = load_auth_user_from_database(
                    self.user_model,
                    {api_settings.USER_ID_FIELD: user_id},
                )
            except self.user_model.DoesNotExist as exc:
                raise AuthenticationFailed(_("User not found"), code="user_not_found") from exc

        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

        if simplejwt_api_settings.CHECK_REVOKE_TOKEN:
            if validated_token.get(
                simplejwt_api_settings.REVOKE_TOKEN_CLAIM
            ) != get_md5_hash_password(user.password):
                raise AuthenticationFailed(
                    _("The user's password has been changed."),
                    code="password_changed",
                )

        return user
