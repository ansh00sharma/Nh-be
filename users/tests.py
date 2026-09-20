from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase


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
        self.assertNotIn("password", response.data)
        self.assertTrue(User.objects.filter(email="alice@example.com").exists())

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
        self.assertIn("email", response.data)

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
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_authenticated_me(self):
        user = User.objects.create_user(
            email="alice@example.com",
            first_name="Alice",
            last_name="Example",
            password="strong-password-123",
        )
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
                "first_name": "Alice",
                "last_name": "Example",
                "email": "alice@example.com",
                "created_at": response.data["created_at"],
                "updated_at": response.data["updated_at"],
            },
        )

    def test_unauthenticated_me(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
