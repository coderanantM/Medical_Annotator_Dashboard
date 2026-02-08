# annotations/forms.py
from django import forms
from .models import Annotation  # <-- 1. Import Annotation, NOT Patient

class PatientAnnotationForm(forms.ModelForm):
    
    class Meta:
        model = Annotation  # <-- 2. Change model to Annotation
        
        # These fields are all correct, as they are on the Annotation model
        fields = ['vasculitis_present', 'activity', 'quality', 'comment']
        
        # All your widgets are perfect and can stay the same
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
            'comment': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Add your comments here...'}),
        }
        labels = {
            'quality': 'Image Quality (1-10)'
        }