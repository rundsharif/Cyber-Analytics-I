# Cyber-Analytics-I

check_dataset.py Usage:
  python check_dataset.py -i \{Input File\} -p \{Whatever headers you want to look at\}\n
    Optional: "-d" for "disregard" useful if you have a lot of headers, and you want to analyze most of them. Use "-p" to specify the headers you want to disregard, followed by "-d"\n
    ex. python check_dataset.py -i \{Input File\} -p \{Whatever headers you want disregard\} -d\n
  Input file should be in the following format:\n
    \{key1:value1, key2:value2\}\n
    \{key1:value3, key2:value4\}\n
    \{key1:value5, key2:value6\}\n
    ...\n
  No output file is created by this script, it is only for sanity checking a json lines file\n
\n
separate_headers_body.py Usage:\n
  python separate_headers_body.py -i \{Input File(s) or Directory\} -o \{Output file name\}\n
    -i accepts a file, multiple files, or a directory. If a directory, it finds all .eml files in that directory that are one level deep (doesnt dig into all directories inside).\n
    -o is optional, otherwise saves output to a default output filename\n
  Output file is in the following format:\n
    \{header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format)\}\n
    \{header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format)\}\n
    \{header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format)\}\n
    ...\n
