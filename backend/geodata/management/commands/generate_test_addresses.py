"""
Management command for generating test addresses for terrain classification.
"""
import json
import csv
import time
from django.core.management.base import BaseCommand
from geodata.services_address import address_service
from geodata.services import terrain_service


class Command(BaseCommand):
    help = 'Generate random French addresses for terrain classification testing'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=50,
            help='Number of addresses to generate (default: 50)'
        )
        parser.add_argument(
            '--terrain-type',
            type=str,
            choices=['0', 'II', 'IIIa', 'IIIb', 'IV'],
            help='Generate addresses for specific terrain type only'
        )
        parser.add_argument(
            '--all-terrain-types',
            action='store_true',
            help='Generate addresses for all terrain types equally'
        )
        parser.add_argument(
            '--export-csv',
            action='store_true',
            help='Export addresses to CSV file'
        )
        parser.add_argument(
            '--export-json',
            action='store_true',
            help='Export addresses to JSON file'
        )
        parser.add_argument(
            '--filename',
            type=str,
            help='Custom output filename (without extension)'
        )
        parser.add_argument(
            '--include-terrain',
            action='store_true',
            help='Include terrain classification for each address'
        )
        parser.add_argument(
            '--validate-coords',
            action='store_true',
            help='Validate coordinates are within France bounds'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Generating test addresses...'))
        
        # Generate addresses
        if options['all_terrain_types']:
            addresses = self.generate_all_terrain_types(options['count'] // 5)
        elif options['terrain_type']:
            addresses = address_service.get_random_addresses(options['count'], options['terrain_type'])
        else:
            addresses = address_service.get_random_addresses(options['count'])
        
        self.stdout.write(f"Generated {len(addresses)} addresses")
        
        # Add terrain classification if requested
        if options['include_terrain']:
            self.stdout.write("Classifying terrain for addresses...")
            addresses = self.add_terrain_classification(addresses)
        
        # Validate coordinates if requested
        if options['validate_coords']:
            self.stdout.write("Validating coordinates...")
            valid_addresses = []
            invalid_count = 0
            
            for addr in addresses:
                if address_service.validate_coordinates(addr['longitude'], addr['latitude']):
                    valid_addresses.append(addr)
                else:
                    invalid_count += 1
            
            addresses = valid_addresses
            self.stdout.write(f"Removed {invalid_count} addresses with invalid coordinates")
        
        # Export results
        base_filename = options.get('filename', f'test_addresses_{int(time.time())}')
        
        if options['export_csv']:
            self.export_csv(addresses, f"{base_filename}.csv")
        
        if options['export_json']:
            self.export_json(addresses, f"{base_filename}.json")
        
        # Print summary
        self.print_summary(addresses, options)
    
    def generate_all_terrain_types(self, count_per_type):
        """Generate addresses for all terrain types."""
        self.stdout.write(f"Generating {count_per_type} addresses per terrain type...")
        
        all_addresses = []
        
        for terrain_type in ['0', 'II', 'IIIa', 'IIIb', 'IV']:
            self.stdout.write(f"  Generating addresses for terrain {terrain_type}...")
            addresses = address_service.get_random_addresses(count_per_type, terrain_type)
            all_addresses.extend(addresses)
        
        return all_addresses
    
    def add_terrain_classification(self, addresses):
        """Add terrain classification to addresses."""
        classified_addresses = []
        
        for i, addr in enumerate(addresses):
            lon, lat = addr['longitude'], addr['latitude']
            terrain = terrain_service.get_terrain_type_at_coordinates(lon, lat)
            
            addr['classified_terrain'] = terrain
            classified_addresses.append(addr)
            
            # Progress indicator
            if (i + 1) % 10 == 0:
                self.stdout.write(f"  Classified {i + 1}/{len(addresses)} addresses...")
        
        return classified_addresses
    
    def export_csv(self, addresses, filename):
        """Export addresses to CSV."""
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # Determine fieldnames based on available data
            sample_addr = addresses[0] if addresses else {}
            fieldnames = [
                'search_term', 'label', 'name', 'postcode', 'city', 'context',
                'type', 'importance', 'longitude', 'latitude', 'target_terrain'
            ]
            
            # Add terrain classification field if present
            if 'classified_terrain' in sample_addr:
                fieldnames.append('classified_terrain')
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for addr in addresses:
                row = {field: addr.get(field, '') for field in fieldnames}
                writer.writerow(row)
        
        self.stdout.write(
            self.style.SUCCESS(f"  Addresses exported to {filename}")
        )
    
    def export_json(self, addresses, filename):
        """Export addresses to JSON."""
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(addresses, jsonfile, indent=2, ensure_ascii=False)
        
        self.stdout.write(
            self.style.SUCCESS(f"  Addresses exported to {filename}")
        )
    
    def print_summary(self, addresses, options):
        """Print generation summary."""
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("ADDRESS GENERATION SUMMARY")
        self.stdout.write(f"{'='*60}")
        
        self.stdout.write(f"Total addresses: {len(addresses)}")
        
        # Terrain type distribution
        terrain_counts = {}
        for addr in addresses:
            terrain = addr.get('target_terrain', 'UNKNOWN')
            terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1
        
        self.stdout.write("\nTarget terrain distribution:")
        for terrain, count in sorted(terrain_counts.items()):
            percentage = count / len(addresses) * 100
            self.stdout.write(f"  {terrain}: {count} ({percentage:.1f}%)")
        
        # Classification accuracy if terrain was classified
        if options['include_terrain']:
            classified = [a for a in addresses if a.get('classified_terrain')]
            if classified:
                correct = sum(1 for a in classified 
                             if a.get('classified_terrain') == a.get('target_terrain'))
                accuracy = correct / len(classified) * 100
                self.stdout.write(f"\nClassification accuracy: {accuracy:.1f}% ({correct}/{len(classified)})")
        
        # Geographic distribution
        cities = {}
        for addr in addresses:
            city = addr.get('city', 'UNKNOWN')
            cities[city] = cities.get(city, 0) + 1
        
        self.stdout.write(f"\nGeographic distribution: {len(cities)} unique cities")
        
        # Top cities
        top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:10]
        self.stdout.write("Top 10 cities:")
        for city, count in top_cities:
            self.stdout.write(f"  {city}: {count}")
        
        # Coordinate ranges
        longitudes = [a['longitude'] for a in addresses]
        latitudes = [a['latitude'] for a in addresses]
        
        self.stdout.write(f"\nCoordinate ranges:")
        self.stdout.write(f"  Longitude: {min(longitudes):.4f} to {max(longitudes):.4f}")
        self.stdout.write(f"  Latitude: {min(latitudes):.4f} to {max(latitudes):.4f}")
        
        self.stdout.write(f"{'='*60}")
