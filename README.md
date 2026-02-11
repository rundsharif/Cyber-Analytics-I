# Cyber-Analytics-I

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


## parse_emails.py Usage:
The purpose of parse_emails.py is to take a raw .eml file and break it into its parts to facilitate simpler processing later down the line.\
This script takes either a single .eml file as input or a directory name as input. If a directory name, it will recursively process all .eml files in the specified directory and output the result to a singular file.

## Example output for singular eml:
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
