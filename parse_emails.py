from email.parser import BytesParser
import argparse
from email import policy
import ujson
import re
import os
from bs4 import BeautifulSoup
from io_helpers import get_sample, get_all_files_from_dir
import time
import mimetypes
import hashlib
import base64
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("--input", "-i", nargs="+", help="The name of the file to fix", required=True)
parser.add_argument("--output", "-o", help="The name of the file to output to", required=False)
parser.add_argument("--debug", "-d", help="debug mode", action="store_true", required=False)
parser.add_argument("--sample", "-s", help="use a sample of files instead of all files from dir, specify number of samples desired", required=False)



'''
Takes in raw EML files, outputs a json lines file with 
    raw headers, body text, and a string of header names separated by commas

    
parse_emailsy.py Usage:

python parse_emails.py -i {Input File(s) or Directory} -o {Output file name}
    -i accepts a file, multiple files, or a directory. If a directory, it finds all .eml files in that directory that are one level deep (doesnt dig into all directories inside).
    -o is optional, otherwise saves output to a default output filename
Output file is in the following format:
    {header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format)}
    {header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format)}
    {header_list:"header1,header2,header3", raw_headers:(raw headers in UTF-8 format), body: (body text in UTF-8 format)}
    ...
'''


def extract_attachments(msg):
    
    attachments = []
    
    for part in msg.walk():
        # Skip multipart containers (they're just structure)
        if part.get_content_maintype() == 'multipart':
            continue
        
        # Check if this part is an attachment
        content_disposition = part.get_content_disposition()
        
        if content_disposition == 'attachment' or content_disposition == 'inline':
            # Inline can be images embedded in HTML - often need analysis too
            
            # Get filename
            filename = part.get_filename()
            if not filename:
                # Some attachments don't have filenames, generate one
                ext = mimetypes.guess_extension(part.get_content_type())
                filename = f"unnamed_attachment{ext or '.bin'}"
            
            # Get the binary data
            try:
                data = part.get_payload(decode=True)  # decode=True handles Base64/etc
                
                if data is None:
                    # Malformed attachment
                    continue
                
                # Calculate hash for identification/deduplication
                content_hash = hashlib.sha256(data).hexdigest()
                
                attachment_info = {
                    'filename': filename,
                    'content_type': part.get_content_type(),
                    'data': data,  # Raw bytes
                    'hash': content_hash,
                    'content_disposition': content_disposition
                }
                
                attachments.append(attachment_info)
                
            except Exception as e:
                # Log but don't fail entire parsing
                print(f"Warning: Failed to extract attachment {filename}: {e}")
                continue
    
    return attachments

def html_to_text(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return text


def safe_decode_payload(part):
    """
    Safely decode a message part's payload, handling various charset issues.
    Returns decoded string content or empty string on failure.
    """
    try:
        # First try the standard method
        return part.get_content()
    except (KeyError, AttributeError, LookupError, UnicodeDecodeError) as e:
        # Fallback for malformed content (e.g., invalid charset like "DEFAULT")
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = part.get_payload()
                if isinstance(payload, bytes):
                    return payload.decode("utf-8", errors="replace")
                else:
                    return str(payload or "")
            
            # Get charset and sanitize it
            charset = part.get_content_charset()
            if not charset or charset.lower() in ("default", "unknown", "none", ""):
                charset = "utf-8"
            
            # Try the specified charset, fall back to common encodings
            for enc in [charset, "utf-8", "latin-1", "cp1252", "iso-8859-1"]:
                try:
                    return payload.decode(enc, errors="replace")
                except (LookupError, UnicodeDecodeError, AttributeError):
                    continue
            
            # If all else fails, decode as latin-1 (never fails)
            return payload.decode("latin-1", errors="replace")
        except Exception:
            # Last resort fallback
            try:
                return str(part.get_payload() or "")
            except:
                return ""

def extract_body_content(msg):
    """
    Extract body content from email message, handling both simple and multipart messages.
    Returns tuple of (plain_text, html_text).
    """
    body_plain = ""
    body_html = ""
    
    if msg.is_multipart():
        # Walk through all parts for multipart messages
        for part in msg.walk():
            content_type = part.get_content_type()
            
            # Skip multipart containers or attachments
            if part.get_content_maintype() == 'multipart' or part.get_content_disposition() == 'attachment':
                continue
            
            try:
                if content_type == 'text/plain':
                    body_plain += safe_decode_payload(part)
                elif content_type == 'text/html':
                    body_html += safe_decode_payload(part)
            except Exception:
                continue
    else:
        # Simple non-multipart message
        content_type = msg.get_content_type()
        try:
            if content_type == 'text/plain':
                body_plain = safe_decode_payload(msg)
            elif content_type == 'text/html':
                body_html = safe_decode_payload(msg)
            elif msg.get_content_maintype() == 'text':
                # Fallback for other text types
                body_plain = safe_decode_payload(msg)
        except Exception:
            pass
    
    return body_plain, body_html

def parse_eml(path_to_eml):
    with open(path_to_eml, "rb") as f:
        raw = f.read()

    msg = BytesParser(policy=policy.SMTP).parsebytes(raw)
    headers_list = list(msg.keys())

    split_marker = b"\r\n\r\n"
    alt_split = b"\n\n"
    if split_marker in raw:
        raw_headers_bytes, _ = raw.split(split_marker, 1)
    elif alt_split in raw:
        raw_headers_bytes, _ = raw.split(alt_split, 1)
    else:
        raw_headers_bytes = raw
    
    # Decode raw headers safely
    raw_headers_str = raw_headers_bytes.decode('utf-8', errors='replace')
    # 2) Parse the message with a modern policy so decoding is handled for you

    body_plain, body_html = extract_body_content(msg)

    if body_plain:
        body_text = body_plain
    elif body_html:
        body_text = html_to_text(body_html)
    else:
        body_text = ""
    
    body_text = body_text.strip()

    attachments = extract_attachments(msg)

    attachment_data = [
        {
            'filename': att['filename'],
            'content_type': att['content_type'],
            'hash': att['hash'],
            'data_base64': base64.b64encode(att['data']).decode('ascii')
        }
        for att in attachments
    ]


    email_id = str(uuid.uuid4())
    return {"email_id":email_id,"header_list":",".join(headers_list), "raw_headers":raw_headers_str, "body":body_text, "og_fname":os.path.basename(path_to_eml), "attachments":attachment_data}

def write_out(outname, out_d):
    with open(outname, "a", encoding="utf-8") as wf:
        wf.write(ujson.dumps(out_d, ensure_ascii=False)+ "\n")



def find_all_of_filetype(given_dir, ext):
    found_files = []
    for root, _, files in os.walk(given_dir):
        for file in files:
            if file.endswith(ext):
                found_files.append(os.path.join(root, file))
    return found_files


def sanitize_flist(flist, ext):
    ext_regx = re.compile(rf".*\.{ext}$")
    sanitized = []
    for f in flist:
        if ext_regx.search(f):
            sanitized.append(f)
    return sanitized
            
def get_flist_abspath(flist):
    abspath_list = []
    for f in flist:
        abspath_list.append(os.path.abspath(f))
    return abspath_list


def parsing_wrapper(infile, outfile = "", debug = False, sample = False):
    if not outfile:
        outfile = "default_out.json"
    elif os.path.exists(outfile):
        if input(f"please enter anything if you want to first delete the existing output file {outfile}: \n"):
            os.remove(outfile)
    if not all(os.path.isfile(fname) for fname in infile) and os.path.isdir(infile[0]):
        dirname = infile[0]
        print(f"Input directory detected: {dirname}")
#        infile = find_all_of_filetype(dirname, ".eml")
#        san_list = sanitize_flist(os.listdir(dirname), "eml")
#        infile = get_flist_abspath(san_list)
        infile = get_all_files_from_dir(dirname)
        if sample:
            infile = get_sample(infile, sample)
        print(f"{len(infile)} Files detected in {dirname}")
    t1 = time.time()
    for i, name in enumerate(infile):
        try:
            out_dict = parse_eml(name)
        except Exception as e:
            print(f"Error processing {os.path.basename(name)}: {e}")
            raise e
        write_out(outfile, out_dict)
        if i % 1000 == 0 and i != 0:
            t2 = time.time()
            print(f"{i} EML files processed at {str(i / (t2-t1))[:8]} per second")
        if debug:
            print(f"Headers: {out_dict["header_list"]}")
            print(f"Raw Headers: {out_dict["raw_headers"]}")
            print(f"\nBody Text: \n{out_dict["body"][:500]}")
    
    return outfile



if __name__ == '__main__':
    args = parser.parse_args()
    infile = args.input
    outfile = args.output
    debug = args.debug
    sample = args.sample
    if not outfile:
        outfile = "default_out.json"
    elif os.path.exists(outfile):
        if input(f"please enter anything if you want to first delete the existing output file {outfile}: \n"):
            os.remove(outfile)
    if not all(os.path.isfile(fname) for fname in infile) and os.path.isdir(infile[0]):
        dirname = infile[0]
        print(f"Input directory detected: {dirname}")
#        infile = find_all_of_filetype(dirname, ".eml")
#        san_list = sanitize_flist(os.listdir(dirname), "eml")
#        infile = get_flist_abspath(san_list)
        infile = get_all_files_from_dir(dirname)
        if sample:
            infile = get_sample(infile, sample)
        print(f"{len(infile)} Files detected in {dirname}")
    t1 = time.time()
    for i, name in enumerate(infile):
        try:
            out_dict = parse_eml(name)
        except Exception as e:
            print(f"Error processing {os.path.basename(name)}: {e}")
            raise e
        write_out(outfile, out_dict)
        if i % 1000 == 0 and i != 0:
            t2 = time.time()
            print(f"{i} EML files processed at {str(i / (t2-t1))[:8]} per second")
        if debug:
            print(f"Headers: {out_dict["header_list"]}")
            print(f"Raw Headers: {out_dict["raw_headers"]}")
            print(f"\nBody Text: \n{out_dict["body"][:500]}")