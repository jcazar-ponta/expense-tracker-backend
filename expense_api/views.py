from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import (
    ActionType,
    AppSettings,
    EntityType,
    ItemExpense,
    LedgerEvent,
    Payment,
    Person,
    PublicShareLink,
    ShareScopeType,
)
from .serializers import (
    AppSettingsSerializer,
    ItemExpenseSerializer,
    LedgerEventSerializer,
    PaymentSerializer,
    PersonSerializer,
    PublicShareLinkCreateSerializer,
    PublicShareLinkSerializer,
    PublicShareLinkUpdateSerializer,
)
from .services.month_utils import iter_months_inclusive
from .services.payables import calculate_monthly_summary, generate_schedule, get_relevant_months
from .services.share_tokens import hash_share_token
from .utils import to_json_safe


class OwnedQuerySetMixin:
    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)


class PersonViewSet(OwnedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Person.objects.all()
    serializer_class = PersonSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        LedgerEvent.objects.create(
            owner=instance.owner,
            ts=timezone.now(),
            actor=instance.owner.email or instance.owner.username,
            entity_type=EntityType.PERSON,
            entity_id=str(instance.id),
            action=ActionType.DELETE,
            diff=None,
        )

    def perform_update(self, serializer):
        person = serializer.save()
        LedgerEvent.objects.create(
            owner=person.owner,
            ts=timezone.now(),
            actor=person.owner.email or person.owner.username,
            entity_type=EntityType.PERSON,
            entity_id=str(person.id),
            action=ActionType.UPDATE,
            diff=to_json_safe(serializer.validated_data),
        )

    def perform_create(self, serializer):
        person = serializer.save(owner=self.request.user)
        LedgerEvent.objects.create(
            owner=person.owner,
            ts=timezone.now(),
            actor=person.owner.email or person.owner.username,
            entity_type=EntityType.PERSON,
            entity_id=str(person.id),
            action=ActionType.CREATE,
            diff={"name": person.name},
        )


class ItemExpenseViewSet(OwnedQuerySetMixin, viewsets.ModelViewSet):
    queryset = ItemExpense.objects.prefetch_related("allocations").all()
    serializer_class = ItemExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        owner = instance.owner
        entity_id = str(instance.id)
        instance.delete()
        LedgerEvent.objects.create(
            owner=owner,
            ts=timezone.now(),
            actor=owner.email or owner.username,
            entity_type=EntityType.ITEM,
            entity_id=entity_id,
            action=ActionType.DELETE,
            diff=None,
        )


class PaymentViewSet(OwnedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        month = self.request.query_params.get("month")
        person_id = self.request.query_params.get("personId")
        if month:
            qs = qs.filter(month=month)
        if person_id:
            qs = qs.filter(person_id=person_id)
        return qs

    def perform_destroy(self, instance):
        owner = instance.owner
        entity_id = str(instance.id)
        instance.delete()
        LedgerEvent.objects.create(
            owner=owner,
            ts=timezone.now(),
            actor=owner.email or owner.username,
            entity_type=EntityType.PAYMENT,
            entity_id=entity_id,
            action=ActionType.DELETE,
            diff=None,
        )


class LedgerViewSet(OwnedQuerySetMixin, viewsets.ModelViewSet):
    queryset = LedgerEvent.objects.all()
    serializer_class = LedgerEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        qs = super().get_queryset()
        entity_type = self.request.query_params.get("entityType")
        entity_id = self.request.query_params.get("entityId")
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class AppSettingsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        settings_obj, _ = AppSettings.objects.get_or_create(owner=request.user)
        if request.method.lower() == "get":
            return Response(AppSettingsSerializer(settings_obj).data)

        serializer = AppSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        LedgerEvent.objects.create(
            owner=request.user,
            ts=timezone.now(),
            actor=request.user.email or request.user.username,
            entity_type=EntityType.SETTINGS,
            entity_id="global",
            action=ActionType.UPDATE,
            diff=to_json_safe(serializer.validated_data),
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class PublicShareLinkViewSet(OwnedQuerySetMixin, viewsets.ModelViewSet):
    queryset = PublicShareLink.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        if self.action == "create":
            return PublicShareLinkCreateSerializer
        if self.action == "partial_update":
            return PublicShareLinkUpdateSerializer
        return PublicShareLinkSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        share = serializer.save()

        payload = PublicShareLinkSerializer(share).data
        base_url = getattr(settings, "PUBLIC_SHARE_BASE_URL", "http://localhost:5000").rstrip("/")
        payload["shareUrl"] = f"{base_url}/public/payables/{share._raw_token}"
        return Response(payload, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        share = self.get_object()
        if share.revoked_at is None:
            share.revoked_at = timezone.now()
            share.save(update_fields=["revoked_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def partial_update(self, request, *args, **kwargs):
        share = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        update_fields = ["updated_at"]
        if "expiresInDays" in serializer.validated_data:
            expires_in_days = serializer.validated_data["expiresInDays"]
            share.expires_at = None if expires_in_days is None else timezone.now() + timedelta(days=expires_in_days)
            update_fields.append("expires_at")

        if "includeBreakdown" in serializer.validated_data:
            permissions_payload = dict(share.permissions or {})
            permissions_payload["viewOnly"] = True
            permissions_payload["includeBreakdown"] = serializer.validated_data["includeBreakdown"]
            share.permissions = permissions_payload
            update_fields.append("permissions")

        share.save(update_fields=update_fields)
        return Response(PublicShareLinkSerializer(share).data, status=status.HTTP_200_OK)


class PublicPayablesView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_payables"

    def get(self, request, token):
        token_hash = hash_share_token(token)
        share = PublicShareLink.objects.filter(token_hash=token_hash).first()
        if not share:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        if share.revoked_at is not None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if share.expires_at is not None and share.expires_at <= now:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        owner = share.owner
        include_breakdown = bool((share.permissions or {}).get("includeBreakdown", True))
        scope_payload = share.scope_payload or {}

        people = list(Person.objects.filter(owner=owner, is_active=True))
        items = list(ItemExpense.objects.filter(owner=owner).prefetch_related("allocations"))
        payments = list(Payment.objects.filter(owner=owner))
        schedule = generate_schedule(items)
        all_months = get_relevant_months(schedule, payments)

        if share.scope_type == ShareScopeType.MONTH:
            months = [scope_payload.get("month")]
            person_ids = {str(person.id) for person in people}
        elif share.scope_type == ShareScopeType.RANGE:
            months = list(iter_months_inclusive(scope_payload.get("start"), scope_payload.get("end")))
            person_ids = {str(person.id) for person in people}
        elif share.scope_type == ShareScopeType.PERSON_MONTH:
            months = [scope_payload.get("month")]
            person_ids = {str(scope_payload.get("personId"))}
        elif share.scope_type == ShareScopeType.PERSON_RANGE:
            months = list(iter_months_inclusive(scope_payload.get("start"), scope_payload.get("end")))
            person_ids = {str(scope_payload.get("personId"))}
        else:
            return Response({"detail": "Invalid scope."}, status=status.HTTP_400_BAD_REQUEST)

        people_by_id = {str(person.id): person for person in people}
        item_by_id = {str(item.id): item for item in items}

        rows = []
        for month in months:
            for person_id in person_ids:
                person = people_by_id.get(person_id)
                if not person:
                    continue

                summary = calculate_monthly_summary(person_id, month, schedule, payments, all_months)
                if all(float(summary[key]) == 0 for key in summary):
                    continue

                total_due = float(summary["totalPayable"])
                total_paid = float(summary["paid"])
                if total_paid >= total_due and total_due > 0:
                    row_status = "PAID"
                elif total_paid > 0:
                    row_status = "PARTIAL"
                elif total_due > 0:
                    row_status = "UNPAID"
                else:
                    row_status = "NO_DUES"

                row = {
                    "personId": person_id,
                    "personName": person.name,
                    "month": month,
                    "status": row_status,
                    **summary,
                }

                if include_breakdown:
                    row["items"] = [
                        {
                            "itemId": schedule_entry["item_id"],
                            "title": item_by_id[schedule_entry["item_id"]].title if schedule_entry["item_id"] in item_by_id else "Unknown Item",
                            "category": item_by_id[schedule_entry["item_id"]].category if schedule_entry["item_id"] in item_by_id else "General",
                            "amount": float(schedule_entry["total_due"]),
                        }
                        for schedule_entry in schedule
                        if schedule_entry["month"] == month and schedule_entry["person_id"] == person_id
                    ]
                    row["payments"] = [
                        {
                            "id": str(payment.id),
                            "amountPaid": float(payment.amount_paid),
                            "status": payment.status,
                            "paidAt": payment.paid_at,
                            "method": payment.method,
                            "notes": payment.notes,
                        }
                        for payment in payments
                        if payment.month == month and str(payment.person_id) == person_id
                    ]
                rows.append(row)

        share.last_accessed_at = now
        share.access_count = share.access_count + 1
        share.save(update_fields=["last_accessed_at", "access_count", "updated_at"])

        response = Response(
            {
                "sharedView": True,
                "scopeType": share.scope_type,
                "scopePayload": share.scope_payload,
                "permissions": share.permissions,
                "generatedAt": now,
                "summary": {
                    "totalPayable": sum(row["totalPayable"] for row in rows),
                    "totalCollected": sum(row["paid"] for row in rows),
                    "outstanding": sum(row["remaining"] for row in rows),
                },
                "rows": rows,
            },
            status=status.HTTP_200_OK,
        )
        response["Cache-Control"] = "no-store, private"
        response["Pragma"] = "no-cache"
        return response
