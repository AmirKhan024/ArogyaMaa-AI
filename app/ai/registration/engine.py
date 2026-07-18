"""
Registration Engine — deterministic step flow with LLM-assisted extraction.

The question text is fixed, curated, and bilingual (see questions.py) — the LLM
is used ONLY to extract structured fields from the mother's free-form answers
(FAST model, temperature 0). Step selection, skipping, derivations (EDD/week/
age), yes-no normalization, progress, the summary card, and the completion
message are all deterministic, which makes the flow idempotent: re-processing
the same answer can never advance the flow twice.

Public contract (unchanged from the previous engine):
    provide_next_question(session_data, last_message=None)
        -> (updates_dict, display_text, is_complete, ui_details)
ui_details = {"type": ..., "options": [labels], "speech_text": str}
"""

import json
import logging
import os
import re
from datetime import date, timedelta

from app.ai.registration.assistant import AIAssistant
from app.ai.registration.questions import REGISTRATION_STEPS

logger = logging.getLogger(__name__)

FAST_MODEL = os.getenv("LLM_MODEL_FAST", "llama-3.1-8b-instant")

_YES_WORDS = {"yes", "y", "haan", "ha", "han", "ji", "जी", "हाँ", "हां", "true", "yeah", "yep"}
_NO_WORDS = {"no", "n", "nahi", "nahin", "na", "नहीं", "ना", "none", "false", "nope", "nahee"}

_NONE_TO_ALL_RE = re.compile(
    r"\b(none|nothing|all normal|i'?m fine|no problems?)\b"
    r"|कुछ नहीं|सब (सामान्य|ठीक)|मैं ठीक|कोई नहीं",
    re.IGNORECASE,
)

_ACKS = {
    "en": ["Thank you 🙏", "Got it 💚", "Noted 🌸", "Perfect 💚"],
    "hi": ["धन्यवाद 🙏", "ठीक है 💚", "समझ गई 🌸", "बहुत अच्छा 💚"],
}

_SORRY = {
    "en": "Sorry, I didn't quite catch that 🙏 ",
    "hi": "माफ़ कीजिए, मैं ठीक से समझ नहीं पाई 🙏 ",
}

_CORRECTION_PROMPT = {
    "en": ("No problem — tell me what to fix, in your own words. "
           "(For example: \"my village is Sitapur\" or \"blood group is O+\")"),
    "hi": ("कोई बात नहीं — बताइए क्या ठीक करना है, अपने शब्दों में। "
           "(जैसे: \"मेरा गाँव सीतापुर है\" या \"ब्लड ग्रुप O+ है\")"),
}

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]", flags=re.UNICODE
)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


def _norm_yes_no(value):
    """Canonicalize a yes/no answer to 'Yes'/'No'; None when unrecognizable."""
    v = _strip_emoji(str(value or "")).strip().lower().rstrip("!.।")
    if v in _YES_WORDS:
        return "Yes"
    if v in _NO_WORDS:
        return "No"
    return None


def _parse_date(text):
    """Parse a date string; returns datetime.date or None.

    ISO (YYYY-MM-DD) is tried first — the engine normalizes stored dates to ISO
    and re-parses them on every pass, and dateparser's DMY ordering would
    silently swap day/month on ISO input.
    """
    text = str(text).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        import dateparser
        dt = dateparser.parse(text, settings={"DATE_ORDER": "DMY"})
        return dt.date() if dt else None
    except Exception:
        return None


class RegistrationEngine:
    def __init__(self, ai_assistant: AIAssistant):
        self.ai = ai_assistant

    # ── Public entry point ────────────────────────────────────────────────────

    def provide_next_question(self, current_data: dict, last_message: str = None) -> tuple:
        data = dict(current_data or {})
        lang = self._lang(data)
        updates: dict = {}

        # Correction mode: the mother said "something is wrong" on the summary.
        if data.get("_correction_mode") and last_message:
            updates = self._extract(self._all_fields(), last_message)
            updates["_correction_mode"] = None
            data.update({k: v for k, v in updates.items() if v is not None})
            data["_correction_mode"] = None
            self._derive(data, updates)
            consent_step = REGISTRATION_STEPS[-1]
            text = self._summary_card(data, lang)
            return updates, text, False, self._ui(consent_step, lang, text)

        pending = self._pending(data)
        if not pending:
            text = self._completion_msg(data, lang)
            return {}, text, True, {"type": "text", "options": [], "speech_text": _strip_emoji(text)}

        current = pending[0]
        answered = False

        if last_message:
            step_updates = self._answer_step(current, last_message, data)

            # Consent "No" → correction mode instead of storing a refusal.
            if current["id"] == "consent" and step_updates.get("doctor_consent") == "No":
                updates = {"doctor_consent": None, "_correction_mode": True}
                text = _CORRECTION_PROMPT[lang]
                return updates, text, False, {"type": "text", "options": [],
                                              "speech_text": _strip_emoji(text)}

            updates.update(step_updates)
            data.update({k: v for k, v in step_updates.items() if v is not None})
            self._derive(data, updates)
            answered = self._step_done(current, data)

        pending = self._pending(data)
        if not pending:
            text = self._completion_msg(data, lang)
            return updates, text, True, {"type": "text", "options": [],
                                         "speech_text": _strip_emoji(text)}

        nxt = pending[0]
        lang = self._lang(data)  # may have just been chosen in step 1
        question = nxt["text_en"] if lang == "en" else nxt["text_hi"]

        if nxt.get("is_summary"):
            question = self._summary_card(data, lang)
        elif last_message and not answered and nxt is current:
            question = _SORRY[lang] + question
        elif last_message and answered:
            ack = _ACKS[lang][sum(1 for v in data.values() if v is not None) % len(_ACKS[lang])]
            question = f"{ack}\n\n{question}"

        display = question
        if not nxt.get("no_progress"):
            applicable = self._applicable(data)
            pos = applicable.index(nxt) + 1
            step_word = "Step" if lang == "en" else "चरण"
            display = f"🌸 {step_word} {pos}/{len(applicable)}\n\n{question}"

        return updates, display, False, self._ui(nxt, lang, question)

    # ── Step helpers ──────────────────────────────────────────────────────────

    def _lang(self, data) -> str:
        return "en" if "english" in str(data.get("preferred_language", "")).lower() else "hi"

    def _applicable(self, data):
        return [s for s in REGISTRATION_STEPS if s.get("applies", lambda d: True)(data)]

    def _pending(self, data):
        return [s for s in self._applicable(data) if not self._step_done(s, data)]

    def _step_done(self, step, data) -> bool:
        present = [f["key"] for f in step["fields"] if data.get(f["key"]) is not None]
        need = step.get("min_fields", len(step["fields"]))
        return len(present) >= need

    def _all_fields(self):
        fields = []
        for s in REGISTRATION_STEPS:
            fields.extend(s["fields"])
        return fields

    def _ui(self, step, lang, question_text) -> dict:
        return {
            "type": step.get("ui", "text"),
            "options": [o[f"label_{lang}"] for o in step.get("options", [])],
            "speech_text": _strip_emoji(question_text),
        }

    # ── Answering a step ──────────────────────────────────────────────────────

    def _answer_step(self, step, message, data) -> dict:
        message = str(message).strip()

        # Fast path: keyboard tap / exact option match — no LLM involved.
        if step.get("options"):
            low = _strip_emoji(message).strip().lower()
            for opt in step["options"]:
                if low in {opt["value"].lower(),
                           _strip_emoji(opt["label_en"]).strip().lower(),
                           _strip_emoji(opt["label_hi"]).strip().lower()}:
                    return {step["fields"][0]["key"]: opt["value"]}
            # A yes/no said in another way ("haan ji")
            if len(step["fields"]) == 1 and step["fields"][0]["type"] == "yes_no":
                norm = _norm_yes_no(message)
                if norm:
                    return {step["fields"][0]["key"]: norm}

        single_field = len(step["fields"]) == 1

        # Deterministic single-field handling that needs no LLM.
        if single_field:
            f = step["fields"][0]
            if f["type"] == "yes_no":
                norm = _norm_yes_no(message)
                return {f["key"]: norm} if norm else {}
            if step["id"] == "phone":
                digits = re.sub(r"\D", "", message)
                return {f["key"]: digits} if len(digits) >= 10 else {f["key"]: message}
            if step["id"] == "emergency_contact":
                return {f["key"]: message}

        # LLM extraction (FAST model first; escalate to the big model when the
        # fast one returns nothing usable — small models sometimes parrot the
        # schema instead of extracting).
        extracted = self._extract(step["fields"], message, step)
        cleaned = self._clean(step, extracted)

        if not cleaned and _NONE_TO_ALL_RE.search(message):
            cleaned = self._none_fill(step)

        if not cleaned and not single_field:
            big_model = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
            extracted = self._extract(step["fields"], message, step, model=big_model)
            cleaned = self._clean(step, extracted)

        if cleaned:
            data.pop(f"_retry_{step['id']}", None)
            return cleaned

        # Nothing usable — retry (grouped) or store raw (single-field).
        if single_field:
            return {step["fields"][0]["key"]: message}

        retries = int(data.get(f"_retry_{step['id']}") or 0)
        if retries >= 1:
            # Second failure: keep the raw answer in the primary field, mark the
            # rest Unknown so the flow can never get stuck.
            fill = {f["key"]: "Unknown" for f in step["fields"]}
            fill[step.get("primary_field", step["fields"][0]["key"])] = message
            fill[f"_retry_{step['id']}"] = None
            return fill
        return {f"_retry_{step['id']}": retries + 1}

    def _clean(self, step, extracted) -> dict:
        """Normalize + validate LLM output against the step's field specs."""
        cleaned = {}
        valid_keys = {f["key"]: f for f in step["fields"]}
        for k, v in (extracted or {}).items():
            f = valid_keys.get(k)
            if f is None or v in (None, ""):
                continue
            if f["type"] == "yes_no":
                norm = _norm_yes_no(v)
                if norm:
                    cleaned[k] = norm
            elif f["type"] == "number":
                m = re.search(r"\d+", str(v))
                if m:
                    cleaned[k] = m.group()
            else:
                cleaned[k] = str(v).strip()
        return cleaned

    def _none_fill(self, step) -> dict:
        out = {}
        for f in step["fields"]:
            out[f["key"]] = "No" if f["type"] == "yes_no" else "None"
        return out

    @staticmethod
    def _field_lines(fields) -> str:
        lines = []
        for f in fields:
            if f["type"] == "yes_no":
                val = 'must be exactly "Yes" or "No"'
            elif f["type"] == "number":
                val = "a plain number as a string"
            elif f["type"] == "date":
                val = "the date exactly as she said it"
            else:
                val = "a short English phrase"
            lines.append(f'- "{f["key"]}": {f["desc"]} — value: {val}')
        return "\n".join(lines)

    def _extract(self, fields, message, step=None, model=None) -> dict:
        question = ""
        if step is not None:
            question = f'The mother was asked: "{step["text_en"]}"\n'
        prompt = f"""{question}She replied: "{message}"

Fields to extract (use EXACTLY these keys):
{self._field_lines(fields)}

Rules:
- Yes/No fields: haan/हाँ/ji/taken/done = "Yes"; nahi/नहीं/none/not yet = "No".
- If she says nothing/none/kuch nahi/sab theek for the whole question, set EVERY
  Yes/No field to "No" and every text field to "None".
- Translate Hindi content into short English phrases.
- Include ONLY the fields she actually addressed. If nothing is extractable, return {{}}.
Return ONLY a JSON object — no markdown, no explanations."""

        system = ("You extract registration data for a maternal health service in India. "
                  "Users answer in English, Hindi, or Hinglish. Return only JSON.")
        try:
            raw = self.ai._call_groq(prompt, system,
                                     model=model or FAST_MODEL, temperature=0.0)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start == -1 or end <= start:
                return {}
            return json.loads(raw[start:end]) or {}
        except Exception as e:
            logger.warning(f"[Registration] Extraction failed: {e}")
            return {}

    # ── Derivations ───────────────────────────────────────────────────────────

    def _derive(self, data: dict, updates: dict):
        """Fill derivable fields (EDD/LMP/week, age) after each merge."""
        def set_both(key, value):
            data[key] = value
            updates[key] = value

        lmp = _parse_date(data.get("lmp_date")) if data.get("lmp_date") else None
        edd = _parse_date(data.get("edd_date")) if data.get("edd_date") else None
        week = None
        try:
            week = int(float(data.get("gestational_week")))
        except (TypeError, ValueError):
            pass

        today = date.today()

        # An explicitly stated week is the strongest signal when LMP is absent —
        # and small models sometimes hallucinate an EDD, so sanity-check it.
        if lmp is None and week is not None:
            lmp = today - timedelta(weeks=week)
            edd = None  # recompute from the trusted anchor
        elif lmp is None and edd is not None:
            lmp = edd - timedelta(days=280)

        if lmp is not None:
            expected_edd = lmp + timedelta(days=280)
            if edd is None or abs((edd - expected_edd).days) > 45:
                edd = expected_edd  # inconsistent/hallucinated EDD — LMP wins
            if week is None:
                week = max(1, min(42, (today - lmp).days // 7))
            set_both("lmp_date", lmp.isoformat())
            set_both("edd_date", edd.isoformat())
            set_both("gestational_week", str(week))

        # Age from dob (deterministic; finalize keeps its own fallback).
        if data.get("dob") and not data.get("age"):
            born = _parse_date(data["dob"])
            if born:
                age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
                if 10 <= age <= 60:
                    set_both("age", age)
                    set_both("dob", born.isoformat())

        # First pregnancy → skip previous-details questions.
        if str(data.get("first_pregnancy", "")).lower() == "yes":
            if not data.get("previous_pregnancies_count"):
                set_both("previous_pregnancies_count", "0")
            if not data.get("previous_complications"):
                set_both("previous_complications", "No")

    # ── Summary & completion ──────────────────────────────────────────────────

    def _summary_card(self, data, lang) -> str:
        def g(key, default="—"):
            v = data.get(key)
            return str(v) if v not in (None, "") else default

        week = g("gestational_week")
        if lang == "en":
            lines = [
                "🌸 Almost done! Here's what I have:",
                "",
                f"👤 {g('full_name')} · {g('age')} yrs",
                f"📱 {g('phone_number')}",
                f"📍 {g('location')}",
                f"🤰 Week {week} · Due date: {g('edd_date')}",
                f"🩸 Blood group: {g('blood_group')}",
                f"🩺 Conditions: {g('medical_conditions', 'None')} · Allergies: {g('allergies', 'None')}",
                f"⚠️ Symptoms: {g('current_symptoms', 'None')}",
                f"📞 Emergency: {g('emergency_contact')}",
                "",
                REGISTRATION_STEPS[-1]["text_en"],
            ]
        else:
            lines = [
                "🌸 बस हो गया! यह रही आपकी जानकारी:",
                "",
                f"👤 {g('full_name')} · {g('age')} वर्ष",
                f"📱 {g('phone_number')}",
                f"📍 {g('location')}",
                f"🤰 {week}वाँ हफ्ता · डिलीवरी: {g('edd_date')}",
                f"🩸 ब्लड ग्रुप: {g('blood_group')}",
                f"🩺 बीमारियाँ: {g('medical_conditions', 'कुछ नहीं')} · एलर्जी: {g('allergies', 'कुछ नहीं')}",
                f"⚠️ लक्षण: {g('current_symptoms', 'कुछ नहीं')}",
                f"📞 आपातकालीन: {g('emergency_contact')}",
                "",
                REGISTRATION_STEPS[-1]["text_hi"],
            ]
        return "\n".join(lines)

    def _completion_msg(self, data, lang) -> str:
        name = data.get("full_name") or ("dear" if lang == "en" else "प्रिय")
        week = data.get("gestational_week") or "?"
        if lang == "en":
            return (
                f"💚 Thank you, {name}! Your registration is complete.\n\n"
                "What happens next:\n"
                "• An ASHA worker will be assigned to you soon\n"
                f"• You'll get care tips matched to week {week} of your pregnancy\n"
                "• Message me anytime — day or night, I'm here\n\n"
                "Press /start to see your health menu."
            )
        return (
            f"💚 धन्यवाद, {name}! आपका पंजीकरण पूरा हो गया।\n\n"
            "अब आगे क्या होगा:\n"
            "• जल्द ही एक आशा दीदी आपके लिए नियुक्त होंगी\n"
            f"• आपको {week}वें हफ्ते के हिसाब से देखभाल की सलाह मिलेगी\n"
            "• कभी भी संदेश भेजें — मैं हमेशा यहाँ हूँ\n\n"
            "/start दबाकर अपना स्वास्थ्य मेनू देखें।"
        )
