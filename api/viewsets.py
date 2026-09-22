from rest_framework.viewsets import ModelViewSet

from api.profiling import profile_timer


class ProfiledModelViewSet(ModelViewSet):
    def check_permissions(self, request):
        with profile_timer("permission_time"):
            return super().check_permissions(request)
