# annotations/forms.py
from django import forms
from .models import Patient

class PatientAnnotationForm(forms.ModelForm):
    
    class Meta:
        model = Patient
        fields = ['vasculitis_present', 'activity', 'quality']
        widgets = {
            'vasculitis_present': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'activity': forms.Select(attrs={'class': 'form-select'}),
            'quality': forms.NumberInput(
                attrs={
                    'type': 'range', 
                    'class': 'form-range', 
                    'min': '1', 
                    'max': '10', 
                    'step': '1'
                }
            ),
        }
        labels = {
            'quality': 'Image Quality (1-10)'
        }