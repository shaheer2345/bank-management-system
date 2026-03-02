from django.urls import path
from . import views

urlpatterns = [
    path('', views.LoanListCreateAPIView.as_view(), name='loan-list-create'),
    path('<int:pk>/', views.LoanDetailAPIView.as_view(), name='loan-detail'),
    path('<int:pk>/approve/', views.LoanApproveAPIView.as_view(), name='loan-approve'),
    path('<int:pk>/repay/', views.LoanRepayAPIView.as_view(), name='loan-repay'),
]
