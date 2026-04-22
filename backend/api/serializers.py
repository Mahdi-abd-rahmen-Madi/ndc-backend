from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Role, EngineerProfile


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'description', 'permissions', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class EngineerProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = EngineerProfile
        fields = ['id', 'user', 'username', 'email', 'employee_id', 'specializations', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    role = RoleSerializer(read_only=True)
    engineer_profile = EngineerProfileSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'username', 'email', 'first_name', 'last_name',
            'phone', 'department', 'role', 'engineer_profile', 'avatar',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
