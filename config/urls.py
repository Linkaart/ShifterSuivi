from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "ShifterSuivi — administration"
admin.site.site_title = "ShifterSuivi"
admin.site.index_title = "Gestion des comptes et des données"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("garage.urls")),
]
