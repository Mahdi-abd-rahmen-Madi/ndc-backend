from django.shortcuts import render
from rest_framework import viewsets, filters, status, permissions, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
from .models import AntennaEquipment, AntennaSpecification, TerrainLoadCalculation
from api.permissions import IsAdminOrEngineerPermission, IsAdminOrResponsibleEngineerPermission
from .serializers import (
    AntennaEquipmentSerializer, AntennaEquipmentListSerializer,
    AntennaSpecificationSerializer, TerrainLoadCalculationSerializer
)
from .services import terrain_service
from .services_address import address_service
from .services import TerrainClassificationService
from .terrain_config_service import terrain_config_service


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


class TerrainConfigViewSet(viewsets.ViewSet):
    """ViewSet for terrain configuration management"""
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def config(self, request):
        """Get current terrain configuration"""
        try:
            config = terrain_config_service.load_config()
            return Response(config)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get configuration summary"""
        try:
            summary = terrain_config_service.get_config_summary()
            return Response(summary)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def clc_mappings(self, request):
        """Get CLC code to terrain mappings"""
        try:
            mappings = terrain_config_service.get_clc_code_mappings()
            return Response(mappings)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def classification_rules(self, request):
        """Get classification rules"""
        try:
            rules = terrain_config_service.get_classification_rules()
            return Response(rules)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def spatial_analysis(self, request):
        """Get spatial analysis configuration"""
        try:
            spatial_config = terrain_config_service.get_spatial_analysis_config()
            return Response(spatial_config)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def influence_percentages(self, request):
        """Get influence percentages"""
        try:
            influence = terrain_config_service.get_influence_percentages()
            return Response(influence)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrEngineerPermission])
    def update_config(self, request):
        """Update terrain configuration"""
        try:
            new_config = request.data
            success = terrain_config_service.update_config(new_config)
            
            if success:
                return Response({
                    'message': 'Configuration updated successfully',
                    'config': terrain_config_service.load_config()
                })
            else:
                return Response(
                    {'error': 'Failed to update configuration'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrEngineerPermission])
    def reset(self, request):
        """Reset configuration to defaults"""
        try:
            success = terrain_config_service.reset_to_defaults()
            
            if success:
                return Response({
                    'message': 'Configuration reset successfully',
                    'config': terrain_config_service.load_config()
                })
            else:
                return Response(
                    {'error': 'Failed to reset configuration'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def export(self, request):
        """Export configuration as JSON"""
        try:
            config_json = terrain_config_service.export_config()
            return Response({
                'config': config_json,
                'filename': 'terrain_config.json'
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrEngineerPermission])
    def import_config(self, request):
        """Import configuration from JSON"""
        try:
            config_json = request.data.get('config', '')
            if not config_json:
                return Response(
                    {'error': 'Configuration JSON is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            success = terrain_config_service.import_config(config_json)
            
            if success:
                return Response({
                    'message': 'Configuration imported successfully',
                    'config': terrain_config_service.load_config()
                })
            else:
                return Response(
                    {'error': 'Failed to import configuration'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def test_coordinates(self, request):
        """Test coordinates with current configuration"""
        try:
            longitude = float(request.data.get('longitude'))
            latitude = float(request.data.get('latitude'))
            
            from .services import TerrainClassificationService
            terrain_service = TerrainClassificationService()
            
            # Get detailed terrain classification information
            classification_details = terrain_service.get_terrain_classification_details(longitude, latitude)
            
            # Get region from coordinates
            region = terrain_service.get_region_from_coordinates(longitude, latitude)
            
            # Get spatial extent (using cached data if available)
            gdf = terrain_service._load_land_use_data()
            spatial_extent = terrain_service._calculate_spatial_extent_percentages(longitude, latitude, gdf)
            
            # Clean spatial extent data to handle np.float64 and nan values
            cleaned_spatial_extent = {}
            if spatial_extent:
                for key, value in spatial_extent.items():
                    if isinstance(value, (float, int)):
                        # Handle nan values and convert to regular Python float
                        if value != value:  # nan check
                            cleaned_spatial_extent[key] = 0.0
                        else:
                            cleaned_spatial_extent[key] = float(value)
                    else:
                        cleaned_spatial_extent[key] = value
            
            # Clean confidence score
            confidence_score = classification_details['confidence_score']
            if isinstance(confidence_score, (float, int)):
                if confidence_score != confidence_score:  # nan check
                    confidence_score = 0.0
                else:
                    confidence_score = float(confidence_score)
            
            return Response({
                'terrain_type': classification_details['terrain_type'],
                'base_terrain_type': classification_details['base_terrain_type'],
                'confidence_score': confidence_score,
                'detected_clc_codes': classification_details['detected_clc_codes'],
                'primary_clc_code': classification_details['primary_clc_code'],
                'region': {
                    'number': region,
                    'name': f"Region {region}" if region else "Unknown"
                },
                'coordinates': {
                    'longitude': float(longitude),
                    'latitude': float(latitude)
                },
                'spatial_extent': cleaned_spatial_extent,
                'applicable_rules': classification_details['applicable_rules'],
                'rule_explanations': classification_details['rule_explanations']
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def performance_metrics(self, request):
        """Get performance metrics for monitoring."""
        try:
            metrics = terrain_service.get_performance_metrics()
            return Response(metrics)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def reset_metrics(self, request):
        """Reset performance metrics."""
        try:
            terrain_service.reset_performance_metrics()
            return Response({'message': 'Performance metrics reset successfully'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def clear_cache(self, request):
        """Clear terrain classification cache."""
        try:
            pattern = request.data.get('pattern')
            terrain_service.clear_cache(pattern)
            return Response({'message': 'Cache cleared successfully'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def optimize_memory(self, request):
        """Optimize memory usage."""
        try:
            terrain_service.optimize_memory_usage()
            return Response({'message': 'Memory optimization completed'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def edge_cases(self, request):
        """Get configuration edge cases and warnings."""
        try:
            config = terrain_config_service.load_config()
            edge_cases = terrain_config_service.detect_edge_cases(config)
            return Response({
                'edge_cases': edge_cases,
                'edge_case_count': len(edge_cases)
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def terrain_confidence(self, request):
        """Get confidence score for terrain classification at coordinates."""
        try:
            longitude = float(request.query_params.get('longitude'))
            latitude = float(request.query_params.get('latitude'))
            
            confidence = terrain_service.get_terrain_confidence(longitude, latitude)
            
            return Response({
                'coordinates': {
                    'longitude': longitude,
                    'latitude': latitude
                },
                'confidence_score': confidence
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
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


class GeocodingSearchViewSet(viewsets.ViewSet):
    """ViewSet for geocoding search functionality"""
    permission_classes = [permissions.AllowAny]  # Allow public access for frontend
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search for addresses using geocoding API"""
        query = request.query_params.get('q', '').strip()
        limit = int(request.query_params.get('limit', 5))
        terrain_type = request.query_params.get('terrain_type', None)
        
        if not query:
            return Response(
                {'error': 'Search query parameter "q" is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            if terrain_type and terrain_type in address_service.terrain_search_terms:
                # Get addresses for specific terrain type
                addresses = address_service.get_random_addresses(limit, terrain_type)
                # Filter by search query if provided
                if query:
                    addresses = [
                        addr for addr in addresses 
                        if query.lower() in addr.get('city', '').lower() or 
                           query.lower() in addr.get('label', '').lower()
                    ]
            else:
                # Direct search using geocoding API
                addresses = address_service.search_addresses(query, limit)
                # Convert to frontend format
                formatted_addresses = []
                for addr in addresses:
                    props = addr.get('properties', {})
                    geometry = addr.get('geometry', {})
                    coordinates = geometry.get('coordinates', [])
                    
                    if len(coordinates) == 2:
                        formatted_addr = {
                            'label': props.get('label', ''),
                            'name': props.get('name', ''),
                            'postcode': props.get('postcode', ''),
                            'city': props.get('city', ''),
                            'context': props.get('context', ''),
                            'type': props.get('type', ''),
                            'importance': props.get('importance', 0),
                            'longitude': coordinates[0],
                            'latitude': coordinates[1],
                            'target_terrain': None
                        }
                        formatted_addresses.append(formatted_addr)
                
                addresses = formatted_addresses
            
            return Response({
                'results': addresses,
                'count': len(addresses),
                'query': query,
                'terrain_type': terrain_type
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def terrain_types(self, request):
        """Get available terrain types with descriptions"""
        terrain_descriptions = {
            '0': 'Water/coastal areas',
            'II': 'Open countryside',
            'IIIa': 'Campaign with obstacles',
            'IIIb': 'Urbanized/industrial',
            'IV': 'Dense urban'
        }
        
        return Response({
            'terrain_types': terrain_descriptions
        })
    
    @action(detail=False, methods=['get'])
    def random_addresses(self, request):
        """Get random addresses for testing"""
        count = int(request.query_params.get('count', 10))
        terrain_type = request.query_params.get('terrain_type', None)
        
        try:
            addresses = address_service.get_random_addresses(count, terrain_type)
            return Response({
                'results': addresses,
                'count': len(addresses),
                'terrain_type': terrain_type
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def terrain_map_view(request):
    """Render the terrain classification map page"""
    return render(request, 'geodata/terrain_map.html')


def region_map_view(request):
    """Render the region visualization map page"""
    return render(request, 'geodata/region_map.html')


class RegionGeoJSONViewSet(viewsets.ViewSet):
    """ViewSet for serving region boundaries as GeoJSON"""
    permission_classes = [permissions.AllowAny]  # Allow public access for frontend
    
    @action(detail=False, methods=['get'])
    def regions(self, request):
        """Get all region boundaries as GeoJSON from actual wind coefficient data"""
        try:
            import json
            from collections import defaultdict
            from django.conf import settings
            import os
            
            # Load the actual GeoJSON file
            geojson_path = os.path.join(settings.BASE_DIR, 'backend', 'data', 'ec1_windCoeff.geojson')
            
            with open(geojson_path, 'r') as f:
                data = json.load(f)
            
            # Group features by V_B0 value (region)
            regions = defaultdict(list)
            region_mapping = {
                22: 1,  # Region 1
                24: 2,  # Region 2
                26: 3,  # Region 3
                28: 4   # Region 4
            }
            
            region_descriptions = {
                1: "Northern France (V_B0: 22)",
                2: "Western France (V_B0: 24)", 
                3: "Central France (V_B0: 26)",
                4: "Eastern France (V_B0: 28)"
            }
            
            # Group all geometries by their V_B0 value
            for feature in data.get('features', []):
                v_b0 = feature.get('properties', {}).get('V_B0')
                if v_b0 and v_b0 in region_mapping:
                    region_id = region_mapping[v_b0]
                    # Add the feature to the appropriate region
                    regions[region_id].append(feature.get('geometry'))
            
            # Create combined features for each region
            combined_features = []
            for region_id in [1, 2, 3, 4]:
                if region_id in regions and regions[region_id]:
                    # Combine all geometries for this region
                    combined_feature = {
                        "type": "Feature",
                        "properties": {
                            "region_id": region_id,
                            "name": f"Region {region_id}",
                            "description": region_descriptions[region_id],
                            "v_b0_value": {v: k for k, v in region_mapping.items()}[region_id]
                        },
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": []
                        }
                    }
                    
                    # Collect all polygon coordinates
                    all_polygons = []
                    for geom in regions[region_id]:
                        if geom.get('type') == 'MultiPolygon':
                            all_polygons.extend(geom.get('coordinates', []))
                        elif geom.get('type') == 'Polygon':
                            all_polygons.append(geom.get('coordinates', []))
                    
                    combined_feature["geometry"]["coordinates"] = all_polygons
                    combined_feature["properties"]["feature_count"] = len(all_polygons)
                    combined_features.append(combined_feature)
            
            regions_geojson = {
                "type": "FeatureCollection",
                "features": combined_features
            }
            
            return Response(regions_geojson)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def region(self, request):
        """Get specific region boundary as GeoJSON from actual wind coefficient data"""
        region_id = request.query_params.get('region_id')
        
        if not region_id:
            return Response(
                {'error': 'region_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            import json
            from collections import defaultdict
            from django.conf import settings
            import os
            
            region_id = int(region_id)
            if region_id not in [1, 2, 3, 4]:
                return Response(
                    {'error': 'Invalid region_id. Must be 1, 2, 3, or 4'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Load the actual GeoJSON file
            geojson_path = os.path.join(settings.BASE_DIR, 'backend', 'data', 'ec1_windCoeff.geojson')
            
            with open(geojson_path, 'r') as f:
                data = json.load(f)
            
            # Group features by V_B0 value (region)
            region_mapping = {
                22: 1,  # Region 1
                24: 2,  # Region 2
                26: 3,  # Region 3
                28: 4   # Region 4
            }
            
            region_descriptions = {
                1: "Northern France (V_B0: 22)",
                2: "Western France (V_B0: 24)", 
                3: "Central France (V_B0: 26)",
                4: "Eastern France (V_B0: 28)"
            }
            
            # Find the V_B0 value for this region
            v_b0_value = {v: k for k, v in region_mapping.items()}[region_id]
            
            # Collect all geometries for this specific region
            all_polygons = []
            for feature in data.get('features', []):
                v_b0 = feature.get('properties', {}).get('V_B0')
                if v_b0 == v_b0_value:
                    geom = feature.get('geometry')
                    if geom.get('type') == 'MultiPolygon':
                        all_polygons.extend(geom.get('coordinates', []))
                    elif geom.get('type') == 'Polygon':
                        all_polygons.append(geom.get('coordinates', []))
            
            # Create the region feature
            region_feature = {
                "type": "Feature",
                "properties": {
                    "region_id": region_id,
                    "name": f"Region {region_id}",
                    "description": region_descriptions[region_id],
                    "v_b0_value": v_b0_value,
                    "feature_count": len(all_polygons)
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": all_polygons
                }
            }
            
            return Response(region_feature)
            
        except ValueError:
            return Response(
                {'error': 'Invalid region_id format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@csrf_exempt
@require_http_methods(["POST"])
def terrain_classification_api(request):
    """API endpoint for terrain classification at coordinates"""
    try:
        data = json.loads(request.body)
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
        
        if not latitude or not longitude:
            return JsonResponse(
                {'error': 'Latitude and longitude are required'},
                status=400
            )
        
        # Initialize terrain classification service
        terrain_service = TerrainClassificationService()
        
        # Get terrain type at coordinates
        terrain_type = terrain_service.get_terrain_type_at_coordinates(longitude, latitude)
        
        if terrain_type is None:
            return JsonResponse({
                'terrain_type': None,
                'error': 'No terrain data found at these coordinates',
                'latitude': latitude,
                'longitude': longitude
            })
        
        # Get spatial extent percentages
        gdf = terrain_service._load_land_use_data()
        spatial_extent = terrain_service._calculate_spatial_extent_percentages(
            longitude, latitude, gdf
        )
        
        return JsonResponse({
            'terrain_type': terrain_type,
            'spatial_extent': spatial_extent,
            'latitude': latitude,
            'longitude': longitude
        })
        
    except ValueError as e:
        return JsonResponse(
            {'error': f'Invalid coordinates: {str(e)}'},
            status=400
        )
    except Exception as e:
        return JsonResponse(
            {'error': f'Server error: {str(e)}'},
            status=500
        )
