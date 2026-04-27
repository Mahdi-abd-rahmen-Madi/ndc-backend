"""
Terrain configuration service for managing terrain classification rules and parameters.
"""
import json
import os
import logging
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class TerrainConfigService:
    """Service for managing terrain classification configuration."""
    
    def __init__(self):
        self.config_file = os.path.join(settings.BASE_DIR, 'backend', 'geodata', 'terrain_config.json')
        self._config = None
        self.cache_timeout = 1800  # 30 minutes cache
        
    def load_config(self) -> Dict[str, Any]:
        """Load terrain configuration from JSON file."""
        if self._config is not None:
            return self._config
            
        cache_key = 'terrain_config'
        cached_config = cache.get(cache_key)
        if cached_config is not None:
            self._config = cached_config
            return cached_config
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Validate configuration structure
            self._validate_config(config)
            
            # Cache the configuration
            cache.set(cache_key, config, self.cache_timeout)
            self._config = config
            
            logger.info(f"Loaded terrain configuration from {self.config_file}")
            return config
            
        except FileNotFoundError:
            logger.error(f"Terrain configuration file not found: {self.config_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in terrain configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading terrain configuration: {e}")
            raise
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate the configuration structure with enhanced edge case detection."""
        required_sections = ['clc_code_mappings', 'classification_rules', 'spatial_analysis']
        
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        # Validate CLC code mappings
        clc_mappings = config['clc_code_mappings']
        required_terrain_types = ['terrain_0', 'terrain_II', 'terrain_IIIa', 'terrain_IIIb', 'terrain_IV']
        
        for terrain_type in required_terrain_types:
            if terrain_type not in clc_mappings:
                raise ValueError(f"Missing terrain type mapping: {terrain_type}")
            if 'codes' not in clc_mappings[terrain_type]:
                raise ValueError(f"Missing codes for terrain type: {terrain_type}")
        
        # Enhanced validation for classification rules
        self._validate_classification_rules(config.get('classification_rules', {}))
        
        # Validate spatial analysis parameters
        self._validate_spatial_analysis(config.get('spatial_analysis', {}))
        
        # Validate influence percentages
        self._validate_influence_percentages(config.get('influence_percentages', {}))
    
    def _validate_classification_rules(self, rules: Dict[str, Any]) -> None:
        """Validate classification rules for logical consistency."""
        # Check for priority conflicts
        priorities = {}
        for rule_name, rule in rules.items():
            priority = rule.get('priority', 999)
            if priority in priorities:
                existing_rule = priorities[priority]
                logger.warning(f"Priority conflict: {rule_name} and {existing_rule} both have priority {priority}")
            priorities[priority] = rule_name
        
        # Validate rule conditions
        for rule_name, rule in rules.items():
            conditions = rule.get('conditions', {})
            
            # Check applicable terrain validity
            applicable_terrain = conditions.get('applicable_to_terrain', [])
            valid_terrains = ['0', 'II', 'IIIa', 'IIIb', 'IV']
            
            for terrain in applicable_terrain:
                if terrain not in valid_terrains:
                    logger.warning(f"Invalid terrain type '{terrain}' in rule '{rule_name}'")
            
            # Validate threshold values
            if 'distance_threshold_km' in conditions:
                threshold = conditions['distance_threshold_km']
                if not isinstance(threshold, (int, float)) or threshold <= 0:
                    logger.warning(f"Invalid distance threshold in rule '{rule_name}': {threshold}")
            
            # Validate percentage thresholds
            percentage_keys = [
                'dense_urban_threshold', 'total_urban_threshold', 'agriculture_threshold',
                'complex_agriculture_threshold', 'forest_threshold', 'urban_dominance_threshold'
            ]
            
            for key in percentage_keys:
                if key in conditions:
                    value = conditions[key]
                    if not isinstance(value, (int, float)) or not (0 <= value <= 100):
                        logger.warning(f"Invalid percentage threshold '{key}' in rule '{rule_name}': {value}")
    
    def _validate_spatial_analysis(self, spatial_config: Dict[str, Any]) -> None:
        """Validate spatial analysis configuration."""
        # Validate distance thresholds
        distance_thresholds = spatial_config.get('distance_thresholds_km', {})
        for key, value in distance_thresholds.items():
            if not isinstance(value, (int, float)) or value <= 0:
                logger.warning(f"Invalid distance threshold '{key}': {value}")
        
        # Validate analysis radii
        analysis_radii = spatial_config.get('analysis_radii_km', {})
        for key, value in analysis_radii.items():
            if not isinstance(value, (int, float)) or value <= 0:
                logger.warning(f"Invalid analysis radius '{key}': {value}")
        
        # Validate density thresholds
        density_thresholds = spatial_config.get('density_thresholds', {})
        for key, value in density_thresholds.items():
            if not isinstance(value, (int, float)) or not (0 <= value <= 1):
                logger.warning(f"Invalid density threshold '{key}': {value}")
    
    def _validate_influence_percentages(self, influence_config: Dict[str, Any]) -> None:
        """Validate influence percentages configuration."""
        spatial_categories = influence_config.get('spatial_extent_categories', {})
        
        for category_name, category_config in spatial_categories.items():
            if 'codes' not in category_config:
                logger.warning(f"Missing codes for spatial category '{category_name}'")
                continue
            
            codes = category_config['codes']
            if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
                logger.warning(f"Invalid codes format for spatial category '{category_name}'")
            
            # Validate weight if present
            weight = category_config.get('default_weight')
            if weight is not None and (not isinstance(weight, (int, float)) or weight <= 0):
                logger.warning(f"Invalid weight for spatial category '{category_name}': {weight}")
    
    def detect_edge_cases(self, config: Dict[str, Any]) -> List[str]:
        """Detect potential edge cases and configuration issues."""
        edge_cases = []
        
        # Check for overlapping terrain classifications
        clc_mappings = config.get('clc_code_mappings', {})
        all_codes = []
        
        for terrain_type, mapping in clc_mappings.items():
            codes = mapping.get('codes', [])
            for code in codes:
                if code in all_codes:
                    edge_cases.append(f"CLC code '{code}' appears in multiple terrain mappings")
                else:
                    all_codes.append(code)
        
        # Check for rule priority gaps
        rules = config.get('classification_rules', {})
        priorities = [rule.get('priority', 999) for rule in rules.values()]
        priorities.sort()
        
        for i in range(len(priorities) - 1):
            if priorities[i + 1] - priorities[i] > 10:
                edge_cases.append(f"Large priority gap between rules: {priorities[i]} and {priorities[i + 1]}")
        
        # Check for performance issues
        spatial_config = config.get('spatial_analysis', {})
        analysis_radii = spatial_config.get('analysis_radii_km', {})
        
        for key, radius in analysis_radii.items():
            if radius > 10.0:  # Large analysis radius
                edge_cases.append(f"Large analysis radius '{key}': {radius}km may impact performance")
        
        # Check cache settings
        performance_settings = config.get('performance_settings', {})
        cache_timeout = performance_settings.get('cache_timeout_seconds', 3600)
        
        if cache_timeout < 300:  # Less than 5 minutes
            edge_cases.append(f"Short cache timeout ({cache_timeout}s) may reduce performance")
        elif cache_timeout > 86400:  # More than 24 hours
            edge_cases.append(f"Long cache timeout ({cache_timeout}s) may cause stale data")
        
        return edge_cases
    
    def get_clc_code_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Get CLC code to terrain type mappings."""
        config = self.load_config()
        return config['clc_code_mappings']
    
    def get_terrain_type_from_clc_code(self, clc_code: str) -> Optional[str]:
        """Get terrain type from CLC code using configuration."""
        clc_mappings = self.get_clc_code_mappings()
        
        for terrain_type, mapping in clc_mappings.items():
            if clc_code in mapping['codes']:
                # Extract terrain type number from key (e.g., 'terrain_0' -> '0')
                return terrain_type.split('_')[1]
        
        return None
    
    def get_classification_rules(self) -> Dict[str, Dict[str, Any]]:
        """Get enhanced classification rules."""
        config = self.load_config()
        return config['classification_rules']
    
    def get_spatial_analysis_config(self) -> Dict[str, Dict[str, Any]]:
        """Get spatial analysis parameters."""
        config = self.load_config()
        return config['spatial_analysis']
    
    def get_influence_percentages(self) -> Dict[str, Dict[str, Any]]:
        """Get influence percentages for land use categories."""
        config = self.load_config()
        return config['influence_percentages']
    
    def get_rule_parameter(self, rule_name: str, parameter_path: str, default=None):
        """Get a specific parameter from a classification rule.
        
        Args:
            rule_name: Name of the classification rule
            parameter_path: Dot-separated path to parameter (e.g., 'conditions.distance_threshold_km')
            default: Default value if parameter not found
        """
        rules = self.get_classification_rules()
        
        if rule_name not in rules:
            logger.warning(f"Classification rule not found: {rule_name}")
            return default
        
        rule = rules[rule_name]
        path_parts = parameter_path.split('.')
        current = rule
        
        try:
            for part in path_parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            logger.warning(f"Parameter not found in rule {rule_name}: {parameter_path}")
            return default
    
    def get_spatial_parameter(self, category: str, parameter_name: str, default=None):
        """Get a spatial analysis parameter.
        
        Args:
            category: Category name (e.g., 'distance_thresholds_km', 'analysis_radii_km')
            parameter_name: Name of the parameter
            default: Default value if parameter not found
        """
        spatial_config = self.get_spatial_analysis_config()
        
        if category not in spatial_config:
            logger.warning(f"Spatial analysis category not found: {category}")
            return default
        
        category_config = spatial_config[category]
        return category_config.get(parameter_name, default)
    
    def update_config(self, new_config: Dict[str, Any]) -> bool:
        """Update terrain configuration and save to file."""
        try:
            # Validate new configuration
            self._validate_config(new_config)
            
            # Create backup of current config
            backup_file = f"{self.config_file}.backup"
            try:
                with open(self.config_file, 'r', encoding='utf-8') as src:
                    with open(backup_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
            except Exception as e:
                logger.warning(f"Could not create backup: {e}")
            
            # Save new configuration
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=2, ensure_ascii=False)
            
            # Clear cache and reload
            self._config = None
            cache.delete('terrain_config')
            self.load_config()
            
            logger.info("Terrain configuration updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error updating terrain configuration: {e}")
            return False
    
    def reset_to_defaults(self) -> bool:
        """Reset configuration to default values."""
        try:
            # This would load from a default template or recreate the initial config
            # For now, we'll just clear the cache and reload
            self._config = None
            cache.delete('terrain_config')
            self.load_config()
            return True
        except Exception as e:
            logger.error(f"Error resetting terrain configuration: {e}")
            return False
    
    def export_config(self) -> str:
        """Export configuration as JSON string."""
        config = self.load_config()
        return json.dumps(config, indent=2, ensure_ascii=False)
    
    def import_config(self, config_json: str) -> bool:
        """Import configuration from JSON string."""
        try:
            config = json.loads(config_json)
            return self.update_config(config)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in imported configuration: {e}")
            return False
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of current configuration for display."""
        config = self.load_config()
        
        summary = {
            'metadata': config.get('metadata', {}),
            'terrain_type_count': len(config.get('clc_code_mappings', {})),
            'classification_rules_count': len(config.get('classification_rules', {})),
            'enabled_rules': [
                name for name, rule in config.get('classification_rules', {}).items()
                if rule.get('enabled', True)
            ],
            'spatial_categories': list(config.get('spatial_analysis', {}).keys())
        }
        
        return summary
    
    def validate_coordinates_with_config(self, longitude: float, latitude: float) -> Dict[str, Any]:
        """Validate coordinates and return relevant configuration parameters."""
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'applicable_rules': []
        }
        
        # Check coordinate ranges
        if not (-180 <= longitude <= 180):
            validation_result['valid'] = False
            validation_result['errors'].append('Longitude out of range (-180 to 180)')
        
        if not (-90 <= latitude <= 90):
            validation_result['valid'] = False
            validation_result['errors'].append('Latitude out of range (-90 to 90)')
        
        # Get applicable rules based on configuration
        rules = self.get_classification_rules()
        for rule_name, rule in rules.items():
            if rule.get('enabled', True):
                validation_result['applicable_rules'].append({
                    'name': rule_name,
                    'priority': rule.get('priority', 999),
                    'description': rule.get('description', '')
                })
        
        # Sort rules by priority
        validation_result['applicable_rules'].sort(key=lambda x: x['priority'])
        
        return validation_result


# Global service instance
terrain_config_service = TerrainConfigService()
