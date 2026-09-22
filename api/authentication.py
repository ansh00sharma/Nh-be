from rest_framework_simplejwt.authentication import JWTAuthentication

from api.profiling import profile_timer


class ProfiledJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        with profile_timer("auth_time"):
            return super().authenticate(request)
