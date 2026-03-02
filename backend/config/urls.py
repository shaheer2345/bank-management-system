"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from banking import views as banking_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/', include('banking.urls')),
    path('api/loans/', include('loans.urls')),
    # individual banking page for opening account
    path('accounts/open/', banking_views.open_account_view, name='open-account'),
    path('accounts/<int:pk>/', banking_views.account_detail_view, name='account-detail'),
    path('accounts/<int:pk>/deposit/', banking_views.deposit_view, name='deposit'),
    path('accounts/<int:pk>/withdraw/', banking_views.withdraw_view, name='withdraw'),
    path('accounts/<int:pk>/transfer/', banking_views.transfer_view, name='transfer'),
    path('accounts/<int:pk>/close/', banking_views.close_account_view, name='close-account'),
    # authentication endpoints (login/logout/password, etc.)
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('accounts.urls')),
    path('', include('frontend.urls')),
]