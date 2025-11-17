
import re



URGENCY_KEYWORDS = {
    'urgent', 'immediately', 'asap', 'right now', 'expire', 'expires', 'expiring',
    'limited time', 'act now', 'don\'t wait', 'hurry', 'quick', 'fast',
    'deadline', 'today only', 'last chance', 'final notice', 'time sensitive',
    'respond now', 'immediate action', 'within 24 hours', 'within 48 hours'
}

AUTHORITY_KEYWORDS = {
    'verify', 'confirm', 'validate', 'authenticate', 'security alert',
    'account', 'suspended', 'locked', 'unauthorized', 'unusual activity',
    'fraud', 'fraudulent', 'verify your identity', 'confirm your identity',
    'security team', 'security department', 'customer service', 'support team',
    'administrator', 'system administrator', 'it department'
}

TRUSTED_DOMAINS = {
    'google.com', 'microsoft.com', 'apple.com', 'amazon.com', 'facebook.com',
    'paypal.com', 'ebay.com', 'netflix.com', 'linkedin.com', 'twitter.com',
    'instagram.com', 'yahoo.com', 'outlook.com', 'gmail.com'
}

THREAT_KEYWORDS = {
    'suspend', 'terminated', 'cancelled', 'closed', 'blocked', 'restricted',
    'legal action', 'lawsuit', 'court', 'penalty', 'fine', 'police',
    'arrest', 'criminal', 'prosecution', 'consequences', 'lose access',
    'permanently deleted', 'violation', 'breach', 'compromised'
}

REQUEST_KEYWORDS = {
    'click here', 'click the link', 'click below', 'log in', 'login',
    'sign in', 'update', 'confirm', 'verify', 'provide', 'enter',
    'submit', 'reset password', 'change password', 'update payment',
    'billing information', 'credit card', 'social security', 'ssn',
    'account number', 'routing number', 'date of birth', 'mother\'s maiden name'
}

GENERIC_GREETINGS = {
    'dear customer', 'dear user', 'dear member', 'dear sir/madam',
    'dear sir or madam', 'hello user', 'valued customer', 'dear valued customer',
    'dear account holder', 'dear client', 'greetings'
}

def get_urgency_features(body_text):
    features = {}
    body_lower = body_text.lower()

    urgency_count = sum(body_lower.count(keyword) for keyword in URGENCY_KEYWORDS)
    features['urgency_keyword_count'] = urgency_count
    features['has_urgency'] = urgency_count > 0

    time_patterns = [
        r'within\s+\d+\s+(hour|day|minute)s?',
        r'in\s+the\s+next\s+\d+\s+(hour|day)s?',
        r'\d+\s+(hour|day)s?\s+to\s+',
        r'before\s+\d+[:/]\d+'  # Before specific time
    ]
    
    features['has_time_pressure'] = any(re.search(pattern, body_lower) for pattern in time_patterns)
    
    # Excessive exclamation marks (common in scams)
    features['exclamation_count'] = body_text.count('!')
    features['excessive_exclamation'] = body_text.count('!') >= 3
    
    return features

def get_authority_features(body_text):
    features = {}
    body_lower = body_text.lower()
    
    # Authority keyword count
    authority_count = sum(body_lower.count(keyword) for keyword in AUTHORITY_KEYWORDS)
    features['authority_keyword_count'] = authority_count
    features['has_authority_language'] = authority_count > 0
    
    # Check for impersonation patterns
    impersonation_patterns = [
        r'(we are|this is|i am)\s+(from|with|representing)\s+',
        r'official\s+(notice|notification|communication|email)',
        r'on\s+behalf\s+of',
        r'authorized\s+(representative|agent|personnel)'
    ]
    
    features['has_impersonation_pattern'] = any(re.search(pattern, body_lower) for pattern in impersonation_patterns)
    
    # Check if claims to be from trusted domain
    features['claims_trusted_domain'] = any(domain in body_lower for domain in TRUSTED_DOMAINS)
    
    return features

def get_threat_features(body_text):
    features = {}
    body_lower = body_text.lower()
    
    threat_count = sum(body_lower.count(keyword) for keyword in THREAT_KEYWORDS)
    features['threat_keyword_count'] = threat_count
    features['has_threat'] = threat_count > 0
    
    # Patterns indicating negative consequences
    consequence_patterns = [
        r'(will|may|could)\s+be\s+(suspended|terminated|closed|deleted|removed)',
        r'(lose|loss of)\s+(access|account|data|information)',
        r'unable\s+to\s+(access|use|log in|sign in)'
    ]
    
    features['has_consequence_language'] = any(re.search(pattern, body_lower) for pattern in consequence_patterns)
    
    return features

def extract_urls(text):
    urls = []
    
    # Pattern 1: Explicit http/https URLs (high confidence)
    # Matches: http://example.com, https://example.com/path
    http_pattern = r'https?://(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?:[/?#][^\s<>"{}|\\^`\[\]]*)?'
    http_urls = re.findall(http_pattern, text, re.IGNORECASE)
    urls.extend(http_urls)
    
    # Pattern 2: Protocol-less URLs with common TLDs (medium confidence)
    # matching things like "see example.com in the documentation."
    # We explicitly check for common TLDs to reduce false positives
    common_tlds = r'(?:com|org|net|edu|gov|mil|co|io|ai|app|dev|tech|info|biz|name|pro|xyz|online|site|website|store|shop|blog|news|media|tv|me|us|uk|ca|au|de|fr|jp|cn|in|br|ru|it|es|nl|se|no|dk|fi|pl|be|ch|at|cz|gr|pt|ie|nz|sg|hk|kr|tw|th|my|id|ph|vn|za|ae|il|tr|mx|ar|cl)'
    
    # Matches: example.com/path or subdomain.example.com
    # Must be preceded by whitespace/start or followed by whitespace/end
    # Does NOT match if @ symbol present (email addresses)
    protocol_less_pattern = rf'(?:(?<=\s)|(?<=^))(?![\w.-]*@)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{{0,61}}[a-zA-Z0-9])?\.)+(?:{common_tlds})(?:[/?#][^\s<>"{{}}|\\^`\[\]]*)?(?=\s|$|[,;!?)])'
    
    protocol_less_urls = re.findall(protocol_less_pattern, text, re.IGNORECASE | re.MULTILINE)
    urls.extend(protocol_less_urls)
    
    # Pattern 3: www. prefixed URLs (high confidence)
    www_pattern = r'(?:(?<=\s)|(?<=^))www\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:[/?#][^\s<>"{}|\\^`\[\]]*)?(?=\s|$|[,;!?)])'
    www_urls = re.findall(www_pattern, text, re.IGNORECASE | re.MULTILINE)
    urls.extend(www_urls)
    
    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        url_clean = url.strip()
        # Remove trailing punctuation that might have been captured
        # Reasoning: URLs in sentences often end with periods/commas
        url_clean = re.sub(r'[.,;!?)\]]+$', '', url_clean)
        
        if url_clean and url_clean not in seen:
            seen.add(url_clean)
            unique_urls.append(url_clean)
    
    return unique_urls

def get_request_features(body_text):
    features = {}
    body_lower = body_text.lower()
    
    request_count = sum(body_lower.count(keyword) for keyword in REQUEST_KEYWORDS)
    features['request_keyword_count'] = request_count
    features['has_request'] = request_count > 0
    
    # Check for specific sensitive information requests
    features['requests_password'] = any(phrase in body_lower for phrase in ['password', 'passphrase', 'pin', 'security code'])
    features['requests_financial'] = any(phrase in body_lower for phrase in ['credit card', 'bank account', 'routing number', 'card number', 'cvv', 'billing'])
    features['requests_personal'] = any(phrase in body_lower for phrase in ['social security', 'ssn', 'date of birth', 'driver\'s license', 'passport'])
    
    # Form or input field indicators
    features['mentions_form'] = any(phrase in body_lower for phrase in ['fill out', 'complete the form', 'enter your', 'input your', 'provide your'])
    
    return features

def get_linguistic_features(body_text):
    features = {}

    words = body_text.split()
    features['word_count'] = len(words)
    features['avg_word_length'] = round(sum(len(word) for word in words) / max(len(words), 1), 2)
    
    # Sentence analysis
    sentences = re.split(r'[.!?]+', body_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    features['sentence_count'] = len(sentences)
    features['avg_sentence_length'] = round(len(words) / max(len(sentences), 1), 2)
    
    # Capitalization analysis (ALL CAPS is common in scams)
    uppercase_count = sum(1 for char in body_text if char.isupper())
    total_letters = sum(1 for char in body_text if char.isalpha())
    features['capitalization_ratio'] = round(uppercase_count / max(total_letters, 1), 3)
    
    # Check for common spelling errors or doubled words
    # Simple heuristic: look for repeated words
    word_lower = [w.lower() for w in words]
    repeated_words = sum(1 for i in range(len(word_lower)-1) if word_lower[i] == word_lower[i+1])
    features['repeated_word_count'] = repeated_words
    
    # Check for excessive spacing or formatting issues
    features['has_excessive_spacing'] = bool(re.search(r'\s{4,}', body_text))
    
    # Readability proxy: very short or very long sentences can indicate poor writing
    if sentences:
        sentence_lengths = [len(s.split()) for s in sentences]
        features['has_irregular_sentences'] = any(length < 3 or length > 50 for length in sentence_lengths)
    else:
        features['has_irregular_sentences'] = False

    body_text = body_text.lower()

    imperative_verbs = ['click', 'verify', 'confirm', 'update', 'download', 'open', 'call', 
                       'contact', 'respond', 'reply', 'send', 'provide', 'enter', 'submit',
                       'reset', 'change', 'renew', 'activate', 'complete', 'review']
    features['imperative_verb_count'] = sum(body_text.count(verb) for verb in imperative_verbs)
    
    # Second-person pronouns (targeting the victim)
    # Reasoning: Phishing often directly addresses "you" to create urgency
    second_person = ['you', 'your', 'yours', "you're", "you've", "you'll"]
    second_person_count = sum(body_text.count(f' {pronoun} ') + body_text.count(f' {pronoun},') + 
                             body_text.count(f' {pronoun}.') + body_text.startswith(pronoun + ' ')
                             for pronoun in second_person)
    features['second_person_pronoun_ratio'] = round(second_person_count / max(len(words), 1), 3)
    
    # First-person plural (corporate impersonation)
    # Reasoning: "We at [Company]" is common in phishing impersonating organizations
    first_person_plural = [' we ', ' our ', ' us ', "we're", "we've", "we'll"]
    fpp_count = sum(body_text.count(pronoun) for pronoun in first_person_plural)
    features['first_person_plural_ratio'] = round(fpp_count / max(len(words), 1), 3)
    
    return features

def get_structural_features(body_text):
    features = {}

    features['body_length'] = len(body_text)
    
    # Line and paragraph analysis
    lines = body_text.split('\n')
    features['line_count'] = len([l for l in lines if l.strip()])
    
    # Paragraphs (separated by blank lines)
    paragraphs = re.split(r'\n\s*\n', body_text)
    features['paragraph_count'] = len([p for p in paragraphs if p.strip()])
    
    # Check for HTML tags (if body contains HTML)
    html_pattern = r'<[^>]+>'
    html_tags = re.findall(html_pattern, body_text)
    features['has_html_tags'] = len(html_tags) > 0
    features['html_tag_count'] = len(html_tags)
    
    # Check for special characters that might indicate encoding issues
    special_char_count = sum(1 for char in body_text if ord(char) > 127)
    features['special_char_ratio'] = round(special_char_count / max(len(body_text), 1), 3)
    
    return features

def get_personalization_features(body_text):
    features = {}
    body_lower = body_text.lower()
    
    # Check for generic greetings in first 200 characters
    body_start = body_lower[:200]
    features['has_generic_greeting'] = any(greeting in body_start for greeting in GENERIC_GREETINGS)
    
    # Check for personalization indicators
    personalization_indicators = ['dear [a-z]+', 'hi [a-z]+', 'hello [a-z]+']
    features['has_name_in_greeting'] = any(re.search(pattern, body_start) for pattern in personalization_indicators)
    
    # Check for first person singular (might indicate personal communication)
    first_person = ['i am', 'i have', 'i will', 'i need', 'i want', 'my name']
    features['uses_first_person'] = any(phrase in body_lower for phrase in first_person)
    
    return features

def get_money_features(body_text):
    features = {}
    body_lower = body_text.lower()
    
    # Check for monetary amounts
    money_pattern = r'[\$£€¥]\s*\d+(?:,\d{3})*(?:\.\d{2})?|\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:dollars|USD|EUR|GBP)'
    money_mentions = re.findall(money_pattern, body_text)
    features['money_mention_count'] = len(money_mentions)
    features['mentions_money'] = len(money_mentions) > 0
    
    # Check for large sums (common in advance-fee fraud)
    large_sum_pattern = r'[\$£€¥]\s*\d{1,3}(?:,\d{3})+|\d+\s*(?:million|billion|thousand)'
    features['mentions_large_sum'] = bool(re.search(large_sum_pattern, body_text, re.IGNORECASE))
    
    # Check for money-related keywords
    money_keywords = ['refund', 'prize', 'lottery', 'inheritance', 'compensation', 'owed', 'transfer', 'wire', 'payment', 'invoice']
    features['money_keyword_count'] = sum(body_lower.count(keyword) for keyword in money_keywords)
    
    # Check for "too good to be true" patterns
    prize_patterns = ['you have won', 'you\'ve won', 'congratulations', 'claim your', 'you are selected', 'you have been chosen']
    features['has_prize_language'] = any(pattern in body_lower for pattern in prize_patterns)
    
    return features

def get_body_features(parsed_emls):
    raw_body = parsed_emls.get('body', '')
    og_fname = parsed_emls.get('og_fname', '')


    if not raw_body or raw_body.strip() == "":
        return {
            'urgency_keyword_count': 0, 'has_urgency': False, 'has_time_pressure': False,
            'exclamation_count': 0, 'excessive_exclamation': False,
            'authority_keyword_count': 0, 'has_authority_language': False,
            'has_impersonation_pattern': False, 'claims_trusted_domain': False,
            'threat_keyword_count': 0, 'has_threat': False, 'has_consequence_language': False,
            'url_count': 0, 'has_links': False, 'link_density': 0, 'has_ip_url': False,
            'has_shortened_url': False, 'has_suspicious_tld': False, 'has_at_in_url': False,
            'has_excessive_subdomains': False, 'has_misleading_link_text': False,
            'request_keyword_count': 0, 'has_request': False, 'requests_password': False,
            'requests_financial': False, 'requests_personal': False, 'mentions_form': False,
            'word_count': 0, 'avg_word_length': 0, 'sentence_count': 0,
            'avg_sentence_length': 0, 'capitalization_ratio': 0, 'repeated_word_count': 0,
            'has_excessive_spacing': False, 'has_irregular_sentences': False,
            'imperative_verb_count': 0, 'second_person_pronoun_ratio': 0, 'first_person_plural_ratio': 0,
            'body_length': 0, 'line_count': 0, 'paragraph_count': 0, 'has_html_tags': False,
            'html_tag_count': 0, 'special_char_ratio': 0, 'has_generic_greeting': False,
            'has_name_in_greeting': False, 'uses_first_person': False,
            'money_mention_count': 0, 'mentions_money': False, 'mentions_large_sum': False,
            'money_keyword_count': 0, 'has_prize_language': False
        }, []

    try:
        features = {}
        features.update(get_urgency_features(raw_body))
        features.update(get_authority_features(raw_body))
        features.update(get_threat_features(raw_body))
        features.update(get_request_features(raw_body))
        features.update(get_linguistic_features(raw_body))
        features.update(get_structural_features(raw_body))
        features.update(get_personalization_features(raw_body))
        features.update(get_money_features(raw_body))

        urls = extract_urls(raw_body)
        features.update({"URLs":urls})

        return features, urls

    except Exception as e:
        print(f"failed data from original file: {og_fname}")
        raise e
    

features, urls = get_body_features(parsed_eml)
