from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings ## --- ADDED: To link to the User model ---

## --- This is unchanged ---
ACTIVITY_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
    ('unknown', 'Unknown'),
]

# -----------------------------------------------------------------
# MODEL 1: THE PATIENT
# This model now ONLY stores patient-specific data.
# All annotation fields have been REMOVED.
# -----------------------------------------------------------------
class Patient(models.Model):
    
    patient_id = models.CharField(max_length=50, unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    ## --- REMOVED ---
    # vasculitis_present, activity, quality, and is_annotated
    # have all been REMOVED from this model.

    def __str__(self):
        return self.patient_id

# -----------------------------------------------------------------
# MODEL 2: THE PATIENT IMAGE
# This model is unchanged. It correctly links images to a Patient.
# -----------------------------------------------------------------
class PatientImage(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='images')
    
    STAGE_CHOICES = [
        ('early', 'Early'),
        ('mid', 'Mid'),
        ('late', 'Late'),
    ]
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
    
    image_url = models.URLField(max_length=500)
    
    class Meta:
        unique_together = ('patient', 'stage')

    def __str__(self):
        return f"{self.patient.patient_id} - {self.stage}"

# -----------------------------------------------------------------
# MODEL 3: THE ANNOTATION (NEW!)
# This is the new, most important model.
# It links a User to a Patient and stores their work.
# -----------------------------------------------------------------
class Annotation(models.Model):
    # Link to the User who made this annotation
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='annotations'
    )
    
    # Link to the Patient being annotated
    patient = models.ForeignKey(
        Patient, 
        on_delete=models.CASCADE,
        related_name='annotations'
    )
    
    # --- All the form fields are now stored HERE ---
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
    
    # This field updates every time the user saves
    annotated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ## This is CRITICAL. It ensures one user can only
        ## have ONE annotation for each patient.
        unique_together = ('user', 'patient')

    def __str__(self):
        return f"Annotation for {self.patient.patient_id} by {self.user.username}"