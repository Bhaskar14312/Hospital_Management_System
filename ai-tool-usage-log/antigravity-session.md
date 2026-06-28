# AI Tool Usage Log

## Session Details
- **AI Assistant**: Antigravity (Google DeepMind pair programming assistant)
- **Model**: Gemini 3.5 Flash (Medium)
- **User Task**: Week 1 Banao Technologies Shortlisting Task (Mini HMS System)

---

## Log of Interactions

### 1. Initial Prompt & Analysis
- **User Request**: Asked to complete Banao Week 1 Task, pasting the introductory HR email.
- **AI Action**: Identified that the initial message lacked specific task details and queried the user for requirements.
- **User Input**: Uploaded task PDF with details of Task A — Mini Hospital Management System (HMS), detailing:
  - Django backend, SQLite/PostgreSQL, Google Calendar OAuth integration, and a separate Serverless email notification service running locally via `serverless-offline`.
  - Design decision requirement and submission layout.

### 2. Architectural Design & Plan Approval
- **AI Action**: Created an `implementation_plan.md` outlining the SQLite configuration with concurrency handling, local package setup for Serverless CLI, and custom OAuth token flow.
- **User Response**: Approved the implementation plan and requested: *"start code but dont make too complex code"*.

### 3. Implementation Process
- **Step 1: Dependency Setup**: Wrote `requirements.txt` and `package.json` for Serverless config.
- **Step 2: Serverless Service**: Implemented Serverless config and a Python SMTP notification dispatcher in `handler.py` supporting simulated or actual SMTP delivery.
- **Step 3: Django Codebase**:
  - Initialized Django project and `hms_app`.
  - Created `models.py` (CustomUser, AvailabilitySlot, Booking, GoogleAuthToken).
  - Implemented row locking logic (`select_for_update()`) and database unique constraint validation.
  - Coded `forms.py`, access control `decorators.py`, helper `google_calendar.py`, and `views.py`.
  - Created premium glassmorphism layouts with modern Vanilla CSS.
- **Step 4: Database Setup & Migrations**: Generated and applied Django database migrations.
- **Step 5: Testing and Optimization**:
  - Implemented unit tests simulating concurrent slot-booking race conditions.
  - Resolved SQLite concurrency limits during testing by configuring database timeout options and adding retry logic in tests. The tests compiled and ran with a success (`OK`) status.
- **Step 6: Documentation**: Created final `README.md` containing all required headings and reports.
