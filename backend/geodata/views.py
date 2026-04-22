from django.shortcuts import render
from rest_framework import viewsets, filters, status, permissions, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import AntennaEquipment, AntennaSpecification, TerrainLoadCalculation
from api.permissions import IsAdminOrEngineerPermission, IsAdminOrResponsibleEngineerPermission
from .serializers import (
    AntennaEquipmentSerializer, AntennaEquipmentListSerializer,
    AntennaSpecificationSerializer, TerrainLoadCalculationSerializer
)
from .services import terrain_service


class AntennaEquipmentViewSet(viewsets.ModelViewSet):
    """ViewSet for AntennaEquipment model"""
    permission_classes = [IsAdminOrEngineerPermission]
    queryset = AntennaEquipment.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['region', 'status']
    search_fields = ['name', 'responsible_person', 'sub_elements', 'item_id']
    ordering_fields = ['name', 'created_at', 'building_height', 'mast_height']
    ordering = ['name']

    def get_queryset(self):
        """
        Filter queryset based on user role and responsibility.
        Admins see all equipment, engineers see only equipment they're responsible for.
        """
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return AntennaEquipment.objects.all()
        
        # Engineers see only equipment they're responsible for
        return AntennaEquipment.objects.filter(responsible_user=user)

    def get_permissions(self):
        """
        Custom permissions for different actions.
        """
        if self.action in ['update', 'partial_update', 'destroy']:
            # For update/delete, check if user is responsible for this specific equipment
            self.permission_classes = [IsAdminOrResponsibleEngineerPermission]
        else:
            # For list/retrieve/create, allow admins and engineers
            self.permission_classes = [IsAdminOrEngineerPermission]
        
        return super().get_permissions()

    def perform_create(self, serializer):
        """
        When engineers create equipment, automatically assign them as responsible.
        """
        # If user is an engineer, assign them as responsible user
        if hasattr(self.request.user, 'engineer_profile'):
            serializer.save(responsible_user=self.request.user)
        else:
            # Admins can specify responsible user or leave it null
            serializer.save()

    def get_serializer_class(self):
        if self.action == 'list':
            return AntennaEquipmentListSerializer
        return AntennaEquipmentSerializer

    @action(detail=True, methods=['get'])
    def specifications(self, request, pk=None):
        """Get all specifications for this equipment"""
        equipment = self.get_object()
        specifications = equipment.specifications.all()
        serializer = AntennaSpecificationSerializer(specifications, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def terrain_calculations(self, request, pk=None):
        """Get all terrain calculations for this equipment"""
        equipment = self.get_object()
        calculations = equipment.terrain_calculations.all()
        serializer = TerrainLoadCalculationSerializer(calculations, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def terrain_type(self, request, pk=None):
        """Determine terrain type for this equipment based on location"""
        equipment = self.get_object()
        
        # Check if equipment has coordinates
        if not hasattr(equipment, 'longitude') or not hasattr(equipment, 'latitude'):
            return Response(
                {'error': 'Equipment must have longitude and latitude coordinates'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            terrain_type = terrain_service.get_terrain_type_for_equipment(equipment)
            if terrain_type:
                return Response({
                    'terrain_type': terrain_type,
                    'coordinates': {
                        'longitude': float(equipment.longitude),
                        'latitude': float(equipment.latitude)
                    }
                })
            else:
                return Response(
                    {'error': 'No terrain classification found at these coordinates'},
                    status=status.HTTP_404_NOT_FOUND
                )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AntennaSpecificationViewSet(viewsets.ModelViewSet):
    """ViewSet for AntennaSpecification model"""
    permission_classes = [IsAdminOrEngineerPermission]
    serializer_class = AntennaSpecificationSerializer
    queryset = AntennaSpecification.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['antenna_type', 'equipment']
    search_fields = ['equipment__name', 'antenna_type']

    def get_queryset(self):
        """
        Filter queryset based on user role and equipment responsibility.
        Admins see all specifications, engineers see only specifications for their equipment.
        """
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return AntennaSpecification.objects.all()
        
        # Engineers see only specifications for equipment they're responsible for
        return AntennaSpecification.objects.filter(equipment__responsible_user=user)

    def get_permissions(self):
        """
        Custom permissions for different actions.
        """
        if self.action in ['update', 'partial_update', 'destroy']:
            # For update/delete, check if user is responsible for the equipment
            self.permission_classes = [IsAdminOrResponsibleEngineerPermission]
        else:
            # For list/retrieve/create, allow admins and engineers
            self.permission_classes = [IsAdminOrEngineerPermission]
        
        return super().get_permissions()

    def perform_create(self, serializer):
        """
        Validate and create specifications with RBAC checks.
        """
        equipment = serializer.validated_data['equipment']
        antenna_type = serializer.validated_data['antenna_type']
        
        # If user is an engineer, check if they're responsible for this equipment
        if hasattr(self.request.user, 'engineer_profile'):
            if equipment.responsible_user != self.request.user:
                raise serializers.ValidationError(
                    "You can only create specifications for equipment you are responsible for."
                )
        
        # Validate that equipment doesn't already have this antenna type
        if AntennaSpecification.objects.filter(
            equipment=equipment, 
            antenna_type=antenna_type
        ).exists():
            raise serializers.ValidationError({
                'antenna_type': 'This equipment already has a specification for this antenna type.'
            })
        
        serializer.save()

    ordering_fields = ['equipment__name', 'antenna_type', 'height_mm', 'width_mm']
    ordering = ['equipment__name', 'antenna_type']


class TerrainClassificationViewSet(viewsets.ViewSet):
    """ViewSet for terrain classification services"""
    permission_classes = [IsAdminOrEngineerPermission]
    
    @action(detail=False, methods=['get'])
    def classify_coordinates(self, request):
        """Classify terrain type at specific coordinates"""
        longitude = request.query_params.get('longitude')
        latitude = request.query_params.get('latitude')
        
        if not longitude or not latitude:
            return Response(
                {'error': 'Both longitude and latitude parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            lon = float(longitude)
            lat = float(latitude)
            
            # Validate coordinate ranges
            if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                return Response(
                    {'error': 'Invalid coordinate ranges'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            terrain_type = terrain_service.get_terrain_type_at_coordinates(lon, lat)
            
            if terrain_type:
                return Response({
                    'terrain_type': terrain_type,
                    'coordinates': {'longitude': lon, 'latitude': lat}
                })
            else:
                return Response(
                    {'error': 'No terrain classification found at these coordinates'},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except ValueError:
            return Response(
                {'error': 'Invalid coordinate format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def batch_classify(self, request):
        """Classify terrain types for multiple coordinates"""
        coordinates = request.data if request.method == 'POST' else request.query_params
        
        if 'coordinates' not in coordinates:
            return Response(
                {'error': 'coordinates parameter is required (list of [longitude, latitude] pairs)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            coords_list = coordinates['coordinates']
            if not isinstance(coords_list, list):
                raise ValueError('coordinates must be a list')
            
            results = []
            for i, coord_pair in enumerate(coords_list):
                if not isinstance(coord_pair, list) or len(coord_pair) != 2:
                    return Response(
                        {'error': f'Invalid coordinate format at index {i}. Expected [longitude, latitude]'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                lon, lat = coord_pair
                terrain_type = terrain_service.get_terrain_type_at_coordinates(float(lon), float(lat))
                results.append({
                    'coordinates': {'longitude': lon, 'latitude': lat},
                    'terrain_type': terrain_type
                })
            
            return Response({'results': results})
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get terrain type distribution statistics"""
        try:
            stats = terrain_service.get_terrain_statistics()
            return Response(stats)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def mappings(self, request):
        """Get all terrain type mappings"""
        try:
            mappings = AntennaEquipment.get_all_terrain_mappings()
            return Response(mappings)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TerrainLoadCalculationViewSet(viewsets.ModelViewSet):
    """ViewSet for TerrainLoadCalculation model"""
    permission_classes = [IsAdminOrEngineerPermission]
    serializer_class = TerrainLoadCalculationSerializer
    queryset = TerrainLoadCalculation.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['terrain_type', 'equipment']
    search_fields = ['equipment__name', 'terrain_type', 'section_material']
    ordering_fields = ['equipment__name', 'terrain_type', 'created_at']
    ordering = ['equipment__name', 'terrain_type']

    def get_queryset(self):
        """
        Filter queryset based on user role and equipment responsibility.
        Admins see all calculations, engineers see only calculations for their equipment.
        """
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return TerrainLoadCalculation.objects.all()
        
        # Engineers see only calculations for equipment they're responsible for
        return TerrainLoadCalculation.objects.filter(equipment__responsible_user=user)

    def get_permissions(self):
        """
        Custom permissions for different actions.
        """
        if self.action in ['update', 'partial_update', 'destroy']:
            # For update/delete, check if user is responsible for the equipment
            self.permission_classes = [IsAdminOrResponsibleEngineerPermission]
        else:
            # For list/retrieve/create, allow admins and engineers
            self.permission_classes = [IsAdminOrEngineerPermission]
        
        return super().get_permissions()

    def perform_create(self, serializer):
        """
        Validate and create terrain calculations with RBAC checks.
        """
        equipment = serializer.validated_data['equipment']
        terrain_type = serializer.validated_data['terrain_type']
        
        # If user is an engineer, check if they're responsible for this equipment
        if hasattr(self.request.user, 'engineer_profile'):
            if equipment.responsible_user != self.request.user:
                raise serializers.ValidationError(
                    "You can only create terrain calculations for equipment you are responsible for."
                )
        
        # Validate that equipment doesn't already have this terrain type
        if TerrainLoadCalculation.objects.filter(
            equipment=equipment, 
            terrain_type=terrain_type
        ).exists():
            raise serializers.ValidationError({
                'terrain_type': 'This equipment already has a calculation for this terrain type.'
            })
        
        serializer.save()
