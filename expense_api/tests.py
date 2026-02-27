from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

User = get_user_model()


class HealthTest(APITestCase):
    def test_health(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


class AuthFlowTest(APITestCase):
    def test_register_login_me(self):
        register = self.client.post(
            "/api/v1/auth/register/",
            {"email": "test@example.com", "password": "StrongPass123", "name": "Test"},
            format="json",
        )
        self.assertEqual(register.status_code, 201)
        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "test@example.com", "password": "StrongPass123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        access = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "test@example.com")
