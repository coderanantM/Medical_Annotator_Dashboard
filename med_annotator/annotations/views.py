# annotations/views.py
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
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

from .models import Patient, PatientImage, Annotation
from .forms import PatientAnnotationForm

# (This is the new view from our previous conversation)
class AnnotationQueueView(LoginRequiredMixin, View):
    
    def get(self, request):
        # 1. Run the sync if the database is empty (for first-time setup)
        if Patient.objects.count() == 0:
            try:
                self.sync_drive(request)
            except Exception as e:
                messages.error(request, f"Error during sync: {e}")
                return render(request, 'annotation_complete.html')

        # --- NEW PER-USER LOGIC ---
        
        # 2. Get the patient to show.
        #    Did the user click a "Next/Prev" button?
        requested_patient_id_str = request.GET.get('patient_id')
        
        patient_to_load = None
        
        if requested_patient_id_str:
            # If yes, load that specific patient
            patient_to_load = Patient.objects.filter(patient_id=requested_patient_id_str).first()
        else:
            # If no, find the *next patient this user hasn't annotated*
            
            # Get Patient IDs this user *has* touched
            annotated_patient_pks = Annotation.objects.filter(
                user=request.user
            ).values_list('patient_id', flat=True)
            
            # Find the first patient that is NOT in that list
            patient_to_load = Patient.objects.exclude(
                pk__in=annotated_patient_pks
            ).order_by('patient_id').first()

            if not patient_to_load:
                # User has annotated everything.
                # Just show a "complete" message.
                messages.success(request, "You have annotated all available patients.")
                return render(request, 'annotation_complete.html')

        if not patient_to_load:
            # This should only happen if sync returns 0 patients
            messages.error(request, "No patients found in the database.")
            return render(request, 'annotation_complete.html')

        # 3. --- THIS IS THE MAGIC ---
        #    We have a patient. Now get (or create) this user's
        #    personal annotation for it.
        annotation, created = Annotation.objects.get_or_create(
            user=request.user,
            patient=patient_to_load,
            # 'defaults' can be used to set initial values if you want
            # defaults={'quality': 5} 
        )

        # 4. Prepare the context for the template
        form = PatientAnnotationForm(instance=annotation)
        images = patient_to_load.images.order_by('stage')
        
        # For Next/Prev buttons
        prev_patient = Patient.objects.filter(patient_id__lt=patient_to_load.patient_id).order_by('-patient_id').first()
        next_patient = Patient.objects.filter(patient_id__gt=patient_to_load.patient_id).order_by('patient_id').first()

        context = {
            'patient': patient_to_load, # The patient (for images, ID)
            'annotation': annotation, # The user's specific work (for the form)
            'images': images,
            'form': form,
            'prev_patient_id': prev_patient.patient_id if prev_patient else None,
            'next_patient_id': next_patient.patient_id if next_patient else None,
        }
        return render(request, 'annotation_page.html', context)


    def post(self, request):
        # This logic now saves an ANNOTATION, not a Patient
        
        # Get the hidden Annotation ID from the form
        annotation_id = request.POST.get('annotation_id')
        
        # Find *this user's* annotation.
        # This is a security check so a user can't edit someone else's work.
        annotation = get_object_or_404(
            Annotation, 
            id=annotation_id, 
            user=request.user
        )
        
        form = PatientAnnotationForm(request.POST, instance=annotation)
        
        if form.is_valid():
            form.save() # This updates the user's existing annotation
            messages.success(request, f"Annotations for {annotation.patient.patient_id} saved.")

            action = request.POST.get('action', 'save')
            if action == 'save_and_next':
                # Find the next *un-annotated* patient
                annotated_patient_pks = Annotation.objects.filter(
                    user=request.user
                ).values_list('patient_id', flat=True)
                
                next_patient_to_load = Patient.objects.exclude(
                    pk__in=annotated_patient_pks
                ).order_by('patient_id').first()

                if next_patient_to_load:
                    # Send them to the next patient's page
                    redirect_url = f"{reverse('annotation_queue')}?patient_id={next_patient_to_load.patient_id}"
                    return redirect(redirect_url)
                else:
                    # They are done, send to "complete" page
                    messages.success(request, "All patients annotated!")
                    return redirect('annotation_queue')
            else:
                # User clicked "Save", just reload the same patient page
                redirect_url = f"{reverse('annotation_queue')}?patient_id={annotation.patient.patient_id}"
                return redirect(redirect_url)
        else:
            # Form was invalid, re-render the page with errors
            patient = annotation.patient
            images = patient.images.order_by('stage')
            prev_patient = Patient.objects.filter(patient_id__lt=patient.patient_id).order_by('-patient_id').first()
            next_patient = Patient.objects.filter(patient_id__gt=patient.patient_id).order_by('patient_id').first()
            context = {
                'patient': patient,
                'annotation': annotation,
                'images': images,
                'form': form, # The invalid form with errors
                'prev_patient_id': prev_patient.patient_id if prev_patient else None,
                'next_patient_id': next_patient.patient_id if next_patient else None,
            }
            return render(request, 'annotation_page.html', context)


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