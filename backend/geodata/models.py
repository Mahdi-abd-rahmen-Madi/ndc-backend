from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _


class AntennaEquipment(models.Model):
    """Represents antenna equipment and mounting systems"""
    
    REGION_CHOICES = [
        (1, "Region 1"),
        (2, "Region 2"), 
        (3, "Region 3"),
        (4, "Region 4"),
    ]
    
    # Mapping from V_B0 values to region numbers
    V_B0_TO_REGION = {
        22: 1,  # Region 1
        24: 2,  # Region 2
        26: 3,  # Region 3
        28: 4,  # Region 4
    }
    
    # Terrain classification mapping from CLC Code_18 to terrain types
    CLC_CODE_TO_TERRAIN = {
        # Terrain 0: Water/coastal areas
        '511': '0',   # Water courses
        '512': '0',   # Water bodies  
        '521': '0',   # Coastal lagoons
        '522': '0',   # Estuaries
        '523': '0',   # Sea and ocean
        '423': '0',   # Intertidal flats
        '421': '0',   # Salt marshes
        '422': '0',   # Salines
        
        # Terrain II: Open countryside (rase campagne)
        '211': 'II',   # Non-irrigated arable land
        '212': 'II',   # Permanently irrigated land
        '213': 'II',   # Rice fields
        '231': 'II',   # Pastures
        '331': 'II',   # Beaches - dunes - sands
        '332': 'II',   # Bare rocks
        '333': 'II',   # Sparsely vegetated areas
        '334': 'II',   # Burnt areas
        '335': 'II',   # Glaciers and perpetual snow
        
        # Terrain IIIa: Campaign with obstacles (bocage, habitat dispersé)
        '221': 'IIIa', # Vineyards
        '222': 'IIIa', # Fruit trees and berry plantations
        '223': 'IIIa', # Olive groves
        '241': 'IIIa', # Annual crops associated with permanent crops
        '242': 'IIIa', # Complex cultivation patterns
        '243': 'IIIa', # Land principally occupied by agriculture with significant areas of natural vegetation
        '244': 'IIIa', # Agro-forestry areas
        '311': 'IIIa', # Broad-leaved forest
        '312': 'IIIa', # Coniferous forest
        '313': 'IIIa', # Mixed forest
        '321': 'IIIa', # Natural grasslands
        '322': 'IIIa', # Moors and heathland
        '323': 'IIIa', # Sclerophyllous vegetation
        '324': 'IIIa', # Transitional woodland-shrub
        '411': 'IIIa', # Inland marshes
        '412': 'IIIa', # Peat bogs
        
        # Terrain IIIb: Urbanized/industrial zones (bocage denser)
        '121': 'IIIb', # Industrial or commercial units
        '122': 'IIIb', # Road and rail networks and associated land
        '123': 'IIIb', # Port areas
        '124': 'IIIb', # Airports
        '131': 'IIIb', # Mineral extraction sites
        '132': 'IIIb', # Dump sites
        '133': 'IIIb', # Construction sites
        '142': 'IIIb', # Sport and leisure facilities
        
        # Terrain IV: Dense urban zones
        '111': 'IV',   # Continuous urban fabric
        '112': 'IV',   # Discontinuous urban fabric
        '141': 'IV',   # Green urban areas
    }
    
    name = models.CharField(max_length=255, verbose_name=_("Equipment Name"))
    sub_elements = models.CharField(max_length=255, blank=True, verbose_name=_("Sub Elements"))
    responsible_person = models.CharField(max_length=255, blank=True, verbose_name=_("Responsible Person"))
    responsible_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='equipment_responsible', verbose_name=_("Responsible User"))
    status = models.CharField(max_length=50, blank=True, verbose_name=_("Status"))
    date = models.DateField(null=True, blank=True, verbose_name=_("Date"))
    region = models.IntegerField(choices=REGION_CHOICES, blank=True, null=True, verbose_name=_("Region"))
    building_height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name=_("Building Height (m)"))
    mast_height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name=_("Mast Height (m)"))
    comments = models.TextField(blank=True, verbose_name=_("Comments"))
    item_id = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name=_("Item ID"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Antenna Equipment")
        verbose_name_plural = _("Antenna Equipment")
        ordering = ['name']

    @classmethod
    def get_region_from_vb0(cls, vb0_value):
        """Get region number from V_B0 value"""
        return cls.V_B0_TO_REGION.get(vb0_value)
    
    @classmethod
    def get_terrain_from_clc_code(cls, clc_code):
        """Get terrain type from CLC Code_18 value"""
        return cls.CLC_CODE_TO_TERRAIN.get(str(clc_code))
    
    @classmethod
    def get_all_terrain_mappings(cls):
        """Get all terrain mappings for reference"""
        return cls.CLC_CODE_TO_TERRAIN.copy()
    
    def __str__(self):
        return self.name


class AntennaSpecification(models.Model):
    """Represents technical specifications for 4G/5G antennas"""
    ANTENNA_TYPES = [
        ('4G', '4G'),
        ('5G', '5G'),
    ]

    equipment = models.ForeignKey(AntennaEquipment, on_delete=models.CASCADE, related_name='specifications', verbose_name=_("Equipment"))
    antenna_type = models.CharField(max_length=10, choices=ANTENNA_TYPES, verbose_name=_("Antenna Type"))
    height_mm = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_("Height (mm)"))
    width_mm = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_("Width (mm)"))
    thickness_mm = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_("Thickness (mm)"))
    weight_dan = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_("Weight (daN)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Antenna Specification")
        verbose_name_plural = _("Antenna Specifications")
        ordering = ['equipment', 'antenna_type']
        unique_together = ['equipment', 'antenna_type']

    def __str__(self):
        return f"{self.equipment.name} - {self.antenna_type}"


class TerrainDocumentation(models.Model):
    """Represents documentation files for terrain calculations"""
    TERRAIN_TYPES = [
        ('0', 'Terrain 0'),
        ('II', 'Terrain II'),
        ('IIIa', 'Terrain IIIa'),
        ('IIIb', 'Terrain IIIb'),
        ('IV', 'Terrain IV'),
    ]

    equipment = models.ForeignKey(AntennaEquipment, on_delete=models.CASCADE, related_name='terrain_documentations', verbose_name=_("Equipment"))
    terrain_type = models.CharField(max_length=10, choices=TERRAIN_TYPES, verbose_name=_("Terrain Type"))
    document_urls = models.TextField(help_text=_("Comma-separated URLs for terrain calculation documents"), verbose_name=_("Document URLs"))
    document_types = models.JSONField(default=list, blank=True, help_text=_("List of document file extensions (e.g., ['.docx', '.rtd'])"), verbose_name=_("Document Types"))
    upload_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Upload Date"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Terrain Documentation")
        verbose_name_plural = _("Terrain Documentations")
        ordering = ['equipment', 'terrain_type']
        unique_together = ['equipment', 'terrain_type']

    def __str__(self):
        return f"{self.equipment.name} - {self.terrain_type} Documentation"

    def get_document_list(self):
        """Parse document URLs into a list"""
        if self.document_urls:
            return [url.strip() for url in self.document_urls.split(',') if url.strip()]
        return []


class TerrainLoadCalculation(models.Model):
    """Represents terrain load calculations for equipment"""
    TERRAIN_TYPES = [
        ('0', 'Terrain 0'),
        ('II', 'Terrain II'),
        ('IIIa', 'Terrain IIIa'),
        ('IIIb', 'Terrain IIIb'),
        ('IV', 'Terrain IV'),
    ]

    equipment = models.ForeignKey(AntennaEquipment, on_delete=models.CASCADE, related_name='terrain_calculations', verbose_name=_("Equipment"))
    terrain_type = models.CharField(max_length=10, choices=TERRAIN_TYPES, verbose_name=_("Terrain Type"))
    section_material = models.CharField(max_length=255, blank=True, verbose_name=_("Section Material"))
    material_specification = models.CharField(max_length=255, blank=True, help_text=_("Material section specification (e.g., '139x6.3mm')"), verbose_name=_("Material Specification"))
    load_calculations = models.JSONField(default=dict, blank=True, verbose_name=_("Load Calculations"))
    documentation = models.OneToOneField(TerrainDocumentation, on_delete=models.SET_NULL, null=True, blank=True, related_name='load_calculation', verbose_name=_("Documentation"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Terrain Load Calculation")
        verbose_name_plural = _("Terrain Load Calculations")
        ordering = ['equipment', 'terrain_type']
        unique_together = ['equipment', 'terrain_type']

    def __str__(self):
        return f"{self.equipment.name} - {self.terrain_type}"
