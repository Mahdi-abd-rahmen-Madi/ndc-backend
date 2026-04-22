# Terrain Verification Guide for Civil Engineers

This guide provides comprehensive tools and procedures for verifying the terrain classification system used in antenna wind load calculations.

## Overview

The terrain classification system converts French land use data (Corine Land Cover codes) into 5 terrain types required for wind load calculations:
- **Terrain 0**: Water/coastal areas (mer/côtière)
- **Terrain II**: Open countryside (rase campagne)
- **Terrain IIIa**: Campaign with obstacles (bocage, habitat dispersé)
- **Terrain IIIb**: Urbanized/industrial zones (bocage denser)
- **Terrain IV**: Dense urban zones

## Quick Start Commands

### 1. Generate Test Addresses
```bash
# Generate 10 random addresses with terrain classification
python manage.py generate_test_addresses --count 10 --include-terrain --export-json

# Generate addresses for specific terrain type
python manage.py generate_test_addresses --count 20 --terrain-type IV --include-terrain

# Generate addresses for all terrain types equally
python manage.py generate_test_addresses --count 50 --all-terrain-types --include-terrain
```

### 2. Test Specific Locations
```bash
# Test specific coordinates
python manage.py test_terrain_classification --coordinates 2.3522 48.8566 4.8322 45.7578

# Test specific addresses (cities)
python manage.py test_terrain_classification --addresses Paris Lyon Marseille

# Run performance tests
python manage.py test_terrain_classification --performance-test
```

### 3. Verify System Accuracy
```bash
# Test known locations with expected terrain types
python manage.py verify_terrain_accuracy --test-locations

# Random sampling verification
python manage.py verify_terrain_accuracy --random-sampling 100

# Cross-validation test
python manage.py verify_terrain_accuracy --cross-validation

# Full verification with report
python manage.py verify_terrain_accuracy --test-locations --export-report
```

## Detailed Usage Examples

### Address Generation for Testing

#### Generate Test Dataset
```bash
# Create comprehensive test dataset
python manage.py generate_test_addresses \
  --count 100 \
  --all-terrain-types \
  --include-terrain \
  --validate-coords \
  --export-csv \
  --export-json \
  --filename civil_engineer_test_dataset
```

This creates:
- 100 addresses (20 per terrain type)
- Terrain classification for each address
- Coordinate validation
- Both CSV and JSON exports
- Files: `civil_engineer_test_dataset.csv` and `civil_engineer_test_dataset.json`

#### Targeted Terrain Testing
```bash
# Test coastal areas specifically
python manage.py generate_test_addresses \
  --count 30 \
  --terrain-type 0 \
  --include-terrain \
  --filename coastal_test_addresses

# Test dense urban areas
python manage.py generate_test_addresses \
  --count 30 \
  --terrain-type IV \
  --include-terrain \
  --filename urban_test_addresses
```

### Terrain Classification Testing

#### Coordinate Testing
```bash
# Test specific project coordinates
python manage.py test_terrain_classification \
  --coordinates 2.3522 48.8566 4.8322 45.7578 2.0 47.0 \
  --export-csv \
  --create-equipment \
  --user your_username
```

#### Address Testing
```bash
# Test project addresses
python manage.py test_terrain_classification \
  --addresses "Paris" "Lyon" "Marseille" "Bordeaux" "Nantes" \
  --export-json \
  --filename project_addresses_test
```

### System Verification

#### Comprehensive Verification
```bash
# Run all verification tests
python manage.py verify_terrain_accuracy \
  --test-locations \
  --random-sampling 50 \
  --cross-validation \
  --export-report \
  --tolerance 0.75
```

#### Compare with Existing Equipment
```bash
# Verify terrain classification for existing equipment
python manage.py verify_terrain_accuracy \
  --compare-with-equipment \
  --export-report
```

## Understanding Results

### Address Generation Results

The JSON export contains:
```json
{
  "search_term": "Paris",
  "label": "Paris, 75001, France",
  "name": "Paris",
  "postcode": "75001",
  "city": "Paris",
  "longitude": 2.3522,
  "latitude": 48.8566,
  "target_terrain": "IV",
  "classified_terrain": "IV"
}
```

- **target_terrain**: Expected terrain type based on search term
- **classified_terrain**: Actual terrain classification from coordinates
- **accuracy**: Percentage of correct classifications

### Terrain Classification Results

```
Location: Paris - Eiffel Tower: IV (2.3522, 48.8566) - 0.032s
Location: Lyon - Basilique: IV (4.8322, 45.7578) - 0.028s
Location: Central France: II (2.0000, 47.0000) - 0.035s
```

### Verification Report

The verification report shows:
- **Overall accuracy**: Percentage of correct classifications
- **Individual test results**: Accuracy for each test type
- **Detailed breakdown**: Pass/fail status for each location

## Using the French Geocoding API

The system uses the French national geocoding API: https://data.geopf.fr/geocodage/search

### API Response Format
```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": {
      "type": "Point",
      "coordinates": [2.3522, 48.8566]
    },
    "properties": {
      "label": "Paris, 75001, France",
      "name": "Paris",
      "postcode": "75001",
      "city": "Paris",
      "context": "75, Paris, Île-de-France",
      "type": "municipality",
      "importance": 0.67303
    }
  }]
}
```

## Integration with Wind Load Calculations

### Step-by-Step Workflow

1. **Generate Test Addresses**
   ```bash
   python manage.py generate_test_addresses --count 50 --all-terrain-types --include-terrain
   ```

2. **Verify Classification Accuracy**
   ```bash
   python manage.py verify_terrain_accuracy --test-locations --tolerance 0.8
   ```

3. **Test Project Coordinates**
   ```bash
   python manage.py test_terrain_classification --coordinates LON LAT --export-csv
   ```

4. **Create Equipment with Terrain Data**
   ```bash
   python manage.py test_terrain_classification --coordinates LON LAT --create-equipment
   ```

### Using Results in Calculations

The terrain classification results can be used to:
- Select appropriate terrain coefficients for wind load calculations
- Validate project site classifications
- Generate terrain-specific load calculations
- Create documentation for project verification

## Troubleshooting

### Common Issues

1. **Low Accuracy Rates**
   - Check if coordinates are within France bounds
   - Verify land use data coverage for the area
   - Review terrain classification mapping

2. **Missing Classifications**
   - Ensure coordinates are valid (longitude: -5.5 to 9.8, latitude: 41.3 to 51.1)
   - Check if land use data covers the area
   - Verify API connectivity

3. **Performance Issues**
   - Use caching for repeated coordinates
   - Batch process multiple coordinates
   - Consider using performance test results

### Validation Checklist

- [ ] Coordinates are within France bounds
- [ ] Terrain classification returns expected results
- [ ] Verification accuracy meets project requirements
- [ ] Export files contain complete data
- [ ] Equipment creation works with classified terrain

## Best Practices

1. **Before Project Start**
   - Run verification tests with known locations
   - Generate test addresses for project area
   - Validate terrain classification accuracy

2. **During Project**
   - Test all project coordinates
   - Document any classification discrepancies
   - Use consistent coordinate formats

3. **Quality Assurance**
   - Run cross-validation tests
   - Compare with manual classifications
   - Maintain test result documentation

## Data Sources

- **Land Use Data**: Corine Land Cover (CLC) 2018
- **Geocoding**: French National Geocoding API (data.geopf.fr)
- **Coordinate System**: WGS84 (EPSG:4326)
- **Coverage**: Metropolitan France

## Support

For technical support or questions about the terrain classification system:
1. Check this guide first
2. Review verification reports for accuracy issues
3. Use performance tests to identify bottlenecks
4. Export detailed results for further analysis
