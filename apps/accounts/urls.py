from django.contrib.auth import views as auth_views
from django.urls import path
from .forms import AccesoInstitucionalForm
urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='public/login.html', authentication_form=AccesoInstitucionalForm), name='login'),
    path('salir/', auth_views.LogoutView.as_view(), name='logout'),
]
