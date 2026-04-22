from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import AntennaEquipment, AntennaSpecification, TerrainLoadCalculation, TerrainDocumentation
from api.permissions import IsAdminOrResponsibleEngineerPermission


class AntennaSpecificationInline(admin.TabularInline):
    model = AntennaSpecification
    extra = 0
    min_num = 0


class TerrainLoadCalculationInline(admin.TabularInline):
    model = TerrainLoadCalculation
    extra = 0
    min_num = 0
    fields = ['terrain_type', 'material_specification', 'section_material', 'documentation']


@admin.register(AntennaEquipment)
class AntennaEquipmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'responsible_display', 'region', 'building_height', 'mast_height', 'created_at']
    list_filter = ['region', 'status', 'responsible_user', 'created_at']
    search_fields = ['name', 'responsible_person', 'responsible_user__username', 'sub_elements', 'item_id']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [AntennaSpecificationInline, TerrainLoadCalculationInline]
    
    def get_queryset(self, request):
        """Filter queryset based on user permissions"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Engineers can only see equipment they're responsible for
        if hasattr(request.user, 'engineer_profile'):
            return qs.filter(responsible_user=request.user)
        return qs.none()
    
    def has_change_permission(self, request, obj=None):
        """Check if user can change equipment"""
        if request.user.is_superuser:
            return True
        if obj and hasattr(request.user, 'engineer_profile'):
            return obj.responsible_user == request.user
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Check if user can delete equipment"""
        return self.has_change_permission(request, obj)
    
    def responsible_display(self, obj):
        """Display both responsible_user and responsible_person for compatibility"""
        if obj.responsible_user:
            return f"{obj.responsible_user.username} ({obj.responsible_person})"
        return obj.responsible_person or 'Not assigned'
    responsible_display.short_description = 'Responsible Person'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'sub_elements', 'responsible_user', 'responsible_person', 'status', 'date', 'region')
        }),
        ('Technical Specifications', {
            'fields': ('building_height', 'mast_height')
        }),
        ('Additional Information', {
            'fields': ('comments', 'item_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AntennaSpecification)
class AntennaSpecificationAdmin(admin.ModelAdmin):
    list_display = ['equipment', 'antenna_type', 'height_mm', 'width_mm', 'thickness_mm', 'weight_dan']
    list_filter = ['antenna_type', 'created_at']
    search_fields = ['equipment__name', 'antenna_type']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Equipment Information', {
            'fields': ('equipment', 'antenna_type')
        }),
        ('Dimensions', {
            'fields': ('height_mm', 'width_mm', 'thickness_mm')
        }),
        ('Weight', {
            'fields': ('weight_dan',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TerrainLoadCalculation)
class TerrainLoadCalculationAdmin(admin.ModelAdmin):
    list_display = ['equipment', 'terrain_type', 'material_specification', 'section_material', 'created_at']
    list_filter = ['terrain_type', 'created_at']
    search_fields = ['equipment__name', 'terrain_type', 'section_material', 'material_specification']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Equipment Information', {
            'fields': ('equipment', 'terrain_type')
        }),
        ('Material Information', {
            'fields': ('material_specification', 'section_material')
        }),
        ('Load Data', {
            'fields': ('load_calculations',)
        }),
        ('Documentation', {
            'fields': ('documentation',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TerrainDocumentation)
class TerrainDocumentationAdmin(admin.ModelAdmin):
    list_display = ['equipment', 'terrain_type', 'document_count', 'upload_date', 'created_at']
    list_filter = ['terrain_type', 'upload_date', 'created_at']
    search_fields = ['equipment__name', 'terrain_type']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Equipment Information', {
            'fields': ('equipment', 'terrain_type')
        }),
        ('Documents', {
            'fields': ('document_urls', 'document_types')
        }),
        ('Metadata', {
            'fields': ('upload_date',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def document_count(self, obj):
        return len(obj.get_document_list())
    document_count.short_description = 'Number of Documents'
