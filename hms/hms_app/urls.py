from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('doctor/', views.doctor_dashboard_view, name='doctor_dashboard'),
    path('doctor/create-slot/', views.create_slot_view, name='create_slot'),
    path('patient/', views.patient_dashboard_view, name='patient_dashboard'),
    path('patient/book-slot/<int:slot_id>/', views.book_slot_view, name='book_slot'),
    path('google/connect/', views.connect_google_calendar_view, name='connect_google'),
    path('google/callback/', views.google_oauth_callback_view, name='google_callback'),
    path('google/disconnect/', views.disconnect_google_calendar_view, name='disconnect_google'),
]
