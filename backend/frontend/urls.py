from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('admin-dashboard/', views.admin_dashboard_view, name='admin-dashboard'),
    path('loans/<int:pk>/', views.loan_detail_view, name='loan-detail'),
    path('loans/', views.loan_list_view, name='loan-list'),
    path('recurring/', views.recurring_list_view, name='recurring-list'),
    path('statements/', views.statement_view, name='statements'),
    path('search/', views.search_view, name='search'),
]