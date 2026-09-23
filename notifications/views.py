from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from core.observability.decorators import traced
from notifications.models import Notification
from notifications.serializers import NotificationSerializer


class NotificationListView(ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    @traced("notification.repository.list_for_user")
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
