# extract_benign_features.py
import os, sys, hashlib, json, math
import magic
import numpy as np
import pandas as pd
from collections import Counter

# Optional PE parsing
try:
    import pefile
    HAS_PE = True
except Exception:
    HAS_PE = False

# Optional VirusTotal
VT_API_KEY = None  # set to str('YOUR_KEY') to enable
import requests

def sha256_bytes(b):
    import hashlib
    return hashlib.sha256(b).hexdigest()

def md5_bytes(b):
    import hashlib
    return hashlib.md5(b).hexdigest()

def sha1_bytes(b):
    import hashlib
    return hashlib.sha1(b).hexdigest()

def byte_entropy(b: bytes):
    if not b:
        return 0.0
    arr = np.frombuffer(b, dtype=np.uint8)
    counts = np.bincount(arr, minlength=256)
    probs = counts[counts>0] / arr.size
    return float(-(probs * np.log2(probs)).sum())

def byte_histogram(b: bytes, bins=32):
    if not b:
        return [0]*bins
    arr = np.frombuffer(b, dtype=np.uint8)
    counts = np.bincount(arr, minlength=256)
    # group into 'bins' buckets
    step = 256 // bins
    h = [int(counts[i*step:(i+1)*step].sum()) for i in range(bins)]
    total = sum(h)
    if total==0:
        return [0]*bins
    return [x/total for x in h]

def extract_strings_stats(b: bytes, min_len=4):
    # basic ASCII string extraction
    s = b.decode('latin1', errors='ignore')
    strings = []
    cur = []
    for ch in s:
        if 32 <= ord(ch) <= 126:
            cur.append(ch)
        else:
            if len(cur) >= min_len:
                strings.append(''.join(cur))
            cur = []
    if len(cur) >= min_len:
        strings.append(''.join(cur))
    if not strings:
        return 0, 0.0
    lens = [len(x) for x in strings]
    return len(strings), float(sum(lens)/len(lens))

def extract_pe_features(b: bytes):
    if not HAS_PE:
        return {}
    try:
        pe = pefile.PE(data=b)
        # num sections
        num_sections = len(pe.sections)
        # imports
        num_imports = 0
        imports = []
        if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                imports.append(entry.dll.decode(errors='ignore').lower())
                for imp in entry.imports:
                    num_imports += 1
        # imphash
        imphash = None
        try:
            imphash = pe.get_imphash()
        except Exception:
            imphash = None
        # debug info
        has_debug = bool(getattr(pe, 'DIRECTORY_ENTRY_DEBUG', None))
        # 64-bit detection
        is_64 = None
        try:
            magic_val = pe.OPTIONAL_HEADER.Magic
            is_64 = (magic_val == 0x20b)
        except Exception:
            is_64 = None
        # section entropies
        secs = []
        for s in pe.sections:
            try:
                secs.append(s.get_entropy())
            except Exception:
                pass
        return {
            'pe_is_pe': True,
            'is_64bit': is_64,
            'num_sections': num_sections,
            'num_imports': num_imports,
            'imported_dlls': imports,
            'imphash': imphash,
            'has_debug_info': has_debug,
            'section_entropies_median': np.median(secs) if secs else None,
            'section_entropies_max': max(secs) if secs else None
        }
    except Exception:
        return {}

def vt_check_hash(sha256):
    if not VT_API_KEY:
        return None
    url = f"https://www.virustotal.com/api/v3/files/{sha256}"
    headers = {"x-apikey": VT_API_KEY}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        j = r.json()
        stats = j.get('data', {}).get('attributes', {}).get('last_analysis_stats', {})
        positives = sum(stats.get(k,0) for k in stats)
        return positives
    else:
        return None

def process_file(path):
    with open(path, 'rb') as fh:
        b = fh.read()
    rec = {}
    rec['filename'] = os.path.basename(path)
    rec['file_size'] = len(b)
    rec['sha256'] = sha256_bytes(b)
    rec['md5'] = md5_bytes(b)
    rec['sha1'] = sha1_bytes(b)
    rec['mime'] = magic.from_buffer(b, mime=True) if b else None
    rec['entropy'] = byte_entropy(b)
    bh = byte_histogram(b, bins=32)
    for i,val in enumerate(bh):
        rec[f'byte_hist_{i}'] = val
    scount, avg_slen = extract_strings_stats(b, min_len=4)
    rec['strings_count'] = scount
    rec['strings_avg_len'] = avg_slen
    # PE features
    pef = extract_pe_features(b)
    rec.update(pef)
    # is_executable heuristic
    rec['is_executable'] = False
    mime = (rec['mime'] or '').lower()
    if 'pe' in mime or rec.get('pe_is_pe') or rec['filename'].lower().endswith(('.exe','.dll','.scr','.sys')):
        rec['is_executable'] = True
    # optionally VT
    vtpos = vt_check_hash(rec['sha256'])
    rec['vt_positives'] = vtpos
    # benign label
    rec['is_malware'] = 0
    return rec

def process_folder(folder, out_csv):
    rows = []
    for root, dirs, files in os.walk(folder):
        for fn in files:
            path = os.path.join(root, fn)
            try:
                r = process_file(path)
                rows.append(r)
            except Exception as e:
                print("error processing", path, e)
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    print("wrote", len(df), "rows to", out_csv)
    return df

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("usage: python extract_benign_features.py <folder_with_files> <out.csv>")
        sys.exit(1)
    folder = sys.argv[1]
    out_csv = sys.argv[2]
    df = process_folder(folder, out_csv)