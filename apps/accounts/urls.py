from django.contrib.auth import views as auth_views
from django.urls import path
urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='public/login.html'), name='login'),
    path('salir/', auth_views.LogoutView.as_view(), name='logout'),
]
