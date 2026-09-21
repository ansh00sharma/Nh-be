from rest_framework import serializers

from projects.models import Project
from projects.querysets import get_project_queryset_for_user
from tasks.models import Task


class TaskSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.none())
    project_name = serializers.CharField(source="project.name", read_only=True)
    assignee_name = serializers.SerializerMethodField()
    assignee_email = serializers.EmailField(source="assignee.email", read_only=True)
    assigned_by_name = serializers.SerializerMethodField()
    assigned_by_email = serializers.EmailField(source="project.owner.email", read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "project",
            "project_name",
            "title",
            "description",
            "status",
            "assignee",
            "assignee_name",
            "assignee_email",
            "assigned_by_name",
            "assigned_by_email",
            "due_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "project_name",
            "assignee_name",
            "assignee_email",
            "assigned_by_name",
            "assigned_by_email",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["project"].queryset = get_project_queryset_for_user(request.user)

    def get_assignee_name(self, obj):
        if not obj.assignee:
            return None
        return f"{obj.assignee.first_name} {obj.assignee.last_name}".strip()

    def get_assigned_by_name(self, obj):
        owner = obj.project.owner
        return f"{owner.first_name} {owner.last_name}".strip()
