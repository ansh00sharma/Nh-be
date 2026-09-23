from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from django.test.utils import CaptureQueriesContext
from rest_framework_simplejwt.tokens import RefreshToken

from projects.models import Project
from users.querysets import with_taskflow_role
from users.roles import ADMIN, AGENT, MANAGER, assign_taskflow_role
from users.serializers import ManagedUserSerializer
from users.seed import ensure_final_seed_data


User = get_user_model()


class AuthAPITests(APITestCase):
    def user_selects(self, queries):
        return [
            query["sql"]
            for query in queries
            if "SELECT" in query["sql"].upper()
            and '"users_user"' in query["sql"]
        ]

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

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "auth-cache-tests",
            }
        }
    )
    def test_same_authenticated_user_hits_auth_cache_on_second_request(self):
        cache.clear()
        user = User.objects.create_user(
            email="cached-auth@example.com",
            first_name="Cached",
            last_name="Auth",
            password="strong-password-123",
        )
        assign_taskflow_role(user, ADMIN)
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        with CaptureQueriesContext(connection) as first_queries:
            first_response = self.client.get("/api/auth/me/")
        with CaptureQueriesContext(connection) as second_queries:
            second_response = self.client.get("/api/auth/me/")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.user_selects(first_queries))
        self.assertEqual(self.user_selects(second_queries), [])
        self.assertEqual(second_response.data["role"], ADMIN)


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


class ManagedUserAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-list@example.com",
            first_name="Admin",
            last_name="List",
            password="strong-password-123",
        )
        assign_taskflow_role(self.admin, ADMIN)
        self.admin._taskflow_role_cache = ADMIN
        self.client.force_authenticate(user=self.admin)

    def create_users(self, count):
        roles = (ADMIN, MANAGER, AGENT)
        users = []
        for index in range(count):
            user = User.objects.create_user(
                email=f"user-{index}@example.com",
                first_name=f"User{index}",
                last_name="Example",
                password="strong-password-123",
            )
            assign_taskflow_role(user, roles[index % len(roles)])
            users.append(user)
        return users

    def test_managed_user_list_response_contract(self):
        self.create_users(1)

        response = self.client.get("/api/users/?page_size=10")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_user = response.data["results"][0]
        self.assertEqual(
            set(first_user.keys()),
            {
                "id",
                "username",
                "first_name",
                "last_name",
                "email",
                "role",
                "modules",
                "created_at",
                "updated_at",
            },
        )
        self.assertIn(first_user["role"], (ADMIN, MANAGER, AGENT))

    def test_managed_user_list_queries_do_not_scale_with_returned_users(self):
        self.create_users(20)

        with CaptureQueriesContext(connection) as ten_user_context:
            ten_user_response = self.client.get("/api/users/?page_size=10")

        with CaptureQueriesContext(connection) as twenty_user_context:
            twenty_user_response = self.client.get("/api/users/?page_size=20")

        self.assertEqual(ten_user_response.status_code, status.HTTP_200_OK)
        self.assertEqual(twenty_user_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(ten_user_response.data["results"]), 10)
        self.assertEqual(len(twenty_user_response.data["results"]), 20)
        self.assertLessEqual(
            len(twenty_user_context),
            len(ten_user_context) + 1,
        )

    def test_managed_user_serializer_does_not_query_for_annotated_roles(self):
        self.create_users(10)
        users = list(with_taskflow_role(User.objects.order_by("id"))[:10])

        with self.assertNumQueries(0):
            data = ManagedUserSerializer(users, many=True).data

        self.assertEqual(len(data), 10)
        self.assertTrue(all(item["role"] in (ADMIN, MANAGER, AGENT) for item in data))
