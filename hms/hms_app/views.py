import threading
import requests
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import datetime

from .models import CustomUser, AvailabilitySlot, Booking, GoogleAuthToken
from .forms import CustomUserCreationForm
from .decorators import doctor_required, patient_required
from .google_calendar import (
    get_google_auth_url,
    exchange_code_for_tokens,
    sync_booking_to_google_calendars,
    is_google_configured
)

# Background email dispatcher helper
def send_email_async(payload):
    # serverless-offline default address
    url = "http://localhost:3000/dev/send-email"
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=5)
        print(f"[EMAIL SERVICE RESPONSE] Status: {response.status_code}, Body: {response.text}")
    except Exception as e:
        print(f"[EMAIL SERVICE ERROR] Could not connect to Serverless service: {str(e)}")

def trigger_email(payload):
    thread = threading.Thread(target=send_email_async, args=(payload,))
    thread.daemon = True
    thread.start()

# Auth Views
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.username}! Your account has been created.")
            
            # Send welcome email trigger via Serverless
            trigger_email({
                "trigger": "SIGNUP_WELCOME",
                "email": user.email,
                "name": f"{user.first_name} {user.last_name}".strip() or user.username
            })
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'hms_app/signup.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {username}!")
                return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'hms_app/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('login')

# Dashboard routing
@login_required
def dashboard_view(request):
    if request.user.is_doctor():
        return redirect('doctor_dashboard')
    else:
        return redirect('patient_dashboard')

# Doctor Views
@login_required
@doctor_required
def doctor_dashboard_view(request):
    slots = AvailabilitySlot.objects.filter(doctor=request.user).order_by('date', 'start_time')
    
    # Check if Google Calendar is authorized for the doctor
    is_connected = GoogleAuthToken.objects.filter(user=request.user).exists()
    google_configured = is_google_configured()
    
    context = {
        'slots': slots,
        'is_google_connected': is_connected,
        'google_configured': google_configured,
    }
    return render(request, 'hms_app/doctor_dashboard.html', context)

@login_required
@doctor_required
def create_slot_view(request):
    if request.method == 'POST':
        date_str = request.POST.get('date')
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time')

        if not date_str or not start_time_str or not end_time_str:
            messages.error(request, "Please fill in all date and time fields.")
            return redirect('doctor_dashboard')

        try:
            date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_time_val = datetime.strptime(start_time_str, '%H:%M').time()
            end_time_val = datetime.strptime(end_time_str, '%H:%M').time()

            if start_time_val >= end_time_val:
                messages.error(request, "Start time must be before end time.")
                return redirect('doctor_dashboard')

            if date_val < timezone.now().date():
                messages.error(request, "Cannot create availability slot in the past.")
                return redirect('doctor_dashboard')

            # Save slot
            AvailabilitySlot.objects.create(
                doctor=request.user,
                date=date_val,
                start_time=start_time_val,
                end_time=end_time_val
            )
            messages.success(request, "Availability slot created successfully!")
        except Exception as e:
            # Handle unique constraint or formatting issues
            messages.error(request, f"Could not create slot: {str(e)}")
            
    return redirect('doctor_dashboard')

# Patient Views
@login_required
@patient_required
def patient_dashboard_view(request):
    # Fetch patient's bookings
    bookings = Booking.objects.filter(patient=request.user).order_by('slot__date', 'slot__start_time')
    
    # Fetch all doctors list
    doctors = CustomUser.objects.filter(role='DOCTOR')
    
    # Filter available future slots
    selected_doctor_id = request.GET.get('doctor_id')
    available_slots = AvailabilitySlot.objects.filter(
        is_booked=False,
        date__gte=timezone.now().date()
    )
    
    # Exclude past slots if date is today but start time is in past
    # Filter them in memory or with dynamic Django filters. Let's filter in python for simplicity.
    now = timezone.now()
    valid_slots = []
    for s in available_slots:
        slot_dt = timezone.make_aware(datetime.combine(s.date, s.start_time))
        if slot_dt > now:
            if not selected_doctor_id or s.doctor_id == int(selected_doctor_id):
                valid_slots.append(s)

    is_connected = GoogleAuthToken.objects.filter(user=request.user).exists()
    google_configured = is_google_configured()

    context = {
        'bookings': bookings,
        'doctors': doctors,
        'available_slots': valid_slots,
        'selected_doctor_id': selected_doctor_id,
        'is_google_connected': is_connected,
        'google_configured': google_configured,
    }
    return render(request, 'hms_app/patient_dashboard.html', context)

@login_required
@patient_required
def book_slot_view(request, slot_id):
    if request.method == 'POST':
        try:
            # Atomic transaction to handle simultaneous bookings (race condition)
            with transaction.atomic():
                # Lock the row for update. If another request is currently updating this slot,
                # Django will block until the transaction is completed.
                slot = AvailabilitySlot.objects.select_for_update().get(id=slot_id)
                
                # Check if it was already booked in the meantime
                if slot.is_booked:
                    messages.error(request, "This slot has already been booked by another patient.")
                    return redirect('patient_dashboard')
                
                # Verify date/time is still future
                slot_dt = timezone.make_aware(datetime.combine(slot.date, slot.start_time))
                if slot_dt <= timezone.now():
                    messages.error(request, "Cannot book a slot that has already passed.")
                    return redirect('patient_dashboard')

                # Perform booking
                slot.is_booked = True
                slot.save()
                
                booking = Booking.objects.create(
                    patient=request.user,
                    slot=slot
                )

                # Sync to Google Calendars in background thread so it doesn't slow down the page reload
                threading.Thread(target=sync_booking_to_google_calendars, args=(booking,)).start()

                # Dispatch welcome email trigger asynchronously
                trigger_email({
                    "trigger": "BOOKING_CONFIRMATION",
                    "doctor_email": slot.doctor.email,
                    "doctor_name": slot.doctor.get_full_name() or slot.doctor.username,
                    "patient_email": request.user.email,
                    "patient_name": request.user.get_full_name() or request.user.username,
                    "slot_details": f"{slot.date} at {slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}"
                })

                messages.success(request, f"Successfully booked appointment with Dr. {slot.doctor.get_full_name() or slot.doctor.username}!")
                
        except AvailabilitySlot.DoesNotExist:
            messages.error(request, "Selected slot does not exist.")
        except Exception as e:
            messages.error(request, f"Booking failed: {str(e)}")
            
    return redirect('patient_dashboard')

# Google OAuth Views
@login_required
def connect_google_calendar_view(request):
    if not is_google_configured():
        messages.error(request, "Google OAuth Credentials are not configured by the system administrator.")
        return redirect('dashboard')
    auth_url = get_google_auth_url()
    return redirect(auth_url)

@login_required
def google_oauth_callback_view(request):
    code = request.GET.get('code')
    error = request.GET.get('error')
    
    if error:
        messages.error(request, f"Google authorization failed: {error}")
        return redirect('dashboard')
        
    if code:
        try:
            exchange_code_for_tokens(request.user, code)
            messages.success(request, "Successfully connected to your Google Calendar!")
        except Exception as e:
            messages.error(request, f"Failed to authenticate with Google: {str(e)}")
            
    return redirect('dashboard')

@login_required
def disconnect_google_calendar_view(request):
    GoogleAuthToken.objects.filter(user=request.user).delete()
    messages.success(request, "Disconnected from Google Calendar.")
    return redirect('dashboard')
