from django.contrib import admin
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "ShifterSuivi — administration"
admin.site.site_title = "ShifterSuivi"
admin.site.index_title = "Gestion des comptes et des données"

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=static("img/favicon.svg"), permanent=True)),
    path("admin/", admin.site.urls),
    path("", include("garage.urls")),
]
