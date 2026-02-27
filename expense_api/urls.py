from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AppSettingsViewSet,
    ItemExpenseViewSet,
    LedgerViewSet,
    PaymentViewSet,
    PersonViewSet,
    PublicPayablesView,
    PublicShareLinkViewSet,
)

router = DefaultRouter()
router.register(r"people", PersonViewSet, basename="person")
router.register(r"items", ItemExpenseViewSet, basename="item")
router.register(r"payments", PaymentViewSet, basename="payment")
router.register(r"ledger", LedgerViewSet, basename="ledger")
router.register(r"settings", AppSettingsViewSet, basename="settings")
router.register(r"shares", PublicShareLinkViewSet, basename="share")

urlpatterns = [
    path("public/payables/<str:token>/", PublicPayablesView.as_view(), name="public-payables"),
    path("", include(router.urls)),
]
