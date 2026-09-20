from django import forms
from django.contrib import admin

from users.models import User
from users.roles import TASKFLOW_ROLES


class UserAdminForm(forms.ModelForm):
    def clean_groups(self):
        groups = self.cleaned_data["groups"]
        role_count = groups.filter(name__in=TASKFLOW_ROLES).count()
        if role_count > 1:
            raise forms.ValidationError("Select only one TaskFlow role group.")
        return groups


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ("email", "first_name", "last_name", "is_staff")
    list_filter = ("groups", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    filter_horizontal = ("groups", "user_permissions")
