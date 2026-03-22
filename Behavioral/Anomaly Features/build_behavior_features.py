#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_behavior_features.py
Creates behavior/anomaly feature tables from train/test JSON datasets.
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from email import message_from_string
from email.utils import parsedate_to_datetime

import numpy as np
import pandas as pd
import joblib

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "train-test-data"
OUT_DIR = BASE_DIR / "behavior_features"
OUT_DIR.mkdir(exist_ok=True)

TRAIN_JSON = DATA_DIR / "train-data.json"
TEST_JSON = DATA_DIR / "test-data.json"

URL_REGEX = re.compile(r"https?://\S+", re.IGNORECASE)


def load_records(path: Path):
    print(f"[+] Loading records from {path} ...")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[+] Loaded {len(data):,} records from {path.name}")
    return data


def parse_headers(raw_headers: str):
    """Parse raw header string safely."""
    if not raw_headers:
        return None
    try:
        return message_from_string(raw_headers)
    except Exception:
        return None


def extract_basic_fields(rec):
    """Extract primitives needed for behavioral features."""
    raw_headers = rec.get("raw_headers") or ""
    body = rec.get("body") or ""
    attachments = rec.get("attachments") or []

    msg = parse_headers(raw_headers)

    # sender & domain
    sender = None
    domain = None
    if msg:
        from_hdr = msg.get("From", "")
        if "<" in from_hdr and ">" in from_hdr:
            sender = from_hdr.split("<")[-1].split(">")[0].strip()
        else:
            sender = from_hdr.strip()
    if sender and "@" in sender:
        domain = sender.split("@")[-1].lower()

    # send time → seconds since midnight
    send_time_seconds = None
    if msg and msg.get("Date"):
        try:
            dt = parsedate_to_datetime(msg.get("Date"))
            send_time_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        except Exception:
            send_time_seconds = None

    # counts
    body_length = len(body)
    link_count = len(URL_REGEX.findall(body))
    attachment_count = len(attachments)

    # label
    label = rec.get("label")
    if label is None:
        label = rec.get("x-label")

    return {
        "email_id": rec.get("email_id"),
        "sender": sender,
        "domain": domain,
        "send_time_seconds": send_time_seconds,
        "body_length": body_length,
        "link_count": link_count,
        "attachment_count": attachment_count,
        "label": int(label) if label is not None else None,
    }


def build_aggregates(train_rows):
    """Compute sender/domain history & prior phish rates (train only)."""
    sender_stats = defaultdict(lambda: {"count": 0, "mal": 0})
    domain_stats = defaultdict(lambda: {"count": 0, "mal": 0})

    for r in train_rows:
        sender = r["sender"]
        domain = r["domain"]
        lab = r["label"]

        if sender:
            sender_stats[sender]["count"] += 1
            sender_stats[sender]["mal"] += lab

        if domain:
            domain_stats[domain]["count"] += 1
            domain_stats[domain]["mal"] += lab

    sender_rates = {
        s: {
            "count": st["count"],
            "prior": st["mal"] / st["count"] if st["count"] else 0.0,
        }
        for s, st in sender_stats.items()
    }

    domain_rates = {
        d: {
            "count": st["count"],
            "prior": st["mal"] / st["count"] if st["count"] else 0.0,
        }
        for d, st in domain_stats.items()
    }

    return sender_rates, domain_rates


def compute_global_stats(train_df):
    """Means/stds for numeric columns."""
    def mean_std(col):
        vals = train_df[col].dropna().values
        if len(vals) == 0:
            return (0.0, 1.0)
        return (float(vals.mean()), float(vals.std() + 1e-6))

    return {
        "send_time": mean_std("send_time_seconds"),
        "body_length": mean_std("body_length"),
        "link_count": mean_std("link_count"),
        "attachment_count": mean_std("attachment_count"),
    }


def add_behavior_features(rows, sender_rates, domain_rates, global_stats):
    """Full final behavioral feature set."""
    features = []

    mean_send, std_send = global_stats["send_time"]
    mean_body, std_body = global_stats["body_length"]
    mean_link, std_link = global_stats["link_count"]
    mean_attach, std_attach = global_stats["attachment_count"]

    def z(x, mean, std):
        if x is None:
            return 0.0
        if std <= 1e-6:
            return 0.0
        return (x - mean) / std

    for r in rows:
        s = r["sender"]
        d = r["domain"]

        s_info = sender_rates.get(s)
        d_info = domain_rates.get(d)

        features.append({
            "email_id": r["email_id"],
            "send_time_zscore": z(r["send_time_seconds"], mean_send, std_send),
            "body_length_zscore": z(r["body_length"], mean_body, std_body),
            "link_count_zscore": z(r["link_count"], mean_link, std_link),
            "attachment_count_zscore": z(r["attachment_count"], mean_attach, std_attach),
            "sender_seen_before": 1 if (s_info and s_info["count"] > 0) else 0,
            "first_contact_flag": 1 if (s_info and s_info["count"] == 1) else 0,
            "sender_prior_phish_rate": s_info["prior"] if s_info else 0.0,
            "domain_prior_phish_rate": d_info["prior"] if d_info else 0.0,
            "label": r["label"],
        })

    return pd.DataFrame(features)


def main():
    train = load_records(TRAIN_JSON)
    test = load_records(TEST_JSON)

    print("[+] Extracting primitives...")
    train_rows = [extract_basic_fields(r) for r in train]
    test_rows = [extract_basic_fields(r) for r in test]

    train_df = pd.DataFrame(train_rows)
    global_stats = compute_global_stats(train_df)

    print("[+] Building sender/domain history...")
    sender_rates, domain_rates = build_aggregates(train_rows)

    print("[+] Creating TRAIN feature table...")
    train_feat = add_behavior_features(train_rows, sender_rates, domain_rates, global_stats)

    print("[+] Creating TEST feature table...")
    test_feat = add_behavior_features(test_rows, sender_rates, domain_rates, global_stats)

    OUT_DIR.mkdir(exist_ok=True)
    train_csv = OUT_DIR / "behavior_train.csv"
    test_csv = OUT_DIR / "behavior_test.csv"

    print(f"[+] Saving: {train_csv}")
    train_feat.to_csv(train_csv, index=False)

    print(f"[+] Saving: {test_csv}")
    test_feat.to_csv(test_csv, index=False)

    meta = {
        "global_stats": global_stats,
        "sender_rates": sender_rates,
        "domain_rates": domain_rates,
    }

    meta_path = OUT_DIR / "behavior_feature_meta.joblib"
    print(f"[+] Saving metadata: {meta_path}")
    joblib.dump(meta, meta_path)

    print("[+] Done building behavior features.")


if __name__ == "__main__":
    main()