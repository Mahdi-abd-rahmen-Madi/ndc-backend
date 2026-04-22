from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from geodata.models import AntennaEquipment
from api.models import EngineerProfile


class Command(BaseCommand):
    help = 'Assign existing antenna equipment to engineers for testing RBAC system'

    def handle(self, *args, **options):
        # Get engineer users
        engineer_profiles = EngineerProfile.objects.all()
        
        if not engineer_profiles.exists():
            self.stdout.write(
                self.style.ERROR('No engineer profiles found. Please run create_rbac_data first.')
            )
            return

        # Get all equipment
        equipment_list = AntennaEquipment.objects.all()
        
        if not equipment_list.exists():
            self.stdout.write(
                self.style.ERROR('No antenna equipment found. Please import antenna data first.')
            )
            return

        self.stdout.write(f"Found {engineer_profiles.count()} engineers and {equipment_list.count()} equipment items")

        # Assign equipment to engineers in a round-robin fashion
        engineers = list(engineer_profiles)
        assignments = 0
        
        for i, equipment in enumerate(equipment_list):
            engineer = engineers[i % len(engineers)]
            equipment.responsible_user = engineer.user
            equipment.save()
            assignments += 1
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Assigned '{equipment.name}' to {engineer.user.username} ({engineer.employee_id})"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f"Successfully assigned {assignments} equipment items to engineers")
        )

        # Display assignment summary
        self.stdout.write("\n=== Assignment Summary ===")
        for engineer in engineers:
            equipment_count = AntennaEquipment.objects.filter(responsible_user=engineer.user).count()
            self.stdout.write(
                f"{engineer.user.username} ({engineer.employee_id}): {equipment_count} equipment items"
            )
