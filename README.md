# Cyber-Analytics-I

## check_dataset.py Usage:
###  python check_dataset.py -i \{Input File\} -p \{Whatever headers you want to look at\}
    Optional: "-d" for "disregard" useful if you have a lot of headers, and you want to analyze most of them. Use "-p" to specify the headers you want to disregard, followed by "-d"
    ex. python check_dataset.py -i {Input File} -p {Whatever headers you want disregard} -d

###  Input file should be in the following format:
    {key1:value1, key2:value2}
    {key1:value3, key2:value4}
    {key1:value5, key2:value6}
    ...

###  No output file is created by this script, it is only for sanity checking a json lines file

## parse_emls.py Usage:

###  python parse_emls.py -i {Input File(s) or Directory} -o {Output file name} (Following flags are optional) -s {number} -l {label}
    -i accepts a file, multiple files, or a directory. If a directory, it finds all .eml files in that directory that are one level deep (doesnt dig into all directories inside).
    -o is optional, otherwise saves output to a default output filename
    -s is optional, used for getting a sample rather than all files. For example, if you give it a directory as "input file" that has 50k emails, but you just want 5k, you use '-s 5000'
    -l is optional, used for labeling each email that is processed. For example, using '-l benign' will add a k/v pair to each line {"label":"benign"} 

###  Output file is in the following format:
    {header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format), "og_fname": (name of original file without full path) , "attachments":attachment_data}
    {header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format), "og_fname": (name of original file without full path) , "attachments":attachment_data}
    {header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format), "og_fname": (name of original file without full path) , "attachments":attachment_data}
    ...
### Attachment data is in the following format:
        {
            'filename': str(original attachment filename),
            'content_type': (MIME content type, as specified in original EML),
            'hash': (sha256 hash of attachment),
            'data_base64': (base-64 encoded bytes of original attachment, since raw bytes are not json serializable)
        }


