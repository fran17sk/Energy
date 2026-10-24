from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.tramites.urls_public')),
    path('institucional/', include('apps.tramites.urls_institutional')),
    path('acceso/', include('apps.accounts.urls')),
]
