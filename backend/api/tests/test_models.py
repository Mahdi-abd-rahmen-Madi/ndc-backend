from django.test import TestCase
from django.contrib.auth.models import User
from ..models import UserProfile


class UserProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            phone="123-456-7890",
            department="IT",
            role="Developer"
        )

    def test_user_profile_creation(self):
        self.assertEqual(self.profile.user, self.user)
        self.assertEqual(self.profile.phone, "123-456-7890")
        self.assertEqual(self.profile.department, "IT")
        self.assertEqual(self.profile.role, "Developer")
        self.assertEqual(str(self.profile), f"{self.user.username}'s Profile")

    def test_one_to_one_relationship(self):
        with self.assertRaises(Exception):
            UserProfile.objects.create(user=self.user)
