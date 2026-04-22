from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import User
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import UserProfile
from .serializers import UserProfileSerializer


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all().select_related('user')
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['department', 'role']
    search_fields = ['user__username', 'user__email', 'department', 'role']
    ordering_fields = ['user__username', 'department', 'role', 'created_at', 'updated_at']
    ordering = ['user__username']

    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        if request.method == 'GET':
            try:
                profile = request.user.profile
                serializer = self.get_serializer(profile)
                return Response(serializer.data)
            except UserProfile.DoesNotExist:
                return Response({'detail': 'Profile not found'}, status=404)
        
        elif request.method == 'PATCH':
            try:
                profile = request.user.profile
                serializer = self.get_serializer(profile, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            except UserProfile.DoesNotExist:
                return Response({'detail': 'Profile not found'}, status=404)


class HomeView(APIView):
    """
    Simple home view to handle root URL requests
    """
    def get(self, request):
        return Response({
            'message': 'Welcome to NDC API',
            'endpoints': {
                'user-profiles': '/api/user-profiles/',
                'admin': '/admin/'
            }
        })
