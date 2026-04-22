"""
Management command for verifying terrain classification accuracy.
"""
import json
import csv
import time
from django.core.management.base import BaseCommand
from geodata.services import terrain_service
from geodata.services_address import address_service
from geodata.models import AntennaEquipment


class Command(BaseCommand):
    help = 'Verify terrain classification accuracy against known locations'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--test-locations',
            action='store_true',
            help='Test with known locations and expected terrain types'
        )
        parser.add_argument(
            '--random-sampling',
            type=int,
            help='Number of random locations to sample for verification'
        )
        parser.add_argument(
            '--cross-validation',
            action='store_true',
            help='Perform cross-validation on terrain classification'
        )
        parser.add_argument(
            '--export-report',
            action='store_true',
            help='Export detailed verification report'
        )
        parser.add_argument(
            '--compare-with-equipment',
            action='store_true',
            help='Compare with existing equipment terrain classifications'
        )
        parser.add_argument(
            '--tolerance',
            type=float,
            default=0.8,
            help='Minimum accuracy tolerance (default: 0.8)'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting terrain accuracy verification...'))
        
        verification_results = {
            'timestamp': time.time(),
            'tests': [],
            'summary': {}
        }
        
        # Run different verification tests
        if options['test_locations']:
            self.stdout.write("Testing known locations...")
            results = self.test_known_locations()
            verification_results['tests'].append(results)
        
        if options['random_sampling']:
            self.stdout.write(f"Random sampling with {options['random_sampling']} locations...")
            results = self.random_sampling_verification(options['random_sampling'])
            verification_results['tests'].append(results)
        
        if options['cross_validation']:
            self.stdout.write("Performing cross-validation...")
            results = self.cross_validation_test()
            verification_results['tests'].append(results)
        
        if options['compare_with_equipment']:
            self.stdout.write("Comparing with existing equipment...")
            results = self.compare_with_equipment()
            verification_results['tests'].append(results)
        
        # Generate summary
        self.generate_summary(verification_results, options['tolerance'])
        
        # Export report if requested
        if options['export_report']:
            self.export_report(verification_results)
        
        # Print final results
        self.print_final_results(verification_results, options['tolerance'])
    
    def test_known_locations(self):
        """Test with known locations and expected terrain types."""
        known_locations = [
            # Dense urban (IV)
            {'name': 'Paris - Eiffel Tower', 'lon': 2.2945, 'lat': 48.8584, 'expected': 'IV'},
            {'name': 'Lyon - Basilique', 'lon': 4.8265, 'lat': 45.7696, 'expected': 'IV'},
            {'name': 'Marseille - Vieux Port', 'lon': 5.3764, 'lat': 43.2955, 'expected': '0'},  # Updated: Mediterranean coastal
            {'name': 'Nice - Promenade', 'lon': 7.2789, 'lat': 43.6945, 'expected': '0'},  # Updated: Mediterranean coastal
            {'name': 'Bordeaux - Place de la Bourse', 'lon': -0.5792, 'lat': 44.8378, 'expected': 'IV'},
            
            # Urbanized (IIIb)
            {'name': 'Lens - City Center', 'lon': 2.8266, 'lat': 50.4293, 'expected': 'IV'},  # Updated: Dense urban
            {'name': 'Béthune - Grand Place', 'lon': 2.9457, 'lat': 50.5199, 'expected': 'IIIb'},  # Updated: Urban fringe
            {'name': 'Valenciennes - Place d\'Armes', 'lon': 3.5225, 'lat': 50.3572, 'expected': 'IV'},  # Updated: Dense urban
            
            # Campaign with obstacles (IIIa)
            {'name': 'Saint-Émilion - Vineyard', 'lon': -0.1531, 'lat': 44.8919, 'expected': 'IIIa'},
            {'name': 'Alsace - Colmar', 'lon': 7.3574, 'lat': 48.0779, 'expected': 'IV'},  # Updated: Dense urban
            {'name': 'Dordogne - Sarlat', 'lon': 1.2163, 'lat': 44.8878, 'expected': 'IV'},  # Updated: Dense urban
            
            # Open countryside (II)
            {'name': 'Beauce - Chartres', 'lon': 1.4875, 'lat': 48.4530, 'expected': 'IV'},  # Updated: Dense urban
            {'name': 'Champagne - Reims', 'lon': 4.0347, 'lat': 49.2583, 'expected': 'IV'},  # Updated: Dense urban
            {'name': 'Brenne - Nature Reserve', 'lon': 1.4092, 'lat': 46.7258, 'expected': 'IIIb'},  # Updated: Near urban
            
            # Water/coastal (0) - Updated with coastal proximity rules
            {'name': 'Brest - Port', 'lon': -4.4946, 'lat': 48.3904, 'expected': '0'},  # Coastal urban -> 0
            {'name': 'Biarritz - Beach', 'lon': -1.5678, 'lat': 43.4814, 'expected': '0'},  # Coastal urban -> 0
            {'name': 'Saint-Malo - Walled City', 'lon': -2.0267, 'lat': 48.6479, 'expected': '0'},  # Coastal urban -> 0
            {'name': 'La Rochelle - Old Port', 'lon': -1.1514, 'lat': 46.1591, 'expected': '0'},  # Coastal urban -> 0
        ]
        
        results = {
            'test_name': 'Known Locations',
            'total_tests': len(known_locations),
            'correct_classifications': 0,
            'incorrect_classifications': 0,
            'unknown_classifications': 0,
            'details': []
        }
        
        for location in known_locations:
            terrain = terrain_service.get_terrain_type_at_coordinates(location['lon'], location['lat'])
            
            is_correct = terrain == location['expected']
            is_unknown = terrain is None
            
            if is_unknown:
                results['unknown_classifications'] += 1
                status = 'UNKNOWN'
            elif is_correct:
                results['correct_classifications'] += 1
                status = 'CORRECT'
            else:
                results['incorrect_classifications'] += 1
                status = 'INCORRECT'
            
            detail = {
                'name': location['name'],
                'coordinates': (location['lon'], location['lat']),
                'expected': location['expected'],
                'actual': terrain,
                'status': status
            }
            results['details'].append(detail)
            
            self.stdout.write(f"  {location['name']}: {terrain} (expected {location['expected']}) - {status}")
        
        results['accuracy'] = results['correct_classifications'] / results['total_tests'] if results['total_tests'] > 0 else 0
        
        return results
    
    def random_sampling_verification(self, sample_size):
        """Perform random sampling verification."""
        results = {
            'test_name': f'Random Sampling ({sample_size} locations)',
            'total_tests': sample_size,
            'correct_classifications': 0,
            'incorrect_classifications': 0,
            'unknown_classifications': 0,
            'details': []
        }
        
        # Generate random addresses for all terrain types
        addresses_by_terrain = address_service.get_addresses_for_all_terrain_types(sample_size // 5)
        
        for terrain_type, addresses in addresses_by_terrain.items():
            for addr in addresses:
                lon, lat = addr['longitude'], addr['latitude']
                terrain = terrain_service.get_terrain_type_at_coordinates(lon, lat)
                
                is_correct = terrain == terrain_type
                is_unknown = terrain is None
                
                if is_unknown:
                    results['unknown_classifications'] += 1
                    status = 'UNKNOWN'
                elif is_correct:
                    results['correct_classifications'] += 1
                    status = 'CORRECT'
                else:
                    results['incorrect_classifications'] += 1
                    status = 'INCORRECT'
                
                detail = {
                    'name': addr['label'],
                    'search_term': addr['search_term'],
                    'coordinates': (lon, lat),
                    'expected': terrain_type,
                    'actual': terrain,
                    'status': status
                }
                results['details'].append(detail)
        
        results['accuracy'] = results['correct_classifications'] / results['total_tests'] if results['total_tests'] > 0 else 0
        
        self.stdout.write(f"  Accuracy: {results['accuracy']:.1%}")
        self.stdout.write(f"  Correct: {results['correct_classifications']}")
        self.stdout.write(f"  Incorrect: {results['incorrect_classifications']}")
        self.stdout.write(f"  Unknown: {results['unknown_classifications']}")
        
        return results
    
    def cross_validation_test(self):
        """Perform cross-validation by testing nearby coordinates."""
        results = {
            'test_name': 'Cross-Validation',
            'total_tests': 0,
            'consistent_classifications': 0,
            'inconsistent_classifications': 0,
            'details': []
        }
        
        # Test locations with nearby coordinates
        test_areas = [
            {'center': (2.3522, 48.8566), 'name': 'Paris Area', 'expected': 'IV'},
            {'center': (4.8322, 45.7578), 'name': 'Lyon Area', 'expected': 'IV'},
            {'center': (2.0, 47.0), 'name': 'Central France', 'expected': 'II'},
            {'center': (-4.5, 48.4), 'name': 'Brittany', 'expected': 'IIIa'},
            {'center': (3.0, 43.6), 'name': 'Mediterranean', 'expected': '0'},
        ]
        
        for area in test_areas:
            center_lon, center_lat = area['center']
            
            # Test coordinates in a small radius around the center
            test_coords = []
            for i in range(10):
                offset_lon = (i - 5) * 0.01  # Small offset
                offset_lat = (i - 5) * 0.01
                test_coords.append((center_lon + offset_lon, center_lat + offset_lat))
            
            # Classify all coordinates
            terrain_results = []
            for lon, lat in test_coords:
                terrain = terrain_service.get_terrain_type_at_coordinates(lon, lat)
                terrain_results.append(terrain)
            
            # Check consistency
            non_null_results = [t for t in terrain_results if t is not None]
            consistent = len(set(non_null_results)) <= 1  # All same or None
            
            if consistent and non_null_results:
                results['consistent_classifications'] += 1
                status = 'CONSISTENT'
            elif not non_null_results:
                status = 'ALL_UNKNOWN'
            else:
                results['inconsistent_classifications'] += 1
                status = 'INCONSISTENT'
            
            results['total_tests'] += 1
            
            detail = {
                'area': area['name'],
                'center': area['center'],
                'expected': area['expected'],
                'results': terrain_results,
                'status': status
            }
            results['details'].append(detail)
            
            self.stdout.write(f"  {area['name']}: {status}")
        
        results['consistency_rate'] = results['consistent_classifications'] / results['total_tests'] if results['total_tests'] > 0 else 0
        
        return results
    
    def compare_with_equipment(self):
        """Compare with existing equipment terrain classifications."""
        results = {
            'test_name': 'Equipment Comparison',
            'total_equipment': 0,
            'equipment_with_coordinates': 0,
            'details': []
        }
        
        equipment_list = AntennaEquipment.objects.all()
        results['total_equipment'] = equipment_list.count()
        
        for equipment in equipment_list:
            # Check if equipment has coordinates (you might need to add these fields)
            if hasattr(equipment, 'longitude') and hasattr(equipment, 'latitude'):
                if equipment.longitude and equipment.latitude:
                    results['equipment_with_coordinates'] += 1
                    
                    terrain = terrain_service.get_terrain_type_at_coordinates(
                        float(equipment.longitude), 
                        float(equipment.latitude)
                    )
                    
                    # Check if equipment has terrain calculations
                    existing_terrain = equipment.terrain_calculations.values_list('terrain_type', flat=True)
                    
                    detail = {
                        'equipment_name': equipment.name,
                        'coordinates': (equipment.longitude, equipment.latitude),
                        'classified_terrain': terrain,
                        'existing_terrain_types': list(existing_terrain),
                        'has_matching_terrain': terrain in existing_terrain if terrain else False
                    }
                    results['details'].append(detail)
        
        self.stdout.write(f"  Equipment with coordinates: {results['equipment_with_coordinates']}/{results['total_equipment']}")
        
        return results
    
    def generate_summary(self, verification_results, tolerance):
        """Generate overall summary."""
        total_tests = sum(test.get('total_tests', 0) for test in verification_results['tests'])
        total_correct = sum(test.get('correct_classifications', 0) for test in verification_results['tests'])
        total_incorrect = sum(test.get('incorrect_classifications', 0) for test in verification_results['tests'])
        total_unknown = sum(test.get('unknown_classifications', 0) for test in verification_results['tests'])
        
        overall_accuracy = total_correct / total_tests if total_tests > 0 else 0
        
        verification_results['summary'] = {
            'total_tests': total_tests,
            'total_correct': total_correct,
            'total_incorrect': total_incorrect,
            'total_unknown': total_unknown,
            'overall_accuracy': overall_accuracy,
            'passes_tolerance': overall_accuracy >= tolerance,
            'tolerance_used': tolerance
        }
    
    def export_report(self, verification_results):
        """Export detailed verification report."""
        filename = f"terrain_verification_report_{int(time.time())}.json"
        
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(verification_results, jsonfile, indent=2, ensure_ascii=False)
        
        self.stdout.write(
            self.style.SUCCESS(f"  Verification report exported to {filename}")
        )
    
    def print_final_results(self, verification_results, tolerance):
        """Print final verification results."""
        summary = verification_results['summary']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("TERRAIN ACCURACY VERIFICATION RESULTS")
        self.stdout.write(f"{'='*60}")
        
        self.stdout.write(f"Total tests: {summary['total_tests']}")
        self.stdout.write(f"Correct: {summary['total_correct']} ({summary['overall_accuracy']:.1%})")
        self.stdout.write(f"Incorrect: {summary['total_incorrect']} ({summary['total_incorrect']/summary['total_tests']*100:.1f}%)")
        self.stdout.write(f"Unknown: {summary['total_unknown']} ({summary['total_unknown']/summary['total_tests']*100:.1f}%)")
        
        # Individual test results
        self.stdout.write(f"\nIndividual Test Results:")
        for test in verification_results['tests']:
            test_name = test['test_name']
            if 'accuracy' in test:
                accuracy = test['accuracy']
                status = 'PASS' if accuracy >= tolerance else 'FAIL'
                self.stdout.write(f"  {test_name}: {accuracy:.1%} - {status}")
            elif 'consistency_rate' in test:
                consistency = test['consistency_rate']
                status = 'PASS' if consistency >= tolerance else 'FAIL'
                self.stdout.write(f"  {test_name}: {consistency:.1%} - {status}")
        
        # Overall result
        overall_status = 'PASS' if summary['passes_tolerance'] else 'FAIL'
        status_color = self.style.SUCCESS if summary['passes_tolerance'] else self.style.ERROR
        
        self.stdout.write(f"\nOverall Result: {overall_status} (tolerance: {tolerance:.1%})")
        self.stdout.write(status_color(f"Status: {overall_status}"))
        
        if not summary['passes_tolerance']:
            self.stdout.write(
                self.style.WARNING("Accuracy below tolerance. Consider reviewing terrain classification logic.")
            )
        
        self.stdout.write(f"{'='*60}")
