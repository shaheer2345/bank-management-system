from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile_view, name='edit-profile'),
    path('login-history/', views.login_history_view, name='login-history'),
    path('security/', views.security_center_view, name='security-center'),
    path('change-password/', views.change_password_view, name='change-password'),
    path('suspicious-activity/', views.suspicious_activity_view, name='suspicious-activity'),
    path('register/', views.register_view, name='register'),
    path('enable-totp/', views.enable_totp_view, name='enable_totp'),
]
