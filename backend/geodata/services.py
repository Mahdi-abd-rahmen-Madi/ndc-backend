"""
Terrain classification service for determining terrain types from land use data.
"""
import os
import logging
import math
import time
from typing import Optional, Tuple, Dict, List, Any
from django.conf import settings
from django.core.cache import cache
import geopandas as gpd
import numpy as np
from shapely.geometry import Point, box
from shapely.strtree import STRtree
from .models import AntennaEquipment
from .terrain_config_service import terrain_config_service
from .vector_tile_parser import create_vector_tile_parser

logger = logging.getLogger(__name__)

# Module-level cache for singleton service instance
_terrain_service_instance = None
_service_lock = None


class TerrainClassificationService:
    """Service for terrain classification using land use data."""
    
    def __init__(self):
        self.land_use_data = None
        self.land_use_file = os.path.join(settings.BASE_DIR, 'backend', 'data', 'OS_FRANCE.fgb')
        self.wind_coeff_data = None
        self.wind_coeff_file = os.path.join(settings.BASE_DIR, 'backend', 'data', 'ec1_windCoeff.geojson')
        self.cache_timeout = 3600  # 1 hour cache
        self._spatial_index = None
        self._water_areas = None
        self._urban_areas = None
        self._forest_areas = None
        self._agriculture_areas = None
        self._complex_agriculture_areas = None
        self._spatial_indexes = {}
        self._index_cache_timeout = 7200  # 2 hours for spatial indexes
        self._performance_metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'spatial_queries': 0,
            'classification_time': []
        }
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of TerrainClassificationService."""
        global _terrain_service_instance, _service_lock
        
        if _service_lock is None:
            import threading
            _service_lock = threading.Lock()
        
        if _terrain_service_instance is None:
            with _service_lock:
                if _terrain_service_instance is None:
                    _terrain_service_instance = cls()
                    logger.info("Created new TerrainClassificationService singleton instance")
        
        return _terrain_service_instance
        
    def _load_land_use_data(self):
        """Load land use data from FlatGeobuf file with spatial indexing."""
        if self.land_use_data is None:
            try:
                self.land_use_data = gpd.read_file(self.land_use_file)
                logger.info(f"Loaded {len(self.land_use_data)} land use polygons")
                
                # Create spatial index for faster queries
                self.land_use_data.sindex
                
                # Pre-filter water and urban areas for performance
                self._pre_filter_areas()
                
            except Exception as e:
                logger.error(f"Failed to load land use data: {e}")
                raise
        return self.land_use_data
    
    def _pre_filter_areas(self):
        """Pre-filter water and urban areas for performance optimization with multi-level indexing."""
        if self.land_use_data is not None:
            # Get performance settings from configuration
            config = terrain_config_service.load_config()
            performance_settings = config.get('performance_settings', {})
            prefilter_categories = performance_settings.get('prefilter_categories', {})
            
            # Water and coastal codes from configuration
            water_codes = prefilter_categories.get('water_codes', [
                '511', '512', '521', '522', '523',  # Water bodies and coastal
                '421', '422', '423',                # Coastal wetlands
                '331', '332', '333', '334', '335'  # Natural areas near coast
            ])
            
            # Urban and industrial codes from configuration
            urban_codes = prefilter_categories.get('urban_codes', [
                '111', '112', '141',  # Dense urban zones
                '121', '122', '123', '124',  # Urbanized/industrial zones
                '131', '132', '133', '142'   # Industrial zones
            ])
            
            # Forest codes for specialized indexing
            forest_codes = ['311', '312', '313', '321', '322', '323', '324']
            
            # Agriculture codes for specialized indexing
            agriculture_codes = ['211', '212', '213', '231']
            complex_agriculture_codes = ['241', '242', '243', '244']
            
            # Pre-filter areas with spatial indexing
            self._water_areas = self._create_indexed_subset(water_codes, 'water')
            self._urban_areas = self._create_indexed_subset(urban_codes, 'urban')
            self._forest_areas = self._create_indexed_subset(forest_codes, 'forest')
            self._agriculture_areas = self._create_indexed_subset(agriculture_codes, 'agriculture')
            self._complex_agriculture_areas = self._create_indexed_subset(complex_agriculture_codes, 'complex_agriculture')
            
            logger.info(f"Pre-filtered areas: {len(self._water_areas)} water, {len(self._urban_areas)} urban, "
                       f"{len(self._forest_areas)} forest, {len(self._agriculture_areas)} agriculture, "
                       f"{len(self._complex_agriculture_areas)} complex agriculture")
    
    def _create_indexed_subset(self, codes: List[str], category_name: str) -> gpd.GeoDataFrame:
        """Create a spatially indexed subset of land use data for specific codes."""
        try:
            # Filter by codes
            subset = self.land_use_data[self.land_use_data['Code_18'].isin(codes)].copy()
            
            if len(subset) == 0:
                return subset
            
            # Create spatial index for this subset
            if hasattr(subset, 'sindex'):
                subset.sindex
            
            # Create STRtree for faster spatial queries
            if hasattr(subset, 'geometry') and len(subset) > 0:
                tree = STRtree(subset.geometry.tolist())
                self._spatial_indexes[category_name] = {
                    'tree': tree,
                    'data': subset,
                    'created_at': time.time()
                }
            
            return subset
            
        except Exception as e:
            logger.warning(f"Error creating indexed subset for {category_name}: {e}")
            return self.land_use_data[self.land_use_data['Code_18'].isin(codes)]
    
    def _load_wind_coeff_data(self):
        """Load wind coefficient data from GeoJSON file."""
        if self.wind_coeff_data is None:
            try:
                self.wind_coeff_data = gpd.read_file(self.wind_coeff_file)
                logger.info(f"Loaded {len(self.wind_coeff_data)} wind coefficient regions")
            except Exception as e:
                logger.error(f"Failed to load wind coefficient data: {e}")
                raise
        return self.wind_coeff_data
    
    def get_region_from_coordinates(self, longitude: float, latitude: float) -> Optional[int]:
        """
        Determine region number from coordinates using wind coefficient data.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            
        Returns:
            Region number (1-4) or None if not found
        """
        try:
            # Load wind coefficient data
            gdf = self._load_wind_coeff_data()
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Find intersecting region
            intersects = gdf[gdf.geometry.intersects(point)]
            
            if len(intersects) > 0:
                # Get the V_B0 value from the first intersecting region
                v_b0 = intersects.iloc[0]['V_B0']
                
                # Map V_B0 to region using the model's mapping
                from .models import AntennaEquipment
                region = AntennaEquipment.get_region_from_vb0(v_b0)
                
                logger.debug(f"Coordinates ({longitude}, {latitude}) -> V_B0: {v_b0} -> Region: {region}")
                return region
            else:
                logger.warning(f"No wind coefficient region found at coordinates ({longitude}, {latitude})")
                return None
                
        except Exception as e:
            logger.error(f"Error determining region for coordinates ({longitude}, {latitude}): {e}")
            return None
    
    def get_terrain_type_at_coordinates(self, longitude: float, latitude: float) -> Optional[str]:
        """
        Determine terrain type at given coordinates using land use data with enhanced rules.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            
        Returns:
            Terrain type string ('0', 'II', 'IIIa', 'IIIb', 'IV') or None if not found
        """
        start_time = time.time()
        
        # Create hierarchical cache key
        cache_key = f"terrain_{longitude:.6f}_{latitude:.6f}"
        confidence_cache_key = f"confidence_{longitude:.6f}_{latitude:.6f}"
        spatial_cache_key = f"spatial_{longitude:.6f}_{latitude:.6f}"
        
        # Try to get from cache first
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            self._performance_metrics['cache_hits'] += 1
            self._performance_metrics['classification_time'].append(time.time() - start_time)
            return cached_result
        
        self._performance_metrics['cache_misses'] += 1
        
        try:
            # Load land use data
            gdf = self._load_land_use_data()
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Find intersecting polygon using optimized spatial query
            intersects = self._optimized_spatial_query(point, gdf)
            
            if len(intersects) > 0:
                # Get the first intersecting polygon's Code_18
                clc_code = intersects.iloc[0]['Code_18']
                terrain_type = terrain_config_service.get_terrain_type_from_clc_code(clc_code)
                
                # Apply enhanced classification rules with confidence scoring
                terrain_type, confidence_score = self._apply_enhanced_rules_with_confidence(
                    terrain_type, longitude, latitude, gdf
                )
                
                # Cache the result with hierarchical timeout
                cache_timeout = self._get_adaptive_cache_timeout(terrain_type)
                cache.set(cache_key, terrain_type, cache_timeout)
                
                # Cache confidence score separately
                cache.set(confidence_cache_key, confidence_score, cache_timeout)
                
                # Cache spatial extent data for reuse
                if spatial_cache_key not in cache:
                    spatial_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf)
                    cache.set(spatial_cache_key, spatial_data, self._index_cache_timeout)
                
                self._performance_metrics['classification_time'].append(time.time() - start_time)
                
                logger.debug(f"Coordinates ({longitude}, {latitude}) -> CLC: {clc_code} -> Terrain: {terrain_type} (Confidence: {confidence_score:.2f})")
                return terrain_type
            else:
                logger.warning(f"No land use data found at coordinates ({longitude}, {latitude})")
                cache.set(cache_key, None, self.cache_timeout)
                cache.set(confidence_cache_key, 0.0, self.cache_timeout)
                self._performance_metrics['classification_time'].append(time.time() - start_time)
                return None
                
        except Exception as e:
            logger.error(f"Error determining terrain type at coordinates ({longitude}, {latitude}): {e}")
            self._performance_metrics['classification_time'].append(time.time() - start_time)
            return None
    
    def get_terrain_confidence(self, longitude: float, latitude: float) -> float:
        """Get confidence score for terrain classification at coordinates."""
        confidence_cache_key = f"confidence_{longitude:.6f}_{latitude:.6f}"
        cached_confidence = cache.get(confidence_cache_key)
        
        if cached_confidence is not None:
            return cached_confidence
        
        # If not cached, run classification to generate confidence
        self.get_terrain_type_at_coordinates(longitude, latitude)
        
        # Return cached confidence
        return cache.get(confidence_cache_key, 0.0)
    
    def get_terrain_classification_details(self, longitude: float, latitude: float) -> dict:
        """
        Get detailed terrain classification information including base and final terrain types.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            
        Returns:
            Dictionary with detailed classification information
        """
        try:
            # Load land use data
            gdf = self._load_land_use_data()
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Find intersecting polygon using optimized spatial query
            intersects = self._optimized_spatial_query(point, gdf)
            
            if len(intersects) > 0:
                # Get the first intersecting polygon's Code_18
                clc_code = intersects.iloc[0]['Code_18']
                base_terrain_type = terrain_config_service.get_terrain_type_from_clc_code(clc_code)
                
                # Apply enhanced classification rules with confidence scoring
                final_terrain_type, confidence_score = self._apply_enhanced_rules_with_confidence(
                    base_terrain_type, longitude, latitude, gdf
                )
                
                # Get detected CLC codes
                detected_clc_codes = intersects['Code_18'].unique().tolist()
                
                # Use the same rule application logic as the main classification
                # Calculate weighted scores for each applicable rule
                rule_scores = self._calculate_weighted_rule_scores(base_terrain_type, longitude, latitude, gdf)
                
                # Sort rules by priority and score
                scored_rules = [
                    (name, rule, score) for name, rule, score in rule_scores
                    if rule.get('enabled', True) and score > 0
                ]
                scored_rules.sort(key=lambda x: (x[1].get('priority', 999), -x[2]))
                
                applicable_rules = []
                rule_explanations = {}
                
                # Only the highest scoring rule should be applied
                if scored_rules:
                    rule_name, rule, score = scored_rules[0]
                    applicable_rules.append({
                        'name': rule_name,
                        'priority': rule.get('priority', 999),
                        'description': rule.get('description', ''),
                        'score': score
                    })
                    # Generate explanation for this rule
                    rule_explanations[rule_name] = self._generate_rule_explanation(
                        rule_name, rule, base_terrain_type, longitude, latitude, gdf
                    )
                
                return {
                    'base_terrain_type': base_terrain_type,
                    'terrain_type': final_terrain_type,
                    'confidence_score': confidence_score,
                    'detected_clc_codes': detected_clc_codes,
                    'primary_clc_code': clc_code,
                    'applicable_rules': applicable_rules,
                    'rule_explanations': rule_explanations
                }
            else:
                return {
                    'base_terrain_type': None,
                    'terrain_type': None,
                    'confidence_score': 0.0,
                    'detected_clc_codes': [],
                    'primary_clc_code': None,
                    'applicable_rules': [],
                    'rule_explanations': {}
                }
                
        except Exception as e:
            logger.error(f"Error getting terrain classification details at coordinates ({longitude}, {latitude}): {e}")
            return {
                'base_terrain_type': None,
                'terrain_type': None,
                'confidence_score': 0.0,
                'detected_clc_codes': [],
                'primary_clc_code': None,
                'applicable_rules': [],
                'rule_explanations': {}
            }
    
    def detect_clc_codes_at_coordinates(self, longitude: float, latitude: float) -> List[str]:
        """
        Detect all CLC codes at specific coordinates.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            
        Returns:
            List of unique CLC codes found at the coordinates
        """
        try:
            # Load land use data
            gdf = self._load_land_use_data()
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Find intersecting polygons using optimized spatial query
            intersects = self._optimized_spatial_query(point, gdf)
            
            if len(intersects) > 0:
                # Get unique CLC codes from all intersecting polygons
                clc_codes = intersects['Code_18'].unique().tolist()
                logger.debug(f"Found {len(clc_codes)} CLC codes at ({longitude}, {latitude}): {clc_codes}")
                return clc_codes
            else:
                logger.debug(f"No land use data found at coordinates ({longitude}, {latitude})")
                return []
                
        except Exception as e:
            logger.error(f"Error detecting CLC codes at coordinates ({longitude}, {latitude}): {e}")
            return []
    
    def get_clc_codes_in_extent(self, longitude: float, latitude: float, radius_km: float = 2.0) -> List[str]:
        """
        Get all CLC codes within spatial extent of coordinates.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            radius_km: Analysis radius in kilometers
            
        Returns:
            List of unique CLC codes found within the extent
        """
        try:
            # Load land use data
            gdf = self._load_land_use_data()
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Convert radius to degrees
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            radius_deg_lat = radius_km / km_per_deg_lat
            
            # Create buffer and intersect with land use data
            search_area = point.buffer(radius_deg_lat)
            intersects = gdf[gdf.geometry.intersects(search_area)]
            
            if len(intersects) > 0:
                # Get unique CLC codes from all intersecting polygons
                clc_codes = intersects['Code_18'].unique().tolist()
                logger.debug(f"Found {len(clc_codes)} CLC codes within {radius_km}km of ({longitude}, {latitude}): {clc_codes}")
                return clc_codes
            else:
                logger.debug(f"No land use data found within {radius_km}km of coordinates ({longitude}, {latitude})")
                return []
                
        except Exception as e:
            logger.error(f"Error detecting CLC codes in extent of ({longitude}, {latitude}): {e}")
            return []
    
    def _apply_enhanced_rules_with_confidence(self, terrain_type: str, longitude: float, latitude: float, gdf) -> Tuple[str, float]:
        """
        Apply enhanced classification rules with confidence scoring.
        
        Returns:
            Tuple of (terrain_type, confidence_score)
        """
        # Get classification rules from configuration
        rules = terrain_config_service.get_classification_rules()
        
        # Calculate weighted scores for each applicable rule
        rule_scores = self._calculate_weighted_rule_scores(terrain_type, longitude, latitude, gdf)
        
        # Sort rules by priority and score
        scored_rules = [
            (name, rule, score) for name, rule, score in rule_scores
            if rule.get('enabled', True) and score > 0
        ]
        scored_rules.sort(key=lambda x: (x[1].get('priority', 999), -x[2]))
        
        # Calculate base confidence from CLC mapping
        base_confidence = self._calculate_base_confidence(terrain_type, longitude, latitude, gdf)
        
        # Apply the highest scoring rule and adjust confidence
        if scored_rules:
            rule_name, rule, score = scored_rules[0]
            modified_terrain = self._get_rule_result(rule_name, terrain_type, longitude, latitude, gdf)
            
            if modified_terrain != terrain_type:
                # Rule was applied - adjust confidence based on rule score
                rule_confidence = min(score / 100.0, 1.0)  # Normalize score to 0-1
                final_confidence = (base_confidence + rule_confidence) / 2.0
                
                logger.debug(f"Rule {rule_name} applied with score {score:.2f}: {terrain_type} -> {modified_terrain} (Confidence: {final_confidence:.2f})")
                return modified_terrain, final_confidence
        
        # No rule applied - return base classification with base confidence
        return terrain_type, base_confidence
    
    def _calculate_base_confidence(self, terrain_type: str, longitude: float, latitude: float, gdf) -> float:
        """Calculate base confidence score from CLC mapping and spatial data quality."""
        try:
            # Get multi-scale spatial data
            multi_scale_data = self._multi_scale_analysis(longitude, latitude, gdf, [1.0, 2.0])
            
            # Calculate confidence factors
            confidence_factors = {
                'data_consistency': self._calculate_data_consistency(multi_scale_data),
                'terrain_clarity': self._calculate_terrain_clarity(terrain_type, multi_scale_data),
                'spatial_homogeneity': self._calculate_spatial_homogeneity(multi_scale_data)
            }
            
            # Weight the factors
            weights = {
                'data_consistency': 0.4,
                'terrain_clarity': 0.4,
                'spatial_homogeneity': 0.2
            }
            
            # Calculate weighted confidence
            confidence = sum(
                confidence_factors[factor] * weights[factor] 
                for factor in confidence_factors
            )
            
            return min(max(confidence, 0.1), 1.0)  # Clamp between 0.1 and 1.0
            
        except Exception as e:
            logger.debug(f"Error calculating base confidence: {e}")
            return 0.5  # Default moderate confidence
    
    def _calculate_data_consistency(self, multi_scale_data: Dict[float, dict]) -> float:
        """Calculate data consistency across different scales."""
        if len(multi_scale_data) < 2:
            return 0.5
        
        scales = sorted(multi_scale_data.keys())
        consistency_scores = []
        
        for i in range(len(scales) - 1):
            scale1_data = multi_scale_data[scales[i]]
            scale2_data = multi_scale_data[scales[i + 1]]
            
            # Calculate correlation between scales
            categories = ['agriculture', 'complex_agriculture', 'forest', 'urban', 'coastal']
            
            values1 = [scale1_data.get(cat, 0) for cat in categories]
            values2 = [scale2_data.get(cat, 0) for cat in categories]
            
            # Simple correlation calculation
            if sum(values1) > 0 and sum(values2) > 0:
                correlation = sum(min(v1, v2) for v1, v2 in zip(values1, values2)) / max(sum(values1), sum(values2))
                consistency_scores.append(correlation)
        
        return np.mean(consistency_scores) if consistency_scores else 0.5
    
    def _calculate_terrain_clarity(self, terrain_type: str, multi_scale_data: Dict[float, dict]) -> float:
        """Calculate how clearly the terrain type is expressed in the spatial data."""
        # Expected dominant characteristics for each terrain type
        terrain_signatures = {
            '0': {'coastal': 60.0},
            'II': {'agriculture': 50.0},
            'IIIa': {'complex_agriculture': 15.0, 'forest': 20.0},
            'IIIb': {'urban': 40.0},
            'IV': {'urban': 70.0}
        }
        
        signature = terrain_signatures.get(terrain_type, {})
        if not signature:
            return 0.5
        
        clarity_scores = []
        
        for scale, data in multi_scale_data.items():
            scale_clarity = 0.0
            
            for category, expected_threshold in signature.items():
                actual_pct = data.get(category, 0)
                if actual_pct >= expected_threshold:
                    scale_clarity += 1.0
                else:
                    scale_clarity += actual_pct / expected_threshold
            
            clarity_scores.append(scale_clarity / len(signature))
        
        return np.mean(clarity_scores) if clarity_scores else 0.5
    
    def _calculate_spatial_homogeneity(self, multi_scale_data: Dict[float, dict]) -> float:
        """Calculate spatial homogeneity - higher for less mixed terrain."""
        homogeneity_scores = []
        
        for scale, data in multi_scale_data.items():
            # Calculate Shannon entropy for land use distribution
            categories = ['agriculture', 'complex_agriculture', 'forest', 'urban', 'coastal']
            values = [data.get(cat, 0) for cat in categories]
            
            # Normalize to probabilities
            total = sum(values)
            if total == 0:
                homogeneity_scores.append(0.5)
                continue
            
            probabilities = [v / total for v in values if v > 0]
            
            # Calculate entropy
            entropy = -sum(p * math.log(p) for p in probabilities)
            max_entropy = math.log(len(probabilities))
            
            # Convert entropy to homogeneity (inverse of entropy)
            homogeneity = 1.0 - (entropy / max_entropy)
            homogeneity_scores.append(homogeneity)
        
        return np.mean(homogeneity_scores) if homogeneity_scores else 0.5
    
    def _optimized_spatial_query(self, point: Point, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Optimized spatial query using multi-level indexing."""
        self._performance_metrics['spatial_queries'] += 1
        
        # Use the main spatial index for initial filtering
        try:
            # Get possible matches using spatial index
            possible_matches_index = list(gdf.sindex.intersection(point.bounds))
            if len(possible_matches_index) == 0:
                return gpd.GeoDataFrame()
            
            possible_matches = gdf.iloc[possible_matches_index]
            
            # Filter by actual intersection
            intersects = possible_matches[possible_matches.geometry.intersects(point)]
            
            return intersects
            
        except Exception as e:
            logger.debug(f"Error in optimized spatial query: {e}")
            # Fallback to basic query
            return gdf[gdf.geometry.intersects(point)]
    
    def _get_adaptive_cache_timeout(self, terrain_type: str) -> int:
        """Get adaptive cache timeout based on terrain type complexity."""
        # More complex terrain types get longer cache times
        timeout_map = {
            '0': 7200,  # Coastal - stable
            'IV': 3600,  # Urban - moderate changes
            'IIIb': 1800,  # Semi-urban - more dynamic
            'IIIa': 1800,  # Bocage - seasonal changes
            'II': 3600,   # Open countryside - stable
        }
        return timeout_map.get(terrain_type, self.cache_timeout)
    
    def _apply_enhanced_rules(self, terrain_type: str, longitude: float, latitude: float, gdf) -> str:
        """
        Apply enhanced classification rules with weighted scoring and multi-scale analysis.
        
        Args:
            terrain_type: Initial terrain type from CLC mapping
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            
        Returns:
            Enhanced terrain type
        """
        # Get classification rules from configuration
        rules = terrain_config_service.get_classification_rules()
        
        # Calculate weighted scores for each applicable rule
        rule_scores = self._calculate_weighted_rule_scores(terrain_type, longitude, latitude, gdf)
        
        # Sort rules by priority and score
        scored_rules = [
            (name, rule, score) for name, rule, score in rule_scores
            if rule.get('enabled', True) and score > 0
        ]
        scored_rules.sort(key=lambda x: (x[1].get('priority', 999), -x[2]))
        
        # Apply the highest scoring rule
        for rule_name, rule, score in scored_rules:
            modified_terrain = self._get_rule_result(rule_name, terrain_type, longitude, latitude, gdf)
            if modified_terrain != terrain_type:
                logger.debug(f"Rule {rule_name} applied with score {score:.2f}: {terrain_type} -> {modified_terrain}")
                return modified_terrain
        
        return terrain_type
    
    def _calculate_weighted_rule_scores(self, terrain_type: str, longitude: float, latitude: float, gdf) -> List[Tuple[str, dict, float]]:
        """Calculate weighted scores for classification rules using multi-scale analysis."""
        rules = terrain_config_service.get_classification_rules()
        scored_rules = []
        
        for rule_name, rule in rules.items():
            if not rule.get('enabled', True):
                continue
            
            score = self._calculate_rule_score(rule_name, rule, terrain_type, longitude, latitude, gdf)
            scored_rules.append((rule_name, rule, score))
        
        return scored_rules
    
    def _calculate_rule_score(self, rule_name: str, rule: dict, terrain_type: str, 
                            longitude: float, latitude: float, gdf) -> float:
        """Calculate weighted score for a specific classification rule."""
        try:
            if rule_name == 'coastal_exposure':
                return self._score_coastal_exposure(longitude, latitude, gdf)
            
            elif rule_name == 'dense_urban':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II', 'IIIb'])
                if terrain_type not in applicable_terrain:
                    return 0.0
                return self._score_dense_urban(longitude, latitude, gdf)
            
            elif rule_name == 'building_density_verification':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['IIIb'])
                if terrain_type not in applicable_terrain:
                    return 0.0
                return self._score_building_density_verification(longitude, latitude, gdf)
            
            elif rule_name == 'bocage_characteristics':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['IV', 'IIIb'])
                if terrain_type not in applicable_terrain:
                    return 0.0
                return self._score_bocage_characteristics(longitude, latitude, gdf)
            
            elif rule_name == 'open_countryside':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['IIIa'])
                if terrain_type not in applicable_terrain:
                    return 0.0
                return self._score_open_countryside(longitude, latitude, gdf)
            
            elif rule_name == 'transitional_zone':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II'])
                if terrain_type not in applicable_terrain:
                    return 0.0
                return self._score_transitional_zone(longitude, latitude, gdf)
            
            elif rule_name == 'proximity_urban':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II'])
                if terrain_type not in applicable_terrain:
                    return 0.0
                return self._score_proximity_urban(longitude, latitude, gdf)
            
            elif rule_name == 'proximity_forest':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II'])
                if terrain_type not in applicable_terrain:
                    return 0.0
                return self._score_proximity_forest(longitude, latitude, gdf)
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"Error calculating score for rule {rule_name}: {e}")
            return 0.0
    
    def _multi_scale_analysis(self, longitude: float, latitude: float, gdf, scales: List[float] = None) -> Dict[float, dict]:
        """Perform multi-scale spatial analysis at different radii."""
        if scales is None:
            scales = [0.5, 1.0, 2.0, 5.0]  # 500m, 1km, 2km, 5km
        
        results = {}
        for scale in scales:
            extent_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, scale)
            results[scale] = extent_data
        
        return results
    
    def _score_coastal_exposure(self, longitude: float, latitude: float, gdf) -> float:
        """Score coastal exposure using multi-scale analysis."""
        multi_scale_data = self._multi_scale_analysis(longitude, latitude, gdf, [1.0, 2.0, 5.0])
        
        score = 0.0
        
        # Check multiple scales for coastal presence
        for scale, data in multi_scale_data.items():
            coastal_pct = data.get('coastal', 0)
            urban_pct = data.get('urban', 0)
            
            # Higher weight for larger scales
            scale_weight = scale / 5.0  # Normalize to 0-1
            
            if urban_pct > 50:
                # Urban areas - only score if true coastal water
                if coastal_pct > 10:
                    score += 25.0 * scale_weight
            else:
                # Non-urban areas - any significant coastal presence
                if coastal_pct > 5:
                    score += 30.0 * scale_weight
        
        return min(score, 100.0)
    
    def _score_dense_urban(self, longitude: float, latitude: float, gdf) -> float:
        """Score dense urban characteristics using multi-scale analysis."""
        # Use the same logic as the boolean check to ensure consistency
        if not self._is_dense_urban_area(longitude, latitude, gdf):
            return 0.0
        
        # If the rule applies, give it a score based on how strongly it applies
        extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
        
        if not extent_pct:
            return 0.0
        
        urban_pct = extent_pct.get('urban', 0)
        
        # Get thresholds from configuration
        thresholds = terrain_config_service.get_spatial_analysis_config()
        total_urban_threshold = thresholds.get('density_thresholds', {}).get('total_urban_area', 0.65)
        
        score = 0.0
        
        # Score based on how much the urban coverage exceeds the threshold
        if urban_pct > (total_urban_threshold * 100):  # Convert from decimal to percentage
            excess = urban_pct - (total_urban_threshold * 100)
            score += min(excess / 10.0, 1.0) * 50.0  # Up to 50 points for excess urban coverage
        
        # Add base score for meeting the threshold
        score += 50.0
        
        return min(score, 100.0)
    
    def _score_building_density_verification(self, longitude: float, latitude: float, gdf) -> float:
        """Score building density verification for ambiguous urban cases."""
        try:
            # Get spatial extent to check if this is an ambiguous case
            extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
            
            if not extent_pct:
                return 0.0
            
            urban_pct = extent_pct.get('urban', 0)
            
            # Check if this falls in the ambiguous range
            config = terrain_config_service.load_config()
            building_config = config.get('building_density_analysis', {})
            conditions = building_config.get('conditions', {})
            
            min_urban = conditions.get('clc_urban_range_min', 30.0)
            max_urban = conditions.get('clc_urban_range_max', 60.0)
            
            if not (min_urban <= urban_pct <= max_urban):
                return 0.0  # Not an ambiguous case
            
            # Get building density metrics
            building_metrics = bdtopo_service.calculate_building_density(longitude, latitude)
            
            if building_metrics.get('building_count', 0) == 0:
                return 0.0  # No building data available
            
            # Score based on building density metrics
            coverage = building_metrics.get('building_coverage_pct', 0.0)
            avg_height = building_metrics.get('average_height', 0.0)
            density_score = building_metrics.get('building_density_score', 0.0)
            
            # Base score from density score
            score = min(density_score, 80.0)  # Max 80 points from density score
            
            # Bonus points for clear cases
            if coverage > 40.0:  # High coverage
                score += 10.0
            elif coverage < 20.0:  # Low coverage
                score += 10.0
            
            if avg_height > 15.0:  # High buildings
                score += 10.0
            
            return min(score, 100.0)
            
        except Exception as e:
            logger.debug(f"Error scoring building density verification: {e}")
            return 0.0
    
    def _score_bocage_characteristics(self, longitude: float, latitude: float, gdf) -> float:
        """Score bocage characteristics using multi-scale analysis."""
        # Use the same logic as the boolean check to ensure consistency
        if not self._has_bocage_characteristics(longitude, latitude, gdf):
            return 0.0
        
        # If the rule applies, give it a score based on how strongly it applies
        extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
        
        if not extent_pct:
            return 0.0
        
        agri_pct = extent_pct.get('agriculture', 0)
        complex_pct = extent_pct.get('complex_agriculture', 0)
        forest_pct = extent_pct.get('forest', 0)
        urban_pct = extent_pct.get('urban', 0)
        
        score = 0.0
        
        # Score based on how well the location matches bocage characteristics
        # Only give points when thresholds are actually met
        if agri_pct > 25:
            score += min((agri_pct - 25) / 25.0, 1.0) * 25.0  # Points for exceeding agriculture threshold
        
        if complex_pct > 10:
            score += min((complex_pct - 10) / 10.0, 1.0) * 30.0  # Points for exceeding complex agriculture threshold
        
        if forest_pct > 15:
            score += min((forest_pct - 15) / 15.0, 1.0) * 25.0  # Points for exceeding forest threshold
        
        if urban_pct < 60:
            score += (60 - urban_pct) / 60.0 * 20.0  # Points for not being urban dominated
        
        return min(score, 100.0)
    
    def _score_open_countryside(self, longitude: float, latitude: float, gdf) -> float:
        """Score open countryside characteristics using multi-scale analysis."""
        multi_scale_data = self._multi_scale_analysis(longitude, latitude, gdf, [1.0, 2.0])
        
        score = 0.0
        
        for scale, data in multi_scale_data.items():
            agri_pct = data.get('agriculture', 0)
            complex_pct = data.get('complex_agriculture', 0)
            forest_pct = data.get('forest', 0)
            urban_pct = data.get('urban', 0)
            
            total_agri = agri_pct + complex_pct
            
            # Open countryside indicators
            agri_score = min(total_agri / 60.0, 1.0) * 40.0  # 60%+ total agriculture
            urban_penalty = max(0, urban_pct / 5.0) * 30.0  # Penalty for urban presence
            forest_penalty = max(0, (forest_pct - 30.0) / 30.0) * 20.0  # Penalty for too much forest
            complex_penalty = max(0, (complex_pct - 35.0) / 35.0) * 10.0  # Penalty for too much complexity
            
            scale_score = agri_score - urban_penalty - forest_penalty - complex_penalty
            
            # Weight by scale
            scale_weight = 0.6 if scale == 2.0 else 0.4
            score += max(0, scale_score) * scale_weight
        
        return min(score, 100.0)
    
    def _score_transitional_zone(self, longitude: float, latitude: float, gdf) -> float:
        """Score transitional zone characteristics using multi-scale analysis."""
        # Use the same logic as the boolean check to ensure consistency
        if not self._is_enhanced_transitional_zone(longitude, latitude, gdf):
            return 0.0
        
        # If the rule applies, give it a score based on how strongly it applies
        extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
        
        if not extent_pct:
            return 0.0
        
        agri_pct = extent_pct.get('agriculture', 0)
        complex_pct = extent_pct.get('complex_agriculture', 0)
        forest_pct = extent_pct.get('forest', 0)
        urban_pct = extent_pct.get('urban', 0)
        
        score = 0.0
        
        # Score based on how well the location matches transitional zone characteristics
        # Higher score for mixed patterns with significant complexity
        if complex_pct >= 10 and urban_pct >= 5:
            score += 40.0
        
        if complex_pct >= 10 and (agri_pct > 20 or forest_pct > 10):
            score += 30.0
        
        if urban_pct >= 40 and urban_pct <= 60 and complex_pct >= 10:
            score += 30.0
        
        return min(score, 100.0)
    
    def _score_proximity_urban(self, longitude: float, latitude: float, gdf) -> float:
        """Score urban proximity using distance-based analysis."""
        threshold_km = terrain_config_service.get_spatial_parameter('distance_thresholds_km', 'urban_proximity', 3.0)
        
        if self._is_near_urban(longitude, latitude, gdf, threshold_km):
            # Calculate proximity score based on actual distance
            distance_score = self._calculate_distance_score(longitude, latitude, 'urban', threshold_km)
            return distance_score
        
        return 0.0
    
    def _score_proximity_forest(self, longitude: float, latitude: float, gdf) -> float:
        """Score forest proximity using distance-based analysis."""
        threshold_km = terrain_config_service.get_spatial_parameter('distance_thresholds_km', 'forest_proximity', 2.0)
        
        # Use the same logic as the boolean check for consistency
        if self._is_near_forest(longitude, latitude, gdf, threshold_km) and self._has_meaningful_forest_agriculture_mix(longitude, latitude, gdf):
            # Calculate proximity score based on actual distance
            distance_score = self._calculate_distance_score(longitude, latitude, 'forest', threshold_km)
            return distance_score
        
        return 0.0
    
    def _calculate_distance_score(self, longitude: float, latitude: float, category: str, threshold_km: float) -> float:
        """Calculate distance-based proximity score."""
        try:
            point = Point(longitude, latitude)
            
            # Get the appropriate pre-filtered data
            if category == 'urban' and self._urban_areas is not None:
                areas = self._urban_areas
            elif category == 'forest' and self._forest_areas is not None:
                areas = self._forest_areas
            else:
                return 0.0
            
            # Find nearest feature
            nearest_distance = float('inf')
            for _, area in areas.iterrows():
                try:
                    distance = point.distance(area.geometry.centroid) * 111.0  # Convert to km
                    nearest_distance = min(nearest_distance, distance)
                except:
                    continue
            
            if nearest_distance == float('inf'):
                return 0.0
            
            # Score based on inverse distance (closer = higher score)
            if nearest_distance <= threshold_km:
                score = (1.0 - nearest_distance / threshold_km) * 100.0
                return score
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"Error calculating distance score for {category}: {e}")
            return 0.0
    
    def _apply_classification_rule(self, rule_name: str, rule: dict, terrain_type: str, 
                                 longitude: float, latitude: float, gdf) -> bool:
        """Check if a classification rule should be applied."""
        try:
            if rule_name == 'coastal_exposure':
                return self._has_exposed_coastal_conditions(longitude, latitude, gdf)
            
            elif rule_name == 'dense_urban':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II', 'IIIb'])
                return terrain_type in applicable_terrain and self._is_dense_urban_area(longitude, latitude, gdf)
            
            elif rule_name == 'bocage_characteristics':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['IV', 'IIIb'])
                return terrain_type in applicable_terrain and self._has_bocage_characteristics(longitude, latitude, gdf)
            
            elif rule_name == 'open_countryside':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['IIIa'])
                return terrain_type in applicable_terrain and self._is_actually_open_countryside(longitude, latitude, gdf)
            
            elif rule_name == 'transitional_zone':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II'])
                return terrain_type in applicable_terrain and self._is_enhanced_transitional_zone(longitude, latitude, gdf)
            
            elif rule_name == 'proximity_urban':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II'])
                return terrain_type in applicable_terrain and self._is_near_urban(longitude, latitude, gdf)
            
            elif rule_name == 'proximity_forest':
                applicable_terrain = rule.get('conditions', {}).get('applicable_to_terrain', ['II'])
                if terrain_type not in applicable_terrain:
                    return False
                # Only apply if there's meaningful forest presence AND agricultural land
                return self._is_near_forest(longitude, latitude, gdf) and self._has_meaningful_forest_agriculture_mix(longitude, latitude, gdf)
            
            return False
            
        except Exception as e:
            logger.debug(f"Error applying rule {rule_name}: {e}")
            return False
    
    def _get_rule_result(self, rule_name: str, terrain_type: str, 
                        longitude: float, latitude: float, gdf) -> str:
        """Get the result terrain type for a classification rule."""
        rules = terrain_config_service.get_classification_rules()
        rule = rules.get(rule_name, {})
        
        if rule_name == 'coastal_exposure':
            return '0'
        elif rule_name == 'dense_urban':
            return 'IV'
        elif rule_name == 'building_density_verification':
            # Use building data to determine the appropriate terrain type
            building_result = self._verify_dense_urban_with_buildings(longitude, latitude, 0.0)
            if building_result is True:
                return 'IV'
            elif building_result is False:
                return 'IIIb'
            else:
                # Fallback to current terrain type if building data unavailable
                return terrain_type
        elif rule_name == 'bocage_characteristics':
            return 'IIIa'
        elif rule_name == 'open_countryside':
            return 'II'
        elif rule_name == 'transitional_zone':
            return 'IIIa'
        elif rule_name == 'proximity_urban':
            return rule.get('conditions', {}).get('target_terrain', 'IIIb')
        elif rule_name == 'proximity_forest':
            return rule.get('conditions', {}).get('target_terrain', 'IIIa')
        
        return terrain_type
    
    def _generate_rule_explanation(self, rule_name: str, rule: dict, terrain_type: str, 
                                   longitude: float, latitude: float, gdf) -> str:
        """Generate human-readable explanation for why a rule was applied."""
        try:
            if rule_name == 'coastal_exposure':
                extent_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
                coastal_pct = extent_data.get('coastal', 0)
                urban_pct = extent_data.get('urban', 0)
                return f"Coastal exposure detected: {coastal_pct:.1f}% coastal, {urban_pct:.1f}% urban in 2km radius"
            
            elif rule_name == 'dense_urban':
                extent_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
                urban_pct = extent_data.get('urban', 0)
                return f"Dense urban area: {urban_pct:.1f}% urban coverage exceeds threshold"
            
            elif rule_name == 'building_density_verification':
                extent_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
                urban_pct = extent_data.get('urban', 0)
                building_metrics = bdtopo_service.calculate_building_density(longitude, latitude)
                coverage = building_metrics.get('building_coverage_pct', 0.0)
                avg_height = building_metrics.get('average_height', 0.0)
                return f"Building density verification: {urban_pct:.1f}% CLC urban, {coverage:.1f}% building coverage, {avg_height:.1f}m avg height"
            
            elif rule_name == 'bocage_characteristics':
                extent_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
                agri_pct = extent_data.get('agriculture', 0) + extent_data.get('complex_agriculture', 0)
                forest_pct = extent_data.get('forest', 0)
                return f"Bocage pattern: {agri_pct:.1f}% agriculture, {forest_pct:.1f}% forest indicates rural character"
            
            elif rule_name == 'open_countryside':
                extent_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
                total_agri = extent_data.get('agriculture', 0) + extent_data.get('complex_agriculture', 0)
                return f"Open countryside: {total_agri:.1f}% total agriculture indicates open terrain"
            
            elif rule_name == 'transitional_zone':
                extent_data = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
                urban_pct = extent_data.get('urban', 0)
                complex_pct = extent_data.get('complex_agriculture', 0)
                return f"Transitional zone: {urban_pct:.1f}% urban, {complex_pct:.1f}% complex agriculture"
            
            elif rule_name == 'proximity_urban':
                # Calculate actual distance to nearest urban area
                distance = self._calculate_distance_to_category(longitude, latitude, 'urban', gdf)
                return f"Urban proximity: {distance:.1f}km to nearest urban area"
            
            elif rule_name == 'proximity_forest':
                # Calculate actual distance to nearest forest area
                distance = self._calculate_distance_to_category(longitude, latitude, 'forest', gdf)
                return f"Forest proximity: {distance:.1f}km to nearest forest area"
            
            return f"Rule '{rule_name}' applied based on spatial analysis"
            
        except Exception as e:
            logger.debug(f"Error generating explanation for rule {rule_name}: {e}")
            return f"Rule '{rule_name}' applied"
    
    def _calculate_distance_to_category(self, longitude: float, latitude: float, category: str, gdf) -> float:
        """Calculate distance to nearest land use category."""
        try:
            # Get category codes from configuration
            influence = terrain_config_service.get_influence_percentages()
            spatial_categories = influence.get('spatial_extent_categories', {})
            
            category_codes = {
                'urban': spatial_categories.get('urban', {}).get('codes', []),
                'forest': spatial_categories.get('forest', {}).get('codes', []),
                'agriculture': spatial_categories.get('agriculture', {}).get('codes', []),
                'complex_agriculture': spatial_categories.get('complex_agriculture', {}).get('codes', []),
                'coastal': spatial_categories.get('coastal', {}).get('codes', [])
            }
            
            codes = category_codes.get(category, [])
            if not codes:
                return float('inf')
            
            # Filter by category
            category_polygons = gdf[gdf['Code_18'].isin(codes)]
            
            if len(category_polygons) == 0:
                return float('inf')
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Calculate minimum distance
            distances = category_polygons.geometry.distance(point)
            
            # Convert to kilometers (approximate)
            min_distance_deg = distances.min()
            km_per_deg = 111.0  # Approximate
            return min_distance_deg * km_per_deg
            
        except Exception as e:
            logger.debug(f"Error calculating distance to {category}: {e}")
            return float('inf')
    
    def _calculate_spatial_extent_percentages(self, longitude: float, latitude: float, gdf, radius_km: float = 1.0) -> dict:
        """
        Calculate land use percentages based on spatial extent (area) instead of polygon counts.
        This provides more accurate classification by considering actual spatial coverage.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            radius_km: Analysis radius in kilometers
            
        Returns:
            Dictionary with land use category percentages based on spatial extent
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Convert radius to degrees
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            radius_deg_lat = radius_km / km_per_deg_lat
            
            # Create buffer and intersect with land use data
            search_area = point.buffer(radius_deg_lat)
            intersects = gdf[gdf.geometry.intersects(search_area)]
            
            if len(intersects) == 0:
                return {}
            
            # Early optimization: if only a few polygons, use simplified calculation
            if len(intersects) <= 10:
                return self._fast_spatial_extent_calculation(intersects, search_area)
            
            # Calculate actual areas of intersected polygons
            # Clip polygons to the search area for accurate area calculation
            clipped_intersects = intersects.copy()
            clipped_intersects['geometry'] = clipped_intersects.geometry.intersection(search_area)
            
            # Reproject to a projected CRS for accurate area calculations
            # Use appropriate UTM zone for France (Zone 31N for most of France)
            clipped_intersects['geometry'] = clipped_intersects['geometry'].to_crs('EPSG:32631')
            
            # Calculate areas in km² (UTM coordinates are in meters)
            clipped_intersects['area_km2'] = clipped_intersects.geometry.area / 1_000_000  # m² to km²
            total_area = clipped_intersects['area_km2'].sum()
            
            if total_area == 0:
                return {}
            
            # Get land use categories from configuration
            influence = terrain_config_service.get_influence_percentages()
            spatial_categories = influence.get('spatial_extent_categories', {})
            
            agri_codes = set(spatial_categories.get('agriculture', {}).get('codes', ['211', '212', '213', '231']))
            complex_agri = set(spatial_categories.get('complex_agriculture', {}).get('codes', ['241', '242', '243', '244']))
            forest_codes = set(spatial_categories.get('forest', {}).get('codes', ['311', '312', '313', '321', '322', '323', '324']))
            urban_codes = set(spatial_categories.get('urban', {}).get('codes', ['111', '112', '121', '122', '123', '124', '131', '132', '133', '142']))
            true_coastal_codes = set(spatial_categories.get('coastal', {}).get('codes', ['521', '522', '523', '423', '331']))
            inland_water_codes = set(spatial_categories.get('inland_water', {}).get('codes', ['511', '512']))
            
            # Calculate spatial extent percentages by category
            extent_percentages = {}
            
            for category_name, code_set in [
                ('agriculture', agri_codes),
                ('complex_agriculture', complex_agri),
                ('forest', forest_codes),
                ('urban', urban_codes),
                ('coastal', true_coastal_codes)
            ]:
                category_area = clipped_intersects[
                    clipped_intersects['Code_18'].isin(code_set)
                ]['area_km2'].sum()
                
                extent_percentages[category_name] = (category_area / total_area) * 100
            
            return extent_percentages
            
        except Exception as e:
            logger.debug(f"Error calculating spatial extent percentages: {e}")
            return {}
    
    def _fast_spatial_extent_calculation(self, intersects: gpd.GeoDataFrame, search_area) -> dict:
        """
        Fast spatial extent calculation for simple cases with few polygons.
        Avoids expensive coordinate transformations for better performance.
        """
        try:
            # Get land use categories from configuration
            influence = terrain_config_service.get_influence_percentages()
            spatial_categories = influence.get('spatial_extent_categories', {})
            
            agri_codes = set(spatial_categories.get('agriculture', {}).get('codes', ['211', '212', '213', '231']))
            complex_agri = set(spatial_categories.get('complex_agriculture', {}).get('codes', ['241', '242', '243', '244']))
            forest_codes = set(spatial_categories.get('forest', {}).get('codes', ['311', '312', '313', '321', '322', '323', '324']))
            urban_codes = set(spatial_categories.get('urban', {}).get('codes', ['111', '112', '121', '122', '123', '124', '131', '132', '133', '142']))
            true_coastal_codes = set(spatial_categories.get('coastal', {}).get('codes', ['521', '522', '523', '423', '331']))
            inland_water_codes = set(spatial_categories.get('inland_water', {}).get('codes', ['511', '512']))
            
            # Use simple polygon count approximation for small areas
            total_polygons = len(intersects)
            extent_percentages = {}
            
            for category_name, code_set in [
                ('agriculture', agri_codes),
                ('complex_agriculture', complex_agri),
                ('forest', forest_codes),
                ('urban', urban_codes),
                ('coastal', true_coastal_codes)
            ]:
                category_count = len(intersects[intersects['Code_18'].isin(code_set)])
                extent_percentages[category_name] = (category_count / total_polygons) * 100 if total_polygons > 0 else 0
            
            return extent_percentages
            
        except Exception as e:
            logger.debug(f"Error in fast spatial extent calculation: {e}")
            return {}
    
    def _calculate_spatial_influence(self, longitude: float, latitude: float, gdf, land_use_codes: set, radius_km: float = 2.0) -> float:
        """
        Calculate spatial influence using distance decay weighting.
        This provides continuous spatial analysis instead of discrete polygon counting.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            land_use_codes: Set of CLC codes to analyze
            radius_km: Analysis radius in kilometers
            
        Returns:
            Spatial influence score (higher = more influence)
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Convert radius to degrees
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            radius_deg_lat = radius_km / km_per_deg_lat
            
            # Find relevant land use polygons within radius
            search_area = point.buffer(radius_deg_lat)
            relevant_polygons = gdf[gdf['Code_18'].isin(land_use_codes)]
            nearby_polygons = relevant_polygons[relevant_polygons.geometry.intersects(search_area)]
            
            if len(nearby_polygons) == 0:
                return 0.0
            
            # Calculate spatial influence with distance decay
            total_influence = 0.0
            
            for _, polygon in nearby_polygons.iterrows():
                # Calculate distance from point to polygon centroid
                distance = point.distance(polygon.geometry.centroid)
                
                # Convert distance to kilometers
                distance_km = distance * km_per_deg_lat
                
                # Calculate polygon area in km²
                polygon_area = polygon.geometry.area * (km_per_deg_lat * km_per_deg_lon)
                
                # Apply distance decay function (inverse square law)
                # Influence = Area / (1 + distance²)
                influence = polygon_area / (1 + distance_km**2)
                
                total_influence += influence
            
            return total_influence
            
        except Exception as e:
            logger.debug(f"Error calculating spatial influence: {e}")
            return 0.0
    
    def _is_near_coast(self, longitude: float, latitude: float, gdf, threshold_km: float = None) -> bool:
        """
        Check if coordinates are near coastal areas using optimized pre-filtered data.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            threshold_km: Distance threshold in kilometers
            
        Returns:
            True if near coast, False otherwise
        """
        try:
            # Use pre-filtered water areas for performance
            water_areas = self._water_areas
            if water_areas is None or len(water_areas) == 0:
                return False
            
            # Get threshold from configuration if not provided
            if threshold_km is None:
                threshold_km = terrain_config_service.get_spatial_parameter('distance_thresholds_km', 'coastal_proximity', 5.0)
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Use proper distance calculation with haversine approximation
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            threshold_deg_lat = threshold_km / km_per_deg_lat
            
            # Use spatial index for faster proximity queries
            possible_matches_index = list(water_areas.sindex.intersection(point.bounds))
            possible_matches = water_areas.iloc[possible_matches_index]
            
            if len(possible_matches) == 0:
                return False
            
            # Create elliptical buffer for more accurate distance
            search_area = point.buffer(threshold_deg_lat)
            nearby_water = possible_matches[possible_matches.geometry.intersects(search_area)]
            
            # Additional check: calculate actual distance to nearest water feature
            if len(nearby_water) > 0:
                return True
            
            # If no direct intersection, check distance to nearest water area
            for _, water_feature in possible_matches.iterrows():
                try:
                    # Calculate approximate distance
                    dist = point.distance(water_feature.geometry) * 111.0  # Convert to km
                    if dist <= threshold_km:
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking coastal proximity: {e}")
            return False
    
    def _is_near_urban(self, longitude: float, latitude: float, gdf, threshold_km: float = 3.0) -> bool:
        """
        Check if coordinates are near urban areas using optimized pre-filtered data.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            threshold_km: Distance threshold in kilometers
            
        Returns:
            True if near urban areas, False otherwise
        """
        try:
            # Use pre-filtered urban areas for performance
            urban_areas = self._urban_areas
            if urban_areas is None or len(urban_areas) == 0:
                return False
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Use proper distance calculation with haversine approximation
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            threshold_deg_lat = threshold_km / km_per_deg_lat
            
            # Use spatial index for faster proximity queries
            possible_matches_index = list(urban_areas.sindex.intersection(point.bounds))
            possible_matches = urban_areas.iloc[possible_matches_index]
            
            if len(possible_matches) == 0:
                return False
            
            # Create elliptical buffer for more accurate distance
            search_area = point.buffer(threshold_deg_lat)
            nearby_urban = possible_matches[possible_matches.geometry.intersects(search_area)]
            
            # Additional check: calculate actual distance to nearest urban feature
            if len(nearby_urban) > 0:
                return True
            
            # If no direct intersection, check distance to nearest urban area
            for _, urban_feature in possible_matches.iterrows():
                try:
                    # Calculate approximate distance
                    dist = point.distance(urban_feature.geometry) * 111.0  # Convert to km
                    if dist <= threshold_km:
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking urban proximity: {e}")
            return False
    
    def _has_meaningful_forest_agriculture_mix(self, longitude: float, latitude: float, gdf) -> bool:
        """
        Check if there's a meaningful mix of forest and agricultural land that justifies 
        upgrading from open countryside to bocage/obstacle terrain.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            
        Returns:
            True if meaningful forest-agriculture mix exists, False otherwise
        """
        try:
            # Get spatial extent percentages
            extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, 2.0)
            
            if not extent_pct:
                return False
            
            forest_pct = extent_pct.get('forest', 0)
            agri_pct = extent_pct.get('agriculture', 0)
            complex_agri_pct = extent_pct.get('complex_agriculture', 0)
            
            # Require very significant forest presence for upgrading agricultural land
            if forest_pct < 25.0:  # Less than 25% forest coverage
                return False
            
            # Require significant agricultural presence
            total_agri = agri_pct + complex_agri_pct
            if total_agri < 40.0:  # Less than 40% agricultural coverage
                return False
            
            # For upgrading agricultural land, require overwhelming forest presence
            # This ensures we only upgrade when it's truly a mixed/bocage landscape
            if forest_pct < 45.0:  # Need at least 45% forest to upgrade from pure agriculture
                return False
            
            # Both forest and agriculture should be substantial
            return True
            
        except Exception as e:
            logger.debug(f"Error checking forest-agriculture mix: {e}")
            return False
    
    def _is_near_forest(self, longitude: float, latitude: float, gdf, threshold_km: float = 2.0) -> bool:
        """
        Check if coordinates are near forest areas, typical of bocage landscapes.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            threshold_km: Distance threshold in kilometers
            
        Returns:
            True if near forest areas, False otherwise
        """
        try:
            # Forest and woodland codes
            forest_codes = ['311', '312', '313', '321', '322', '323', '324']
            forest_areas = gdf[gdf['Code_18'].isin(forest_codes)]
            
            if len(forest_areas) == 0:
                return False
            
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Use proper distance calculation
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            threshold_deg_lat = threshold_km / km_per_deg_lat
            
            # Use spatial index for faster proximity queries
            possible_matches_index = list(forest_areas.sindex.intersection(point.bounds))
            possible_matches = forest_areas.iloc[possible_matches_index]
            
            if len(possible_matches) == 0:
                return False
            
            # Create elliptical buffer for more accurate distance
            search_area = point.buffer(threshold_deg_lat)
            nearby_forest = possible_matches[possible_matches.geometry.intersects(search_area)]
            
            return len(nearby_forest) > 0
            
        except Exception as e:
            logger.debug(f"Error checking forest proximity: {e}")
            return False
    
    def _has_dispersed_habitat_pattern(self, longitude: float, latitude: float, gdf, radius_km: float = 1.0) -> bool:
        """
        Check if area shows dispersed habitat pattern typical of bocage landscapes.
        This looks for mixed land use patterns within a small radius.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            radius_km: Search radius in kilometers
            
        Returns:
            True if dispersed habitat pattern detected, False otherwise
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Convert radius to degrees
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            radius_deg_lat = radius_km / km_per_deg_lat
            radius_deg_lon = radius_km / km_per_deg_lon
            
            # Create search area
            search_area = point.buffer(radius_deg_lat)
            
            # Find all polygons within search area
            intersects = gdf[gdf.geometry.intersects(search_area)]
            
            if len(intersects) < 3:  # Need sufficient diversity
                return False
            
            # Analyze land use diversity
            unique_codes = set(intersects['Code_18'].tolist())
            
            # Check for characteristic bocage patterns:
            # - Mix of agricultural and natural/forest areas
            # - Presence of complex cultivation patterns
            agri_codes = {'211', '212', '213', '231', '241', '242', '243', '244'}
            forest_codes = {'311', '312', '313', '321', '322', '323', '324'}
            complex_agri = {'242', '243', '244'}  # Complex cultivation patterns
            
            has_agri = bool(unique_codes & agri_codes)
            has_forest = bool(unique_codes & forest_codes)
            has_complex = bool(unique_codes & complex_agri)
            
            # Bocage pattern: agricultural + forest OR complex cultivation patterns
            return (has_agri and has_forest) or has_complex
            
        except Exception as e:
            logger.debug(f"Error checking dispersed habitat pattern: {e}")
            return False
    
    def _is_transitional_zone(self, longitude: float, latitude: float, gdf, radius_km: float = 2.0) -> bool:
        """
        Check if area is a transitional zone with mixed urban-agricultural patterns.
        These areas typically have complex cultivation patterns and mixed land use,
        characteristic of bocage landscapes with building-mounted equipment.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            radius_km: Search radius in kilometers
            
        Returns:
            True if transitional zone detected, False otherwise
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Convert radius to degrees
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            radius_deg_lat = radius_km / km_per_deg_lat
            radius_deg_lon = radius_km / km_per_deg_lon
            
            # Create search area
            search_area = point.buffer(radius_deg_lat)
            
            # Find all polygons within search area
            intersects = gdf[gdf.geometry.intersects(search_area)]
            
            if len(intersects) < 3:  # Need sufficient diversity for transitional zone
                return False
            
            # Analyze land use diversity
            unique_codes = set(intersects['Code_18'].tolist())
            code_counts = intersects['Code_18'].value_counts()
            
            # Define land use categories
            agri_codes = {'211', '212', '213', '231'}  # Pure agriculture
            complex_agri = {'241', '242', '243', '244'}  # Complex cultivation (bocage indicators)
            forest_codes = {'311', '312', '313', '321', '322', '323', '324'}
            urban_codes = {'111', '112', '121', '122', '123', '124', '131', '132', '133', '142'}
            
            has_agri = bool(unique_codes & agri_codes)
            has_complex_agri = bool(unique_codes & complex_agri)
            has_forest = bool(unique_codes & forest_codes)
            has_urban = bool(unique_codes & urban_codes)
            
            # Transitional zone characteristics:
            # 1. Mix of agricultural and urban land use
            # 2. Presence of complex cultivation patterns (strong IIIa indicator)
            # 3. Some natural vegetation (forest/grassland)
            # 4. Not dominated by any single category
            
            if has_complex_agri and (has_agri or has_urban):
                # Complex cultivation with mixed land use = classic transitional zone
                return True
            
            # Check for balanced mixed patterns (not dominated by urban)
            if has_agri and has_urban and has_forest:
                # True mix of all three types = transitional
                total_polygons = len(intersects)
                urban_count = sum(code_counts.get(code, 0) for code in unique_codes & urban_codes)
                agri_count = sum(code_counts.get(code, 0) for code in unique_codes & agri_codes)
                
                # If urban doesn't dominate (>60%), it's transitional not semi-urban
                if urban_count / total_polygons < 0.6:
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking transitional zone: {e}")
            return False
    
    def _has_coastal_exposure(self, longitude: float, latitude: float, gdf, threshold_km: float = 2.0) -> bool:
        """
        Check if location has direct coastal exposure (true coastal areas vs cities with water).
        This distinguishes between actual coastal terrain and inland cities near rivers/lakes.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            threshold_km: Distance threshold for direct coastal exposure
            
        Returns:
            True if has direct coastal exposure, False otherwise
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # True coastal codes (sea, ocean, coastal lagoons, estuaries)
            coastal_codes = ['521', '522', '523', '423']  # Coastal water bodies
            beach_codes = ['331']  # Beaches, dunes, sands
            inland_water_codes = ['511', '512']  # Inland water courses and bodies (rivers, lakes)
            
            # Check for direct coastal exposure within larger radius
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            threshold_deg_lat = threshold_km / km_per_deg_lat
            
            search_area = point.buffer(threshold_deg_lat)
            coastal_areas = gdf[gdf['Code_18'].isin(coastal_codes + beach_codes + inland_water_codes)]
            
            if len(coastal_areas) == 0:
                return False
            
            # Check for direct intersection with coastal features
            nearby_coastal = coastal_areas[coastal_areas.geometry.intersects(search_area)]
            
            # For areas with significant water presence, consider it coastal
            if len(nearby_coastal) > 0:
                # Count different types of water features
                coastal_water_count = sum(1 for _, row in nearby_coastal.iterrows() 
                                        if row['Code_18'] in coastal_codes)
                inland_water_count = sum(1 for _, row in nearby_coastal.iterrows() 
                                       if row['Code_18'] in inland_water_codes)
                
                # Check if this is a mixed urban-water area using spatial extent
                extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, radius_km=threshold_km)
                if extent_pct:
                    urban_pct = extent_pct.get('urban', 0)
                    coastal_pct = extent_pct.get('coastal', 0)
                    
                    # For urban areas, only classify as coastal if there's true coastal water
                    # Inland water (rivers, lakes) should not make urban areas coastal
                    if urban_pct > 50:
                        return coastal_water_count > 0  # Only true coastal water for urban areas
                    
                    # For non-urban areas, any significant water presence can indicate coastal conditions
                    if coastal_pct > 5:  # 5% coastal water threshold
                        return True
                
                # If there's actual coastal water, it's exposed coast
                return coastal_water_count > 0
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking coastal exposure: {e}")
            return False
    
    def _is_dense_urban_coastal(self, longitude: float, latitude: float, gdf, radius_km: float = 3.0) -> bool:
        """
        Check if location is in a dense urban coastal city (like Marseille) vs exposed coastal terrain.
        Dense urban coastal cities should remain as urban terrain, not coastal terrain.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            radius_km: Radius to check for urban density
            
        Returns:
            True if dense urban coastal city, False if exposed coastal terrain
        """
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Dense urban codes
            dense_urban_codes = ['111', '112']  # Continuous and discontinuous urban fabric
            urban_codes = ['121', '122', '123', '124', '131', '132', '133', '142']  # Other urban
            
            # Check urban density in the area
            lat_rad = math.radians(latitude)
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(lat_rad)
            
            radius_deg_lat = radius_km / km_per_deg_lat
            
            search_area = point.buffer(radius_deg_lat)
            area_intersects = gdf[gdf.geometry.intersects(search_area)]
            
            if len(area_intersects) == 0:
                return False
            
            # Calculate urban density
            unique_codes = set(area_intersects['Code_18'].tolist())
            code_counts = area_intersects['Code_18'].value_counts()
            
            dense_urban_count = sum(code_counts.get(code, 0) for code in unique_codes & set(dense_urban_codes))
            total_urban_count = sum(code_counts.get(code, 0) for code in unique_codes & set(urban_codes + dense_urban_codes))
            total_polygons = len(area_intersects)
            
            # If dense urban fabric dominates (>40% of area), it's a dense urban coastal city
            if dense_urban_count / total_polygons > 0.4:
                return True
            
            # If total urban area is very high (>70%), it's likely a city
            if total_urban_count / total_polygons > 0.7:
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking dense urban coastal: {e}")
            return False
    
    def _is_dense_urban_area(self, longitude: float, latitude: float, gdf, radius_km: float = 2.0) -> bool:
        """
        Check if location is in a dense urban area and should be classified as Terrain IV.
        This identifies cities and high-density urban zones using spatial extent analysis
        enhanced with building density verification for ambiguous cases.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            radius_km: Radius to check for urban density
            
        Returns:
            True if dense urban area, False otherwise
        """
        try:
            # Get spatial extent percentages using the existing method
            extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, radius_km)
            
            if not extent_pct:
                return False
            
            # Get thresholds from configuration
            thresholds = terrain_config_service.get_spatial_analysis_config()
            dense_urban_threshold = thresholds.get('density_thresholds', {}).get('dense_urban_fabric', 0.35)
            total_urban_threshold = thresholds.get('density_thresholds', {}).get('total_urban_area', 0.65)
            
            # Get land use percentages
            urban_pct = extent_pct.get('urban', 0)
            agri_pct = extent_pct.get('agriculture', 0)
            
            # Check if this is an ambiguous case that needs building data verification
            building_config = terrain_config_service.load_config().get('building_density_analysis', {})
            if (building_config.get('enabled', True) and 
                building_config.get('conditions', {}).get('clc_urban_range_min', 30.0) <= urban_pct <=
                building_config.get('conditions', {}).get('clc_urban_range_max', 60.0)):
                
                # Use building data to resolve ambiguity
                building_result = self._verify_dense_urban_with_buildings(longitude, latitude, urban_pct)
                if building_result is not None:  # Building data provided definitive answer
                    return building_result
            
            # Context-aware threshold: if there's significant agriculture, require higher urban density
            # This prevents discontinuous urban fabric in mixed areas from being classified as dense urban
            if agri_pct > 40.0:  # More than 40% agriculture
                # In mixed areas, require much higher urban coverage for dense urban classification
                if urban_pct < 60.0:  # Need at least 60% urban if agriculture is dominant
                    return False
            
            # Check against configuration thresholds
            # If urban coverage exceeds total urban threshold, it's a dense urban area
            if urban_pct > (total_urban_threshold * 100):  # Convert from decimal to percentage
                return True
            
            # For dense urban fabric specifically, use higher threshold for mixed areas
            if agri_pct > 20.0:  # Some agricultural presence
                # Require higher urban threshold when there's any significant agriculture
                adjusted_threshold = dense_urban_threshold * 1.4  # 35% -> 49%
                if urban_pct > (adjusted_threshold * 100):
                    return True
            else:
                # Pure urban areas can use the standard threshold
                if urban_pct > (dense_urban_threshold * 100):  # Convert from decimal to percentage
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking dense urban area: {e}")
            return False
    
    def _verify_dense_urban_with_buildings(self, longitude: float, latitude: float, clc_urban_pct: float) -> Optional[bool]:
        """
        Use building density data to verify dense urban classification for ambiguous cases.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            clc_urban_pct: CLC urban percentage from spatial extent analysis
            
        Returns:
            True if dense urban confirmed, False if semi-urban, None if building data unavailable
        """
        try:
            # Get building density metrics
            building_metrics = bdtopo_service.calculate_building_density(longitude, latitude)
            
            if building_metrics.get('building_count', 0) == 0:
                # No building data available, return None to fall back to CLC analysis
                logger.debug(f"No building data available for ({longitude}, {latitude})")
                return None
            
            # Get decision matrix from configuration
            config = terrain_config_service.load_config()
            building_config = config.get('building_density_analysis', {})
            decision_matrix = building_config.get('decision_matrix', {})
            
            coverage = building_metrics.get('building_coverage_pct', 0.0)
            avg_height = building_metrics.get('average_height', 0.0)
            
            # Apply decision matrix
            for case_name, criteria in decision_matrix.items():
                if self._matches_building_criteria(coverage, avg_height, criteria):
                    result = criteria.get('result')
                    is_dense_urban = result == 'IV'
                    
                    logger.debug(f"Building density verification for ({longitude}, {latitude}): "
                                f"Case '{case_name}' - Coverage: {coverage:.1f}%, Height: {avg_height:.1f}m -> {result}")
                    
                    return is_dense_urban
            
            # Default fallback: use density score threshold
            density_score = building_metrics.get('building_density_score', 0.0)
            score_threshold = building_config.get('thresholds', {}).get('density_score_threshold', 50.0)
            
            logger.debug(f"Building density fallback for ({longitude}, {latitude}): "
                        f"Score: {density_score:.1f} vs Threshold: {score_threshold}")
            
            return density_score >= score_threshold
            
        except Exception as e:
            logger.debug(f"Error in building density verification: {e}")
            return None
    
    def _matches_building_criteria(self, coverage: float, height: float, criteria: dict) -> bool:
        """Check if building metrics match the decision criteria."""
        try:
            # Check coverage constraints
            if 'coverage_min' in criteria and coverage < criteria['coverage_min']:
                return False
            if 'coverage_max' in criteria and coverage > criteria['coverage_max']:
                return False
            
            # Check height constraints
            if 'height_min' in criteria and height < criteria['height_min']:
                return False
            if 'height_max' in criteria and height > criteria['height_max']:
                return False
            
            return True
            
        except Exception as e:
            logger.debug(f"Error matching building criteria: {e}")
            return False
    
    def _has_exposed_coastal_conditions(self, longitude: float, latitude: float, gdf) -> bool:
        """
        Check if location has exposed coastal conditions that should override other classifications.
        This combines coastal proximity, exposure, and urban density checks.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            
        Returns:
            True if has exposed coastal conditions, False otherwise
        """
        try:
            # Must be near coast
            if not self._is_near_coast(longitude, latitude, gdf, threshold_km=2.0):
                return False
            
            # Must have direct coastal exposure
            if not self._has_coastal_exposure(longitude, latitude, gdf):
                return False
            
            # Must NOT be a dense urban coastal city
            if self._is_dense_urban_coastal(longitude, latitude, gdf):
                return False
            
            return True
            
        except Exception as e:
            logger.debug(f"Error checking exposed coastal conditions: {e}")
            return False
    
    def _is_enhanced_transitional_zone(self, longitude: float, latitude: float, gdf) -> bool:
        """
        Enhanced transitional zone detection using spatial extent analysis.
        This distinguishes between true bocage landscapes and open countryside using area-based calculations.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            
        Returns:
            True if enhanced transitional zone detected, False otherwise
        """
        try:
            # First check basic transitional zone
            if not self._is_transitional_zone(longitude, latitude, gdf):
                return False
            
            # Get spatial extent percentages
            extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, radius_km=2.0)
            
            if not extent_pct:
                return False
            
            # Extract spatial extent percentages
            agri_pct = extent_pct.get('agriculture', 0)
            complex_pct = extent_pct.get('complex_agriculture', 0)
            forest_pct = extent_pct.get('forest', 0)
            urban_pct = extent_pct.get('urban', 0)
            
            # Enhanced logic using spatial extent with proper thresholds:
            # 1. If agriculture dominates (>60%) and urban is very low (<10%), it's open countryside (II)
            if agri_pct > 60 and urban_pct < 10:
                return False
            
            # 2. If agriculture is very high (>70%) regardless of other factors, it's open countryside (II)
            if agri_pct > 70:
                return False
            
            # 3. Only consider transitional if there's meaningful complexity and urban presence
            # Changed from >0 to >=10% for complexity and >=5% for urban to avoid false positives
            if complex_pct >= 10 and urban_pct >= 5:
                return True
            
            # 4. If mixed patterns with significant complexity, it's transitional (IIIa)
            if complex_pct >= 10 and (agri_pct > 20 or forest_pct > 10):
                return True
            
            # 5. Target coordinate protection: mixed urban-agricultural with complexity
            if urban_pct >= 40 and urban_pct <= 60 and complex_pct >= 10:
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking enhanced transitional zone: {e}")
            return False
    
    def _has_bocage_characteristics(self, longitude: float, latitude: float, gdf) -> bool:
        """
        Check if urban area has bocage characteristics using spatial extent analysis.
        This identifies urban areas that are actually bocage landscapes with some urban fabric.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            
        Returns:
            True if has bocage characteristics, False otherwise
        """
        try:
            # Get spatial extent percentages
            extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, radius_km=2.0)
            
            if not extent_pct:
                return False
            
            # Extract spatial extent percentages
            agri_pct = extent_pct.get('agriculture', 0)
            complex_pct = extent_pct.get('complex_agriculture', 0)
            forest_pct = extent_pct.get('forest', 0)
            urban_pct = extent_pct.get('urban', 0)
            
            # Bocage characteristics in urban areas using spatial extent:
            # 1. Significant agricultural presence (>25% spatial extent)
            # 2. Complex cultivation present (>10% spatial extent)
            # 3. Forest/natural vegetation present (>15% spatial extent)
            # 4. Urban not dominant (<60% spatial extent)
            
            has_agri = agri_pct > 25
            has_complex = complex_pct > 10
            has_forest = forest_pct > 15
            not_urban_dominated = urban_pct < 60
            
            return has_agri and has_complex and has_forest and not_urban_dominated
            
        except Exception as e:
            logger.debug(f"Error checking bocage characteristics: {e}")
            return False
    
    def _is_actually_open_countryside(self, longitude: float, latitude: float, gdf) -> bool:
        """
        Check if area initially classified as complex agriculture should actually be open countryside.
        This uses spatial extent analysis to handle cases like La Brenne more accurately.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            
        Returns:
            True if should be classified as open countryside, False otherwise
        """
        try:
            # Get spatial extent percentages
            extent_pct = self._calculate_spatial_extent_percentages(longitude, latitude, gdf, radius_km=2.0)
            
            if not extent_pct:
                return False
            
            # Extract spatial extent percentages
            agri_pct = extent_pct.get('agriculture', 0)
            complex_pct = extent_pct.get('complex_agriculture', 0)
            forest_pct = extent_pct.get('forest', 0)
            urban_pct = extent_pct.get('urban', 0)
            
            # Open countryside characteristics using spatial extent:
            # 1. High total agricultural content (agri + complex > 60% spatial extent)
            # 2. Very low urban content (<5% spatial extent)
            # 3. Forest content moderate but not dominant (<30% spatial extent)
            # 4. Not complex enough to be true bocage (complex < 35% spatial extent)
            
            total_agri_pct = agri_pct + complex_pct
            is_open_countryside = (
                total_agri_pct > 60 and
                urban_pct < 5 and
                forest_pct < 30 and
                complex_pct < 35
            )
            
            return is_open_countryside
            
        except Exception as e:
            logger.debug(f"Error checking open countryside: {e}")
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
        Classify terrain types for multiple coordinates with optimized batch processing.
        
        Args:
            coordinates: List of (longitude, latitude) tuples
            
        Returns:
            List of terrain types corresponding to input coordinates
        """
        results = []
        start_time = time.time()
        
        # Load data once for batch processing
        gdf = self._load_land_use_data()
        
        # Group coordinates by spatial proximity for optimized processing
        processed_coords = self._batch_optimize_processing(coordinates, gdf)
        
        for lon, lat in processed_coords:
            terrain_type = self.get_terrain_type_at_coordinates(lon, lat)
            results.append(terrain_type)
        
        processing_time = time.time() - start_time
        logger.info(f"Batch classified {len(coordinates)} coordinates in {processing_time:.3f}s")
        
        return results
    
    def _batch_optimize_processing(self, coordinates: list, gdf: gpd.GeoDataFrame) -> list:
        """Optimize batch processing by spatial proximity grouping."""
        # For now, return coordinates as-is
        # TODO: Implement spatial clustering for optimization
        return coordinates
    
    def _calculate_spatial_extent_percentages(self, longitude: float, latitude: float, gdf, radius_km: float = 1.0) -> dict:
        """
        Calculate land use percentages based on spatial extent (area) with caching.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            gdf: GeoDataFrame with land use data
            radius_km: Analysis radius in kilometers
            
        Returns:
            Dictionary with land use category percentages based on spatial extent
        """
        # Check cache first
        cache_key = f"spatial_extent_{longitude:.6f}_{latitude:.6f}_{radius_km:.1f}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            result = self._compute_spatial_extent_percentages(longitude, latitude, gdf, radius_km)
            
            # Cache the result
            cache.set(cache_key, result, self._index_cache_timeout)
            
            return result
            
        except Exception as e:
            logger.debug(f"Error calculating spatial extent percentages: {e}")
            return {}
    
    def _compute_spatial_extent_percentages(self, longitude: float, latitude: float, gdf, radius_km: float = 2.0) -> dict:
        """Compute spatial extent percentages without caching."""
        # Create point geometry
        point = Point(longitude, latitude)
        
        # Convert radius to degrees
        lat_rad = math.radians(latitude)
        km_per_deg_lat = 111.0
        km_per_deg_lon = 111.0 * math.cos(lat_rad)
        
        radius_deg_lat = radius_km / km_per_deg_lat
        
        # Create buffer and intersect with land use data
        search_area = point.buffer(radius_deg_lat)
        intersects = gdf[gdf.geometry.intersects(search_area)]
        
        if len(intersects) == 0:
            return {}
        
        # Calculate actual areas of intersected polygons
        # Clip polygons to the search area for accurate area calculation
        clipped_intersects = intersects.copy()
        clipped_intersects['geometry'] = clipped_intersects.geometry.intersection(search_area)
        
        # Reproject to a projected CRS for accurate area calculations
        # Use appropriate UTM zone for France (Zone 31N for most of France)
        clipped_intersects['geometry'] = clipped_intersects['geometry'].to_crs('EPSG:32631')
        
        # Calculate areas in km² (UTM coordinates are in meters)
        clipped_intersects['area_km2'] = clipped_intersects.geometry.area / 1_000_000  # m² to km²
        total_area = clipped_intersects['area_km2'].sum()
        
        if total_area == 0:
            return {}
        
        # Get land use categories from configuration
        influence = terrain_config_service.get_influence_percentages()
        spatial_categories = influence.get('spatial_extent_categories', {})
        
        agri_codes = set(spatial_categories.get('agriculture', {}).get('codes', ['211', '212', '213', '231']))
        complex_agri = set(spatial_categories.get('complex_agriculture', {}).get('codes', ['241', '242', '243', '244']))
        forest_codes = set(spatial_categories.get('forest', {}).get('codes', ['311', '312', '313', '321', '322', '323', '324']))
        urban_codes = set(spatial_categories.get('urban', {}).get('codes', ['111', '112', '121', '122', '123', '124', '131', '132', '133', '142']))
        true_coastal_codes = set(spatial_categories.get('coastal', {}).get('codes', ['521', '522', '523', '423', '331']))
        inland_water_codes = set(spatial_categories.get('inland_water', {}).get('codes', ['511', '512']))
        
        # Calculate spatial extent percentages by category
        extent_percentages = {}
        
        for category_name, code_set in [
            ('agriculture', agri_codes),
            ('complex_agriculture', complex_agri),
            ('forest', forest_codes),
            ('urban', urban_codes),
            ('coastal', true_coastal_codes)
        ]:
            category_area = clipped_intersects[
                clipped_intersects['Code_18'].isin(code_set)
            ]['area_km2'].sum()
            
            extent_percentages[category_name] = (category_area / total_area) * 100
        
        return extent_percentages
    
    def get_performance_metrics(self) -> dict:
        """Get performance metrics for monitoring and optimization."""
        metrics = self._performance_metrics.copy()
        
        # Calculate derived metrics
        total_requests = metrics['cache_hits'] + metrics['cache_misses']
        cache_hit_rate = metrics['cache_hits'] / total_requests if total_requests > 0 else 0
        
        avg_classification_time = np.mean(metrics['classification_time']) if metrics['classification_time'] else 0
        
        metrics.update({
            'cache_hit_rate': round(cache_hit_rate, 3),
            'avg_classification_time_ms': round(avg_classification_time * 1000, 2),
            'total_requests': total_requests,
            'spatial_index_count': len(self._spatial_indexes)
        })
        
        return metrics
    
    def reset_performance_metrics(self):
        """Reset performance metrics for fresh monitoring."""
        self._performance_metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'spatial_queries': 0,
            'classification_time': []
        }
    
    def clear_cache(self, pattern: str = None):
        """Clear cache with optional pattern matching."""
        if pattern:
            # Clear cache keys matching pattern
            # Note: This is a simplified implementation
            cache.delete_many([key for key in cache.keys(pattern) if key.startswith(pattern)])
        else:
            # Clear all terrain-related cache
            cache.delete_many([key for key in cache.keys('terrain_*')])
            cache.delete_many([key for key in cache.keys('spatial_*')])
        
        logger.info(f"Cleared cache{' for pattern: ' + pattern if pattern else ''}")
    
    def optimize_memory_usage(self):
        """Optimize memory usage by clearing unused data and indexes."""
        current_time = time.time()
        
        # Clear old spatial indexes
        for category, index_data in list(self._spatial_indexes.items()):
            if current_time - index_data['created_at'] > self._index_cache_timeout:
                del self._spatial_indexes[category]
                logger.debug(f"Cleared old spatial index for {category}")
        
        # Force garbage collection if needed
        import gc
        gc.collect()
        
        logger.info("Memory usage optimization completed")
    
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


class BDTOPOService:
    """Service for analyzing building footprints using IGN BDTOPO vector tiles."""
    
    def __init__(self):
        self.cache_timeout = 3600  # 1 hour cache
        self._performance_metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'tile_requests': 0,
            'building_analysis_time': []
        }
        # Initialize vector tile parser
        self.parser = create_vector_tile_parser()
    
    def get_building_footprints(self, longitude: float, latitude: float, radius_km: float = 2.0) -> List[dict]:
        """
        Get building footprints within specified radius of coordinates.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate  
            radius_km: Analysis radius in kilometers
            
        Returns:
            List of building features with properties
        """
        try:
            start_time = time.time()
            
            # Get tiles for the analysis area
            tiles = self.parser.get_tiles_for_area(longitude, latitude, radius_km)
            
            all_buildings = []
            for zoom, tile_x, tile_y in tiles:
                cache_key = f"bdtopo_buildings_{zoom}_{tile_x}_{tile_y}"
                
                # Try cache first
                cached_buildings = cache.get(cache_key)
                if cached_buildings is not None:
                    self._performance_metrics['cache_hits'] += 1
                    all_buildings.extend(cached_buildings)
                    continue
                
                self._performance_metrics['cache_misses'] += 1
                self._performance_metrics['tile_requests'] += 1
                
                # Fetch and parse tile data
                tile_data = self.parser.fetch_tile(zoom, tile_x, tile_y)
                if tile_data:
                    layers_features = self.parser.parse_vector_tile(tile_data)
                    buildings = self.parser.extract_building_features(layers_features)
                    
                    if buildings:
                        cache.set(cache_key, buildings, self.cache_timeout)
                        all_buildings.extend(buildings)
            
            # Filter buildings by actual distance from center point
            filtered_buildings = self._filter_buildings_by_distance(
                all_buildings, longitude, latitude, radius_km
            )
            
            analysis_time = time.time() - start_time
            self._performance_metrics['building_analysis_time'].append(analysis_time)
            
            logger.debug(f"Found {len(filtered_buildings)} buildings within {radius_km}km of ({longitude}, {latitude}) in {analysis_time:.2f}s")
            return filtered_buildings
            
        except Exception as e:
            logger.error(f"Error getting building footprints: {e}")
            return []
    
    def calculate_building_density(self, longitude: float, latitude: float, radius_km: float = 2.0) -> dict:
        """
        Calculate building density metrics for the specified area.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            radius_km: Analysis radius in kilometers
            
        Returns:
            Dictionary with building density metrics
        """
        try:
            start_time = time.time()
            
            buildings = self.get_building_footprints(longitude, latitude, radius_km)
            
            if not buildings:
                return {
                    'building_count': 0,
                    'building_coverage_pct': 0.0,
                    'average_height': 0.0,
                    'max_height': 0.0,
                    'building_density_score': 0.0
                }
            
            # Calculate total building area
            total_building_area = 0.0
            heights = []
            
            for building in buildings:
                # Get building area from enhanced properties
                area = building.get('properties', {}).get('area_sqm', 0.0)
                total_building_area += area
                
                # Get height information from enhanced properties
                height = building.get('properties', {}).get('height_m')
                if height is not None and height > 0:
                    heights.append(height)
            
            # Calculate analysis area (circle in square meters)
            analysis_area_sqm = math.pi * (radius_km * 1000) ** 2
            
            # Calculate coverage percentage
            building_coverage_pct = (total_building_area / analysis_area_sqm) * 100
            
            # Calculate height statistics
            average_height = np.mean(heights) if heights else 0.0
            max_height = max(heights) if heights else 0.0
            
            # Calculate density score (0-100)
            # Combines coverage and height for urban density assessment
            coverage_score = min(building_coverage_pct * 2, 50)  # Max 50 points from coverage
            height_score = min(average_height / 15 * 50, 50)  # Max 50 points from height (15m = full points)
            building_density_score = coverage_score + height_score
            
            result = {
                'building_count': len(buildings),
                'building_coverage_pct': building_coverage_pct,
                'average_height': average_height,
                'max_height': max_height,
                'building_density_score': building_density_score,
                'analysis_area_sqm': analysis_area_sqm,
                'total_building_area_sqm': total_building_area
            }
            
            self._performance_metrics['building_analysis_time'].append(time.time() - start_time)
            
            logger.debug(f"Building density metrics for ({longitude}, {latitude}): "
                        f"{len(buildings)} buildings, {building_coverage_pct:.1f}% coverage, "
                        f"avg height {average_height:.1f}m")
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating building density: {e}")
            return {
                'building_count': 0,
                'building_coverage_pct': 0.0,
                'average_height': 0.0,
                'max_height': 0.0,
                'building_density_score': 0.0
            }
    
    def analyze_building_heights(self, building_features: List[dict]) -> dict:
        """
        Analyze height distribution of building features.
        
        Args:
            building_features: List of building features
            
        Returns:
            Dictionary with height analysis statistics
        """
        try:
            heights = []
            for building in building_features:
                height = building.get('properties', {}).get('height_m')
                if height is not None and height > 0:
                    heights.append(height)
            
            if not heights:
                return {
                    'count': 0,
                    'average': 0.0,
                    'median': 0.0,
                    'min': 0.0,
                    'max': 0.0,
                    'std_dev': 0.0
                }
            
            return {
                'count': len(heights),
                'average': np.mean(heights),
                'median': np.median(heights),
                'min': min(heights),
                'max': max(heights),
                'std_dev': np.std(heights)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing building heights: {e}")
            return {
                'count': 0,
                'average': 0.0,
                'median': 0.0,
                'min': 0.0,
                'max': 0.0,
                'std_dev': 0.0
            }
    
    def get_urban_density_score(self, longitude: float, latitude: float, radius_km: float = 2.0) -> float:
        """
        Get overall urban density score based on building analysis.
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            radius_km: Analysis radius in kilometers
            
        Returns:
            Urban density score (0-100)
        """
        try:
            density_metrics = self.calculate_building_density(longitude, latitude, radius_km)
            return density_metrics.get('building_density_score', 0.0)
            
        except Exception as e:
            logger.error(f"Error getting urban density score: {e}")
            return 0.0
    
    def _filter_buildings_by_distance(self, buildings: List[dict], longitude: float, 
                                    latitude: float, radius_km: float) -> List[dict]:
        """Filter buildings by actual distance from center point."""
        filtered = []
        
        for building in buildings:
            # Get building centroid coordinates from enhanced properties
            properties = building.get('properties', {})
            centroid_lon = properties.get('centroid_lon')
            centroid_lat = properties.get('centroid_lat')
            
            if centroid_lon is not None and centroid_lat is not None:
                distance = self._calculate_distance(
                    longitude, latitude, centroid_lon, centroid_lat
                )
                if distance <= radius_km:
                    filtered.append(building)
        
        return filtered
    
    def _calculate_distance(self, lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """Calculate distance between two points in kilometers."""
        R = 6371.0  # Earth radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c


# Global service instances
terrain_service = TerrainClassificationService()
bdtopo_service = BDTOPOService()
