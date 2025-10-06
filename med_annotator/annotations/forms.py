# annotations/forms.py
from django import forms

class PatientDetailsForm(forms.Form):
    """A form to capture only the patient's personal details."""
    patient_id = forms.CharField(label="Patient ID", max_length=100)
    full_name = forms.CharField(label="Full Name", max_length=200)
    date_of_birth = forms.DateField(
        label="Date of Birth", 
        required=False, 
        widget=forms.DateInput(attrs={'type': 'date'})
    )

class LocalUploadForm(forms.Form):
    """A form specifically for uploading the three image files locally."""
    early_image = forms.ImageField(label="Early Stage Image")
    mid_image = forms.ImageField(label="Mid Stage Image")
    late_image = forms.ImageField(label="Late Stage Image")