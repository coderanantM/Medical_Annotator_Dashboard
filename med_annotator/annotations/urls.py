# annotations/urls.py
from django.urls import path
from .views import AnnotationQueueView

urlpatterns = [
    # The main homepage is now the annotation queue
    path('', AnnotationQueueView.as_view(), name='annotation_queue'),
    
    # We also need a POST URL for the form submission
    path('save_annotation/', AnnotationQueueView.as_view(), name='save_annotation'),
]