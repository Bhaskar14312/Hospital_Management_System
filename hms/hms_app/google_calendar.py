import os
import requests
from django.utils import timezone
from datetime import datetime, timedelta
from django.conf import settings
from .models import GoogleAuthToken

# Load Google Client Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# Default local redirect URI
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/google/callback/")

def is_google_configured():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

def get_google_auth_url():
    """Generate Google Auth URL to redirect the user to Google OAuth2 consent screen."""
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar.events",
        "access_type": "offline",
        "prompt": "consent",  # Force to get refresh token
    }
    encoded_params = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{encoded_params}"

def exchange_code_for_tokens(user, code):
    """Exchange OAuth code for access and refresh tokens, and store them."""
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    
    response = requests.post(token_url, data=payload)
    if response.status_code != 200:
        raise Exception(f"Failed to exchange code: {response.text}")
        
    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in", 3600)
    
    expires_at = timezone.now() + timedelta(seconds=expires_in)
    
    # Save token for the user
    token_obj, created = GoogleAuthToken.objects.get_or_create(user=user)
    token_obj.access_token = access_token
    if refresh_token:
        token_obj.refresh_token = refresh_token
    token_obj.expires_at = expires_at
    token_obj.save()
    
    return token_obj

def get_valid_access_token(user):
    """Retrieve a valid access token for the user, refreshing it if expired."""
    try:
        token_obj = GoogleAuthToken.objects.get(user=user)
    except GoogleAuthToken.DoesNotExist:
        return None
        
    # Check if expired (with 1 minute buffer)
    if token_obj.expires_at <= timezone.now() + timedelta(minutes=1):
        if not token_obj.refresh_token:
            return None # Can't refresh without refresh token
            
        # Refresh the token
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": token_obj.refresh_token,
            "grant_type": "refresh_token",
        }
        
        response = requests.post(token_url, data=payload)
        if response.status_code == 200:
            data = response.json()
            token_obj.access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            token_obj.expires_at = timezone.now() + timedelta(seconds=expires_in)
            token_obj.save()
        else:
            # Token might be revoked or invalid
            return None
            
    return token_obj.access_token

def create_event(user, summary, date_obj, start_time, end_time, description=""):
    """Helper to create a single Google Calendar event for a user."""
    access_token = get_valid_access_token(user)
    if not access_token:
        print(f"No Google Calendar credentials for user {user.username}")
        return None
        
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    # Combine date and time to ISO format (assume local timezone or UTC)
    # SQLite/Django Date/Time objects
    start_dt = datetime.combine(date_obj, start_time)
    end_dt = datetime.combine(date_obj, end_time)
    
    # Format: YYYY-MM-DDTHH:MM:SS
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()
    
    event_body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_iso,
            # We use UTC or local timezone of system. Since it runs locally, let's use the local timezone offset or let Google handle it.
            # Usually, adding 'Z' or local timezone info is good. Let's make it standard: timezone.get_current_timezone().name
            "timeZone": settings.TIME_ZONE,
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": settings.TIME_ZONE,
        }
    }
    
    response = requests.post(url, json=event_body, headers=headers)
    if response.status_code == 200:
        return response.json().get("id")
    else:
        print(f"Failed to create Google Calendar event for {user.username}: {response.text}")
        return None

def sync_booking_to_google_calendars(booking):
    """Sync the booking to Google Calendar for both the Doctor and Patient if they have authorized."""
    if not is_google_configured():
        return
        
    doctor = booking.slot.doctor
    patient = booking.patient
    slot = booking.slot
    
    # 1. Create event on Doctor's Calendar
    doctor_summary = f"Appointment with {patient.get_full_name() or patient.username}"
    desc = f"HMS Appointment booking ID: {booking.id}. Confirmed via Banao HMS."
    
    doc_event_id = create_event(
        user=doctor,
        summary=doctor_summary,
        date_obj=slot.date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        description=desc
    )
    if doc_event_id:
        booking.google_event_id_doctor = doc_event_id
        
    # 2. Create event on Patient's Calendar
    patient_summary = f"Appointment with Dr. {doctor.get_full_name() or doctor.username}"
    pat_event_id = create_event(
        user=patient,
        summary=patient_summary,
        date_obj=slot.date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        description=desc
    )
    if pat_event_id:
        booking.google_event_id_patient = pat_event_id
        
    if doc_event_id or pat_event_id:
        booking.save()
