from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

# Create your models here.
class Patient(models.Model):
    patient_id = models.CharField(max_length=100, unique=True, help_text="Unique identifier for the patient")
    date_of_birth = models.DateField(null=True, blank=True)
    full_name = models.CharField(max_length=200, default="N/A")
    date_registered = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.full_name} ({self.patient_id})"
    
class PatientImage(models.Model):
    STAGE_CHOICES = [
        ('early', 'Early'),
        ('mid', 'Mid'),
        ('late', 'Late'),
    ]
    ACTIVITY_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='patient_images/')  
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
    
    vasculitis_present = models.BooleanField(default=False, verbose_name = "Vasculitis Present")
    activity = models.CharField(max_length=10, choices=ACTIVITY_CHOICES, blank=True, verbose_name="Active/Inactive")
    quality = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        default = 0,
        verbose_name="Quality (0-10)"
    )
    
    class Meta:
        unique_together = ('patient', 'stage')
    
    def __str__(self):
        return f"{self.patient.patient_id} - {self.get_stage_display()}"
