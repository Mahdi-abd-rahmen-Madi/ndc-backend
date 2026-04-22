"""
Address generation and geocoding service for terrain classification testing.
"""
import requests
import random
import json
import time
from typing import List, Dict, Optional, Tuple
from django.core.cache import cache
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AddressGenerationService:
    """Service for generating and geocoding French addresses for testing."""
    
    def __init__(self):
        self.geocoding_url = "https://data.geopf.fr/geocodage/search"
        self.cache_timeout = 86400  # 24 hours cache
        self.request_delay = 0.1  # 100ms delay between requests
        
        # Predefined search terms for different terrain types
        self.terrain_search_terms = {
            '0': [  # Water/coastal
                "Brest", "Biarritz", "Marseille", "Nice", "Cannes", "Saint-Malo",
                "La Rochelle", "Bordeaux", "Le Havre", "Calais", "Dunkerque",
                "Sète", "Toulon", "Antibes", "Bayonne", "Concarneau"
            ],
            'II': [  # Open countryside
                "Champagne", "Beauce", "Brie", "Saône", "Limagne", "Crau",
                "Camargue", "Marais Poitevin", "Brenne", "Sologne", "Morvan",
                "Luberon", "Alpilles", "Causses", "Cévennes", "Vosges"
            ],
            'IIIa': [  # Campaign with obstacles
                "Bordelais", "Bourgogne", "Alsace", "Val de Loire", "Dordogne",
                "Lot", "Tarn", "Aveyron", "Lozère", "Ariège", "Gers", "Landes",
                "Charente", "Vienne", "Indre", "Creuse", "Corrèze", "Lot-et-Garonne"
            ],
            'IIIb': [  # Urbanized/industrial
                "Lens", "Liévin", "Béthune", "Valenciennes", "Maubeuge",
                "Douai", "Denain", "Saint-Quentin", "Laon", "Charleville-Mézières",
                "Sedan", "Longwy", "Thionville", "Forbach", "Saint-Avold"
            ],
            'IV': [  # Dense urban
                "Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes",
                "Strasbourg", "Montpellier", "Bordeaux", "Lille", "Rennes",
                "Reims", "Le Havre", "Saint-Étienne", "Toulon", "Grenoble"
            ]
        }
        
        # Random French cities for general testing
        self.french_cities = [
            "Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes",
            "Strasbourg", "Montpellier", "Bordeaux", "Lille", "Rennes",
            "Reims", "Le Havre", "Saint-Étienne", "Toulon", "Grenoble",
            "Dijon", "Angers", "Saint-Nazaire", "Nîmes", "Clermont-Ferrand",
            "Le Mans", "Aix-en-Provence", "Brest", "Limoges", "Tours",
            "Amiens", "Metz", "Besançon", "Orléans", "Mulhouse",
            "Rouen", "Boulogne-Billancourt", "Caen", "Nîmes", "Dijon",
            "Perpignan", "Argenteuil", "Roubaix", "Tourcoing", "Nanterre",
            "Avignon", "Créteil", "Dunkerque", "Poitiers", "Courbevoie"
        ]
    
    def search_addresses(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search for addresses using the French geocoding API.
        
        Args:
            query: Search query (city name, address, etc.)
            limit: Maximum number of results to return
            
        Returns:
            List of address features with coordinates
        """
        cache_key = f"geocode_{query}_{limit}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        try:
            params = {
                'q': query,
                'limit': limit,
                'autocomplete': 0
            }
            
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            addresses = data.get('features', [])
            
            # Cache the result
            cache.set(cache_key, addresses, self.cache_timeout)
            
            # Add delay to respect API limits
            time.sleep(self.request_delay)
            
            return addresses
            
        except Exception as e:
            logger.error(f"Error searching addresses for '{query}': {e}")
            return []
    
    def get_random_addresses(self, count: int = 10, terrain_type: Optional[str] = None) -> List[Dict]:
        """
        Generate random French addresses for testing.
        
        Args:
            count: Number of addresses to generate
            terrain_type: Specific terrain type to target (optional)
            
        Returns:
            List of addresses with coordinates and terrain info
        """
        addresses = []
        
        # Choose search terms based on terrain type or random
        if terrain_type and terrain_type in self.terrain_search_terms:
            search_terms = self.terrain_search_terms[terrain_type]
        else:
            search_terms = self.french_cities
        
        for _ in range(count):
            # Random search term
            search_term = random.choice(search_terms)
            
            # Get addresses for this search term
            found_addresses = self.search_addresses(search_term, limit=10)
            
            if found_addresses:
                # Select a random address from results
                address = random.choice(found_addresses)
                
                # Extract relevant information
                props = address.get('properties', {})
                geometry = address.get('geometry', {})
                coordinates = geometry.get('coordinates', [])
                
                if len(coordinates) == 2:
                    address_info = {
                        'search_term': search_term,
                        'label': props.get('label', ''),
                        'name': props.get('name', ''),
                        'postcode': props.get('postcode', ''),
                        'city': props.get('city', ''),
                        'context': props.get('context', ''),
                        'type': props.get('type', ''),
                        'importance': props.get('importance', 0),
                        'longitude': coordinates[0],
                        'latitude': coordinates[1],
                        'target_terrain': terrain_type
                    }
                    addresses.append(address_info)
        
        return addresses
    
    def get_addresses_for_all_terrain_types(self, count_per_type: int = 5) -> Dict[str, List[Dict]]:
        """
        Generate addresses for all terrain types.
        
        Args:
            count_per_type: Number of addresses to generate per terrain type
            
        Returns:
            Dictionary with terrain types as keys and address lists as values
        """
        all_addresses = {}
        
        for terrain_type in ['0', 'II', 'IIIa', 'IIIb', 'IV']:
            addresses = self.get_random_addresses(count_per_type, terrain_type)
            all_addresses[terrain_type] = addresses
            
            logger.info(f"Generated {len(addresses)} addresses for terrain type {terrain_type}")
        
        return all_addresses
    
    def validate_coordinates(self, longitude: float, latitude: float) -> bool:
        """
        Validate if coordinates are within France bounds.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            
        Returns:
            True if coordinates are valid for France
        """
        # Approximate bounds for France
        return (-5.5 <= longitude <= 9.8) and (41.3 <= latitude <= 51.1)
    
    def get_address_by_coordinates(self, longitude: float, latitude: float) -> Optional[Dict]:
        """
        Reverse geocoding to get address from coordinates.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            
        Returns:
            Address information or None if not found
        """
        cache_key = f"reverse_geocode_{longitude}_{latitude}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        try:
            params = {
                'lon': longitude,
                'lat': latitude,
                'limit': 1
            }
            
            response = requests.get(f"{self.geocoding_url}/reverse", params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            features = data.get('features', [])
            
            if features:
                address = features[0]
                cache.set(cache_key, address, self.cache_timeout)
                time.sleep(self.request_delay)
                return address
            
            return None
            
        except Exception as e:
            logger.error(f"Error reverse geocoding coordinates ({longitude}, {latitude}): {e}")
            return None
    
    def export_addresses_to_csv(self, addresses: List[Dict], filename: str = None) -> str:
        """
        Export addresses to CSV format.
        
        Args:
            addresses: List of address dictionaries
            filename: Output filename (optional)
            
        Returns:
            Path to the generated CSV file
        """
        import csv
        import os
        from django.conf import settings
        
        if filename is None:
            filename = f"addresses_test_{int(time.time())}.csv"
        
        filepath = os.path.join(settings.BASE_DIR, 'backend', 'data', filename)
        
        fieldnames = [
            'search_term', 'label', 'name', 'postcode', 'city', 'context',
            'type', 'importance', 'longitude', 'latitude', 'target_terrain'
        ]
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for address in addresses:
                # Only include fields that exist in fieldnames
                row = {field: address.get(field, '') for field in fieldnames}
                writer.writerow(row)
        
        logger.info(f"Exported {len(addresses)} addresses to {filepath}")
        return filepath


# Global service instance
address_service = AddressGenerationService()
