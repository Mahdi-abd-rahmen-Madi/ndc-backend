from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import UserProfile, Role, EngineerProfile


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at', 'updated_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (None, {
            'fields': ('name', 'description')
        }),
        (_('Permissions'), {
            'fields': ('permissions',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(EngineerProfile)
class EngineerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'specializations_count', 'created_at', 'updated_at']
    search_fields = ['user__username', 'user__email', 'employee_id']
    readonly_fields = ['created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    
    def specializations_count(self, obj):
        return len(obj.specializations) if obj.specializations else 0
    specializations_count.short_description = _('Specializations Count')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'role', 'phone', 'created_at', 'updated_at']
    search_fields = ['user__username', 'user__email', 'department', 'role__name']
    list_filter = ['department', 'role', 'created_at', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('user', 'department', 'role', 'phone')
        }),
        (_('Avatar'), {
            'fields': ('avatar',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
