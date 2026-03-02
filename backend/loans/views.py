from django.shortcuts import render
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Loan
from .serializers import LoanSerializer, LoanApprovalSerializer, LoanPaymentSerializer, LoanDetailSerializer
from django.utils import timezone
from .permissions import IsLoanOwnerOrStaff


# API: list/create loans for authenticated users
class LoanListCreateAPIView(generics.ListCreateAPIView):
	serializer_class = LoanSerializer
	permission_classes = [IsLoanOwnerOrStaff]

	def get_queryset(self):
		user = self.request.user
		# staff/admin and tellers see all loans
		if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ('ADMIN', 'TELLER'):
			return Loan.objects.all()
		return Loan.objects.filter(user=user)

	def perform_create(self, serializer):
		serializer.save(user=self.request.user)


class LoanDetailAPIView(generics.RetrieveAPIView):
	queryset = Loan.objects.all()
	serializer_class = LoanDetailSerializer
	permission_classes = [IsLoanOwnerOrStaff]


class LoanRepayAPIView(APIView):
	permission_classes = [IsLoanOwnerOrStaff]

	def post(self, request, pk, format=None):
		try:
			loan = Loan.objects.get(pk=pk)
		except Loan.DoesNotExist:
			return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
		# only owner or staff may create payments
		if not (request.user.id == loan.user_id or getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN'):
			return Response(status=status.HTTP_403_FORBIDDEN)
		amount = request.data.get('amount')
		serializer = LoanPaymentSerializer(data={'loan': loan.id, 'amount': amount})
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data, status=status.HTTP_201_CREATED)


# API: approve/reject loan (staff only)
class LoanApproveAPIView(generics.UpdateAPIView):
	queryset = Loan.objects.all()
	serializer_class = LoanApprovalSerializer
	permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

	def perform_update(self, serializer):
		instance = serializer.save()
		if instance.status == 'APPROVED' and instance.approved_at is None:
			instance.approved_at = timezone.now()
			# schedule first payment due one month later
			from datetime import timedelta
			instance.next_due_date = (instance.approved_at + timedelta(days=30)).date()
			instance.save()
