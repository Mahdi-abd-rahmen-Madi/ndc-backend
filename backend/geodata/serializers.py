from rest_framework import serializers
from django.contrib.auth.models import User
from .models import AntennaEquipment, AntennaSpecification, TerrainLoadCalculation


class ResponsibleUserSerializer(serializers.ModelSerializer):
    """Lightweight serializer for responsible user information"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class AntennaSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AntennaSpecification
        fields = [
            'id', 'equipment', 'antenna_type', 'height_mm', 'width_mm',
            'thickness_mm', 'weight_dan', 'created_at', 'updated_at'
        ]


class TerrainLoadCalculationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerrainLoadCalculation
        fields = [
            'id', 'equipment', 'terrain_type', 'section_material',
            'load_calculations', 'created_at', 'updated_at'
        ]


class AntennaEquipmentSerializer(serializers.ModelSerializer):
    specifications = AntennaSpecificationSerializer(many=True, read_only=True)
    terrain_calculations = TerrainLoadCalculationSerializer(many=True, read_only=True)
    responsible_user = ResponsibleUserSerializer(read_only=True)

    class Meta:
        model = AntennaEquipment
        fields = [
            'id', 'name', 'sub_elements', 'responsible_person', 'responsible_user',
            'status', 'date', 'region', 'building_height', 'mast_height', 'comments',
            'item_id', 'specifications', 'terrain_calculations',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_building_height(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Building height must be positive.")
        return value

    def validate_mast_height(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Mast height must be positive.")
        return value


class AntennaEquipmentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    specifications_count = serializers.SerializerMethodField()
    terrain_calculations_count = serializers.SerializerMethodField()
    responsible_user = ResponsibleUserSerializer(read_only=True)
    responsible_display = serializers.SerializerMethodField()

    class Meta:
        model = AntennaEquipment
        fields = [
            'id', 'name', 'responsible_person', 'responsible_user', 'responsible_display',
            'region', 'building_height', 'mast_height', 'specifications_count', 
            'terrain_calculations_count', 'created_at'
        ]

    def get_specifications_count(self, obj):
        return obj.specifications.count()

    def get_terrain_calculations_count(self, obj):
        return obj.terrain_calculations.count()
    
    def get_responsible_display(self, obj):
        """Display both responsible_user and responsible_person for compatibility"""
        if obj.responsible_user:
            return f"{obj.responsible_user.username}"
        return obj.responsible_person or 'Not assigned'
