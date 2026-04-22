from rest_framework import permissions
from django.contrib.auth.models import User


class IsEngineerPermission(permissions.BasePermission):
    """
    Custom permission to only allow users with engineer role.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'profile') and
            request.user.profile.role and
            request.user.profile.role.name.lower() == 'engineer'
        )


class IsResponsibleEngineerPermission(permissions.BasePermission):
    """
    Custom permission to only allow engineers who are responsible for the equipment.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff or request.user.is_superuser:
            return True
            
        # Check if user is an engineer and is responsible for this equipment
        return (
            request.user and 
            request.user.is_authenticated and
            hasattr(obj, 'responsible_user') and
            obj.responsible_user == request.user
        )


class IsAdminOrEngineerPermission(permissions.BasePermission):
    """
    Custom permission to allow admins or engineers (with appropriate scope).
    Engineers can create equipment and manage their own assigned equipment.
    """
    
    def has_permission(self, request, view):
        # Admin users have full access
        if request.user.is_staff or request.user.is_superuser:
            return True
            
        # Engineers can access all views (list, create, etc.)
        return (
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'profile') and
            request.user.profile.role and
            request.user.profile.role.name.lower() == 'engineer'
        )
    
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff or request.user.is_superuser:
            return True
            
        # For read operations, engineers can see any object
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # For write operations, engineers can only modify objects they're responsible for
        if hasattr(obj, 'responsible_user'):
            return obj.responsible_user == request.user
        elif hasattr(obj, 'equipment') and hasattr(obj.equipment, 'responsible_user'):
            return obj.equipment.responsible_user == request.user
            
        return False


class IsAdminOrResponsibleEngineerPermission(permissions.BasePermission):
    """
    Custom permission to allow admins or engineers responsible for specific equipment.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff or request.user.is_superuser:
            return True
            
        # Check if user is the responsible engineer for this equipment
        return (
            request.user and 
            request.user.is_authenticated and
            hasattr(obj, 'responsible_user') and
            obj.responsible_user == request.user
        )


class IsOwnerOrAdminPermission(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admin users.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff or request.user.is_superuser:
            return True
            
        # Check if user is the owner
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'profile'):
            return obj.profile.user == request.user
            
        return False
