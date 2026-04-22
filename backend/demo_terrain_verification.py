#!/usr/bin/env python
"""
Demo script for terrain verification system.
This script demonstrates how civil engineers can use the terrain classification system.
"""

import os
import sys
import django

# Set up Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from geodata.services import terrain_service
from geodata.services_address import address_service


def demo_address_generation():
    """Demonstrate address generation for testing."""
    print("=" * 60)
    print("DEMO: Address Generation for Terrain Testing")
    print("=" * 60)
    
    # Generate addresses for each terrain type
    print("\n1. Generating addresses for different terrain types...")
    
    for terrain_type in ['0', 'II', 'IIIa', 'IIIb', 'IV']:
        addresses = address_service.get_random_addresses(3, terrain_type)
        print(f"\nTerrain {terrain_type} addresses:")
        for i, addr in enumerate(addresses, 1):
            print(f"  {i}. {addr['label']} ({addr['longitude']:.4f}, {addr['latitude']:.4f})")


def demo_terrain_classification():
    """Demonstrate terrain classification."""
    print("\n" + "=" * 60)
    print("DEMO: Terrain Classification")
    print("=" * 60)
    
    # Test with known locations
    test_locations = [
        ("Paris", 2.3522, 48.8566),
        ("Lyon", 4.8322, 45.7578),
        ("Marseille", 5.3698, 43.2965),
        ("Central France", 2.0, 47.0),
        ("Brittany Coast", -4.5, 48.4),
    ]
    
    print("\n2. Classifying terrain for known locations:")
    for name, lon, lat in test_locations:
        terrain = terrain_service.get_terrain_type_at_coordinates(lon, lat)
        terrain_desc = {
            '0': 'Water/Coastal',
            'II': 'Open Countryside',
            'IIIa': 'Campaign with Obstacles',
            'IIIb': 'Urbanized/Industrial',
            'IV': 'Dense Urban'
        }
        print(f"  {name}: {terrain_desc.get(terrain, 'Unknown')} ({terrain})")


def demo_address_geocoding():
    """Demonstrate address geocoding."""
    print("\n" + "=" * 60)
    print("DEMO: Address Geocoding")
    print("=" * 60)
    
    # Test geocoding French addresses
    search_terms = ["Tour Eiffel Paris", "Vieux Port Marseille", "Basilique Lyon"]
    
    print("\n3. Geocoding French addresses:")
    for term in search_terms:
        addresses = address_service.search_addresses(term, limit=1)
        if addresses:
            addr = addresses[0]
            props = addr.get('properties', {})
            coords = addr.get('geometry', {}).get('coordinates', [])
            
            if len(coords) == 2:
                print(f"  Search: '{term}'")
                print(f"  Found: {props.get('label', 'N/A')}")
                print(f"  Coordinates: ({coords[0]:.4f}, {coords[1]:.4f})")
                print(f"  City: {props.get('city', 'N/A')}")
                print(f"  Postcode: {props.get('postcode', 'N/A')}")
                print()


def demo_terrain_statistics():
    """Demonstrate terrain statistics."""
    print("\n" + "=" * 60)
    print("DEMO: Terrain Statistics")
    print("=" * 60)
    
    print("\n4. Terrain distribution statistics for France:")
    stats = terrain_service.get_terrain_statistics()
    
    total_polygons = sum(data['count'] for data in stats.values())
    
    for terrain, data in sorted(stats.items()):
        terrain_desc = {
            '0': 'Water/Coastal',
            'II': 'Open Countryside',
            'IIIa': 'Campaign with Obstacles',
            'IIIb': 'Urbanized/Industrial',
            'IV': 'Dense Urban'
        }
        
        percentage = data['percentage']
        count = data['count']
        print(f"  {terrain_desc.get(terrain, terrain)}: {percentage:5.1f}% ({count:,} polygons)")
    
    print(f"\n  Total polygons: {total_polygons:,}")


def demo_batch_processing():
    """Demonstrate batch processing."""
    print("\n" + "=" * 60)
    print("DEMO: Batch Processing")
    print("=" * 60)
    
    # Generate coordinates around Paris
    base_lon, base_lat = 2.3522, 48.8566
    coordinates = []
    
    for i in range(10):
        offset = i * 0.01
        coordinates.append((base_lon + offset, base_lat + offset))
    
    print("\n5. Batch terrain classification:")
    results = terrain_service.batch_classify_coordinates(coordinates)
    
    for i, result in enumerate(results, 1):
        if isinstance(result, dict) and 'coordinates' in result:
            coords = result['coordinates']
            terrain = result.get('terrain_type', 'Unknown')
            print(f"  {i:2d}. ({coords[0]:.4f}, {coords[1]:.4f}) -> Terrain {terrain}")
        else:
            print(f"  {i:2d}. Invalid result format")


def demo_validation():
    """Demonstrate coordinate validation."""
    print("\n" + "=" * 60)
    print("DEMO: Coordinate Validation")
    print("=" * 60)
    
    test_coords = [
        ("Paris (valid)", 2.3522, 48.8566),
        ("London (invalid)", -0.1278, 51.5074),
        ("New York (invalid)", -74.0060, 40.7128),
        ("Marseille (valid)", 5.3698, 43.2965),
        ("Invalid coordinates", 200, 200),
    ]
    
    print("\n6. Coordinate validation:")
    for name, lon, lat in test_coords:
        is_valid = address_service.validate_coordinates(lon, lat)
        status = "VALID" if is_valid else "INVALID"
        print(f"  {name}: ({lon:.4f}, {lat:.4f}) -> {status}")


def main():
    """Run all demonstrations."""
    print("TERRAIN CLASSIFICATION SYSTEM DEMO")
    print("For Civil Engineers - Address Verification and Terrain Classification")
    print("Using French Geocoding API: https://data.geopf.fr/geocodage/search")
    
    try:
        demo_address_generation()
        demo_terrain_classification()
        demo_address_geocoding()
        demo_terrain_statistics()
        demo_batch_processing()
        demo_validation()
        
        print("\n" + "=" * 60)
        print("DEMO COMPLETE")
        print("=" * 60)
        print("\nNext steps for civil engineers:")
        print("1. Use management commands for comprehensive testing")
        print("2. Generate test datasets for your project areas")
        print("3. Verify terrain classification accuracy")
        print("4. Integrate with wind load calculations")
        print("\nSee TERRAIN_VERIFICATION_GUIDE.md for detailed instructions")
        
    except Exception as e:
        print(f"\nError during demo: {e}")
        print("Make sure the Django environment is properly configured")


if __name__ == "__main__":
    main()
