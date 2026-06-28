from django.test import TransactionTestCase
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
import datetime
import threading
import time

from .models import AvailabilitySlot, Booking

User = get_user_model()

class HMSIntegrationTests(TransactionTestCase):
    def setUp(self):
        # Create users
        self.doctor = User.objects.create_user(
            username="testdoctor",
            password="password123",
            role="DOCTOR",
            email="doctor@test.com"
        )
        self.patient1 = User.objects.create_user(
            username="patient1",
            password="password123",
            role="PATIENT",
            email="patient1@test.com"
        )
        self.patient2 = User.objects.create_user(
            username="patient2",
            password="password123",
            role="PATIENT",
            email="patient2@test.com"
        )

        # Create slot in future
        self.slot = AvailabilitySlot.objects.create(
            doctor=self.doctor,
            date=timezone.now().date() + datetime.timedelta(days=1),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0)
        )

    def test_user_roles(self):
        """Test user role methods and limits."""
        self.assertTrue(self.doctor.is_doctor())
        self.assertFalse(self.doctor.is_patient())
        self.assertTrue(self.patient1.is_patient())
        self.assertFalse(self.patient1.is_doctor())

    def test_single_booking(self):
        """Test that booking a slot succeeds and marks it booked."""
        # Check slot state
        self.assertFalse(self.slot.is_booked)
        
        # Book slot
        booking = Booking.objects.create(patient=self.patient1, slot=self.slot)
        self.slot.is_booked = True
        self.slot.save()

        self.assertTrue(AvailabilitySlot.objects.get(id=self.slot.id).is_booked)
        self.assertEqual(Booking.objects.filter(slot=self.slot).count(), 1)

    def test_race_condition_double_booking(self):
        """Simulate two patients booking the same slot simultaneously to verify select_for_update / transaction lock works."""
        results = []
        errors = []

        def book_slot_thread(patient, slot_id):
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        slot = AvailabilitySlot.objects.select_for_update().get(id=slot_id)
                        time.sleep(0.2) # Sleep briefly to simulate transaction overlap
                        if slot.is_booked:
                            return
                        
                        slot.is_booked = True
                        slot.save()
                        Booking.objects.create(patient=patient, slot=slot)
                        results.append(patient.username)
                        return
                except Exception as e:
                    # If database is locked, sleep and retry
                    if "locked" in str(e).lower() and attempt < max_retries - 1:
                        time.sleep(0.2)
                        continue
                    errors.append(f"{patient.username}: Error: {str(e)}")
                    return

        # Launch two threads
        t1 = threading.Thread(target=book_slot_thread, args=(self.patient1, self.slot.id))
        t2 = threading.Thread(target=book_slot_thread, args=(self.patient2, self.slot.id))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # Check outcomes: only one booking should succeed
        bookings = Booking.objects.filter(slot=self.slot)
        
        # Verify database level consistency
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(len(results), 1) # Only one thread succeeded
        self.assertTrue(AvailabilitySlot.objects.get(id=self.slot.id).is_booked)
