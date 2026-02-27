from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ActionType, AppSettings, EntityType, ItemExpense, LedgerEvent, Payment, Person
from .serializers import (
    AppSettingsSerializer,
    ItemExpenseSerializer,
    LedgerEventSerializer,
    PaymentSerializer,
    PersonSerializer,
)
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
