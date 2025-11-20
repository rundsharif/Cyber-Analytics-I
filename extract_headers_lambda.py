
import argparse
import os
import ujson
from email import message_from_string
from io_helpers import change_filename
from email.utils import parseaddr, parsedate_tz, getaddresses
import re
from datetime import datetime

def safe_header_get(msg, header_name, default=""):
    """
    Reasoning: Phishing emails may have duplicate, missing, or malformed headers.
    Using .get() prevents KeyErrors, and returning a default ensures 
    downstream functions don't break on None values.
    """
    try:
        value = msg.get(header_name, default)
        return value if value is not None else default
    except Exception:
        return default




def get_authenticity_features(msg): # adds 4 features
    features = {}
    
    # DKIM: Look for DKIM-Signature header
    # Reasoning: DKIM is a specific header, simple presence check
    features['has_dkim'] = 'DKIM-Signature' in msg
    
    # SPF: Check Authentication-Results for SPF info
    # Reasoning: SPF isn't a header itself, but results appear in Authentication-Results
    auth_results = safe_header_get(msg, 'Authentication-Results', '')
    features['has_spf'] = 'spf=' in auth_results.lower()
    
    # Domain mismatch: Compare From and Return-Path domains
    # Reasoning: This is a classic phishing indicator
    from_addr = parseaddr(safe_header_get(msg, 'From'))[1]
    return_path = safe_header_get(msg, 'Return-Path', '').strip('<>')
    
    from_domain = from_addr.split('@')[-1].lower() if '@' in from_addr else ''
    return_domain = return_path.split('@')[-1].lower() if '@' in return_path else ''
    
    features['from_return_mismatch'] = (from_domain != return_domain) and bool(from_domain and return_domain)
    
    features['has_auth_results'] = bool(auth_results)
    
    return features

FREE_EMAIL_PROVIDERS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 
    'aol.com', 'icloud.com', 'mail.com', 'protonmail.com',
    'yandex.com', 'zoho.com', 'gmx.com'
}
def get_sender_features(msg): # adds 4 fatures
    features = {}
    
    # Parse From header: "Display Name <email@domain.com>"
    from_header = safe_header_get(msg, 'From')
    display_name, from_email = parseaddr(from_header)
    
    from_domain = from_email.split('@')[-1].lower() if '@' in from_email else ''
    features['from_free_provider'] = from_domain in FREE_EMAIL_PROVIDERS
    
    # Numbers in email address (excluding domain)
    email_local = from_email.split('@')[0] if '@' in from_email else from_email
    features['from_has_numbers'] = bool(re.search(r'\d', email_local))
    # NEW: Check if display name is missing/empty (suspicious for legitimate senders)
    # Reasoning: Phishing emails often have bare addresses with no display name
    features['display_name_empty'] = not bool(display_name and display_name.strip())
    
    # NEW: Check if display name exactly matches email (redundant, slightly suspicious)
    # Reasoning: "john@company.com <john@company.com>" is unusual
    features['display_name_is_email'] = (
        display_name.lower().strip() == from_email.lower().strip()
    ) if display_name else False
    
    # Reply-To different from From
    reply_to = parseaddr(safe_header_get(msg, 'Reply-To'))[1]
    features['reply_to_differs'] = bool(reply_to) and (reply_to.lower() != from_email.lower())
    
    return features

def get_data_quality_features(msg, all_features): # adds 4 features
    """
    Reasoning: Separate "poorly formatted email" from "malicious email" signals.
    This prevents the model from learning spurious correlations like 
    "malformed date = phishing" when it might just be "old email system".
    
    Call this AFTER all other feature extraction to analyze the extracted features.
    """
    features = {}
    
    # Invalid/malformed date
    # Reasoning: day_of_week == -1 indicates parsing failure
    features['has_valid_date'] = all_features.get('day_of_week', -1) != -1
    
    # Extreme content-type complexity (likely malformed header)
    # Reasoning: Normal emails have 0-3 semicolons; 100+ suggests corruption/attack
    complexity = all_features.get('content_type_complexity', 0)
    features['has_extreme_complexity'] = complexity > 10
    
    # Unusual timezone (outside normal range)
    # Reasoning: Valid timezones are -12 to +14 hours (-43200 to +50400 seconds)
    # Values outside this suggest malformed or spoofed headers
    tz_offset = all_features.get('timezone_offset', 0)
    features['has_unusual_timezone'] = abs(tz_offset) > 50400
    
    # Overall data quality score (0-3, higher = better quality)
    # Reasoning: Provides a single metric for "how well-formed is this email"
    features['data_quality_score'] = sum([
        features['has_valid_date'],
        not features['has_extreme_complexity'],
        not features['has_unusual_timezone']
    ])
    
    return features

def get_structural_features(msg): # adds 4 features
    features = {}
    
    # Message-ID: RFC 5322 requires this, absence is suspicious
    features['missing_message_id'] = 'Message-ID' not in msg
        
    # X-Mailer: Indicates email client used
    features['has_x_mailer'] = 'X-Mailer' in msg
    
    # Content-Type complexity
    # Reasoning: Multipart messages with many boundaries can hide malicious content
    content_type = safe_header_get(msg, 'Content-Type', '')
    # Count semicolons as proxy for complexity (parameters)
    features['content_type_complexity'] = content_type.count(';')
    
    return features

def get_temporal_features(msg): # adds 3 features
    features = {}
    
    date_str = safe_header_get(msg, 'Date')
    
    try:
        # parsedate_tz returns tuple: (year, month, day, hour, min, sec, weekday, yearday, isdst, tz_offset)
        # Reasoning: This handles various date formats per RFC 2822
        parsed = parsedate_tz(date_str)
        
        if parsed:
            dt = datetime(*parsed[:6])
            
            # Business hours: 8 AM - 6 PM Monday-Friday
            # Reasoning: Phishing campaigns often send outside business hours
            is_weekday = dt.weekday() < 5
            is_business_time = 8 <= dt.hour < 18
            features['sent_business_hours'] = is_weekday and is_business_time
            
            # Timezone offset in seconds (converted from parsed[9] which is in seconds)
            features['timezone_offset'] = parsed[9] if parsed[9] is not None else 0
            
            # Day of week (0=Monday, 6=Sunday)
            features['day_of_week'] = dt.weekday()
            
        else:
            # Malformed date
            features['sent_business_hours'] = False
            features['timezone_offset'] = 0
            features['day_of_week'] = -1  # Indicator of missing/malformed
            
    except Exception:
        features['sent_business_hours'] = False
        features['timezone_offset'] = 0
        features['day_of_week'] = -1
    
    return features

def get_encoding_features(msg): #adds 4 features
    features = {}
    
    # Base64 encoding check
    # Reasoning: Look in Content-Transfer-Encoding header and body of headers
    cte = safe_header_get(msg, 'Content-Transfer-Encoding', '').lower()
    features['uses_base64'] = 'base64' in cte
    
    # Quoted-printable
    features['uses_quoted_printable'] = 'quoted-printable' in cte
    
    # Unicode in From/Subject
    # Reasoning: Encoded words like =?UTF-8?B?...?= or actual non-ASCII chars
    from_header = safe_header_get(msg, 'From')
    subject_header = safe_header_get(msg, 'Subject')
    
    def has_unicode(text):
        # Check for encoded words or non-ASCII characters
        has_encoded_word = '=?' in text and '?=' in text
        has_non_ascii = any(ord(char) > 127 for char in text)
        return has_encoded_word or has_non_ascii
    
    features['unicode_in_from'] = has_unicode(from_header)
    features['unicode_in_subject'] = has_unicode(subject_header)
    
    return features


def get_received_path_features(msg): # adds 4 features
    """
    Reasoning: The simple received_count is good, but analyzing the path
    characteristics provides additional signal. Multiple unique IPs suggest
    legitimate routing; zero or single IP suggests direct injection or spoofing.
    """
    features = {}
    
    received_headers = msg.get_all('Received', [])
    features['received_count'] = len(received_headers)  # Keep the original
    
    # Extract IPs from Received headers
    # Reasoning: Each legitimate relay adds its IP; we count unique IPs
    ip_pattern = r'\[?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]?'
    all_ips = []
    
    for header in received_headers:
        # Convert to string in case it's a Header object
        header_str = str(header)
        ips = re.findall(ip_pattern, header_str)
        all_ips.extend(ips)
    
    unique_ips = set(all_ips)
    features['unique_relay_ips'] = len(unique_ips)
    
    # Check if all received headers have localhost/private IPs
    # Reasoning: 127.0.0.1, 10.x.x.x, 192.168.x.x suggest internal/test systems
    private_ip_pattern = r'^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)'
    
    if all_ips:
        private_count = sum(
            1 for ip in all_ips if re.match(private_ip_pattern, ip)
        )
        features['all_private_ips'] = (private_count == len(all_ips))
    else:
        features['all_private_ips'] = False
    
    # Ratio of unique IPs to total received headers
    # Reasoning: Duplicate IPs across hops is unusual; might indicate spoofing
    if received_headers:
        features['ip_diversity_ratio'] = len(unique_ips) / len(received_headers)
    else:
        features['ip_diversity_ratio'] = 0.0
    
    return features

def get_header_features(parsed_eml):
    raw_heads_string = parsed_eml.get('raw_headers', '')
    og_fname = parsed_eml.get('og_fname', '')

    try:
        msg = message_from_string(raw_heads_string)

        features = {"email_id":parsed_eml["email_id"]}
        features.update(get_authenticity_features(msg))
        features.update(get_sender_features(msg))
        features.update(get_structural_features(msg))
        features.update(get_temporal_features(msg))
        features.update(get_encoding_features(msg))
        features.update(get_received_path_features(msg))

        features.update(get_data_quality_features(msg, features))  # 4 features (NEW)

        return features

    except Exception as e:
        print(f"failed data from original file: {og_fname}")
        raise e