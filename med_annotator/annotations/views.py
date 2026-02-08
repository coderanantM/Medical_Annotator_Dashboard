import os
import re
from collections import defaultdict

from google.oauth2 import service_account
from googleapiclient.discovery import build

from django.urls import reverse
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from .models import Patient, PatientImage, Annotation, CaseComment
from .forms import PatientAnnotationForm


# ================================
# Constants
# ================================
MAIN_FOLDER_ID = "1_vDh3Oizwndg_9Q7D8yJPjERswzZwocu"
FOLDER_MIME = "application/vnd.google-apps.folder"
STAGE_REGEX = re.compile(r"(early|mid|late)", re.IGNORECASE)


# ================================
# Recursive Google Drive Scanner
# ================================
def fetch_images_recursive(service, folder_id, patient, collected, folder_name=""):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute()

    for f in results.get("files", []):

        # Recurse into subfolders
        if f["mimeType"] == FOLDER_MIME:
            fetch_images_recursive(
                service,
                f["id"],
                patient,
                collected,
                folder_name=f["name"]
            )
            continue

        # Ignore non-images
        if not f["mimeType"].startswith("image/"):
            continue

        # Determine stage
        match = STAGE_REGEX.search(f["name"])
        if match:
            stage = match.group(1).lower()
        else:
            folder_match = STAGE_REGEX.search(folder_name.lower())
            stage = folder_match.group(1).lower() if folder_match else "mid"

        image_url = f"https://lh3.googleusercontent.com/d/{f['id']}"

        collected.append(
            PatientImage(
                patient=patient,
                stage=stage,
                image_url=image_url
            )
        )


# ================================
# Main Annotation View
# ================================
class AnnotationQueueView(LoginRequiredMixin, View):

    # ----------------------------
    # GET
    # ----------------------------
    def get(self, request):

        # Sync from Drive if requested
        if request.GET.get("sync") == "true":
            try:
                self.sync_drive()
                messages.success(request, "Images synced successfully.")
                return redirect("annotation_queue")
            except Exception as e:
                messages.error(request, f"Drive sync failed: {e}")
                return redirect("annotation_queue")

        requested_patient_id = request.GET.get("patient_id")

        # Patients already annotated by this user
        annotated_ids = Annotation.objects.filter(
            user=request.user,
            annotated_at__isnull=False
        ).values_list("patient__patient_id", flat=True)

        # Choose patient
        if requested_patient_id:
            patient = Patient.objects.filter(
                patient_id=requested_patient_id
            ).first()
        else:
            patient = Patient.objects.exclude(
                patient_id__in=annotated_ids
            ).order_by("patient_id").first()

        if not patient:
            return render(
                request,
                "annotation_complete.html",
                {"no_patients": True}
            )

        # Get or create annotation
        annotation, _ = Annotation.objects.get_or_create(
            patient=patient,
            user=request.user
        )

        form = PatientAnnotationForm(instance=annotation)

        # Shared committed comments
        shared_comments = (
            CaseComment.objects
            .filter(patient=patient)
            .select_related("user")
            .order_by("id")
        )


        # Previous user's annotation (read-only reference)
        previous_annotation = Annotation.objects.filter(
            patient=patient
        ).exclude(user=request.user).order_by("-annotated_at").first()

        # Group images by stage
        image_groups = defaultdict(list)
        for img in patient.images.all():
            image_groups[img.stage].append(img)
            
        all_patients = list(
            Patient.objects.order_by("patient_id").values_list("patient_id", flat=True)
        )
        index = all_patients.index(patient.patient_id)
        prev_patient_id = all_patients[index - 1] if index > 0 else None
        next_patient_id = (
            all_patients[index + 1] if index < len(all_patients) - 1 else None
        )

        context = {
            "patient": patient,
            "annotation": annotation,
            "form": form,
            "image_groups": dict(image_groups),
            "stages": ["early", "mid", "late"],
            "shared_comments": shared_comments,
            "previous_annotation": previous_annotation,
            "next_patient_id": next_patient_id,
            "prev_patient_id": prev_patient_id,
        }

        return render(request, "annotation_page.html", context)

    # ----------------------------
    # POST
    # ----------------------------
    def post(self, request):

        annotation_id = request.POST.get("annotation_id")

        annotation = get_object_or_404(
            Annotation,
            id=annotation_id,
            user=request.user
        )

        form = PatientAnnotationForm(
            request.POST,
            instance=annotation
        )

        if not form.is_valid():
            return self.get(request)

        action = request.POST.get("action", "save")

        with transaction.atomic():
            annotation = form.save(commit=False)

            # Submit & Next = final annotation
            if action == "save_and_next":
                annotation.annotated_at = timezone.now()

                comment_text = form.cleaned_data.get("comment")
                if comment_text:
                    CaseComment.objects.create(
                        patient=annotation.patient,
                        user=request.user,
                        comment=comment_text
                    )

            annotation.save()

        messages.success(
            request,
            f"Annotations saved for {annotation.patient.patient_id}"
        )

        # Load next unannotated patient
        if action == "save_and_next":
            annotated_ids = Annotation.objects.filter(
                user=request.user,
                annotated_at__isnull=False
            ).values_list("patient__patient_id", flat=True)

            next_patient = Patient.objects.exclude(
                patient_id__in=annotated_ids
            ).order_by("patient_id").first()

            if next_patient:
                return redirect(
                    f"{reverse('annotation_queue')}?patient_id={next_patient.patient_id}"
                )

            messages.success(request, "All patients annotated.")
            return redirect("annotation_queue")

        # Just save
        return redirect(
            f"{reverse('annotation_queue')}?patient_id={annotation.patient.patient_id}"
        )

    # ----------------------------
    # Google Drive Sync
    # ----------------------------
    def sync_drive(self):

        SERVICE_ACCOUNT_FILE = os.path.join(
            settings.BASE_DIR,
            "service-account.json"
        )

        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )

        service = build("drive", "v3", credentials=credentials)

        results = service.files().list(
            q=f"'{MAIN_FOLDER_ID}' in parents and mimeType='{FOLDER_MIME}'",
            fields="files(id, name)"
        ).execute()

        folders = results.get("files", [])

        folders.sort(
            key=lambda x: [
                int(t) if t.isdigit() else t
                for t in re.split(r"(\d+)", x["name"])
            ]
        )

        for folder in folders:
            patient_id = folder["name"].strip().upper()
            patient, _ = Patient.objects.get_or_create(
                patient_id=patient_id
            )

            collected = []
            fetch_images_recursive(
                service,
                folder["id"],
                patient,
                collected,
                folder_name=folder["name"]
            )

            with transaction.atomic():
                PatientImage.objects.filter(
                    patient=patient
                ).delete()
                PatientImage.objects.bulk_create(collected)

            print(
                f"[SYNC] {patient_id}: {len(collected)} images"
            )
