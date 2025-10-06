import io
from allauth.socialaccount.models import SocialToken
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from django.core.files.base import ContentFile
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Patient, PatientImage
from .forms import PatientDetailsForm, LocalUploadForm
from django.db import transaction

# Create your views here.
class SignUpView(CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'
    
class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        patients = Patient.objects.all()
        return render(request, 'dashboard.html', {'patients': patients})
    
class AnnotationView(LoginRequiredMixin, View):
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        images = patient.images.order_by('id')
        
        next_patient = Patient.objects.filter(id__gt=patient.id).order_by('id').first()
        prev_patient = Patient.objects.filter(id__lt=patient.id).order_by('-id').first()
        
        context = {
            'patient': patient,
            'images': images,
            'next_patient_id': next_patient.id if next_patient else None,
            'prev_patient_id': prev_patient.id if prev_patient else None,
        }
        return render(request, 'annotation_page.html', context)
    
    def post(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        
        
        for image in patient.images.all():
            prefix = f'image_{image.id}'
            
            
            image.vasculitis_present = request.POST.get(f'{prefix}_vasculitis') == 'on'
            image.activity = request.POST.get(f'{prefix}_activity')
            image.quality = request.POST.get(f'{prefix}_quality')
            image.save()
            
        return redirect('annotate', patient_id=patient.id)
    
    
class PatientProfileView(LoginRequiredMixin, View):
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        return render(request, 'patient_profile.html', {'patient': patient})
    
# annotations/views.py
class PatientDetailsView(LoginRequiredMixin, View):
    def get(self, request):
        form = PatientDetailsForm()
        return render(request, 'patient_create_details.html', {'form': form})

    def post(self, request):
        form = PatientDetailsForm(request.POST)
        if form.is_valid():
            request.session['new_patient_data'] = {
                'patient_id': form.cleaned_data['patient_id'],
                'full_name': form.cleaned_data['full_name'],
                'date_of_birth': form.cleaned_data['date_of_birth'].isoformat() if form.cleaned_data['date_of_birth'] else None,
            }
            return redirect('patient_choose_method')
        return render(request, 'patient_create_details.html', {'form': form})

class UploadChoiceView(LoginRequiredMixin, View):
    def get(self, request):
        if 'new_patient_data' not in request.session:
            return redirect('patient_create_details')
        return render(request, 'patient_choose_method.html')
    
class LocalUploadView(LoginRequiredMixin, View):
    def get(self, request):
        if 'new_patient_data' not in request.session:
            return redirect('patient_create_details')
        form = LocalUploadForm()
        return render(request, 'patient_upload_local.html', {'form': form})
    
    def post(self, request):
        form = LocalUploadForm(request.POST, request.FILES)
        patient_data = request.session.get('new_patient_data')
        
        if form.is_valid() and patient_data:
            with transaction.atomic():
                patient = Patient.objects.create(**patient_data)
                
                PatientImage.objects.create(
                    patient=patient,
                    stage='early',
                    image=form.cleaned_data['early_image']
                )
                
                PatientImage.objects.create(
                    patient=patient,
                    stage='mid',
                    image=form.cleaned_data['mid_image']
                )
                
                PatientImage.objects.create(
                    patient=patient,
                    stage='late',
                    image=form.cleaned_data['late_image']
                )
                
            del request.session['new_patient_data']
            return redirect('dashboard')
        
        return render(request, 'patient_upload_local.html', {'form': form})
    
