from django.test import TestCase
from decimal import Decimal
from django.db import IntegrityError
from geodata.models import AntennaEquipment, AntennaSpecification, TerrainLoadCalculation


class AntennaEquipmentTest(TestCase):
    def test_create_equipment(self):
        """Test creating antenna equipment"""
        equipment = AntennaEquipment.objects.create(
            name="Test Equipment",
            responsible_person="John Doe",
            building_height=Decimal('15.5'),
            mast_height=Decimal('4.0')
        )
        self.assertEqual(equipment.name, "Test Equipment")
        self.assertEqual(equipment.responsible_person, "John Doe")
        self.assertEqual(equipment.building_height, Decimal('15.5'))
        self.assertEqual(equipment.mast_height, Decimal('4.0'))
        self.assertEqual(str(equipment), "Test Equipment")

    def test_equipment_with_specifications(self):
        """Test equipment with related specifications"""
        equipment = AntennaEquipment.objects.create(
            name="Test Equipment",
            responsible_person="John Doe"
        )
        
        # Create 4G specification
        spec_4g = AntennaSpecification.objects.create(
            equipment=equipment,
            antenna_type='4G',
            height_mm=Decimal('210'),
            width_mm=Decimal('45'),
            thickness_mm=Decimal('10'),
            weight_dan=Decimal('5.5')
        )
        
        # Create 5G specification
        spec_5g = AntennaSpecification.objects.create(
            equipment=equipment,
            antenna_type='5G',
            height_mm=Decimal('250'),
            width_mm=Decimal('50'),
            thickness_mm=Decimal('12'),
            weight_dan=Decimal('7.2')
        )
        
        self.assertEqual(equipment.specifications.count(), 2)
        self.assertIn(spec_4g, equipment.specifications.all())
        self.assertIn(spec_5g, equipment.specifications.all())
        self.assertEqual(str(spec_4g), "Test Equipment - 4G")
        self.assertEqual(str(spec_5g), "Test Equipment - 5G")

    def test_equipment_with_terrain_calculations(self):
        """Test equipment with related terrain calculations"""
        equipment = AntennaEquipment.objects.create(
            name="Test Equipment",
            responsible_person="John Doe"
        )
        
        # Create terrain calculations
        terrain_0 = TerrainLoadCalculation.objects.create(
            equipment=equipment,
            terrain_type='0',
            section_material='139x4mm',
            load_calculations={'terrain_value': 'test_value'}
        )
        
        terrain_iv = TerrainLoadCalculation.objects.create(
            equipment=equipment,
            terrain_type='IV',
            section_material='150x5mm',
            load_calculations={'terrain_value': 'test_value_iv'}
        )
        
        self.assertEqual(equipment.terrain_calculations.count(), 2)
        self.assertIn(terrain_0, equipment.terrain_calculations.all())
        self.assertIn(terrain_iv, equipment.terrain_calculations.all())
        self.assertEqual(str(terrain_0), "Test Equipment - 0")
        self.assertEqual(str(terrain_iv), "Test Equipment - IV")

    def test_antenna_specification_unique_constraint(self):
        """Test unique constraint on antenna specifications"""
        equipment = AntennaEquipment.objects.create(
            name="Test Equipment",
            responsible_person="John Doe"
        )
        
        # Create first 4G specification
        AntennaSpecification.objects.create(
            equipment=equipment,
            antenna_type='4G',
            height_mm=Decimal('210'),
            width_mm=Decimal('45'),
            thickness_mm=Decimal('10'),
            weight_dan=Decimal('5.5')
        )
        
        # Try to create duplicate 4G specification - should fail
        with self.assertRaises(IntegrityError):
            AntennaSpecification.objects.create(
                equipment=equipment,
                antenna_type='4G',
                height_mm=Decimal('220'),
                width_mm=Decimal('50'),
                thickness_mm=Decimal('12'),
                weight_dan=Decimal('6.0')
            )

    def test_terrain_calculation_unique_constraint(self):
        """Test unique constraint on terrain calculations"""
        equipment = AntennaEquipment.objects.create(
            name="Test Equipment",
            responsible_person="John Doe"
        )
        
        # Create first terrain calculation
        TerrainLoadCalculation.objects.create(
            equipment=equipment,
            terrain_type='0',
            section_material='139x4mm'
        )
        
        # Try to create duplicate terrain calculation - should fail
        with self.assertRaises(IntegrityError):
            TerrainLoadCalculation.objects.create(
                equipment=equipment,
                terrain_type='0',
                section_material='140x4mm'
            )

    def test_antenna_specification_choices(self):
        """Test antenna type choices"""
        equipment = AntennaEquipment.objects.create(
            name="Test Equipment",
            responsible_person="John Doe"
        )
        
        # Valid antenna types
        for antenna_type in ['4G', '5G']:
            spec = AntennaSpecification.objects.create(
                equipment=equipment,
                antenna_type=antenna_type,
                height_mm=Decimal('200'),
                width_mm=Decimal('40'),
                thickness_mm=Decimal('8'),
                weight_dan=Decimal('5.0')
            )
            self.assertEqual(spec.antenna_type, antenna_type)

    def test_terrain_calculation_choices(self):
        """Test terrain type choices"""
        equipment = AntennaEquipment.objects.create(
            name="Test Equipment",
            responsible_person="John Doe"
        )
        
        # Valid terrain types
        for terrain_type in ['0', 'II', 'IIIa', 'IIIb', 'IV']:
            terrain = TerrainLoadCalculation.objects.create(
                equipment=equipment,
                terrain_type=terrain_type,
                section_material='test_material'
            )
            self.assertEqual(terrain.terrain_type, terrain_type)
