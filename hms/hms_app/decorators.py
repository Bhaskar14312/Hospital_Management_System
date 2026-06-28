from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

def doctor_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_doctor():
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only doctors are allowed to access this page.")
    return _wrapped_view

def patient_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_patient():
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only patients are allowed to access this page.")
    return _wrapped_view
