# annotations/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from .views import SignUpView, DashboardView, AnnotationView, PatientProfileView, PatientDetailsView, UploadChoiceView, LocalUploadView

urlpatterns = [
    # Authentication URLs
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/signup/', SignUpView.as_view(), name='signup'),

    # Application URLs
    path('', DashboardView.as_view(), name='dashboard'),
    path('annotate/patient/<int:patient_id>/', AnnotationView.as_view(), name='annotate'),
    
    path('patient/<int:patient_id>/profile/', PatientProfileView.as_view(), name='patient_profile'),
    
    path('patient/create/details/', PatientDetailsView.as_view(), name='patient_create_details'),

    # Step 2: Choose upload method
    path('patient/create/choose-method/', UploadChoiceView.as_view(), name='patient_choose_method'),

    # Step 3a: The view for local uploads
    path('patient/create/upload-local/', LocalUploadView.as_view(), name='patient_upload_local'),

]