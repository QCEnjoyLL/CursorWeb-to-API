import json
import os

from app.utils import decode_base64url_safe

FP = json.loads(decode_base64url_safe(os.environ.get("FP","eyJVTk1BU0tFRF9WRU5ET1JfV0VCR0wiOiJHb29nbGUgSW5jLiAoSW50ZWwpIiwiVU5NQVNLRURfUkVOREVSRVJfV0VCR0wiOiJBTkdMRSAoSW50ZWwsIEludGVsKFIpIFVIRCBHcmFwaGljcyAoMHgwMDAwOUJBNCkgRGlyZWN0M0QxMSB2c181XzAgcHNfNV8wLCBEM0QxMS0yNi4yMC4xMDAuNzk4NSkiLCJ1c2VyQWdlbnQiOiJNb3ppbGxhLzUuMCAoV2luZG93cyBOVCAxMC4wOyBXaW42NDsgeDY0KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTM5LjAuMC4wIFNhZmFyaS81MzcuMzYifQ==")))
SCRIPT_URL = os.environ.get("SCRIPT_URL",
                            "https://cursor.com/149e9513-01fa-4fb0-aad4-566afd725d1b/2d206a39-8ed7-437e-a3be-862e0f06eea3/a-4-a/c.js?i=0&v=3&h=cursor.com")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "0"))
API_KEY = os.environ.get("API_KEY", "aaa")
MODELS = os.environ.get("MODELS", "gpt-5,gpt-5-codex,gpt-5-mini,gpt-5-nano,gpt-4.1,gpt-4o,claude-3.5-sonnet,claude-3.5-haiku,claude-3.7-sonnet,claude-4-sonnet,claude-4-opus,claude-4.1-opus,gemini-2.5-pro,gemini-2.5-flash,o3,o4-mini,deepseek-r1,deepseek-v3.1,kimi-k2-instruct,grok-3,grok-3-mini,grok-4")