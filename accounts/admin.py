from django.contrib import admin
from .models import UserPreferences
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group


class SuperAdminOnly:
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.unregister(get_user_model())
admin.site.unregister(Group)


@admin.register(get_user_model())
class RestrictedUserAdmin(SuperAdminOnly, UserAdmin):
    pass


@admin.register(Group)
class RestrictedGroupAdmin(SuperAdminOnly, GroupAdmin):
    pass


@admin.register(UserPreferences)
class UserPreferencesAdmin(SuperAdminOnly, admin.ModelAdmin):
    pass
