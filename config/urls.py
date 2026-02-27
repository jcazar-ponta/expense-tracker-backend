from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": getattr(settings, "SERVICE_NAME", "expense-tracker-backend"),
            "version": getattr(settings, "SERVICE_VERSION", "1.0.0"),
        }
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/", include("auth_api.urls")),
    path("api/v1/", include("expense_api.urls")),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
