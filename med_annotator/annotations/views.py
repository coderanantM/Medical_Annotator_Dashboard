# annotations/views.py
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import googleapiclient.discovery
import googleapiclient.errors

# --- NEW IMPORTS FOR SERVICE ACCOUNT ---
from google.oauth2 import service_account
from googleapiclient.discovery import build
# --- END NEW IMPORTS ---

from .models import Patient, PatientImage
from .forms import PatientAnnotationForm

# (This is the new view from our previous conversation)
class AnnotationQueueView(LoginRequiredMixin, View):
    
    def get(self, request):
        # Check if a specific patient is requested (for next/prev buttons)
        requested_patient_id = request.GET.get('patient_id')
        
        if requested_patient_id:
            next_patient = Patient.objects.filter(patient_id=requested_patient_id).first()
        else:
            # 1. Find the first unannotated patient
            next_patient = Patient.objects.filter(is_annotated=False).order_by('patient_id').first()
        
        if not next_patient:
            # 2. If no patient, try to sync
            try:
                self.sync_drive(request)
            except Exception as e:
                messages.error(request, f"Error during sync: {e}")
                return render(request, 'annotation_complete.html')

            # 3. After syncing, try finding a patient again
            next_patient = Patient.objects.filter(is_annotated=False).order_by('patient_id').first()
            
            if not next_patient:
                # 4. If still no patient, all work is done
                messages.success(request, "All patients have been annotated. Sync to find more.")
                return render(request, 'annotation_complete.html')

        # 5. We have a patient. Prepare the page.
        patient = next_patient
        images = patient.images.order_by('stage')
        form = PatientAnnotationForm(instance=patient)
        
        # 6. Find "Previous" and "Next" patients for navigation
        prev_patient = Patient.objects.filter(patient_id__lt=patient.patient_id).order_by('patient_id').last()
        next_patient = Patient.objects.filter(patient_id__gt=patient.patient_id).order_by('patient_id').first()

        context = {
            'patient': patient,
            'images': images,
            'form': form,
            'prev_patient_id': prev_patient.patient_id if prev_patient else None,
            'next_patient_id': next_patient.patient_id if next_patient else None,
        }
        return render(request, 'annotation_page.html', context)

    def post(self, request):
        patient_id = request.POST.get('patient_id')
        patient = get_object_or_404(Patient, patient_id=patient_id)
        form = PatientAnnotationForm(request.POST, instance=patient)
        
        if form.is_valid():
            annotated_patient = form.save(commit=False)
            annotated_patient.is_annotated = True 
            annotated_patient.save()
            messages.success(request, f"Annotations for {patient.patient_id} saved.")
        else:
            messages.error(request, "There was an error saving the form.")

        return redirect('annotation_queue')


    # --- THIS IS THE NEW SYNC FUNCTION ---
    def sync_drive(self, request):
        MAIN_FOLDER_ID = "1_vDh3Oizwndg_9Q7D8yJPjERswzZwocu"
        FILENAME_REGEX = re.compile(r'(early|mid|late)', re.IGNORECASE)

        try:
            # 1. Authenticate using the Service Account JSON file
            SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
            SERVICE_ACCOUNT_FILE = os.path.join(settings.BASE_DIR, 'service-account.json')
            if not os.path.exists(SERVICE_ACCOUNT_FILE):
                raise FileNotFoundError("Service Account key file not found. Make sure 'service-account.json' is in your project root.")

            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )

            # Use googleapiclient.discovery.build directly (not from googleapiclient.discovery import build)
            service = googleapiclient.discovery.build('drive', 'v3', credentials=credentials)

            # 2. Find all sub-folders (C7, C11, etc.)
            folder_query = f"'{MAIN_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder'"
            results = service.files().list(q=folder_query, fields="files(id, name)").execute()
            patient_folders = results.get('files', [])

            if not patient_folders:
                messages.warning(request, "No patient folders found. Did you share the folder with the service account?")
                return

            new_patients_created = 0

            # 3. Process each folder
            with transaction.atomic():
                for folder in patient_folders:
                    patient_id = folder['name'].upper()
                    folder_id = folder['id']

                    if Patient.objects.filter(patient_id=patient_id).exists():
                        continue

                    # 4. Find files inside the folder
                    file_query = f"'{folder_id}' in parents"
                    file_results = service.files().list(q=file_query, fields="files(id, name)").execute()
                    files_in_folder = file_results.get('files', [])

                    stages = {}
                    for file in files_in_folder:
                        match = FILENAME_REGEX.search(file['name'])
                        if match:
                            stages[match.group(1).lower()] = file['id']

                    # 5. Create patient if all 3 stages are found
                    if 'early' in stages and 'mid' in stages and 'late' in stages:
                        patient = Patient.objects.create(patient_id=patient_id)
                        new_patients_created += 1

                        PatientImage.objects.create(patient=patient, stage='early', image_url=self.get_drive_link(stages['early']))
                        PatientImage.objects.create(patient=patient, stage='mid', image_url=self.get_drive_link(stages['mid']))
                        PatientImage.objects.create(patient=patient, stage='late', image_url=self.get_drive_link(stages['late']))

            if new_patients_created > 0:
                messages.success(request, f"Sync complete. Found {new_patients_created} new patients.")
            else:
                messages.info(request, "Sync complete. No new patients found.")

        except FileNotFoundError as fnf:
            raise Exception(str(fnf))
        except googleapiclient.errors.HttpError as api_error:
            raise Exception(f"Google API error: {api_error}")
        except Exception as e:
            raise Exception(f"An error occurred: {e}")

    def get_drive_link(self, file_id):
        return f'https://drive.google.com/thumbnail?id={file_id}&sz=w1000'