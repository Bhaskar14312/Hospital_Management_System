# Mini Hospital Management System (HMS)

A small, premium hospital management web application focused on doctor availability scheduling and patient appointment booking. The project includes a separate serverless email notification service.

---

## Setup and Run

Follow these step-by-step instructions to get the system running locally on your machine.

### Prerequisites
- Python 3.12+ (tested on Python 3.13.7)
- Node.js (tested on Node v22.19.0) and npm

### 1. Set Up the Serverless Email Service
1. Navigate to the `email-service` directory:
   ```bash
   cd email-service
   ```
2. Install the local npm dependencies (including the `serverless` CLI and `serverless-offline` plugin):
   ```bash
   npm install
   ```
3. Start the Serverless offline email service:
   ```bash
   npx serverless offline
   ```
   *The serverless service will start listening locally at `http://localhost:3000`.*

### 2. Set Up the Django Web Backend
1. Open a new terminal window and navigate to the project root.
2. Install the Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Navigate to the `hms` directory:
   ```bash
   cd hms
   ```
4. Run database migrations to initialize the SQLite database:
   ```bash
   python manage.py migrate
   ```
5. Run the test suite to verify the setup (including the concurrent booking race condition handling):
   ```bash
   python manage.py test
   ```
6. Start the local development server:
   ```bash
   python manage.py runserver
   ```
   *The Django application will start running at `http://127.0.0.1:8000`.*

---

## System Architecture

The project consists of two independent services running locally:

### 1. Component Connections
- **Django App (Port 8000)**: Serves as the primary user-facing web interface and database manager.
- **Serverless Email Service (Port 3000)**: Runs inside a simulated local AWS Lambda environment via `serverless-offline`.
- **Communication Flow**: When a user registers or books an appointment, Django sends a non-blocking background HTTP POST request (dispatched in a Python `threading.Thread` context) to the Serverless handler endpoint: `http://localhost:3000/dev/send-email`. This decouples the core web app from email delivery latency.

### 2. Data Model Decisions
- **CustomUser**: Extends Django's `AbstractUser` to support role-based user management with a `role` field (`DOCTOR` vs `PATIENT`).
- **AvailabilitySlot**: Stores availability date and start/end time windows for a doctor. Enforces a `unique_together` constraint on `('doctor', 'date', 'start_time', 'end_time')` to prevent overlapping slot creation.
- **Booking**: Links a `patient` user to a specific `AvailabilitySlot`. A `OneToOneField` is used on `slot` to guarantee that a slot can never be associated with more than one booking at the database level.
- **GoogleAuthToken**: Stores encrypted OAuth2 credentials (`access_token`, `refresh_token`, `expires_at`) for each user to communicate with the Google Calendar API.

### 3. Role-Based Access Enforcement
- Access control is enforced at the view layer using custom decorators (`@doctor_required` and `@patient_required`) that inspect the authenticated user's `role` property and throw a `PermissionDenied` error if an unauthorized user attempts to cross boundaries.

### 4. Google Calendar Integration Structure
- **OAuth2 Flow**: Users are redirected to Google's consent screen. Upon authorization, Google redirects back to the Django callback endpoint with a authorization code, which is exchanged for an access token and a refresh token.
- **Token Refreshing**: Before dispatching Google Calendar API requests, Django checks if the access token has expired. If it has, it automatically performs a silent refresh using the stored `refresh_token`.
- **Sync Event Creation**: When a booking is confirmed, events are created in the Google Calendars of *both* the doctor and the patient (if they have authorized calendar sync).

---

## The Design Decision

### The Problem: Multi-User Concurrent Booking (Race Condition)
When two patients attempt to book the exact same open slot at the same time, a race condition occurs. If untreated:
1. Thread A checks if the slot is open (Yes).
2. Thread B checks if the slot is open (Yes).
3. Thread A books the slot.
4. Thread B books the slot.
Result: The doctor is double-booked, violating a core business rule.

### Approaches Considered

#### Option 1: View-Level Synchronization Lock (Python-level locking)
Use a thread lock (e.g. `threading.Lock`) in views to serialize the booking flow.
- **Pros**: Easy to write.
- **Cons**: Locks are in-memory. They only work on a single process. In production, web servers run multiple worker processes (e.g. gunicorn with 4-8 workers). Process A's lock has no effect on Process B, failing to prevent the race condition.

#### Option 2: Database-Level Row Locking and Constraints (Chosen)
Utilize Django's `select_for_update()` inside a `transaction.atomic()` block, backed by a One-to-One unique constraint on `Booking.slot`.
- **Pros**: 
  - `select_for_update()` instructs the database engine to acquire a lock on the selected row. Any other concurrent transaction trying to fetch or update that row will block until the first transaction finishes.
  - The `OneToOneField` constraint on the `Booking` model acts as a hard database-level safeguard. Even if row-locking fails (e.g. due to database misconfiguration), the database will raise an `IntegrityError` on the duplicate insert, preventing double booking.
- **Cons**: Requires database support. SQLite locks the entire database file during writes, which can sometimes raise `database is locked` exceptions under heavy concurrency.

### Defense of the Chosen Approach
We chose **Option 2** because database-level guarantees are the only way to ensure data integrity across multiple web processes and servers. 

To mitigate SQLite's full-table lock limitations in local environments, we configured the SQLite database options with a `timeout` of 20 seconds. This allows concurrent transactions to wait for locks to release rather than immediately failing. In our unit test suite, we successfully simulated multi-threaded race conditions, showing that when two threads compete, one thread successfully books the slot while the other is safely locked out and retries, leaving exactly one valid booking in the database.

---

## Limitations

If this system were deployed to production, the following limitations would break and need immediate fixes:

1. **SQLite Database Concurrency**:
   - *Problem*: SQLite locks the entire database file for writes. Under moderate user traffic, this will lead to slow response times and frequent "database is locked" errors.
   - *Fix*: Replace SQLite with **PostgreSQL** in production, which supports native row-level locking (`SELECT ... FOR UPDATE`), allowing thousands of concurrent bookings without locking the entire database.
2. **In-Memory Threading for Emails and Calendar Sync**:
   - *Problem*: We use `threading.Thread` to send notifications and sync Google Calendars asynchronously. If the web server crashes or restarts, all active threads are lost, causing missed email notifications and calendar sync failures.
   - *Fix*: Implement a reliable task queue like **Celery** with a **Redis** or **RabbitMQ** broker to manage background tasks.
3. **Plain Text Credentials**:
   - *Problem*: Google Client credentials and SMTP details are loaded directly from raw environment variables.
   - *Fix*: Move secrets to a secure store like **AWS Secrets Manager** or HashiCorp Vault.
