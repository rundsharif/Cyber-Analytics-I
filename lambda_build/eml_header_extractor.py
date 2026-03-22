import email
from email import policy
import re
import json

PRIVATE_IP = re.compile(
    r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.|127\.|169\.254\.)"
)

def extract_first_public_ip(received_headers):
    all_ips = re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", "\n".join(received_headers))
    for ip in all_ips:
        if not PRIVATE_IP.match(ip):
            return ip
    return None

def extract_header_features_from_eml(raw_bytes):
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    headers = dict(msg.items())
    received_headers = msg.get_all("Received", []) or []

    features = {}

    # Basic behavior features
    features["received_count"] = len(received_headers)
    features["unique_relay_ips"] = len(set(extract_first_public_ip(received_headers) or []))
    features["from_return_mismatch"] = int(
        headers.get("From") and headers.get("Return-Path") and
        headers.get("From") != headers.get("Return-Path")
    )
    features["reply_to_differs"] = int(
        headers.get("Reply-To") and headers.get("From") != headers.get("Reply-To")
    )
    features["missing_message_id"] = int("Message-ID" not in headers)

    # SPF/DKIM
    hjson = json.dumps(headers).lower()
    features["has_spf"] = int("spf" in hjson)
    features["has_dkim"] = int("dkim" in hjson)
    features["has_auth_results"] = int("authentication-results" in hjson)

    # Misc heuristics
    features["has_x_mailer"] = int("X-Mailer" in headers)
    features["display_name_empty"] = int("<" in headers.get("From", "") and headers.get("From").split("<")[0].strip() == "")
    features["from_free_provider"] = int(any(x in headers.get("From","").lower() for x in ["gmail","yahoo","outlook"]))

    # Subject checks
    subj = headers.get("Subject","")
    features["unicode_in_subject"] = int(any(ord(c) > 127 for c in subj))

    # Time features
    features["timezone_offset"] = 0
    features["day_of_week"] = 0
    features["sent_business_hours"] = 1

    # Dummy placeholders for fields your model expects
    features.setdefault("content_type_complexity", 1)
    features.setdefault("uses_base64", 0)
    features.setdefault("uses_quoted_printable", 0)
    features.setdefault("unicode_in_from", 0)
    features.setdefault("ip_diversity_ratio", 0)

    return {
        "email_id": headers.get("Message-ID", ""),
        "raw_headers": "\n".join(received_headers),
        "header_features": features,
        "subject": subj
    }
