# Questions for AI Registration (Voice-First & Button-Based)

REGISTRATION_QUESTIONS = [
    {"id": "preferred_language", "text": "Language / भाषा", "ui_type": "binary", "options": ["English", "हिंदी"]},
    {"id": "phone_number", "text": "What is your phone number?", "ui_type": "contact"},
    {"id": "dob", "text": "What is your date of birth?", "ui_type": "text"},
    {"id": "confirm_identity", "text": "Is this information correct?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "location", "text": "Which village / area do you live in?", "ui_type": "text"},
    {"id": "gestational_week", "text": "How many weeks pregnant are you?", "ui_type": "text"},
    {"id": "lmp_date", "text": "What was the first day of your last menstrual period (LMP), if known?", "ui_type": "text"},
    {"id": "edd_date", "text": "What is your expected delivery date (EDD), if known?", "ui_type": "text"},
    {"id": "first_pregnancy", "text": "Is this your first pregnancy?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "previous_pregnancies_count", "text": "How many previous pregnancies have you had?", "ui_type": "text"},
    {"id": "previous_complications", "text": "Did you have any complications in previous pregnancies?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "current_symptoms", "text": "What symptoms are you having currently?", "ui_type": "text"},
    {"id": "danger_signs", "text": "Are you having any danger signs right now?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "medical_conditions", "text": "Do you have any medical conditions?", "ui_type": "text"},
    {"id": "medications_supplements", "text": "Are you taking any medicines, supplements, or injections currently?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "allergies", "text": "Do you have any allergies?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "major_surgeries", "text": "Have you had any major surgeries before?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "blood_group", "text": "Do you know your blood group?", "ui_type": "choice", "options": ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-", "Unknown"]},
    {"id": "vaccines_received", "text": "Have you received tetanus / pregnancy vaccines?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "scans_done", "text": "Have you had any pregnancy scan / ultrasound done?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "lab_tests_done", "text": "Have you done any blood or urine tests in this pregnancy?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "fetal_movement", "text": "Are you feeling the baby's movement?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "substance_usage", "text": "Do you smoke / consume alcohol / use any substances?", "ui_type": "binary", "options": ["Yes", "No"]},
    {"id": "emergency_contact", "text": "What is your emergency contact number?", "ui_type": "text"},
    {"id": "doctor_consent", "text": "Do you consent to share this health history with your assigned doctor and ASHA worker?", "ui_type": "binary", "options": ["Yes", "No"]}
]
