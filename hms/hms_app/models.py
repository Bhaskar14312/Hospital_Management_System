from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('DOCTOR', 'Doctor'),
        ('PATIENT', 'Patient'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='PATIENT')

    def is_doctor(self):
        return self.role == 'DOCTOR'

    def is_patient(self):
        return self.role == 'PATIENT'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class AvailabilitySlot(models.Model):
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='availability_slots',
        limit_choices_to={'role': 'DOCTOR'}
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_booked = models.BooleanField(default=False)

    class Meta:
        ordering = ['date', 'start_time']
        unique_together = ('doctor', 'date', 'start_time', 'end_time')

    def __str__(self):
        return f"Dr. {self.doctor.username} | {self.date} | {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"


class Booking(models.Model):
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings',
        limit_choices_to={'role': 'PATIENT'}
    )
    # Using OneToOneField ensures that a slot can never be booked twice (database-level constraint)
    slot = models.OneToOneField(
        AvailabilitySlot,
        on_delete=models.CASCADE,
        related_name='booking'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Store Google Calendar Event IDs for sync status and cleanup if cancelled
    google_event_id_doctor = models.CharField(max_length=255, blank=True, null=True)
    google_event_id_patient = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Booking: {self.patient.username} with Dr. {self.slot.doctor.username} on {self.slot.date}"


class GoogleAuthToken(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_auth'
    )
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"GoogleAuthToken for {self.user.username}"
