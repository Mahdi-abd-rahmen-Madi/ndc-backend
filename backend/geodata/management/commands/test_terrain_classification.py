"""
Management command for testing terrain classification system.
"""
import json
import csv
import time
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from geodata.models import AntennaEquipment
from geodata.services import terrain_service
from geodata.services_address import address_service
from decimal import Decimal


class Command(BaseCommand):
    help = 'Test terrain classification system with random French addresses'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=10,
            help='Number of addresses to test per terrain type (default: 10)'
        )
        parser.add_argument(
            '--terrain-type',
            type=str,
            choices=['0', 'II', 'IIIa', 'IIIb', 'IV'],
            help='Test specific terrain type only'
        )
        parser.add_argument(
            '--export-csv',
            action='store_true',
            help='Export results to CSV file'
        )
        parser.add_argument(
            '--export-json',
            action='store_true',
            help='Export results to JSON file'
        )
        parser.add_argument(
            '--performance-test',
            action='store_true',
            help='Run performance tests'
        )
        parser.add_argument(
            '--coordinates',
            nargs='+',
            type=float,
            help='Test specific coordinates (longitude latitude pairs)'
        )
        parser.add_argument(
            '--addresses',
            nargs='+',
            type=str,
            help='Test specific addresses (city names)'
        )
        parser.add_argument(
            '--create-equipment',
            action='store_true',
            help='Create test equipment with coordinates'
        )
        parser.add_argument(
            '--user',
            type=str,
            default='test_engineer',
            help='Username for equipment creation (default: test_engineer)'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting terrain classification tests...'))
        
        # Initialize results storage
        all_results = []
        
        if options['coordinates']:
            all_results.extend(self.test_coordinates(options['coordinates']))
        elif options['addresses']:
            all_results.extend(self.test_addresses(options['addresses']))
        elif options['performance_test']:
            self.run_performance_tests()
            return
        else:
            # Default: test random addresses
            if options['terrain_type']:
                all_results.extend(self.test_terrain_type(
                    options['terrain_type'], 
                    options['count']
                ))
            else:
                all_results.extend(self.test_all_terrain_types(options['count']))
        
        # Export results if requested
        if options['export_csv']:
            self.export_csv(all_results)
        
        if options['export_json']:
            self.export_json(all_results)
        
        # Create equipment if requested
        if options['create_equipment']:
            self.create_test_equipment(all_results, options['user'])
        
        # Print summary
        self.print_summary(all_results)
    
    def test_coordinates(self, coordinates):
        """Test specific coordinates."""
        self.stdout.write(f"Testing {len(coordinates)//2} coordinate pairs...")
        
        results = []
        for i in range(0, len(coordinates), 2):
            if i + 1 < len(coordinates):
                lon, lat = coordinates[i], coordinates[i + 1]
                result = self.test_single_coordinate(lon, lat, f"Coordinate {i//2 + 1}")
                results.append(result)
        
        return results
    
    def test_addresses(self, addresses):
        """Test specific addresses."""
        self.stdout.write(f"Testing {len(addresses)} addresses...")
        
        results = []
        for i, address in enumerate(addresses):
            # Search for address
            found_addresses = address_service.search_addresses(address, limit=1)
            
            if found_addresses:
                addr = found_addresses[0]
                props = addr.get('properties', {})
                geometry = addr.get('geometry', {})
                coords = geometry.get('coordinates', [])
                
                if len(coords) == 2:
                    lon, lat = coords
                    result = self.test_single_coordinate(lon, lat, props.get('label', address))
                    result['search_address'] = address
                    result['found_address'] = props.get('label', '')
                    results.append(result)
                else:
                    self.stdout.write(
                        self.style.WARNING(f"No coordinates found for {address}")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(f"No address found for {address}")
                )
        
        return results
    
    def test_terrain_type(self, terrain_type, count):
        """Test specific terrain type."""
        self.stdout.write(f"Testing terrain type {terrain_type} with {count} addresses...")
        
        addresses = address_service.get_random_addresses(count, terrain_type)
        results = []
        
        for i, addr in enumerate(addresses):
            lon, lat = addr['longitude'], addr['latitude']
            result = self.test_single_coordinate(lon, lat, addr['label'])
            result['target_terrain'] = terrain_type
            result['search_term'] = addr['search_term']
            results.append(result)
        
        return results
    
    def test_all_terrain_types(self, count_per_type):
        """Test all terrain types."""
        self.stdout.write(f"Testing all terrain types with {count_per_type} addresses each...")
        
        all_results = []
        
        for terrain_type in ['0', 'II', 'IIIa', 'IIIb', 'IV']:
            results = self.test_terrain_type(terrain_type, count_per_type)
            all_results.extend(results)
        
        return all_results
    
    def test_single_coordinate(self, longitude, latitude, location_name):
        """Test terrain classification for a single coordinate."""
        start_time = time.time()
        terrain = terrain_service.get_terrain_type_at_coordinates(longitude, latitude)
        end_time = time.time()
        
        result = {
            'location': location_name,
            'longitude': longitude,
            'latitude': latitude,
            'terrain_type': terrain,
            'classification_time': end_time - start_time,
            'timestamp': time.time()
        }
        
        # Print result
        terrain_display = terrain if terrain else 'UNKNOWN'
        self.stdout.write(
            f"  {location_name}: {terrain_display} ({longitude:.4f}, {latitude:.4f}) - "
            f"{end_time - start_time:.3f}s"
        )
        
        return result
    
    def run_performance_tests(self):
        """Run performance tests."""
        self.stdout.write("Running performance tests...")
        
        # Test 1: Single coordinate performance
        self.stdout.write("\n1. Single coordinate performance:")
        coordinates = [(2.3522, 48.8566)]
        
        times = []
        for i in range(10):
            start_time = time.time()
            terrain_service.get_terrain_type_at_coordinates(*coordinates[0])
            end_time = time.time()
            times.append(end_time - start_time)
        
        avg_time = sum(times) / len(times)
        self.stdout.write(f"  Average time: {avg_time:.3f}s")
        self.stdout.write(f"  Min time: {min(times):.3f}s")
        self.stdout.write(f"  Max time: {max(times):.3f}s")
        
        # Test 2: Batch performance
        self.stdout.write("\n2. Batch classification performance:")
        batch_coords = [(2.3522 + i*0.01, 48.8566 + i*0.01) for i in range(50)]
        
        start_time = time.time()
        results = terrain_service.batch_classify_coordinates(batch_coords)
        end_time = time.time()
        
        self.stdout.write(f"  50 coordinates: {end_time - start_time:.3f}s")
        self.stdout.write(f"  Average per coordinate: {(end_time - start_time)/50:.3f}s")
        
        # Test 3: Cache performance
        self.stdout.write("\n3. Cache performance test:")
        coord = (2.3522, 48.8566)
        
        # First call (cold cache)
        start_time = time.time()
        terrain1 = terrain_service.get_terrain_type_at_coordinates(*coord)
        cold_time = time.time() - start_time
        
        # Second call (warm cache)
        start_time = time.time()
        terrain2 = terrain_service.get_terrain_type_at_coordinates(*coord)
        warm_time = time.time() - start_time
        
        self.stdout.write(f"  Cold cache: {cold_time:.3f}s")
        self.stdout.write(f"  Warm cache: {warm_time:.3f}s")
        self.stdout.write(f"  Speedup: {cold_time/warm_time:.1f}x")
    
    def create_test_equipment(self, results, username):
        """Create test equipment from results."""
        self.stdout.write(f"\nCreating test equipment for user '{username}'...")
        
        # Get or create user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': f'{username}@example.com'}
        )
        
        if created:
            user.set_password('password123')
            user.save()
            self.stdout.write(f"  Created user: {username}")
        
        created_count = 0
        for result in results:
            if result.get('terrain_type') and result.get('longitude') and result.get('latitude'):
                # Create equipment
                equipment = AntennaEquipment.objects.create(
                    name=f"Test Equipment - {result['location']}",
                    responsible_user=user,
                    building_height=Decimal('15.0'),
                    mast_height=Decimal('4.0')
                )
                
                # Store coordinates (you might want to add these fields to the model)
                equipment.longitude = result['longitude']
                equipment.latitude = result['latitude']
                
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f"  Created {created_count} test equipment records")
        )
    
    def export_csv(self, results):
        """Export results to CSV."""
        filename = f"terrain_test_results_{int(time.time())}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'location', 'longitude', 'latitude', 'terrain_type',
                'target_terrain', 'classification_time', 'timestamp',
                'search_term', 'search_address', 'found_address'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                # Only include fields that exist
                row = {field: result.get(field, '') for field in fieldnames}
                writer.writerow(row)
        
        self.stdout.write(
            self.style.SUCCESS(f"  Results exported to {filename}")
        )
    
    def export_json(self, results):
        """Export results to JSON."""
        filename = f"terrain_test_results_{int(time.time())}.json"
        
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(results, jsonfile, indent=2, ensure_ascii=False)
        
        self.stdout.write(
            self.style.SUCCESS(f"  Results exported to {filename}")
        )
    
    def print_summary(self, results):
        """Print test summary."""
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("TEST SUMMARY")
        self.stdout.write(f"{'='*60}")
        
        total_tests = len(results)
        successful_tests = sum(1 for r in results if r.get('terrain_type'))
        
        self.stdout.write(f"Total tests: {total_tests}")
        self.stdout.write(f"Successful classifications: {successful_tests}")
        self.stdout.write(f"Success rate: {successful_tests/total_tests*100:.1f}%")
        
        # Terrain type distribution
        terrain_counts = {}
        for result in results:
            terrain = result.get('terrain_type', 'UNKNOWN')
            terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1
        
        self.stdout.write("\nTerrain type distribution:")
        for terrain, count in sorted(terrain_counts.items(), key=lambda x: (x[0] is None, x[0])):
            percentage = count / total_tests * 100
            self.stdout.write(f"  {terrain}: {count} ({percentage:.1f}%)")
        
        # Performance summary
        if results:
            times = [r.get('classification_time', 0) for r in results if r.get('classification_time')]
            if times:
                avg_time = sum(times) / len(times)
                self.stdout.write(f"\nAverage classification time: {avg_time:.3f}s")
                self.stdout.write(f"Total classification time: {sum(times):.3f}s")
        
        # Accuracy for targeted tests
        target_results = [r for r in results if r.get('target_terrain')]
        if target_results:
            correct = sum(1 for r in target_results 
                         if r.get('terrain_type') == r.get('target_terrain'))
            accuracy = correct / len(target_results) * 100
            self.stdout.write(f"\nTarget accuracy: {accuracy:.1f}% ({correct}/{len(target_results)})")
        
        self.stdout.write(f"{'='*60}")
