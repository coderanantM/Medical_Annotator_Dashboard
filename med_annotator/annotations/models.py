from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings 

ACTIVITY_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
    ('unknown', 'Unknown'),
]

class Patient(models.Model):
    patient_id = models.CharField(max_length=50, unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.patient_id

class PatientImage(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='images')
    
    STAGE_CHOICES = [
        ('early', 'Early'),
        ('mid', 'Mid'),
        ('late', 'Late'),
    ]
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
    image_url = models.URLField(max_length=500)
    
    # --- CRITICAL FIX: REMOVED unique_together ---
    # This allows multiple 'late' images for a single patient (e.g., C108)
    class Meta:
        # unique_together = ('patient', 'stage')  <-- REMOVE THIS LINE
        pass

    def __str__(self):
        return f"{self.patient.patient_id} - {self.stage}"

class Annotation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='annotations'
    )
    comment = models.TextField(blank=True, null=True)
    patient = models.ForeignKey(
        Patient, 
        on_delete=models.CASCADE,
        related_name='annotations'
    )
    vasculitis_present = models.BooleanField(default=False)
    activity = models.CharField(
        max_length=100, 
        blank=True, null=True, 
        choices=ACTIVITY_CHOICES
    )
    quality = models.IntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Image quality on a scale of 1 (Poor) to 10 (Good)"
    )
    annotated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'patient')

    def __str__(self):
        return f"Annotation for {self.patient.patient_id} by {self.user.username}"
    
# models.py
class CaseComment(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
