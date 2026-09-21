from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from projects.models import Project
from users.roles import ADMIN, AGENT, MANAGER, assign_taskflow_role
from users.seed import ensure_final_seed_data


User = get_user_model()


class AuthAPITests(APITestCase):
    def test_successful_signup(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "first_name": "Alice",
                "last_name": "Example",
                "email": "alice@example.com",
                "password": "strong-password-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["first_name"], "Alice")
        self.assertEqual(response.data["last_name"], "Example")
        self.assertEqual(response.data["email"], "alice@example.com")
        self.assertEqual(response.data["role"], AGENT)
        self.assertNotIn("password", response.data)
        user = User.objects.get(email="alice@example.com")
        self.assertTrue(user.groups.filter(name=AGENT).exists())

    def test_duplicate_signup_rejection(self):
        User.objects.create_user(
            email="alice@example.com",
            first_name="Alice",
            last_name="Example",
            password="strong-password-123",
        )

        response = self.client.post(
            "/api/auth/signup/",
            {
                "first_name": "Alice",
                "last_name": "Example",
                "email": "alice@example.com",
                "password": "another-strong-password-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "error")
        self.assertIsNone(response.data["data"])

    def test_successful_login(self):
        User.objects.create_user(
            email="alice@example.com",
            first_name="Alice",
            last_name="Example",
            password="strong-password-123",
        )

        response = self.client.post(
            "/api/auth/login/",
            {
                "email": "alice@example.com",
                "password": "strong-password-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_invalid_login(self):
        User.objects.create_user(
            email="alice@example.com",
            first_name="Alice",
            last_name="Example",
            password="strong-password-123",
        )

        response = self.client.post(
            "/api/auth/login/",
            {
                "email": "alice@example.com",
                "password": "wrong-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["status"], "error")
        self.assertIsNone(response.data["data"])

    def test_authenticated_me(self):
        user = User.objects.create_user(
            email="alice@example.com",
            first_name="Alice",
            last_name="Example",
            password="strong-password-123",
        )
        assign_taskflow_role(user, AGENT)
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "email": "alice@example.com",
                "password": "strong-password-123",
            },
            format="json",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}"
        )

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "id": user.id,
                "username": "alice@example.com",
                "first_name": "Alice",
                "last_name": "Example",
                "email": "alice@example.com",
                "role": AGENT,
                "modules": ["tasks"],
                "created_at": response.data["created_at"],
                "updated_at": response.data["updated_at"],
            },
        )

    def test_admin_role_is_returned_from_me(self):
        user = User.objects.create_user(
            email="admin-user@example.com",
            first_name="Admin",
            last_name="User",
            password="strong-password-123",
        )
        assign_taskflow_role(user, ADMIN)
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "email": "admin-user@example.com",
                "password": "strong-password-123",
            },
            format="json",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}"
        )

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], ADMIN)
        self.assertIn("dashboard", response.data["modules"])

    def test_unauthenticated_me(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["status"], "error")


class SeedDataTests(APITestCase):
    def test_final_seed_data_exists_and_is_idempotent(self):
        ensure_final_seed_data()
        ensure_final_seed_data()

        for role in (ADMIN, MANAGER, AGENT):
            self.assertTrue(Group.objects.filter(name=role).exists())

        admin = User.objects.get(email="admin@taskflow.in")
        manager = User.objects.get(email="sharma999ansh@gmail.com")
        agent = User.objects.get(email="ansh.sharma.tenant@gmail.com")

        self.assertTrue(admin.groups.filter(name=ADMIN).exists())
        self.assertTrue(manager.groups.filter(name=MANAGER).exists())
        self.assertTrue(agent.groups.filter(name=AGENT).exists())

        self.assertNotEqual(admin.password, "aisufhasiw@eq2weh3as")
        self.assertNotEqual(manager.password, "welcome")
        self.assertNotEqual(agent.password, "welcome")
        self.assertTrue(admin.check_password("aisufhasiw@eq2weh3as"))
        self.assertTrue(manager.check_password("welcome"))
        self.assertTrue(agent.check_password("welcome"))

        self.assertEqual(
            Project.objects.get(name="Fintech", owner=admin).owner_id,
            admin.id,
        )
        self.assertEqual(
            Project.objects.get(name="Sales Marketing", owner=manager).owner_id,
            manager.id,
        )
        self.assertEqual(
            Project.objects.get(name="HR management", owner=manager).owner_id,
            manager.id,
        )

        self.assertEqual(User.objects.filter(email="admin@taskflow.in").count(), 1)
        self.assertEqual(User.objects.filter(email="sharma999ansh@gmail.com").count(), 1)
        self.assertEqual(User.objects.filter(email="ansh.sharma.tenant@gmail.com").count(), 1)
        self.assertEqual(Project.objects.filter(name="Fintech", owner=admin).count(), 1)
        self.assertEqual(
            Project.objects.filter(name="Sales Marketing", owner=manager).count(),
            1,
        )
        self.assertEqual(
            Project.objects.filter(name="HR management", owner=manager).count(),
            1,
        )
