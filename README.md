# Table of Contents 
* [CLI Tools](#cli-tools)
  * [parse_emails.py](#parse_emailspy-usage)
  * [extract_header_features.py](#extract_header_featurespy-usage)
  * [extract_body_features.py](#extract_body_featurespy-usage)
  * [rebuild_attachments.py](#rebuild_attachmentspy-usage)
  * [wrapper_for_parsing.py](#wrapper_for_parsingpy-usage)
  * [check_dataset.py](#check_datasetpy-usage)
  * [jlines_to_csv.py](#jlines_to_csvpy-usage)
* [Non-CLI Tools](#non-cli-tools)
  * [io_helpers.py](#io_helperspy-usage)

# CLI Tools
## parse_emails.py Usage:
The purpose of parse_emails.py is to take a raw .eml file and break it into its parts to facilitate simpler processing later down the line.\
This script takes either a single .eml file as input or a directory name as input. If a directory name, it will recursively process all .eml files in the specified directory and output the result to a singular file.

### Example output for singular eml:
    {"email_id": "{unique uuid4}", "header_list": "{comma separated list of header names}", "raw_headers": "{actual raw headers}", "body": "{raw body content}", "og_fname": "{original filename}", "attachments": \[{"filename": "{attachment filename, or unnamed_attachment.txt as a fallback}", "content_type": "{content type of attachment}", "hash": "{sha256 hash}", "data_base64": "{raw base64 string of attachment data}"}]}
As shown above, the parsing process produces a nested json structure containing the following:
- "email_id": Unique uuid4 identifier for .eml file
- "header_list": list of headers included
- "raw_headers": actual raw headers
- "body": raw body content
- "og_fname": original name of .eml file
- "attachments": list of attachments information
    - "filename": attachment filename, using unnamed_attachment as a default if no filename is found
    - "content_type": the content type of the attachment
    - "hash": sha256 hash of file
    - "data_base64": base64 encoding of raw data contained in the attachment
- (optional) "label": adds a static label on to the json structure\
###  CLI argument options:
    -i, --input (required) Eml file you wish to process
    -o, --output (optional) Saves output to specified filename, otherwise uses default_out.json
    -s, --sample (optional) Parses a sample of the eml files specified in the input directory. Must specify size of sample
    -l, --label (optional) appends a static label onto each output json
    -d, --debug (optional) boolean flag to enable debug output, shows preview of headers and body

## extract_header_features.py Usage:
***Note: extract_headers_lambda.py is the exact same script, only refactored to be used as an AWS lambda function.***\
The purpose of extract_header_features.py is to take the previous output file from parse_emails.py and produce a json lines output file containing 27 features extracted from the raw header content of each parsed email from the input file.

### Features extracted per email:
**Authenticity Features (4 features):**
* "has_dkim": Boolean indicating presence of DKIM-Signature header
* "has_spf": Boolean indicating SPF information in Authentication-Results header
* "from_return_mismatch": Boolean indicating domain mismatch between From and Return-Path headers (phishing indicator)
* "has_auth_results": Boolean indicating presence of Authentication-Results header

**Sender Features (5 features):**
* "from_free_provider": Boolean indicating if sender uses free email provider (gmail, yahoo, hotmail, etc.)
* "from_has_numbers": Boolean indicating presence of numbers in email address local part
* "display_name_empty": Boolean indicating missing or empty display name (suspicious indicator)
* "display_name_is_email": Boolean indicating display name exactly matches email address (unusual pattern)
* "reply_to_differs": Boolean indicating Reply-To address differs from From address

**Structural Features (3 features):**
* "missing_message_id": Boolean indicating absence of Message-ID header (RFC 5322 violation)
* "has_x_mailer": Boolean indicating presence of X-Mailer header
* "content_type_complexity": Integer count of semicolons in Content-Type header (proxy for parameter complexity)

**Temporal Features (3 features):**
* "sent_business_hours": Boolean indicating email sent during business hours (8 AM - 6 PM Monday-Friday)
* "timezone_offset": Integer timezone offset in seconds from UTC
* "day_of_week": Integer day of week (0=Monday, 6=Sunday, -1=malformed/missing date)

**Encoding Features (4 features):**
* "uses_base64": Boolean indicating use of base64 encoding in Content-Transfer-Encoding
* "uses_quoted_printable": Boolean indicating use of quoted-printable encoding
* "unicode_in_from": Boolean indicating Unicode characters or encoded words in From header
* "unicode_in_subject": Boolean indicating Unicode characters or encoded words in Subject header

**Received Path Features (4 features):**
* "received_count": Integer count of Received headers (email relay hops)
* "unique_relay_ips": Integer count of unique IP addresses in Received headers
* "all_private_ips": Boolean indicating all IPs are private/localhost addresses
* "ip_diversity_ratio": Float ratio of unique IPs to total received headers (0.0-1.0)

**Data Quality Features (4 features):**
* "has_valid_date": Boolean indicating successfully parsed date header
* "has_extreme_complexity": Boolean indicating Content-Type complexity exceeds threshold (>10 semicolons)
* "has_unusual_timezone": Boolean indicating timezone offset outside valid range (±14 hours)
* "data_quality_score": Integer score from 0-3 indicating overall email header quality

### CLI argument options:
    -i, --input (required) JSON lines file containing parsed emails (typically from parse_emails.py output)
    -o, --output (optional) Saves output to specified filename, otherwise uses "\{input filename\}_features.json"
    -d, --debug (optional) Boolean flag to enable debug output \(no debug output as of yet\)
### Lambda Version Usage Example:
    from extract_headers_lambda import get_header_features
    parsed_eml = \{json from parse_email.py output\}
    header_features = get_header_features\(parsed_eml\)
    
## extract_body_features.py Usage
***NOTE: This script is likely to be deprecated in future versions of the project***\
***Note: extract_headers_lambda is the exact same script, only refactored to be used as an AWS lambda function.***\
The purpose of extract_body_features.py is to 52 unique features from the raw body text of the email file. These features include features relating to urgency, authority, threat, requests, liguistics, structure, personalization, and monetary language. In addition, this script will produce an additional output file containing the URLs found in the body text in the format of a simple wordlist. 

### Example workflow execution:
    Input: parsed.json (from parse_emails.py)
    ↓
    Process: Extract body features & URLs from email body text
    ↓
    Output 1: parsed_body_features.json (47 features per email)
    Output 2: parsed_URLs.txt (one URL per line, deduplicated)
### Example Output for a single email:
    { "urgency_keyword_count": 1, "has_urgency": true, "has_time_pressure": true, "exclamation_count": 1, "excessive_exclamation": false, "authority_keyword_count": 2, "has_authority_language": true, "has_impersonation_pattern": false, "claims_trusted_domain": false, "threat_keyword_count": 1, "has_threat": true, "has_consequence_language": true, "request_keyword_count": 2, "has_request": true, "requests_password": false, "requests_financial": false, "requests_personal": false, "mentions_form": false, "word_count": 34, "avg_word_length": 5.06, "sentence_count": 4, "avg_sentence_length": 8.5, "capitalization_ratio": 0.071, "repeated_word_count": 0, "has_excessive_spacing": false, "has_irregular_sentences": false, "imperative_verb_count": 2, "second_person_pronoun_ratio": 0.059, "first_person_plural_ratio": 0.0, "body_length": 233, "line_count": 6, "paragraph_count": 4, "has_html_tags": false, "html_tag_count": 0, "special_char_ratio": 0.0, "has_generic_greeting": true, "has_name_in_greeting": false, "uses_first_person": false, "money_mention_count": 0, "mentions_money": false, "mentions_large_sum": false, "money_keyword_count": 0, "has_prize_language": false }

### CLI argument options:
    -i, --input (required) JSON lines file containing parsed emails (from parse_emails.py output)
    -o, --output (optional) Saves body features to specified filename, otherwise appends "_body_features" to input filename
    -d, --debug (optional) Boolean flag to enable debug output
### Lambda Version Usage Example:
    from extract_body_features_lambda import get_body_features
    parsed_eml = \{dict from parse_email.py output\}
    header_features = get_body_features\(parsed_eml\)


## rebuild_attachments.py Usage:
The purpose of rebuild_attachments.py is to extract attachment data from parsed email JSON files and upload them to AWS S3 storage. This script takes a JSON lines file (typically output from parse_emails.py) as input, decodes the base64-encoded attachment data, and uploads each attachment to a specified S3 bucket with organized directory structure.
### Example S3 upload structure:
    s3://bucket-name/test_attachments/{email_id}/{filename}
As shown above, the upload process organizes attachments with the following structure:
* Base path: test_attachments/
  * Email-specific subdirectory: {email_id}/ (unique UUID from parsed email)
    * Attachment filename: {filename} (original attachment filename or generated fallback name)
### Processing Details:
1. Reads JSON lines file containing parsed emails with attachment data
2. Iterates through each email's attachments array
3. Decodes base64-encoded attachment data back to binary format
4. Uploads to S3 using boto3 client with organized path structure
5. Groups all attachments from the same email under a common email_id directory
6. Handles upload errors gracefully and continues processing remaining attachments

### AWS Configuration Requirements:

* AWS credentials must be configured (via ~/.aws/credentials, environment variables, or IAM role)
* S3 bucket must exist and be accessible with write permissions
* boto3 and botocore Python packages must be installed

### CLI argument options:
    -i, --input (required) JSON lines file containing parsed emails with attachments (from parse_emails.py output)
    -b, --bucket (optional) Name of S3 bucket to upload attachments to
    -u, --upload (optional) Boolean flag to enable actual upload to S3 (without this flag, script runs in dry-run mode)

## wrapper_for_parsing.py Usage:
The purpose of wrapper_for_parsing.py is to orchestrate a complete end-to-end email processing pipeline by sequentially executing parse_emails.py, extract_body_features.py, and extract_header_features.py. This wrapper script automates the full workflow from raw .eml files to extracted features, producing multiple output files containing parsed email data, body features, URL extractions, and header features.
### Example workflow execution:
    Input: directory containing .eml files or individual .eml file(s)
    ↓
    Step 1: Parse emails → parsed.json
    ↓
    Step 2: Extract body features & URLs → parsed_body_features.json + parsed_urls.json
    ↓
    Step 3: Extract header features → parsed_header_features.json
    Example console output:
    Input directory detected: /path/to/emails
    1500 Files detected in /path/to/emails
    ...
    Initial Parsing completed. Beginning Body Feature + URL extraction
    ...
    Body Feature + URL extraction completed. Beginning Header feature extraction
    ...
    Parsed Filename: parsed.json
    Body Features Filename: parsed_body_features.json
    URL Features Filename: parsed_urls.json
    Header Features Filename: parsed_header_features.json

As shown above, the wrapper orchestrates the following sequential processing pipeline:

### Output Files Generated:

* Parsed emails JSON: Complete parsed email structure with all components
* Body features JSON: Linguistic and content-based features from email body
* URLs JSON: Extracted and analyzed URLs from email content
* Header features JSON: Technical features extracted from email headers

If no output filename specified, uses default naming convention\
Automatically generates derivative filenames for body and header features\
Preserves filename relationships across all processing stages

### CLI argument options:
    -i, --input (required) .eml file(s) or directory containing .eml files to process
    -o, --output (optional) Base output filename for parsed emails, otherwise uses default naming
    -s, --sample (optional) Process only a sample of .eml files from input directory. Must specify sample size
    -d, --debug (optional) Boolean flag to enable debug output across all processing stages

## check_dataset.py Usage:
The purpose of the check_dataset.py script is mainly for sanity checking a dataset. Often times, after modifying a dataset, you want to ensure that the actual data looks the way that you expect it to.\
Works with both csv and jsonlines files\
Handles list values by counting records (ex. list_length_4: 10 means 10 occurances of lists which contain 4 records)\
Running check_dataset.py using the syntax below, it will open the file and display a count of the unique values in a column given the column header.
### Example output
    ~> check_dataset.py -i {input jsonlines} -p label
    Checking Keys: ['label']
    Total Line Count: 4096663
    Total lines with key 'label':4096663
    Values Count for key 'label':Counter({'0': 2565291, '1': 1531372})
### CLI argument options:
    -i, --input (required) name of csv or jsonlines file you want to check
    -p, --pull-headers (optional*) list of headers/column names you want to analze
    -a, --all-headers (optional*) boolean flag specifying you want to analyze all headers/column names
    -d, --disregard (optional) boolean flag, inverts behavior of -p, instead disregarding headers specified with -p
    * EITHER -p OR -a must be used

## jlines_to_csv.py Usage:
The purpose of jlines_to_csv.py is to convert a JSON Lines file (where each line is a separate JSON object) into a CSV file format. This script reads through the entire input file to collect all unique keys across all JSON objects, then writes them as CSV columns with corresponding values for each row.
The script first scans the input file to identify all unique field names across all JSON objects, ensuring that the CSV output includes columns for every field that appears in any of the JSON records. It then writes a CSV with headers followed by data rows.
### Example input (JSON Lines format):
    {"email_id": "abc-123", "header_list": "From,To,Subject", "body": "Hello world"}
    {"email_id": "def-456", "header_list": "From,To", "body": "Test message", "label": "spam"}
### Example output (CSV format):
    email_id,header_list,body,label
    abc-123,"From,To,Subject","Hello world",
    def-456,"From,To","Test message",spam
As shown above, the conversion process produces a CSV file containing:
* Header row: All unique keys found across all JSON objects in the input file
* Data rows: One row per JSON object, with values populated for available fields and empty cells for missing fields

### CLI argument options:
    -i, --input (required) JSON Lines file you wish to convert to CSV
    -o, --output (optional) Saves output to specified filename, otherwise uses default_out.json (note: output is CSV despite the default extension)
    -d, --debug (optional) Boolean flag to enable debug output
# Non-CLI tools

## io_helpers.py Usage:
The purpose of io_helpers.py is to provide utility functions for file I/O operations used across other scripts in this project. This module is intended to be imported as a library and provides three helper functions for common file handling tasks.
### Available Functions:
**1. change_filename(fname, ext, suffix="")**\
Modifies a filename by changing its extension and optionally adding a suffix to the base name.\
### Example usage:
    from io_helpers import change_filename
    new_ext = change_filename("/path/to/data.txt", "json") #change extension only
    Returns: "/path/to/data.json"
**OR**

    new_ext_and_suffix = change_filename("/path/to/data.txt", "json", "parsed") #change extension and suffix
    Returns: "/path/to/data_parsed.json"

#### Parameters for change_filename:
    fname: Full path to the original file
    ext: New file extension (without the dot)
    suffix: Optional suffix to append to the base filename (default: "")

**2. get_sample(big_list, samp_size)**\
Extracts a random contiguous sample from a list.
### Example usage:
    from io_helpers import get_sample
    file_list = ["file1.eml", "file2.eml", "file3.eml", "file4.eml", "file5.eml"]
    sample = get_sample(file_list, 3)
    Returns: 3 consecutive files starting from a random position
    Ex Return value: ["file2.eml", "file3.eml", "file4.eml"]
#### Parameters for get_sample:
    big_list: List to sample from
    samp_size: Number of consecutive elements to extract

**3. get_all_files_from_dir(dirname)**\
Recursively collects absolute paths of all files in a directory and its subdirectories.
### Example usage:
    from io_helpers import get_all_files_from_dir
    all_files = get_all_files_from_dir("/path/to/email_directory")
    Returns: ["/path/to/email_directory/file1.eml", "/path/to/email_directory/subdir/file2.txt", ...]

#### Parameters for get_all_files_from_dir:
    dirname: Directory path to search

