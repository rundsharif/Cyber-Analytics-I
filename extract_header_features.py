
import argparse
import os
import ujson
from email import message_from_string
from io_helpers import change_filename
from email.utils import parseaddr, parsedate_tz, getaddresses
import re
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument("--input", "-i", help="The name of the file to get features from", required=True)
parser.add_argument("--output", "-o", help="The name of the file to output to", required=False)
parser.add_argument("--debug", "-d", help="debug mode", action="store_true", required=False)



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
    

    features['display_name_mismatch'] = bool(display_name) and (display_name.lower() != from_email.lower())
    
    # Reply-To different from From
    reply_to = parseaddr(safe_header_get(msg, 'Reply-To'))[1]
    features['reply_to_differs'] = bool(reply_to) and (reply_to.lower() != from_email.lower())
    
    return features

def get_structural_features(msg): # adds 4 features
    features = {}
    
    # Message-ID: RFC 5322 requires this, absence is suspicious
    features['missing_message_id'] = 'Message-ID' not in msg
    
    # Received headers count
    # Reasoning: Legitimate emails have 3-10 Received headers typically
    # Too few suggests direct injection, too many suggests relay abuse
    received_headers = msg.get_all('Received', [])
    features['received_count'] = len(received_headers)
    
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


def get_all_features(raw_heads_string, og_fname):

    try:
        msg = message_from_string(raw_heads_string)

        features = {}
        features.update(get_authenticity_features(msg))
        features.update(get_sender_features(msg))
        features.update(get_structural_features(msg))
        features.update(get_temporal_features(msg))
        features.update(get_encoding_features(msg))

        return features

    except Exception as e:
        print(f"failed data from original file: {og_fname}")
        raise e
    


def process_jlines(input, output):
    with open(input, "r",encoding='utf-8') as f, open(output, 'w', encoding='utf-8') as wf:

        for i, line in enumerate(f, 1):
            in_dict = ujson.loads(line)
            features = get_all_features(in_dict.get('raw_headers', ''), in_dict.get('og_fname', ''))

            wf.write(ujson.dumps(features,ensure_ascii=False) + "\n")


if __name__ == "__main__":
    args = parser.parse_args()
    infile = args.input
    outfile = args.output
    debug = args.debug
    if not outfile:
        outfile = change_filename(infile, "csv", "features")
    elif os.path.exists(outfile):
        if input(f"please enter anything if you want to first delete the existing output file {outfile}: \n"):
            os.remove(outfile)
    
    process_jlines(infile, outfile)