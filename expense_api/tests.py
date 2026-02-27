from django.contrib.auth import get_user_model
from datetime import timedelta
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Allocation, ItemExpense, Payment, PaymentStatus, Person, PublicShareLink, ShareScopeType
from .services.share_tokens import generate_share_token

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


class PublicShareLinkTests(APITestCase):
    def setUp(self):
        self.password = "StrongPass123"
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password=self.password)
        self.other = User.objects.create_user(username="other", email="other@example.com", password=self.password)
        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "owner@example.com", "password": self.password},
            format="json",
        )
        self.access = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_generate_token_entropy_length(self):
        token = generate_share_token()
        self.assertGreaterEqual(len(token), 40)

    def test_create_and_list_share_links(self):
        create_response = self.client.post(
            "/api/v1/shares/",
            {
                "scopeType": "MONTH",
                "scopePayload": {"month": "2026-02"},
                "expiresInDays": 7,
                "includeBreakdown": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertIn("shareUrl", create_response.json())

        list_response = self.client.get("/api/v1/shares/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_owner_cannot_revoke_others_links(self):
        share = PublicShareLink.objects.create(
            owner=self.owner,
            token_hash="abc123" * 10 + "abcd",
            scope_type=ShareScopeType.MONTH,
            scope_payload={"month": "2026-02"},
            permissions={"viewOnly": True, "includeBreakdown": True},
        )

        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "other@example.com", "password": self.password},
            format="json",
        )
        other_access = login.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {other_access}")

        response = self.client.delete(f"/api/v1/shares/{share.id}/")
        self.assertEqual(response.status_code, 404)

    def test_public_endpoint_rejects_revoked_or_expired(self):
        create_response = self.client.post(
            "/api/v1/shares/",
            {
                "scopeType": "MONTH",
                "scopePayload": {"month": "2026-02"},
                "expiresInDays": 1,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        token = create_response.json()["shareUrl"].rstrip("/").split("/")[-1]
        share = PublicShareLink.objects.get(id=create_response.json()["id"])

        share.revoked_at = timezone.now()
        share.save(update_fields=["revoked_at", "updated_at"])
        revoked_response = self.client.get(f"/api/v1/public/payables/{token}/")
        self.assertEqual(revoked_response.status_code, 404)

        share.revoked_at = None
        share.expires_at = timezone.now() - timedelta(seconds=1)
        share.save(update_fields=["revoked_at", "expires_at", "updated_at"])
        expired_response = self.client.get(f"/api/v1/public/payables/{token}/")
        self.assertEqual(expired_response.status_code, 404)

    def test_public_endpoint_returns_payload(self):
        person = Person.objects.create(owner=self.owner, name="owen", is_active=True)
        item = ItemExpense.objects.create(
            owner=self.owner,
            title="airfare",
            category="General",
            notes="",
            total_amount="1200.00",
            currency="PHP",
            purchase_date="2026-02-01",
            installment_months=1,
            start_month="2026-02",
            split_type="EQUAL",
        )
        Allocation.objects.create(item=item, person=person, value="1.00")
        Payment.objects.create(
            owner=self.owner,
            person=person,
            month="2026-02",
            amount_paid="500.00",
            status=PaymentStatus.PARTIAL,
        )

        create_response = self.client.post(
            "/api/v1/shares/",
            {
                "scopeType": "MONTH",
                "scopePayload": {"month": "2026-02"},
                "includeBreakdown": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        token = create_response.json()["shareUrl"].rstrip("/").split("/")[-1]

        public_response = self.client.get(f"/api/v1/public/payables/{token}/")
        self.assertEqual(public_response.status_code, 200)
        payload = public_response.json()
        self.assertTrue(payload["sharedView"])
        self.assertEqual(payload["scopeType"], "MONTH")
        self.assertGreaterEqual(len(payload["rows"]), 1)
