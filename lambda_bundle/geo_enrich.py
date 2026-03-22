from __future__ import annotations
import os, re
import ipaddress
from functools import lru_cache
from typing import Optional, Dict, Any
import geoip2.database

_IP_RE = re.compile(
    r'(?P<ip>(?:(?:\d{1,3}\.){3}\d{1,3})|(?:[A-Fa-f0-9:]+:+[A-Fa-f0-9:]+))'
)

def _is_public_ip(ip: str) -> bool:
    try:
        obj = ipaddress.ip_address(ip)
        return not (obj.is_private or obj.is_loopback or obj.is_reserved or obj.is_multicast)
    except ValueError:
        return False

def first_public_ip_from_headers(received_blob: str) -> Optional[str]:
    if not received_blob:
        return None
    lines = [ln for ln in received_blob.splitlines() if "received:" in ln.lower() or " by " in ln or " from " in ln]
    for ln in reversed(lines):  # earliest hop first
        for m in _IP_RE.finditer(ln):
            ip = m.group("ip")
            if _is_public_ip(ip):
                return ip
    for m in _IP_RE.finditer(received_blob):
        ip = m.group("ip")
        if _is_public_ip(ip):
            return ip
    return None

def _open_reader(db_path: Optional[str] = None):
    path = db_path or os.getenv("MAXMIND_DB", "GeoLite2-City.mmdb")
    if not os.path.exists(path):
        raise FileNotFoundError(f"MaxMind DB not found at {path}. Set MAXMIND_DB or place GeoLite2-City.mmdb in project root.")
    return geoip2.database.Reader(path)

@lru_cache(maxsize=50000)
def geo_lookup(ip: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not ip or not _is_public_ip(ip):
        return None
    try:
        reader = _open_reader(db_path)
        resp = reader.city(ip)
        return {
            "origin_ip": ip,
            "origin_country_code": resp.country.iso_code or None,
            "origin_country_name": resp.country.name or None,
            "origin_city": (resp.city.name or None),
            "origin_lat": resp.location.latitude,
            "origin_lon": resp.location.longitude,
        }
    except Exception:
        return None

def enrich_headers_with_geo(raw_headers: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    ip = first_public_ip_from_headers(raw_headers or "")
    if not ip:
        return {"origin_ip": None, "origin_country_code": None, "origin_country_name": None,
                "origin_city": None, "origin_lat": None, "origin_lon": None}
    geo = geo_lookup(ip, db_path=db_path)
    if not geo:
        geo = {"origin_ip": ip, "origin_country_code": None, "origin_country_name": None,
               "origin_city": None, "origin_lat": None, "origin_lon": None}
    return geo