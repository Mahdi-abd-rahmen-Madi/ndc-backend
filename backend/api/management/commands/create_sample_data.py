from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import UserProfile


class Command(BaseCommand):
    help = 'Create sample data for the NDC application'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Creating sample data...'))

        # Create sample user
        user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True
            }
        )
        if created:
            user.set_password('admin123')
            user.save()
            self.stdout.write(self.style.SUCCESS('Created admin user'))

        # Create user profile
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'phone': '+1-555-0123',
                'department': 'IT',
                'role': 'System Administrator'
            }
        )

        self.stdout.write(self.style.SUCCESS('Sample data created successfully!'))
        self.stdout.write(self.style.SUCCESS(f'Created {UserProfile.objects.count()} user profiles'))
        self.stdout.write(self.style.SUCCESS('Admin user: admin / admin123'))
