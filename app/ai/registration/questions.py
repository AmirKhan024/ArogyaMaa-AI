"""
Registration steps for ArogyaMaa — grouped, bilingual, voice-first.

Each step has fixed curated question text (en/hi) — the LLM is used ONLY to
extract fields from the mother's answer, never to write the questions.
Grouped steps capture several session fields from one natural answer.

Field keys are unchanged from the original 24-question flow so
registration_repo.finalize_registration keeps working untouched.
"""


def _first_preg_is_no(d):
    return str(d.get("first_pregnancy", "")).strip().lower() in ("no", "नहीं", "nahi")


def _week_18_plus_or_unknown(d):
    try:
        return int(float(d.get("gestational_week"))) >= 18
    except (TypeError, ValueError):
        return True  # unknown week -> ask anyway (safer)


REGISTRATION_STEPS = [
    {
        "id": "preferred_language",
        "ui": "binary",
        "options": [
            {"value": "English", "label_en": "English", "label_hi": "English"},
            {"value": "हिंदी",   "label_en": "हिंदी",    "label_hi": "हिंदी"},
        ],
        "fields": [{"key": "preferred_language", "type": "choice",
                    "desc": "'English' or 'हिंदी'"}],
        "no_progress": True,
        "text_en": ("🌸 नमस्ते! Welcome to ArogyaMaa — your pregnancy companion.\n"
                    "कृपया अपनी भाषा चुनें / Please choose your language:"),
        "text_hi": ("🌸 नमस्ते! Welcome to ArogyaMaa — your pregnancy companion.\n"
                    "कृपया अपनी भाषा चुनें / Please choose your language:"),
    },
    {
        "id": "phone",
        "ui": "contact",
        "fields": [{"key": "phone_number", "type": "text", "desc": "phone number, digits only"}],
        "text_en": ("Lovely! I'm ArogyaMaa 💚 I'll ask a few short questions — answer by "
                    "voice or typing, whatever is easier.\n\n"
                    "First, please share your phone number (tap the button below)."),
        "text_hi": ("बहुत अच्छा! मैं हूँ आरोग्यमाँ 💚 मैं आपसे कुछ छोटे सवाल पूछूँगी — आप बोलकर या "
                    "लिखकर जवाब दे सकती हैं, जैसे आसान लगे।\n\n"
                    "सबसे पहले, नीचे बटन दबाकर अपना फोन नंबर साझा करें।"),
    },
    {
        "id": "about_you",
        "ui": "text",
        "fields": [
            {"key": "full_name", "type": "text", "desc": "the woman's name"},
            {"key": "dob",       "type": "date", "desc": "date of birth"},
            {"key": "location",  "type": "text", "desc": "village / area name"},
        ],
        "text_en": ("Tell me a little about yourself — your name, date of birth, and your "
                    "village. (Example: \"Sunita, 15 June 1998, Rampur\")"),
        "text_hi": ("अपने बारे में बताइए — आपका नाम, जन्म तिथि, और आपका गाँव। "
                    "(जैसे: \"सुनीता, 15 जून 1998, रामपुर\")"),
    },
    {
        "id": "pregnancy_dates",
        "ui": "text",
        "fields": [
            {"key": "lmp_date",         "type": "date",   "desc": "first day of last menstrual period"},
            {"key": "edd_date",         "type": "date",   "desc": "expected delivery date"},
            {"key": "gestational_week", "type": "number", "desc": "weeks pregnant (number)"},
        ],
        "min_fields": 1,  # any ONE answers the step; the rest are derived
        "text_en": ("Now about your pregnancy 🤰 When was the first day of your last period? "
                    "If you don't remember, your due date or how many weeks pregnant you are — "
                    "any one is fine."),
        "text_hi": ("अब आपकी गर्भावस्था के बारे में 🤰 आपकी आखिरी माहवारी का पहला दिन कब था? "
                    "याद न हो तो डिलीवरी की तारीख या कितने हफ्ते चल रहे हैं — कोई एक बता दें।"),
    },
    {
        "id": "first_pregnancy",
        "ui": "binary",
        "options": [
            {"value": "Yes", "label_en": "Yes, my first", "label_hi": "हाँ, पहली है"},
            {"value": "No",  "label_en": "No",            "label_hi": "नहीं"},
        ],
        "fields": [{"key": "first_pregnancy", "type": "yes_no", "desc": "is this the first pregnancy"}],
        "text_en": "Is this your first pregnancy?",
        "text_hi": "क्या यह आपकी पहली गर्भावस्था है?",
    },
    {   # CONDITIONAL — only when first_pregnancy == "No"
        "id": "previous_details",
        "ui": "text",
        "applies": _first_preg_is_no,
        "fields": [
            {"key": "previous_pregnancies_count", "type": "number", "desc": "number of previous pregnancies"},
            {"key": "previous_complications",     "type": "text_or_none",
             "desc": "'No' if all normal, otherwise short description (C-section, bleeding, high BP...)"},
        ],
        "primary_field": "previous_pregnancies_count",
        "text_en": ("How many times were you pregnant before, and were there any problems — "
                    "like an operation (C-section), heavy bleeding, or high BP? "
                    "If all was fine, just say \"all normal\"."),
        "text_hi": ("इससे पहले आप कितनी बार गर्भवती हुईं, और क्या कोई परेशानी हुई थी — जैसे "
                    "ऑपरेशन, ज़्यादा खून बहना, या हाई बीपी? सब ठीक था तो बस \"सब सामान्य\" कह दें।"),
    },
    {
        "id": "health_now",
        "ui": "text",
        "fields": [
            {"key": "current_symptoms", "type": "text_or_none", "desc": "current symptoms, or 'None'"},
            {"key": "danger_signs",     "type": "yes_no",
             "desc": "'Yes' ONLY if she mentions bleeding, severe headache, blurred vision, "
                     "fits/seizures, severe swelling, or high fever; otherwise 'No'"},
        ],
        "primary_field": "current_symptoms",
        "text_en": ("How are you feeling these days? Any troubles like bleeding, strong headache, "
                    "blurry vision, fits, or swelling? If you feel fine, just say \"I'm fine\"."),
        "text_hi": ("आजकल आप कैसा महसूस कर रही हैं? कोई परेशानी — जैसे खून आना, तेज़ सिरदर्द, "
                    "धुंधला दिखना, दौरे, या सूजन? ठीक हैं तो बस \"मैं ठीक हूँ\" कह दें।"),
    },
    {
        "id": "medical_background",
        "ui": "text",
        "fields": [
            {"key": "medical_conditions",      "type": "text_or_none", "desc": "illnesses (diabetes, BP, thyroid...), or 'None'"},
            {"key": "medications_supplements", "type": "text_or_none", "desc": "regular medicines/supplements, or 'None'"},
            {"key": "allergies",               "type": "text_or_none", "desc": "allergies, or 'None'"},
            {"key": "major_surgeries",         "type": "text_or_none", "desc": "past major surgeries, or 'None'"},
        ],
        "primary_field": "medical_conditions",
        "text_en": ("A little about your health history: any illness like sugar, BP, or thyroid? "
                    "Any daily medicines, any allergies, or any big operation in the past? "
                    "You can simply say \"none\"."),
        "text_hi": ("अब थोड़ा सेहत के बारे में: क्या कोई बीमारी है जैसे शुगर, बीपी, थायरॉइड? कोई दवा "
                    "रोज़ लेती हैं, किसी चीज़ से एलर्जी, या पहले कोई बड़ा ऑपरेशन? कुछ नहीं है तो "
                    "\"कुछ नहीं\" कह दें।"),
    },
    {
        "id": "blood_group",
        "ui": "choice",
        "options": [{"value": v, "label_en": v, "label_hi": v}
                    for v in ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]]
                   + [{"value": "Unknown", "label_en": "Don't know", "label_hi": "पता नहीं"}],
        "fields": [{"key": "blood_group", "type": "choice", "desc": "blood group like B+, or 'Unknown'"}],
        "text_en": "What is your blood group? Tap below — if you don't know, choose \"Don't know\".",
        "text_hi": "आपका ब्लड ग्रुप क्या है? नीचे से चुनें — पता न हो तो \"पता नहीं\" चुनें।",
    },
    {
        "id": "care_so_far",
        "ui": "text",
        "fields": [
            {"key": "vaccines_received", "type": "yes_no", "desc": "tetanus/TT injection taken"},
            {"key": "scans_done",        "type": "yes_no", "desc": "ultrasound/sonography done"},
            {"key": "lab_tests_done",    "type": "yes_no", "desc": "blood or urine tests done"},
        ],
        "primary_field": "vaccines_received",
        "text_en": ("In this pregnancy, have you had: the tetanus (TT) injection? An ultrasound "
                    "(sonography)? Any blood or urine tests? Tell me yes or no for each."),
        "text_hi": ("इस गर्भावस्था में क्या आपने: टिटनेस (TT) का टीका लगवाया? पेट की सोनोग्राफी "
                    "(अल्ट्रासाउंड) करवाई? खून या पेशाब की जाँच करवाई? हर एक के लिए हाँ या नहीं बताएं।"),
    },
    {   # CONDITIONAL — only when gestational week >= 18 (or unknown)
        "id": "fetal_movement",
        "ui": "binary",
        "applies": _week_18_plus_or_unknown,
        "options": [
            {"value": "Yes", "label_en": "Yes", "label_hi": "हाँ"},
            {"value": "No",  "label_en": "No",  "label_hi": "नहीं"},
        ],
        "fields": [{"key": "fetal_movement", "type": "yes_no", "desc": "feels the baby moving"}],
        "text_en": "Can you feel your baby moving?",
        "text_hi": "क्या आपको बच्चे की हलचल महसूस होती है?",
    },
    {
        "id": "substance_usage",
        "ui": "binary",
        "options": [
            {"value": "Yes", "label_en": "Yes", "label_hi": "हाँ"},
            {"value": "No",  "label_en": "No",  "label_hi": "नहीं"},
        ],
        "fields": [{"key": "substance_usage", "type": "yes_no", "desc": "uses tobacco/gutka/alcohol/smoking"}],
        "text_en": ("Do you use tobacco, gutka, alcohol, or smoke? Please answer honestly — "
                    "this stays between us and your doctor."),
        "text_hi": ("क्या आप तंबाकू, गुटखा, शराब या धूम्रपान लेती हैं? सच बताएं — यह बात सिर्फ "
                    "आपके डॉक्टर तक रहेगी।"),
    },
    {
        "id": "emergency_contact",
        "ui": "text",
        "fields": [{"key": "emergency_contact", "type": "text", "desc": "emergency contact name and number"}],
        "text_en": ("Almost there! If we ever need to reach your family quickly, whose number "
                    "should we call? Share the name and number."),
        "text_hi": ("बस थोड़ा और! ज़रूरत पड़ने पर हम आपके परिवार में किसे फोन करें? "
                    "कृपया नाम और नंबर बताएं।"),
    },
    {   # FINAL — the engine prepends the summary card above this question
        "id": "consent",
        "ui": "binary",
        "is_summary": True,
        "options": [
            {"value": "Yes", "label_en": "✅ Yes, I agree",       "label_hi": "✅ हाँ, सहमति है"},
            {"value": "No",  "label_en": "✏️ Something is wrong", "label_hi": "✏️ कुछ गलत है"},
        ],
        "fields": [{"key": "doctor_consent", "type": "yes_no", "desc": "consent to share with doctor/ASHA"}],
        "text_en": "Do you allow me to share this with your doctor and ASHA worker?",
        "text_hi": "क्या आप यह जानकारी अपने डॉक्टर और आशा दीदी के साथ साझा करने की अनुमति देती हैं?",
    },
]

# Back-compat alias (the engine is the only consumer).
REGISTRATION_QUESTIONS = REGISTRATION_STEPS
