from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import Role, EngineerProfile, UserProfile


class Command(BaseCommand):
    help = 'Create initial RBAC data: roles and sample users'

    def handle(self, *args, **options):
        # Create roles
        roles_data = [
            {
                'name': 'admin',
                'description': 'System administrator with full access',
                'permissions': {
                    'can_manage_users': True,
                    'can_manage_all_equipment': True,
                    'can_access_all_data': True
                }
            },
            {
                'name': 'engineer',
                'description': 'Engineer with access to assigned equipment only',
                'permissions': {
                    'can_manage_own_equipment': True,
                    'can_access_own_data': True,
                    'can_create_equipment': True
                }
            },
            {
                'name': 'user',
                'description': 'Regular user with read-only access',
                'permissions': {
                    'can_view_public_data': True
                }
            }
        ]

        created_roles = {}
        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_data['name'],
                defaults={
                    'description': role_data['description'],
                    'permissions': role_data['permissions']
                }
            )
            created_roles[role.name] = role
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created role: {role.name}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Role already exists: {role.name}")
                )

        # Create sample users if they don't exist
        users_data = [
            {
                'username': 'admin',
                'email': 'admin@ndc.com',
                'password': 'admin123',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True
            },
            {
                'username': 'engineer1',
                'email': 'engineer1@ndc.com',
                'password': 'engineer123',
                'role': 'engineer',
                'employee_id': 'ENG001',
                'specializations': ['4G', '5G', 'Antenna Installation']
            },
            {
                'username': 'engineer2',
                'email': 'engineer2@ndc.com',
                'password': 'engineer123',
                'role': 'engineer',
                'employee_id': 'ENG002',
                'specializations': ['4G', 'Terrain Analysis']
            }
        ]

        for user_data in users_data:
            user, created = User.objects.get_or_create(
                username=user_data['username'],
                defaults={
                    'email': user_data['email'],
                    'is_staff': user_data.get('is_staff', False),
                    'is_superuser': user_data.get('is_superuser', False)
                }
            )
            
            if created:
                user.set_password(user_data['password'])
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f"Created user: {user.username}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"User already exists: {user.username}")
                )

            # Create or update user profile
            profile, profile_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': created_roles[user_data['role']],
                    'department': 'Technical Services'
                }
            )
            
            if not profile_created and profile.role != created_roles[user_data['role']]:
                profile.role = created_roles[user_data['role']]
                profile.save()

            # Create engineer profile for engineer users
            if user_data['role'] == 'engineer':
                engineer_profile, eng_created = EngineerProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'employee_id': user_data['employee_id'],
                        'specializations': user_data['specializations']
                    }
                )
                
                if eng_created:
                    self.stdout.write(
                        self.style.SUCCESS(f"Created engineer profile for: {user.username}")
                    )

        self.stdout.write(
            self.style.SUCCESS('RBAC data creation completed successfully!')
        )
        
        # Display summary
        self.stdout.write("\n=== Summary ===")
        self.stdout.write(f"Roles created: {Role.objects.count()}")
        self.stdout.write(f"Users created: {User.objects.count()}")
        self.stdout.write(f"User profiles: {UserProfile.objects.count()}")
        self.stdout.write(f"Engineer profiles: {EngineerProfile.objects.count()}")
