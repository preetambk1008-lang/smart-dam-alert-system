"""
JalSuraksha: Smart Dam Water Level Monitoring & 3-Way Tiered Flood Alert System
Civil Engineering Capstone Project - 5th Semester

Key Hydrology & Disaster Mitigation Modules:
1. Haversine Great-Circle Geodesic Distance Matrix
2. Saint-Venant & Manning's Flood Wave Travel Velocity (v = 2.1 to 3.9 m/s)
3. CWC (Central Water Commission) Multi-Season Reservoir Rule Curve (IS 7323)
4. Geofenced Downstream Inundation Buffers:
   - 0-2 km: Critical Red Zone (Direct Floodplain Evacuation)
   - 2-5 km: Orange Warning Zone (Agricultural Buffer & Equipment Relocation)
   - >5 km: Green/Yellow Advisory Zone (Canal Command Area)
5. 3-Way Multi-Channel Alert Engine (1-Click Simultaneous Dispatch):
   - SMS: Compact 160-char text message for keypad/feature phones
   - WhatsApp: Rich media evacuation instructions with direct click-to-send link
   - Email: Real SMTP HTML advisory sent to registered email via .env
"""

import os
import sys
import json
import math
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import urllib.request
import base64
import re
import hmac
import secrets
import uuid

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Helper to read .env file without external dependencies
def load_env():
    env = {}
    candidates = [
        '.env', 
        '../.env', 
        os.path.join(os.path.dirname(__file__), '.env'), 
        os.path.join(os.path.dirname(__file__), '..', '.env')
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            env[k.strip()] = v.strip().strip('"').strip("'")
            except Exception:
                pass
    # Vercel and other hosts inject secrets as process environment variables.
    # Process values take precedence over local .env values.
    env.update(os.environ)
    return env

def env_value_is_configured(value):
    """Treat blank values and obvious setup placeholders as missing credentials."""
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    placeholders = ("paste_", "your_", "change_me", "changeme", "placeholder", "<", ">")
    return not any(marker in normalized for marker in placeholders)

# Persistent Database File
DB_FILE = os.path.join(os.path.dirname(__file__), 'farmers_db.json')

def load_farmers_from_db():
    # Vercel's deployed filesystem is not durable. Cloud requests hydrate state
    # from the configured Redis REST store before dispatching to this handler.
    # Never let a bundled local JSON file overwrite that shared registry.
    if os.environ.get('VERCEL') and os.environ.get('UPSTASH_REDIS_REST_URL') and os.environ.get('UPSTASH_REDIS_REST_TOKEN'):
        return []
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading DB: {e}")
    return []

def save_farmers_to_db(farmers_list):
    if os.environ.get('VERCEL') and os.environ.get('UPSTASH_REDIS_REST_URL') and os.environ.get('UPSTASH_REDIS_REST_TOKEN'):
        return
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(farmers_list, f, indent=2)
    except Exception as e:
        print(f"Error saving DB: {e}")

# Reference Benchmark: Krishnarajasagara (KRS) Dam / Cauvery River Basin
DAM_DATA = {
    "id": "DAM-KRS-001",
    "name": "Krishnarajasagara (KRS) Dam",
    "river": "Cauvery River",
    "district": "Mandya / Mysuru",
    "state": "Karnataka",
    "latitude": 12.2707,
    "longitude": 76.5742,
    "fullReservoirLevelMeters": 124.80,
    "maxWaterLevelMeters": 125.50,
    "deadStorageTmc": 4.38,
    "maxCapacityTmc": 49.45,
    "currentTmc": 46.80,
    "waterLevelMeters": 123.90,
    "inflowCusecs": 48000,
    "outflowCusecs": 38000,
    "season": "monsoon",
    "lastUpdated": datetime.now(timezone.utc).isoformat()
}

FARMERS = load_farmers_from_db()
ALERT_LOGS = []
ADMIN_SESSIONS = {}
ADMIN_SESSION_SECONDS = 8 * 60 * 60
PUBLIC_REGISTRATION_TIMES = {}

def admin_token_is_valid(token):
    now = time.time()
    for session_token, expires_at in list(ADMIN_SESSIONS.items()):
        if expires_at <= now:
            ADMIN_SESSIONS.pop(session_token, None)
    return bool(token and token in ADMIN_SESSIONS and ADMIN_SESSIONS[token] > now)

# ==============================================================================
# DISASTER NOTIFICATION DRIVERS (SMS, WHATSAPP, EMAIL)
# ==============================================================================

def send_smtp_email(to_email, subject, body_html, body_text):
    """Sends real email via SMTP if credentials exist in .env, otherwise logs simulated dispatch."""
    env = load_env()
    smtp_user = env.get("SMTP_USER", "").strip()
    smtp_pass = env.get("SMTP_PASS", "").strip()
    smtp_host = env.get("SMTP_HOST", "smtp.gmail.com").strip()
    try:
        smtp_port = int(env.get("SMTP_PORT", 587))
    except ValueError:
        smtp_port = 587
    from_name = env.get("SMTP_FROM_NAME", "JalSuraksha Flood Warning Center")

    # Important: Google App passwords may contain spaces like 'rciw bsne cvew dazo'
    # For SMTP auth, standard passwords must have spaces stripped
    smtp_pass_clean = smtp_pass.replace(' ', '')

    is_configured = env_value_is_configured(smtp_user) and env_value_is_configured(smtp_pass)

    if not to_email or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", to_email):
        return {"status": "INVALID_RECIPIENT", "to": to_email, "provider": "SMTP", "detail": "A valid recipient email address is required."}

    if is_configured:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{from_name} <{smtp_user}>"
            msg["To"] = to_email
            
            part1 = MIMEText(body_text, "plain", "utf-8")
            part2 = MIMEText(body_html, "html", "utf-8")
            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass_clean)
                refused = server.sendmail(smtp_user, [to_email], msg.as_string())
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
            print(f"[OK] REAL SMTP EMAIL SENT to {to_email} from {smtp_user}")
            return {
                "status": "ACCEPTED_BY_SMTP",
                "to": to_email,
                "provider": "Gmail SMTP",
                "detail": f"SMTP accepted the message for {to_email}; final inbox delivery depends on the receiving mail provider."
            }
        except Exception as e:
            print(f"[ERR] SMTP Send Failed: {e}")
            return {
                "status": "SMTP_ERROR",
                "to": to_email,
                "provider": f"SMTP ({smtp_host})",
                "detail": f"SMTP Error: {str(e)}"
            }
    else:
        return {
            "status": "NOT_CONFIGURED",
            "to": to_email,
            "provider": "SMTP",
            "detail": "No email was sent. Set SMTP_USER and SMTP_PASS in the project .env file."
        }

def send_carrier_sms(to_phone, message):
    """Send SMS through Fast2SMS (India) or Twilio; never report a local SMS link as delivered."""
    env = load_env()
    twilio_sid = env.get("TWILIO_ACCOUNT_SID", "").strip()
    twilio_token = env.get("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from = env.get("TWILIO_PHONE_NUMBER", "").strip()
    fast2sms_key = env.get("FAST2SMS_API_KEY", "").strip()
    fast2sms_route = env.get("FAST2SMS_ROUTE", "q").strip() or "q"

    digits = ''.join(c for c in str(to_phone or "") if c.isdigit())
    clean_phone = f"+{digits}" if str(to_phone).strip().startswith("+") else digits
    if len(digits) == 10 and not str(to_phone).strip().startswith("+"):
        clean_phone = "+91" + digits
    elif len(digits) == 12 and digits.startswith("91") and not str(to_phone).strip().startswith("+"):
        clean_phone = "+" + digits
    sms_text = message[:150] # Keep a margin for carrier encoding/segment rules.
    base = {"to": clean_phone, "smsText": sms_text, "chars": len(sms_text)}
    if not re.fullmatch(r"\+?[1-9]\d{7,14}", clean_phone):
        return {"status": "INVALID_RECIPIENT", **base, "detail": "Enter a valid phone number in international format, such as +919876543210."}

    if env_value_is_configured(fast2sms_key):
        if not clean_phone.startswith("+91") or len(digits) != 12:
            return {"status": "INVALID_RECIPIENT", **base, "detail": "Fast2SMS requires an Indian mobile number in +91XXXXXXXXXX format."}
        try:
            payload = json.dumps({"route": fast2sms_route, "message": sms_text, "numbers": digits[-10:]}).encode("utf-8")
            req = urllib.request.Request("https://www.fast2sms.com/dev/bulkV2", data=payload, method="POST")
            req.add_header("Authorization", fast2sms_key)
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("return") is True:
                return {"status": "ACCEPTED_BY_FAST2SMS", **base, "provider": "Fast2SMS", "requestId": result.get("request_id"), "detail": "Fast2SMS accepted the request; carrier delivery is not yet confirmed."}
            return {"status": "SMS_GATEWAY_ERROR", **base, "provider": "Fast2SMS", "detail": str(result.get("message", "Fast2SMS rejected the request."))}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = str(e)
            return {"status": "SMS_GATEWAY_ERROR", **base, "provider": "Fast2SMS", "detail": detail}
        except Exception as e:
            return {"status": "SMS_GATEWAY_ERROR", **base, "provider": "Fast2SMS", "detail": str(e)}

    if all(env_value_is_configured(value) for value in (twilio_sid, twilio_token, twilio_from)):
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
            data = urllib.parse.urlencode({
                "From": twilio_from,
                "To": clean_phone,
                "Body": sms_text
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data)
            auth = base64.b64encode(f"{twilio_sid}:{twilio_token}".encode('utf-8')).decode('ascii')
            req.add_header("Authorization", f"Basic {auth}")
            with urllib.request.urlopen(req, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
                return {
                    "status": f"TWILIO_{str(result.get('status', 'queued')).upper()}",
                    **base,
                    "provider": "Twilio",
                    "messageSid": result.get("sid"),
                    "detail": f"Twilio accepted the message with status {result.get('status', 'queued')}; carrier delivery may update later."
                }
        except Exception as e:
            return {
                "status": "SMS_GATEWAY_ERROR",
                **base,
                "provider": "Twilio",
                "detail": str(e)
            }
    else:
        return {
            "status": "NOT_CONFIGURED",
            **base,
            "smsUrl": f"sms:{clean_phone}?body={urllib.parse.quote(sms_text)}",
            "detail": "No SMS was sent. Configure FAST2SMS_API_KEY (India) or all three Twilio credentials in the project .env file."
        }

# ==============================================================================
# CIVIL HYDROLOGY COMPUTATION
# ==============================================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def calculate_wave_arrival(distance_km, discharge_cusecs):
    if discharge_cusecs <= 500:
        return {"arrivalMinutes": None, "speedKmh": 0, "statusText": "Gates closed"}
    
    speed_kmh = 7.5
    if discharge_cusecs > 20000: speed_kmh = 9.0
    if discharge_cusecs > 50000: speed_kmh = 11.5
    if discharge_cusecs > 80000: speed_kmh = 14.0

    arrival_minutes = round((distance_km / speed_kmh) * 60)
    
    if arrival_minutes < 30:
        msg = f"CRITICAL: Reaching plot in {arrival_minutes} mins! Immediate evacuation!"
    elif arrival_minutes < 60:
        msg = f"HIGH ALERT: Reaching plot in {arrival_minutes} mins. Move livestock & pumps."
    else:
        hrs = round(arrival_minutes / 60, 1)
        msg = f"ADVISORY: Reaching plot in approx {hrs} hours."

    return {
        "arrivalMinutes": arrival_minutes,
        "speedKmh": speed_kmh,
        "statusText": msg
    }

def evaluate_reservoir(dam):
    fill_pct = round((dam["currentTmc"] / dam["maxCapacityTmc"]) * 100, 1)
    season = dam["season"]
    inflow = dam["inflowCusecs"]
    outflow = dam["outflowCusecs"]

    alert_level = "GREEN"
    alert_title = "Normal Condition"
    summary = "Reservoir levels are within safe operating limits."
    gates = "Spillway Gates Closed"

    if season == "monsoon":
        if fill_pct >= 95 or (fill_pct >= 88 and inflow > 50000) or outflow >= 50000:
            alert_level = "RED"
            alert_title = "EMERGENCY: RED FLOOD ALERT"
            summary = f"Peak monsoon crest! Reservoir at {fill_pct}%. Outflow {outflow:,} cusecs. Immediate floodplain evacuation!"
            gates = "Spillway Crest Gates Fully Opened"
        elif fill_pct >= 85 or inflow > 35000 or outflow >= 25000:
            alert_level = "ORANGE"
            alert_title = "HIGH ALERT: ORANGE WARNING"
            summary = f"Storage at {fill_pct}%. High inflow ({inflow:,} cusecs). Spillway discharge active."
            gates = "Radial Gates Partially Opened"
        elif fill_pct >= 75 or inflow > 20000:
            alert_level = "YELLOW"
            alert_title = "ADVISORY: YELLOW ALERT"
            summary = f"Storage at {fill_pct}%. Precautionary monitoring active."
            gates = "Canal Sluices Active"
        else:
            alert_level = "GREEN"
            alert_title = "NORMAL: GREEN SAFE"
            summary = f"Storage at {fill_pct}%. Normal monsoon retention curve."
            gates = "River Base Flow Only"
    elif season == "winter":
        if fill_pct >= 98 or outflow >= 40000:
            alert_level = "RED"
            alert_title = "EMERGENCY: RED SPILLWAY OVERFLOW"
            summary = f"Winter maximum storage exceeded ({fill_pct}%)."
            gates = "Spillway Relief Gates Open"
        elif fill_pct >= 92 or outflow >= 20000:
            alert_level = "ORANGE"
            alert_title = "CAUTION: HIGH WINTER STORAGE"
            summary = f"Rabi storage conservation pool at {fill_pct}%."
            gates = "Canals at Full Supply Depth"
        else:
            alert_level = "GREEN"
            alert_title = "OPTIMAL: WINTER CONSERVATION"
            summary = f"Storage at {fill_pct}%. Rabi irrigation steady."
            gates = "Controlled Canal Supply"
    else:  # summer
        if outflow > 15000:
            alert_level = "ORANGE"
            alert_title = "CANAL SURGE ALERT: SUMMER"
            summary = "Emergency irrigation release into canals."
            gates = "Canal Flushing Active"
        elif fill_pct < 20:
            alert_level = "YELLOW"
            alert_title = "DROUGHT ADVISORY: LOW STORAGE"
            summary = f"Reservoir at {fill_pct}% (Conservation pool). Water rationed."
            gates = "Drinking Water Sluice Only"
        else:
            alert_level = "GREEN"
            alert_title = "NORMAL: SUMMER STAGE"
            summary = f"Storage at {fill_pct}%. Rotational irrigation active."
            gates = "Rotational Supply"

    return {
        "fillPercentage": fill_pct,
        "alertLevel": alert_level,
        "alertTitle": alert_title,
        "summaryMessage": summary,
        "gateStatus": gates
    }

def evaluate_farmer(farmer, dam_eval, outflow):
    dist = farmer["distanceKm"]
    river_dist = farmer.get("distanceFromRiverMeters", 300)
    wave = calculate_wave_arrival(dist, outflow)

    if dam_eval["alertLevel"] == "RED":
        if dist <= 2.0 or river_dist <= 250:
            tier = "CRITICAL"
            badge = "red"
            rec = "MANDATORY EVACUATION: Flash flood danger! Unchain cattle, disconnect pumps, move to high ground!"
        elif dist <= 5.0 or river_dist <= 600:
            tier = "WARNING"
            badge = "orange"
            rec = "PREPARE TO EVACUATE: Move livestock and machinery. Keep torches and essentials ready."
        else:
            tier = "ADVISORY"
            badge = "yellow"
            rec = "FLOOD ADVISORY: Stay clear of canal banks and river crossings."
    elif dam_eval["alertLevel"] == "ORANGE":
        if dist <= 2.0:
            tier = "WARNING"
            badge = "orange"
            rec = "CAUTION: Spillway active. Stay clear of riverbank fields."
        elif dist <= 5.0:
            tier = "ADVISORY"
            badge = "yellow"
            rec = "ADVISORY: River channel rising. Secure irrigation pipes."
        else:
            tier = "SAFE"
            badge = "green"
            rec = "Normal vigilance."
    elif dam_eval["alertLevel"] == "YELLOW":
        if dist <= 2.0:
            tier = "ADVISORY"
            badge = "yellow"
            rec = "EARLY NOTICE: Catchment heavy rain. Dam gates may open in 12-24h."
        else:
            tier = "SAFE"
            badge = "green"
            rec = "Safe. Regular operations."
    else:
        tier = "SAFE"
        badge = "green"
        rec = "Green Safe Zone. Normal irrigation schedule."

    return {
        "riskTier": tier,
        "badgeColor": badge,
        "actionRecommendation": rec,
        "waveArrival": wave
    }

def get_enriched_farmers():
    global FARMERS
    db_farmers = load_farmers_from_db()
    if db_farmers:
        FARMERS = db_farmers
    dam_eval = evaluate_reservoir(DAM_DATA)
    enriched = []
    for f in FARMERS:
        try:
            lat = float(f.get("latitude", 12.27))
            lon = float(f.get("longitude", 76.58))
        except (ValueError, TypeError):
            lat, lon = 12.27, 76.58
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            lat, lon = 12.2680, 76.5910

        dist = haversine_distance(DAM_DATA["latitude"], DAM_DATA["longitude"], lat, lon)
        f_copy = dict(f)
        f_copy["latitude"] = lat
        f_copy["longitude"] = lon
        f_copy["distanceKm"] = dist
        f_copy["riskAssessment"] = evaluate_farmer(f_copy, dam_eval, DAM_DATA["outflowCusecs"])
        enriched.append(f_copy)
    return enriched

# Helper to execute 1-Click 3-Way dispatch for a farmer
def execute_3way_alert(farmer, dam_eval):
    wave = farmer["riskAssessment"]["waveArrival"]
    eta_str = f"~{wave['arrivalMinutes']} mins" if wave["arrivalMinutes"] else "Gates closed"
    phone_clean = ''.join(c for c in farmer["phone"] if c.isdigit())
    farmer_email = farmer.get("email", "").strip()

    # 1. COMPACT 160-CHAR SMS (For keypad / feature phones)
    sms_text = f"ALERT! {DAM_DATA['name']}: Outflow {DAM_DATA['outflowCusecs']:,} cusecs. Flood wave arrives Survey {farmer['surveyNumber']} in {eta_str}. Evacuate cattle & motors! -Govt"
    sms_result = send_carrier_sms(farmer["phone"], sms_text)

    # 2. RICH WHATSAPP MESSAGE
    whatsapp_text = (
        f"🌊 *JAL-SURAKSHA FLOOD ALERT* - {DAM_DATA['name']}\n"
        f"Namaskara *{farmer['name']}*,\n"
        f"📍 *Survey Plot*: {farmer['surveyNumber']} ({farmer['village']})\n"
        f"⚠️ *Status*: {dam_eval['alertTitle']}\n"
        f"💧 *Storage*: {DAM_DATA['currentTmc']} TMC ({dam_eval['fillPercentage']}% Capacity)\n"
        f"🚪 *Spillway Outflow*: {DAM_DATA['outflowCusecs']:,} cusecs\n"
        f"⏱️ *Flood Wave Arrival*: {eta_str}\n"
        f"🚨 *Advisory*: {farmer['riskAssessment']['actionRecommendation']}\n"
        f"Issued by: Mandya / Mysuru Disaster Management Authority"
    )
    whatsapp_url = f"https://api.whatsapp.com/send?phone={phone_clean}&text={urllib.parse.quote(whatsapp_text)}"

    # 3. HTML & PLAIN TEXT EMAIL (SMTP via .env)
    email_subject = f"🚨 FLOOD EMERGENCY: {DAM_DATA['name']} Outflow Alert - Survey No. {farmer['surveyNumber']}"
    email_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #dc2626; color: #ffffff; padding: 18px 24px;">
            <h2 style="margin: 0; font-size: 20px;">🌊 JAL-SURAKSHA: DAM FLOOD WARNING</h2>
            <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">Civil Disaster Management Authority • {DAM_DATA['name']}</p>
        </div>
        <div style="padding: 24px; background-color: #ffffff; color: #1e293b;">
            <p style="font-size: 15px;">Dear <b>{farmer['name']}</b>,</p>
            <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; margin: 16px 0;">
                <p style="margin: 0; font-weight: bold; color: #991b1b;">{dam_eval['alertTitle']}</p>
                <p style="margin: 4px 0 0 0; font-size: 13px; color: #7f1d1d;">{dam_eval['summaryMessage']}</p>
            </div>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin: 16px 0;">
                <tr style="border-bottom: 1px solid #f1f5f9;"><td style="padding: 8px 0; color: #64748b;">Land Survey Number:</td><td style="padding: 8px 0; font-weight: bold; color: #0f172a;">{farmer['surveyNumber']}</td></tr>
                <tr style="border-bottom: 1px solid #f1f5f9;"><td style="padding: 8px 0; color: #64748b;">Village / Taluk:</td><td style="padding: 8px 0; color: #0f172a;">{farmer['village']}</td></tr>
                <tr style="border-bottom: 1px solid #f1f5f9;"><td style="padding: 8px 0; color: #64748b;">Current Storage:</td><td style="padding: 8px 0; font-weight: bold; color: #0284c7;">{DAM_DATA['currentTmc']} TMC ({dam_eval['fillPercentage']}%)</td></tr>
                <tr style="border-bottom: 1px solid #f1f5f9;"><td style="padding: 8px 0; color: #64748b;">Spillway Outflow:</td><td style="padding: 8px 0; font-weight: bold; color: #dc2626;">{DAM_DATA['outflowCusecs']:,} cusecs</td></tr>
                <tr style="border-bottom: 1px solid #f1f5f9;"><td style="padding: 8px 0; color: #64748b;">Estimated Wave Arrival:</td><td style="padding: 8px 0; font-weight: bold; color: #dc2626;">{eta_str}</td></tr>
            </table>
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; margin-top: 16px;">
                <p style="margin: 0; font-size: 12px; font-weight: bold; color: #334155;">ACTIONABLE ADVISORY:</p>
                <p style="margin: 4px 0 0 0; font-size: 13px; color: #475569;">{farmer['riskAssessment']['actionRecommendation']}</p>
            </div>
        </div>
        <div style="background-color: #f1f5f9; padding: 12px 24px; font-size: 11px; color: #64748b; text-align: center;">
            Automated Alert System • Multi-channel SMS, WhatsApp & Email Integration
        </div>
    </div>
    """
    email_text = f"JAL-SURAKSHA FLOOD ALERT - {DAM_DATA['name']}\nDear {farmer['name']}, Survey No: {farmer['surveyNumber']} ({farmer['village']})\nStatus: {dam_eval['alertTitle']}\nOutflow: {DAM_DATA['outflowCusecs']:,} cusecs\nETA: {eta_str}\nAction: {farmer['riskAssessment']['actionRecommendation']}"
    email_result = send_smtp_email(farmer_email, email_subject, email_html, email_text)

    dispatch_item = {
        "id": f"ALERT-{int(time.time()*1000)%1000000}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "farmerId": farmer["id"],
        "farmerName": farmer["name"],
        "phone": farmer["phone"],
        "email": farmer_email,
        "surveyNumber": farmer["surveyNumber"],
        "tier": farmer["riskAssessment"]["riskTier"],
        "channel": "1-CLICK 3-WAY (SMS + WHATSAPP + EMAIL)",
        "channels": {
            "sms": sms_result,
            "whatsapp": {
                "status": "READY_AND_DISPATCHED",
                "url": whatsapp_url,
                "text": whatsapp_text
            },
            "email": email_result
        },
        "summary": f"Dispatched via 3 Channels: SMS ({sms_result['status']}), WhatsApp, Email ({email_result['status']})",
        "whatsappUrl": whatsapp_url,
        "smsUrl": sms_result.get("smsUrl", "")
    }
    return dispatch_item

class SingleInstanceHTTPServer(HTTPServer):
    # Windows can otherwise let multiple local listeners share port 5000,
    # causing browser requests to land on stale server instances.
    allow_reuse_address = False


class DamAPIHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def _require_admin(self):
        authorization = self.headers.get('Authorization', '')
        token = authorization[7:].strip() if authorization.lower().startswith('bearer ') else ''
        if admin_token_is_valid(token):
            return True
        self._set_headers(401)
        self.wfile.write(json.dumps({"error": "Admin sign-in required."}).encode())
        return False

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ['/api/farmers', '/api/alerts/history', '/api/env-status'] and not self._require_admin():
            return

        if path in ['/', '/index.html']:
            html_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html')
            try:
                with open(html_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        elif path in ['/farmer', '/farmer.html']:
            html_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'farmer.html')
            try:
                with open(html_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        elif path == '/api/public/dam':
            evaluation = evaluate_reservoir(DAM_DATA)
            self._set_headers(200)
            self.wfile.write(json.dumps({"dam": DAM_DATA, "evaluation": evaluation, "demoTelemetry": True}).encode())
        elif path == '/api/admin/session':
            if not self._require_admin():
                return
            self._set_headers(200)
            self.wfile.write(json.dumps({"authenticated": True}).encode())
        elif path == '/api/dam':
            evaluation = evaluate_reservoir(DAM_DATA)
            self._set_headers(200)
            self.wfile.write(json.dumps({"dam": DAM_DATA, "evaluation": evaluation}).encode())
        elif path == '/api/farmers':
            enriched = get_enriched_farmers()
            self._set_headers(200)
            self.wfile.write(json.dumps({"total": len(enriched), "farmers": enriched}).encode())
        elif path == '/api/alerts/history':
            self._set_headers(200)
            self.wfile.write(json.dumps({"total": len(ALERT_LOGS), "logs": ALERT_LOGS}).encode())
        elif path == '/api/env-status':
            env = load_env()
            smtp_user = env.get("SMTP_USER", "").strip()
            smtp_pass = env.get("SMTP_PASS", "").strip()
            is_smtp_set = env_value_is_configured(smtp_user) and env_value_is_configured(smtp_pass)
            has_twilio = all(env_value_is_configured(env.get(key)) for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"))
            has_fast2sms = env_value_is_configured(env.get("FAST2SMS_API_KEY"))
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "smtpConfigured": is_smtp_set,
                "smtpUser": "Configured" if is_smtp_set else "Not configured",
                "smtpHost": env.get("SMTP_HOST", "smtp.gmail.com"),
                "smsConfigured": has_twilio or has_fast2sms,
                "smsProvider": "Fast2SMS" if has_fast2sms else ("Twilio" if has_twilio else "Not configured"),
                "instructions": "Set FAST2SMS_API_KEY or Twilio credentials for SMS. SMTP uses SMTP_USER and SMTP_PASS."
            }).encode())
        elif path == '/api/system-info':
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "system": "JalSuraksha 3-Way Multi-Channel Flood Alert System",
                "version": "2.2.0",
                "channels": ["SMS (Feature Phones)", "WhatsApp (Smartphones)", "SMTP Email (Landowners & Officials)"],
                "department": "Department of Civil Engineering",
                "curriculum": "5th Semester Capstone Project",
                "standards": "CWC Reservoir Rule Curves & IS 7323",
                "hydraulicModel": "Manning wave celerity + Haversine geofencing"
            }).encode())
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode())

    def do_POST(self):
        global FARMERS
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(post_data.decode('utf-8')) if post_data else {}

        if path == '/api/admin/logout':
            authorization = self.headers.get('Authorization', '')
            token = authorization[7:].strip() if authorization.lower().startswith('bearer ') else ''
            ADMIN_SESSIONS.pop(token, None)
            self._set_headers(200)
            self.wfile.write(json.dumps({"loggedOut": True}).encode())
            return

        if path in ['/api/dam/update', '/api/farmers/register', '/api/alerts/broadcast', '/api/alerts/broadcast-3way', '/api/alerts/send-farmer-3way'] and not self._require_admin():
            return

        if path == '/api/admin/login':
            env = load_env()
            expected_user = env.get('ADMIN_USERNAME', 'admin').strip()
            expected_password = env.get('ADMIN_PASSWORD', '').strip()
            if not env_value_is_configured(expected_password):
                self._set_headers(503)
                self.wfile.write(json.dumps({"error": "Set a strong ADMIN_PASSWORD in the project .env file, then restart the server."}).encode())
                return
            supplied_user = str(body.get('username', '')).strip()
            supplied_password = str(body.get('password', ''))
            if not hmac.compare_digest(supplied_user, expected_user) or not hmac.compare_digest(supplied_password, expected_password):
                self._set_headers(401)
                self.wfile.write(json.dumps({"error": "Username or password is incorrect."}).encode())
                return
            token = secrets.token_urlsafe(36)
            ADMIN_SESSIONS[token] = time.time() + ADMIN_SESSION_SECONDS
            self._set_headers(200)
            self.wfile.write(json.dumps({"token": token, "expiresIn": ADMIN_SESSION_SECONDS}).encode())
            return

        if path == '/api/dam/update':
            if "currentTmc" in body: DAM_DATA["currentTmc"] = float(body["currentTmc"])
            if "waterLevelMeters" in body: DAM_DATA["waterLevelMeters"] = float(body["waterLevelMeters"])
            if "inflowCusecs" in body: DAM_DATA["inflowCusecs"] = int(body["inflowCusecs"])
            if "outflowCusecs" in body: DAM_DATA["outflowCusecs"] = int(body["outflowCusecs"])
            if "season" in body: DAM_DATA["season"] = str(body["season"])
            DAM_DATA["lastUpdated"] = datetime.now(timezone.utc).isoformat()
            
            evaluation = evaluate_reservoir(DAM_DATA)
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "message": "Dam hydrology updated",
                "dam": DAM_DATA,
                "evaluation": evaluation
            }).encode())

        elif path in ['/api/farmers/register', '/api/public/farmers/register']:
            is_public_registration = path == '/api/public/farmers/register'
            if is_public_registration and body.get('website'):
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Registration could not be processed."}).encode())
                return
            if is_public_registration:
                now = time.time()
                client_ip = self.client_address[0]
                recent = [stamp for stamp in PUBLIC_REGISTRATION_TIMES.get(client_ip, []) if now - stamp < 3600]
                if len(recent) >= 5:
                    self._set_headers(429)
                    self.wfile.write(json.dumps({"error": "Too many registration attempts. Please try again later."}).encode())
                    return
                recent.append(now)
                PUBLIC_REGISTRATION_TIMES[client_ip] = recent

            name = str(body.get("name", "")).strip()
            survey_number = str(body.get("surveyNumber", "")).strip()
            village = str(body.get("village", "")).strip()
            district = str(body.get("district", "")).strip()
            email = str(body.get("email", "")).strip().lower()
            phone = str(body.get("phone", "")).strip()
            if is_public_registration and (not name or not survey_number or not village or not district or not body.get('consent')):
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Complete the required fields and consent before submitting."}).encode())
                return
            if len(name) > 100 or len(survey_number) > 50 or len(village) > 100 or len(district) > 100:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "One or more fields are too long."}).encode())
                return
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Enter a valid farmer email address for alerts."}).encode())
                return
            phone_digits = ''.join(c for c in phone if c.isdigit())
            if not re.fullmatch(r"(?:\+?91)?[6-9]\d{9}", phone) and not re.fullmatch(r"(?:91)?[6-9]\d{9}", phone_digits):
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Enter a valid Indian mobile number, with or without the +91 country code."}).encode())
                return
            phone = '+91' + (phone_digits[-10:])
            if is_public_registration:
                existing = load_farmers_from_db()
                email_in_use = any(str(f.get('email', '')).strip().lower() == email for f in existing)
                phone_in_use = any(''.join(c for c in str(f.get('phone', '')) if c.isdigit())[-10:] == phone_digits[-10:] for f in existing)
                if email_in_use or phone_in_use:
                    self._set_headers(409)
                    self.wfile.write(json.dumps({"error": "These contact details are already registered. Contact the dam office to correct an existing record."}).encode())
                    return
            try:
                lat = float(body.get("latitude")) if is_public_registration else float(body.get("latitude", 12.2680))
                lon = float(body.get("longitude")) if is_public_registration else float(body.get("longitude", 76.5910))
            except (ValueError, TypeError):
                if is_public_registration:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "Provide valid farmland latitude and longitude."}).encode())
                    return
                lat, lon = 12.2680, 76.5910

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                if is_public_registration:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "Farmland coordinates must be within valid latitude and longitude ranges."}).encode())
                    return
                lat, lon = 12.2680, 76.5910

            try:
                land_area = max(0.1, min(float(body.get("landAreaAcres", 2.0)), 10000.0))
            except (ValueError, TypeError):
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Enter a valid land area in acres."}).encode())
                return

            dist = haversine_distance(DAM_DATA["latitude"], DAM_DATA["longitude"], lat, lon)
            
            farmer_id = f"FARM-{uuid.uuid4().hex[:12].upper()}"

            new_f = {
                "id": farmer_id,
                "name": name or str(body.get("name", "Farmer")).strip(),
                "phone": phone,
                "email": email,
                "surveyNumber": survey_number or body.get("surveyNumber", "0/0"),
                "village": village or body.get("village", "Cauvery Basin"),
                "district": district or body.get("district", "Mandya"),
                "cropType": body.get("cropType", "Paddy (Rice)"),
                "landAreaAcres": land_area,
                "latitude": lat,
                "longitude": lon,
                "distanceKm": dist,
                "distanceFromRiverMeters": int(body.get("distanceFromRiverMeters", 300)),
                "notes": body.get("notes", "Registered land")
            }
            
            # Prepend and save to persistent DB
            FARMERS.insert(0, new_f)
            save_farmers_to_db(FARMERS)

            dam_eval = evaluate_reservoir(DAM_DATA)
            risk = evaluate_farmer(new_f, dam_eval, DAM_DATA["outflowCusecs"])
            new_f["riskAssessment"] = risk

            self._set_headers(201)
            if is_public_registration:
                response_data = {
                    "message": "Registration received. The operations team can now review your details.",
                    "farmer": {"id": new_f["id"], "name": new_f["name"], "surveyNumber": new_f["surveyNumber"]}
                }
            else:
                response_data = {
                    "message": "Farmer registration saved successfully.",
                    "farmer": new_f,
                    "allFarmers": get_enriched_farmers()
                }
            self.wfile.write(json.dumps(response_data).encode())

        # 1-CLICK 3-WAY BROADCAST TO ALL/ZONE FARMERS
        elif path in ['/api/alerts/broadcast', '/api/alerts/broadcast-3way']:
            target_zone = body.get("targetZone", "0-2km")
            enriched = get_enriched_farmers()
            dam_eval = evaluate_reservoir(DAM_DATA)

            if target_zone == '0-2km':
                recipients = [f for f in enriched if f["distanceKm"] <= 2.0]
            elif target_zone == '2-5km':
                recipients = [f for f in enriched if 2.0 < f["distanceKm"] <= 5.0]
            elif target_zone == 'all-critical':
                recipients = [f for f in enriched if f["riskAssessment"]["riskTier"] == 'CRITICAL']
            else:
                recipients = enriched

            new_dispatches = []
            for f in recipients:
                dispatch_item = execute_3way_alert(f, dam_eval)
                new_dispatches.append(dispatch_item)
                ALERT_LOGS.insert(0, dispatch_item)

            self._set_headers(200)
            self.wfile.write(json.dumps({
                "message": f"⚡ 1-Click 3-Way Alert Broadcast dispatched to {len(new_dispatches)} farmers via SMS + WhatsApp + Email!",
                "count": len(new_dispatches),
                "targetZone": target_zone,
                "dispatches": new_dispatches
            }).encode())

        # 1-CLICK 3-WAY ALERT FOR A SINGLE FARMER (ROBUST MULTI-KEY MATCHING)
        elif path == '/api/alerts/send-farmer-3way':
            farmer_id = str(body.get("farmerId", "")).strip().lower()
            phone = str(body.get("phone", "")).strip()
            survey = str(body.get("surveyNumber", "")).strip().lower()
            email = str(body.get("email", "")).strip().lower()

            enriched = get_enriched_farmers()
            dam_eval = evaluate_reservoir(DAM_DATA)
            
            # Match the selected database record first. Never let a duplicate
            # phone, survey number, or email redirect an alert to another farmer.
            target = next(
                (f for f in enriched if farmer_id and str(f.get("id", "")).strip().lower() == farmer_id),
                None
            )

            # Compatibility fallback for older clients that send no farmer ID.
            if not farmer_id:
                clean_target_phone = ''.join(c for c in phone if c.isdigit())
                candidates = []
                if email:
                    candidates = [f for f in enriched if str(f.get("email", "")).strip().lower() == email]
                if not candidates and clean_target_phone:
                    candidates = [
                        f for f in enriched
                        if ''.join(c for c in str(f.get("phone", "")) if c.isdigit()) == clean_target_phone
                    ]
                if not candidates and survey:
                    candidates = [f for f in enriched if str(f.get("surveyNumber", "")).strip().lower() == survey]
                if len(candidates) == 1:
                    target = candidates[0]

            if not target:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Farmer not found. No alert was sent; check the exact farmer ID, phone, survey number, or email."}).encode())
                return

            dispatch_item = execute_3way_alert(target, dam_eval)
            ALERT_LOGS.insert(0, dispatch_item)

            self._set_headers(200)
            self.wfile.write(json.dumps({
                "message": f"⚡ 3-Way Alert sent to {target['name']} via SMS, WhatsApp, and Email simultaneously!",
                "dispatch": dispatch_item
            }).encode())
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown POST endpoint"}).encode())

def run_server(port=None):
    if port is None:
        try:
            port = int(load_env().get("PORT", "5000"))
        except ValueError:
            port = 5000
    server_address = ('127.0.0.1', port)
    try:
        httpd = SingleInstanceHTTPServer(server_address, DamAPIHandler)
    except OSError as error:
        raise OSError(f"Could not start JalSuraksha on port {port}. Stop the other server using that port, then run start.bat again.") from error
    print("=======================================================")
    print("[*] JALSURAKSHA 3-WAY MULTI-CHANNEL SERVER ACTIVE")
    print(f"[*] Dashboard & API: http://127.0.0.1:{port}")
    print("[*] Channels: [1] SMS (160-char)  [2] WhatsApp  [3] SMTP Email (.env)")
    print("=======================================================")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
