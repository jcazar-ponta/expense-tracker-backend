from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AppSettingsViewSet, ItemExpenseViewSet, LedgerViewSet, PaymentViewSet, PersonViewSet

router = DefaultRouter()
router.register(r"people", PersonViewSet, basename="person")
router.register(r"items", ItemExpenseViewSet, basename="item")
router.register(r"payments", PaymentViewSet, basename="payment")
router.register(r"ledger", LedgerViewSet, basename="ledger")
router.register(r"settings", AppSettingsViewSet, basename="settings")

urlpatterns = [
    path("", include(router.urls)),
]
