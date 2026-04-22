import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from geodata.models import AntennaEquipment, AntennaSpecification, TerrainLoadCalculation
import os


class Command(BaseCommand):
    help = 'Import antenna equipment data from Excel files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Path to Excel file to import'
        )
        parser.add_argument(
            '--dir',
            type=str,
            default='example',
            help='Directory containing Excel files (default: example)'
        )

    def handle(self, *args, **options):
        if options['file']:
            files = [options['file']]
        else:
            # Get all Excel files from the example directory
            example_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), options['dir'])
            files = [os.path.join(example_dir, f) for f in os.listdir(example_dir) if f.endswith('.xlsx')]
        
        if not files:
            self.stdout.write(self.style.ERROR('No Excel files found'))
            return

        for file_path in files:
            self.stdout.write(f'Processing {file_path}...')
            self.import_excel_file(file_path)

    def import_excel_file(self, file_path):
        try:
            # Read Excel file with headers from row 2
            df = pd.read_excel(file_path, header=2)
            
            # Remove empty rows
            df = df.dropna(subset=['Name'])
            
            imported_count = 0
            
            with transaction.atomic():
                for index, row in df.iterrows():
                    if pd.isna(row['Name']) or str(row['Name']).strip() == '':
                        continue
                    
                    # Create or update AntennaEquipment
                    equipment, created = AntennaEquipment.objects.update_or_create(
                        name=str(row['Name']).strip(),
                        defaults={
                            'sub_elements': str(row['Sous-éléments']) if pd.notna(row['Sous-éléments']) else '',
                            'responsible_person': str(row['Personne']).strip() if pd.notna(row['Personne']) else '',
                            'status': str(row['Statut']).strip() if pd.notna(row['Statut']) else '',
                            'date': pd.to_datetime(row['Date']).date() if pd.notna(row['Date']) else None,
                            'region': str(row['REGION']).strip() if pd.notna(row['REGION']) else '',
                            'building_height': float(row['Hauteur BATIMENT (m)']) if pd.notna(row['Hauteur BATIMENT (m)']) else None,
                            'mast_height': float(row['Hauteur MAT (m)']) if pd.notna(row['Hauteur MAT (m)']) else None,
                            'comments': str(row['Commentaire']).strip() if pd.notna(row['Commentaire']) else '',
                            'item_id': str(int(row['Item ID (auto generated)'])) if pd.notna(row['Item ID (auto generated)']) else None,
                        }
                    )
                    
                    # Create 4G specification if data exists
                    if pd.notna(row['Hauteur 4G (mm)']):
                        AntennaSpecification.objects.update_or_create(
                            equipment=equipment,
                            antenna_type='4G',
                            defaults={
                                'height_mm': float(row['Hauteur 4G (mm)']),
                                'width_mm': float(row['Largeur 4G (mm)']) if pd.notna(row['Largeur 4G (mm)']) else 0,
                                'thickness_mm': float(row['Epaisseur 4G (mm)']) if pd.notna(row['Epaisseur 4G (mm)']) else 0,
                                'weight_dan': float(row['Poids 4G (daN)']) if pd.notna(row['Poids 4G (daN)']) else 0,
                            }
                        )
                    
                    # Create 5G specification if data exists
                    if pd.notna(row['Hauteur 5G (mm)']):
                        AntennaSpecification.objects.update_or_create(
                            equipment=equipment,
                            antenna_type='5G',
                            defaults={
                                'height_mm': float(row['Hauteur 5G (mm)']),
                                'width_mm': float(row['Largeur 5G (mm)']) if pd.notna(row['Largeur 5G (mm)']) else 0,
                                'thickness_mm': float(row['Epaisseur 5G (mm)']) if pd.notna(row['Epaisseur 5G (mm)']) else 0,
                                'weight_dan': float(row['Poids 5G (daN)']) if pd.notna(row['Poids 5G (daN)']) else 0,
                            }
                        )
                    
                    # Create terrain calculations for each terrain type
                    terrain_types = ['0', 'II', 'IIIa', 'IIIb', 'IV']
                    terrain_columns = [
                        'Terrain 0', 'Terrain II', 'Terrain IIIa', 'Terrain IIIb', 'Terrain IV'
                    ]
                    section_columns = [
                        'Section Mat Terrain 0', 'Section Mat Terrain II', 
                        'Section Mat T errain IIIa', 'Section Mat Terrain IIIb', 'Section Mat Terrain IV'
                    ]
                    
                    for i, terrain_type in enumerate(terrain_types):
                        terrain_col = terrain_columns[i]
                        section_col = section_columns[i]
                        
                        if pd.notna(row[terrain_col]) or pd.notna(row[section_col]):
                            terrain_data = {}
                            if pd.notna(row[terrain_col]):
                                terrain_data['terrain_value'] = str(row[terrain_col])
                            
                            TerrainLoadCalculation.objects.update_or_create(
                                equipment=equipment,
                                terrain_type=terrain_type,
                                defaults={
                                    'section_material': str(row[section_col]).strip() if pd.notna(row[section_col]) else '',
                                    'load_calculations': terrain_data,
                                }
                            )
                    
                    imported_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully imported {imported_count} equipment records from {os.path.basename(file_path)}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error importing {file_path}: {str(e)}')
            )
