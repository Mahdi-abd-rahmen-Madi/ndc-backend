from django.core.management.base import BaseCommand
from django.db import transaction
import pandas as pd
import os
from geodata.models import AntennaEquipment, AntennaSpecification, TerrainDocumentation, TerrainLoadCalculation
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Import antenna equipment data from Excel files'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the Excel file')
        parser.add_argument('--dry-run', action='store_true', help='Run without saving data')

    def handle(self, *args, **options):
        file_path = options['file_path']
        dry_run = options['dry_run']
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        try:
            # Read Excel file with proper headers (row 2 contains headers)
            df = pd.read_excel(file_path, header=2)
            self.stdout.write(f'Loaded {len(df)} rows from {file_path}')
            
            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN - No data will be saved'))
            
            with transaction.atomic():
                imported_count = 0
                for index, row in df.iterrows():
                    if pd.isna(row['Name']):
                        continue
                        
                    # Create or update AntennaEquipment
                    equipment_data = {
                        'name': str(row['Name']).strip(),
                        'sub_elements': str(row['Sous-éléments']) if pd.notna(row['Sous-éléments']) else '',
                        'responsible_person': str(row['Personne']).strip() if pd.notna(row['Personne']) else '',
                        'status': str(row['Statut']) if pd.notna(row['Statut']) else '',
                        'region': str(int(row['REGION'])) if pd.notna(row['REGION']) else '',
                        'building_height': float(row['Hauteur BATIMENT (m)']) if pd.notna(row['Hauteur BATIMENT (m)']) else None,
                        'mast_height': float(row['Hauteur MAT (m)']) if pd.notna(row['Hauteur MAT (m)']) else None,
                        'comments': str(row['Commentaire']).strip() if pd.notna(row['Commentaire']) else '',
                        'item_id': str(int(row['Item ID (auto generated)'])) if pd.notna(row['Item ID (auto generated)']) else '',
                    }
                    
                    if not dry_run:
                        equipment, created = AntennaEquipment.objects.update_or_create(
                            item_id=equipment_data['item_id'],
                            defaults=equipment_data
                        )
                    else:
                        equipment = AntennaEquipment(**equipment_data)
                    
                    # Create 4G antenna specification
                    if pd.notna(row['Hauteur 4G (mm)']):
                        spec_4g_data = {
                            'equipment': equipment,
                            'antenna_type': '4G',
                            'height_mm': float(row['Hauteur 4G (mm)']),
                            'width_mm': float(row['Largeur 4G (mm)']),
                            'thickness_mm': float(row['Epaisseur 4G (mm)']),
                            'weight_dan': float(row['Poids 4G (daN)']),
                        }
                        if not dry_run:
                            AntennaSpecification.objects.update_or_create(
                                equipment=equipment,
                                antenna_type='4G',
                                defaults=spec_4g_data
                            )
                    
                    # Create 5G antenna specification
                    if pd.notna(row['Hauteur 5G (mm)']):
                        spec_5g_data = {
                            'equipment': equipment,
                            'antenna_type': '5G',
                            'height_mm': float(row['Hauteur 5G (mm)']),
                            'width_mm': float(row['Largeur 5G (mm)']),
                            'thickness_mm': float(row['Epaisseur 5G (mm)']),
                            'weight_dan': float(row['Poids 5G (daN)']),
                        }
                        if not dry_run:
                            AntennaSpecification.objects.update_or_create(
                                equipment=equipment,
                                antenna_type='5G',
                                defaults=spec_5g_data
                            )
                    
                    # Create terrain documentation and load calculations
                    terrain_types = ['0', 'II', 'IIIa', 'IIIb', 'IV']
                    for terrain_type in terrain_types:
                        # Documentation URLs
                        terrain_col = f'Terrain {terrain_type}'
                        section_col = f'Section Mat Terrain {terrain_type}'
                        # Fix for the typo in Excel column name
                        if terrain_type == 'IIIa':
                            section_col = 'Section Mat T errain IIIa'
                        
                        if pd.notna(row[terrain_col]) and str(row[terrain_col]).strip():
                            doc_data = {
                                'equipment': equipment,
                                'terrain_type': terrain_type,
                                'document_urls': str(row[terrain_col]),
                                'document_types': self.extract_file_types(str(row[terrain_col])),
                            }
                            
                            if not dry_run:
                                terrain_doc, created = TerrainDocumentation.objects.update_or_create(
                                    equipment=equipment,
                                    terrain_type=terrain_type,
                                    defaults=doc_data
                                )
                            else:
                                terrain_doc = TerrainDocumentation(**doc_data)
                            
                            # Load calculation with material specification
                            if pd.notna(row[section_col]) and str(row[section_col]).strip():
                                load_data = {
                                    'equipment': equipment,
                                    'terrain_type': terrain_type,
                                    'material_specification': str(row[section_col]).strip(),
                                    'documentation': terrain_doc if not dry_run else None,
                                }
                                
                                if not dry_run:
                                    TerrainLoadCalculation.objects.update_or_create(
                                        equipment=equipment,
                                        terrain_type=terrain_type,
                                        defaults=load_data
                                    )
                    
                    imported_count += 1
                    if index % 5 == 0:
                        self.stdout.write(f'Processed {index + 1}/{len(df)} rows...')
                
                action = "would be" if dry_run else "were"
                self.stdout.write(self.style.SUCCESS(f'Success! {imported_count} equipment records {action} imported'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error importing data: {str(e)}'))
            raise

    def extract_file_types(self, document_urls):
        """Extract file extensions from document URLs"""
        file_types = []
        if document_urls:
            urls = [url.strip() for url in document_urls.split(',') if url.strip()]
            for url in urls:
                if '.' in url:
                    ext = '.' + url.split('.')[-1].lower()
                    if ext not in file_types:
                        file_types.append(ext)
        return file_types
