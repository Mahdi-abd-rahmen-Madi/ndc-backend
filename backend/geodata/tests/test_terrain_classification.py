"""
Comprehensive tests for terrain classification system with address verification.
"""
import json
from decimal import Decimal
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock
from geodata.models import AntennaEquipment, AntennaSpecification, TerrainLoadCalculation
from geodata.services import terrain_service
from geodata.services_address import address_service


class TerrainClassificationTest(TestCase):
    """Test terrain classification functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.test_coordinates = [
            (2.3522, 48.8566),  # Paris - Terrain IV
            (4.8322, 45.7578),  # Lyon - Terrain IV
            (5.3698, 43.2965),  # Marseille - Terrain IV
            (2.0, 47.0),        # Central France - Terrain II
            (6.8652, 45.8326),  # Alps - Terrain II
            (-4.5, 48.4),       # Brittany - Terrain IIIa
            (0.5, 44.5),       # Southwest France - Terrain IIIa
            (3.0, 43.6),       # Mediterranean coast - Terrain 0
        ]
    
    def test_terrain_mapping_completeness(self):
        """Test that all CLC codes are mapped to terrain types."""
        all_mappings = AntennaEquipment.get_all_terrain_mappings()
        
        # Check that we have mappings for all 43 codes
        expected_codes = [
            '111', '112', '121', '122', '123', '124', '131', '132', '133', '141', '142',
            '211', '212', '213', '221', '222', '223', '231', '241', '242', '243', '244',
            '311', '312', '313', '321', '322', '323', '324', '331', '332', '333', '334', '335',
            '411', '412', '421', '422', '423', '511', '512', '521', '522', '523'
        ]
        
        for code in expected_codes:
            self.assertIn(code, all_mappings, f"CLC code {code} not mapped")
        
        # Check that all terrain types are represented
        terrain_types = set(all_mappings.values())
        expected_terrain_types = {'0', 'II', 'IIIa', 'IIIb', 'IV'}
        self.assertEqual(terrain_types, expected_terrain_types)
    
    def test_terrain_classification_accuracy(self):
        """Test terrain classification for known locations."""
        test_cases = [
            # (longitude, latitude, expected_terrain, description)
            (2.3522, 48.8566, 'IV', 'Paris - dense urban'),
            (4.8322, 45.7578, 'IV', 'Lyon - dense urban'),
            (2.0, 47.0, 'II', 'Central France - open countryside'),
            (6.8652, 45.8326, 'II', 'Alps - mountain/open terrain'),
            (-4.5, 48.4, 'IIIa', 'Brittany - rural with obstacles'),
            (3.0, 43.6, '0', 'Mediterranean coast - water/coastal'),
        ]
        
        for lon, lat, expected, description in test_cases:
            with self.subTest(location=description):
                terrain = terrain_service.get_terrain_type_at_coordinates(lon, lat)
                self.assertEqual(terrain, expected,
                               f"Expected {expected} for {description}, got {terrain}")
    
    def test_terrain_service_caching(self):
        """Test that terrain service caching works correctly."""
        lon, lat = 2.3522, 48.8566
        
        # First call should compute result
        terrain1 = terrain_service.get_terrain_type_at_coordinates(lon, lat)
        
        # Second call should use cache
        terrain2 = terrain_service.get_terrain_type_at_coordinates(lon, lat)
        
        self.assertEqual(terrain1, terrain2)
        self.assertIsNotNone(terrain1)
    
    def test_terrain_statistics(self):
        """Test terrain statistics calculation."""
        stats = terrain_service.get_terrain_statistics()
        
        # Check that all terrain types are present
        expected_terrains = ['0', 'II', 'IIIa', 'IIIb', 'IV']
        for terrain in expected_terrains:
            self.assertIn(terrain, stats, f"Terrain {terrain} missing from statistics")
        
        # Check that percentages sum to approximately 100%
        total_percentage = sum(data['percentage'] for data in stats.values())
        self.assertAlmostEqual(total_percentage, 100.0, places=1)
        
        # Check that counts are positive
        for terrain, data in stats.items():
            self.assertGreater(data['count'], 0, f"Terrain {terrain} should have positive count")
            self.assertGreater(data['percentage'], 0, f"Terrain {terrain} should have positive percentage")
    
    def test_invalid_coordinates(self):
        """Test terrain classification with invalid coordinates."""
        # Outside France bounds
        terrain1 = terrain_service.get_terrain_type_at_coordinates(0, 0)
        terrain2 = terrain_service.get_terrain_type_at_coordinates(100, 100)
        
        # Should return None for invalid coordinates
        self.assertIsNone(terrain1)
        self.assertIsNone(terrain2)
    
    def test_batch_classification(self):
        """Test batch terrain classification."""
        coordinates = [(2.3522, 48.8566), (4.8322, 45.7578), (2.0, 47.0)]
        
        results = terrain_service.batch_classify_coordinates(coordinates)
        
        self.assertEqual(len(results), 3)
        
        for result in results:
            self.assertIn('coordinates', result)
            self.assertIn('terrain_type', result)
            self.assertIsNotNone(result['terrain_type'])


class AddressGenerationTest(TestCase):
    """Test address generation and geocoding functionality."""
    
    @patch('geodata.services_address.requests.get')
    def test_address_search_success(self, mock_get):
        """Test successful address search."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'features': [{
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [2.3522, 48.8566]},
                'properties': {
                    'label': 'Paris, France',
                    'name': 'Paris',
                    'postcode': '75001',
                    'city': 'Paris',
                    'context': '75, Paris, Île-de-France',
                    'type': 'municipality',
                    'importance': 0.67303
                }
            }]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        addresses = address_service.search_addresses('Paris')
        
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0]['properties']['label'], 'Paris, France')
        self.assertEqual(addresses[0]['geometry']['coordinates'], [2.3522, 48.8566])
    
    @patch('geodata.services_address.requests.get')
    def test_address_search_error(self, mock_get):
        """Test address search error handling."""
        mock_get.side_effect = Exception("API Error")
        
        addresses = address_service.search_addresses('Paris')
        
        self.assertEqual(len(addresses), 0)
    
    def test_coordinate_validation(self):
        """Test coordinate validation."""
        # Valid France coordinates
        self.assertTrue(address_service.validate_coordinates(2.3522, 48.8566))
        self.assertTrue(address_service.validate_coordinates(-4.5, 48.4))
        
        # Invalid coordinates
        self.assertFalse(address_service.validate_coordinates(0, 0))
        self.assertFalse(address_service.validate_coordinates(100, 100))
        self.assertFalse(address_service.validate_coordinates(-10, 60))
    
    def test_terrain_search_terms(self):
        """Test that terrain search terms are properly categorized."""
        for terrain_type, search_terms in address_service.terrain_search_terms.items():
            self.assertIsInstance(search_terms, list)
            self.assertGreater(len(search_terms), 0)
            
            # Test that search terms are strings
            for term in search_terms:
                self.assertIsInstance(term, str)
                self.assertGreater(len(term), 0)
        
        # Check all terrain types are covered
        expected_terrains = ['0', 'II', 'IIIa', 'IIIb', 'IV']
        for terrain in expected_terrains:
            self.assertIn(terrain, address_service.terrain_search_terms)
    
    def test_french_cities_list(self):
        """Test French cities list."""
        cities = address_service.french_cities
        
        self.assertIsInstance(cities, list)
        self.assertGreater(len(cities), 50)  # Should have many cities
        
        # Check some major cities are included
        major_cities = ['Paris', 'Lyon', 'Marseille', 'Toulouse', 'Nice']
        for city in major_cities:
            self.assertIn(city, cities)


class IntegrationTest(TestCase):
    """Integration tests for the complete system."""
    
    def setUp(self):
        """Set up integration test data."""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test equipment with coordinates
        self.equipment = AntennaEquipment.objects.create(
            name='Test Equipment Paris',
            responsible_user=self.user,
            building_height=Decimal('15.0'),
            mast_height=Decimal('4.0')
        )
        
        # Add coordinates dynamically (these would normally come from address geocoding)
        self.equipment.longitude = 2.3522
        self.equipment.latitude = 48.8566
    
    def test_equipment_terrain_classification(self):
        """Test terrain classification for equipment."""
        # Mock the equipment coordinates
        with patch.object(self.equipment, 'longitude', 2.3522), \
             patch.object(self.equipment, 'latitude', 48.8566):
            
            terrain = terrain_service.get_terrain_type_for_equipment(self.equipment)
            
            # Paris should be classified as Terrain IV (dense urban)
            self.assertEqual(terrain, 'IV')
    
    def test_complete_workflow(self):
        """Test complete workflow from address to terrain classification."""
        # This would be a complete integration test
        # 1. Generate address
        # 2. Geocode to coordinates
        # 3. Classify terrain
        # 4. Create equipment with terrain info
        # 5. Generate load calculations
        
        # For now, test the terrain classification part
        test_coordinates = [(2.3522, 48.8566), (4.8322, 45.7578)]
        
        for lon, lat in test_coordinates:
            terrain = terrain_service.get_terrain_type_at_coordinates(lon, lat)
            self.assertIsNotNone(terrain)
            self.assertIn(terrain, ['0', 'II', 'IIIa', 'IIIb', 'IV'])
    
    def test_terrain_load_calculation_integration(self):
        """Test integration with terrain load calculations."""
        # Create terrain calculations for all terrain types
        terrain_types = ['0', 'II', 'IIIa', 'IIIb', 'IV']
        
        for terrain_type in terrain_types:
            TerrainLoadCalculation.objects.create(
                equipment=self.equipment,
                terrain_type=terrain_type,
                section_material=f'Test material for {terrain_type}',
                load_calculations={'test_value': terrain_type}
            )
        
        # Verify all terrain types are present
        self.assertEqual(self.equipment.terrain_calculations.count(), 5)
        
        for terrain_type in terrain_types:
            self.assertTrue(
                self.equipment.terrain_calculations.filter(terrain_type=terrain_type).exists()
            )


class PerformanceTest(TestCase):
    """Performance tests for terrain classification system."""
    
    def test_batch_classification_performance(self):
        """Test performance of batch terrain classification."""
        import time
        
        # Generate test coordinates
        coordinates = [(2.3522 + i*0.01, 48.8566 + i*0.01) for i in range(100)]
        
        start_time = time.time()
        results = terrain_service.batch_classify_coordinates(coordinates)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        # Should complete within reasonable time (adjust threshold as needed)
        self.assertLess(execution_time, 10.0)  # 10 seconds max
        self.assertEqual(len(results), 100)
        
        # All results should have terrain types
        for result in results:
            self.assertIn('terrain_type', result)
    
    def test_cache_performance(self):
        """Test cache performance benefits."""
        import time
        
        coordinates = (2.3522, 48.8566)
        
        # First call (no cache)
        start_time = time.time()
        terrain1 = terrain_service.get_terrain_type_at_coordinates(*coordinates)
        first_call_time = time.time() - start_time
        
        # Second call (with cache)
        start_time = time.time()
        terrain2 = terrain_service.get_terrain_type_at_coordinates(*coordinates)
        second_call_time = time.time() - start_time
        
        # Results should be the same
        self.assertEqual(terrain1, terrain2)
        
        # Second call should be faster (cache benefit)
        self.assertLess(second_call_time, first_call_time)
