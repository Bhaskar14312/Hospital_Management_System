import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(event, context):
    try:
        # Check if body is string (JSON) or already parsed dict
        body_str = event.get("body", "")
        if isinstance(body_str, str):
            data = json.loads(body_str) if body_str else {}
        else:
            data = body_str if body_str else {}
    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid JSON body: {str(e)}"})
        }

    trigger = data.get("trigger")
    if not trigger:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing 'trigger' in request body"})
        }

    # Retrieve SMTP credentials from environment if available
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")

    subject = ""
    html_content = ""
    recipients = []

    if trigger == "SIGNUP_WELCOME":
        email = data.get("email")
        name = data.get("name", "User")
        if not email:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing 'email' for SIGNUP_WELCOME"})}
        
        recipients = [email]
        subject = "Welcome to Banao HMS!"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #4a90e2;">Welcome to Banao Hospital Management System, {name}!</h2>
                <p>Thank you for signing up on our platform.</p>
                <p>You can now manage your schedule and bookings efficiently.</p>
                <br>
                <p>Best Regards,</p>
                <p><strong>Banao HMS Team</strong></p>
            </body>
        </html>
        """
    elif trigger == "BOOKING_CONFIRMATION":
        doctor_email = data.get("doctor_email")
        doctor_name = data.get("doctor_name", "Doctor")
        patient_email = data.get("patient_email")
        patient_name = data.get("patient_name", "Patient")
        slot_details = data.get("slot_details", "")

        if not doctor_email or not patient_email:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing emails for BOOKING_CONFIRMATION"})}
        
        recipients = [doctor_email, patient_email]
        subject = "Appointment Booking Confirmed!"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #2ecc71;">Appointment Confirmed!</h2>
                <p>Hello,</p>
                <p>We are pleased to inform you that an appointment has been successfully scheduled:</p>
                <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin-top: 15px;">
                    <tr style="background-color: #f2f2f2;">
                        <th style="border: 1px solid #dddddd; text-align: left; padding: 8px;">Doctor</th>
                        <td style="border: 1px solid #dddddd; text-align: left; padding: 8px;">Dr. {doctor_name}</td>
                    </tr>
                    <tr>
                        <th style="border: 1px solid #dddddd; text-align: left; padding: 8px;">Patient</th>
                        <td style="border: 1px solid #dddddd; text-align: left; padding: 8px;">{patient_name}</td>
                    </tr>
                    <tr style="background-color: #f2f2f2;">
                        <th style="border: 1px solid #dddddd; text-align: left; padding: 8px;">Time Slot</th>
                        <td style="border: 1px solid #dddddd; text-align: left; padding: 8px;">{slot_details}</td>
                    </tr>
                </table>
                <p>A Google Calendar event has been generated and added to your schedules.</p>
                <br>
                <p>Best Regards,</p>
                <p><strong>Banao HMS Team</strong></p>
            </body>
        </html>
        """
    else:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Unknown trigger '{trigger}'"})
        }

    # Simulate or send
    if not smtp_user or not smtp_pass:
        # Mock mode
        log_msg = f"[MOCK EMAIL] To: {recipients} | Subject: '{subject}' | Trigger: {trigger}"
        print(log_msg)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Email simulation successful (SMTP credentials not configured)",
                "details": {
                    "to": recipients,
                    "subject": subject,
                    "trigger": trigger,
                    "mocked": True
                }
            })
        }

    # Actual SMTP send
    try:
        for recipient in recipients:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = recipient
            msg.attach(MIMEText(html_content, "html"))

            # Standard SMTP flow
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
            server.quit()
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Emails sent successfully via SMTP",
                "details": {
                    "to": recipients,
                    "subject": subject,
                    "trigger": trigger,
                    "mocked": False
                }
            })
        }
    except Exception as e:
        print(f"[SMTP ERROR] Failed to send email: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": f"Failed to send email via SMTP: {str(e)}",
                "to": recipients,
                "subject": subject
            })
        }
