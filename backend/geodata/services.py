"""
Terrain classification service for determining terrain types from land use data.
"""
import os
import logging
from typing import Optional, Tuple
from django.conf import settings
from django.core.cache import cache
import geopandas as gpd
from shapely.geometry import Point
from .models import AntennaEquipment

logger = logging.getLogger(__name__)


class TerrainClassificationService:
    """Service for terrain classification using land use data."""
    
    def __init__(self):
        self.land_use_data = None
        self.land_use_file = os.path.join(settings.BASE_DIR, 'backend', 'data', 'OS_FRANCE.fgb')
        self.cache_timeout = 3600  # 1 hour cache
        
    def _load_land_use_data(self):
        """Load land use data from FlatGeobuf file."""
        if self.land_use_data is None:
            try:
                self.land_use_data = gpd.read_file(self.land_use_file)
                logger.info(f"Loaded {len(self.land_use_data)} land use polygons")
            except Exception as e:
                logger.error(f"Failed to load land use data: {e}")
                raise
        return self.land_use_data
    
    def get_terrain_type_at_coordinates(self, longitude: float, latitude: float) -> Optional[str]:
        """
        Determine terrain type at given coordinates using land use data with enhanced rules.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            
        Returns:
            Terrain type string ('0', 'II', 'IIIa', 'IIIb', 'IV') or None if not found
        """
        # Create cache key
        cache_key = f"terrain_{longitude:.6f}_{latitude:.6f}"
        
        # Try to get from cache first
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            # Load land use data
            gdf = self._load_land_use_data()
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Find intersecting polygon
            intersects = gdf[gdf.geometry.intersects(point)]
            
            if len(intersects) > 0:
                # Get the first intersecting polygon's Code_18
                clc_code = intersects.iloc[0]['Code_18']
                terrain_type = AntennaEquipment.get_terrain_from_clc_code(clc_code)
                
                # Apply enhanced classification rules
                terrain_type = self._apply_enhanced_rules(terrain_type, longitude, latitude, gdf)
                
                # Cache the result
                cache.set(cache_key, terrain_type, self.cache_timeout)
                
                logger.debug(f"Coordinates ({longitude}, {latitude}) -> CLC: {clc_code} -> Terrain: {terrain_type}")
                return terrain_type
            else:
                logger.warning(f"No land use data found at coordinates ({longitude}, {latitude})")
                cache.set(cache_key, None, self.cache_timeout)
                return None
                
        except Exception as e:
            logger.error(f"Error determining terrain type at coordinates ({longitude}, {latitude}): {e}")
            return None
    
    def _apply_enhanced_rules(self, terrain_type: str, longitude: float, latitude: float, gdf) -> str:
        """
        Apply enhanced classification rules including coastal proximity and urban density.
        
        Args:
            terrain_type: Initial terrain type from CLC mapping
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            
        Returns:
            Enhanced terrain type
        """
        # Coastal proximity rule: Urban areas near coast become Terrain 0
        if terrain_type in ['IV', 'IIIb'] and self._is_near_coast(longitude, latitude, gdf):
            return '0'
        
        # Urban density rule: Agricultural land near urban areas becomes IIIb
        if terrain_type == 'II' and self._is_near_urban(longitude, latitude, gdf):
            return 'IIIb'
        
        return terrain_type
    
    def _is_near_coast(self, longitude: float, latitude: float, gdf, threshold_km: float = 3.0) -> bool:
        """
        Check if coordinates are near coastal areas.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            threshold_km: Distance threshold in kilometers
            
        Returns:
            True if near coast, False otherwise
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Find sea/ocean areas (major water bodies only)
            sea_codes = ['523']  # Sea and ocean only
            sea_areas = gdf[gdf['Code_18'].isin(sea_codes)]
            
            if len(sea_areas) == 0:
                return False
            
            # Check proximity to sea areas
            threshold_deg = threshold_km / 111.0
            search_area = point.buffer(threshold_deg)
            nearby_sea = sea_areas[sea_areas.geometry.intersects(search_area)]
            
            return len(nearby_sea) > 0
            
        except Exception as e:
            logger.debug(f"Error checking coastal proximity: {e}")
            return False
    
    def _is_near_urban(self, longitude: float, latitude: float, gdf, threshold_km: float = 2.0) -> bool:
        """
        Check if coordinates are near urban areas.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            threshold_km: Distance threshold in kilometers
            
        Returns:
            True if near urban areas, False otherwise
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Find urban areas (Terrain IV codes)
            urban_codes = ['111', '112', '141']
            urban_areas = gdf[gdf['Code_18'].isin(urban_codes)]
            
            if len(urban_areas) == 0:
                return False
            
            # Check proximity to urban areas
            threshold_deg = threshold_km / 111.0
            search_area = point.buffer(threshold_deg)
            nearby_urban = urban_areas[urban_areas.geometry.intersects(search_area)]
            
            return len(nearby_urban) > 0
            
        except Exception as e:
            logger.debug(f"Error checking urban proximity: {e}")
            return False
    
    def get_terrain_type_for_equipment(self, equipment) -> Optional[str]:
        """
        Determine terrain type for antenna equipment based on its location.
        
        Args:
            equipment: AntennaEquipment instance
            
        Returns:
            Terrain type string or None
        """
        # This assumes equipment has longitude and latitude fields
        # You may need to adapt this based on your actual model structure
        if hasattr(equipment, 'longitude') and hasattr(equipment, 'latitude'):
            return self.get_terrain_type_at_coordinates(
                float(equipment.longitude), 
                float(equipment.latitude)
            )
        else:
            logger.warning(f"Equipment {equipment.id} has no coordinates")
            return None
    
    def batch_classify_coordinates(self, coordinates: list) -> list:
        """
        Classify terrain types for multiple coordinates.
        
        Args:
            coordinates: List of (longitude, latitude) tuples
            
        Returns:
            List of terrain types corresponding to input coordinates
        """
        results = []
        for lon, lat in coordinates:
            terrain_type = self.get_terrain_type_at_coordinates(lon, lat)
            results.append(terrain_type)
        return results
    
    def get_terrain_statistics(self) -> dict:
        """
        Get statistics of terrain type distribution in the land use data.
        
        Returns:
            Dictionary with terrain type counts and percentages
        """
        try:
            gdf = self._load_land_use_data()
            
            # Count terrain types for all polygons
            terrain_counts = {}
            total_count = len(gdf)
            unclassified_count = 0
            
            for code in gdf['Code_18']:
                terrain = AntennaEquipment.get_terrain_from_clc_code(code)
                if terrain:
                    terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1
                else:
                    unclassified_count += 1
            
            # Calculate percentages
            terrain_stats = {}
            for terrain, count in terrain_counts.items():
                percentage = (count / total_count) * 100
                terrain_stats[terrain] = {
                    'count': count,
                    'percentage': round(percentage, 2)
                }
            
            # Add unclassified if any
            if unclassified_count > 0:
                terrain_stats['unclassified'] = {
                    'count': unclassified_count,
                    'percentage': round((unclassified_count / total_count) * 100, 2)
                }
            
            return terrain_stats
            
        except Exception as e:
            logger.error(f"Error calculating terrain statistics: {e}")
            return {}


# Global service instance
terrain_service = TerrainClassificationService()
