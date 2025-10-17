import os
import sys
import google.generativeai as genai

# Load env automatically
from dotenv import load_dotenv
load_dotenv()

# Required environment variables
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SERVER_SECRET = os.getenv("SECRET", "abcd1234")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FALLBACK_API_KEY = os.getenv("AIPIPE_AKI_KEY", "")
HF_UBUNTU_TOKEN = os.getenv("HF_UBUNTU_TOKEN")

# Internal clients
_primary_client = None
_fallback_client = None

def validate_config():
    missing = []
    if not GITHUB_USERNAME: missing.append("GITHUB_USERNAME")
    if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
    if not GEMINI_API_KEY: missing.append("GEMINI_API_KEY")
    if not SERVER_SECRET: missing.append("SECRET")

    if missing:
        print("❌ Missing required env variables:", missing)
        sys.exit(1)
    print("✅ Config validated successfully.")

def get_gemini_client():
    global _primary_client
    if _primary_client is None:
        genai.configure(api_key=GEMINI_API_KEY)
        _primary_client = genai
    return _primary_client

def get_fallback_client():
    global _fallback_client
    if _fallback_client is None:
        if not FALLBACK_API_KEY:
            raise ValueError("Fallback API key not set (AIPIPE_AKI_KEY)")
        import openai
        _fallback_client = openai.OpenAI(api_key=FALLBACK_API_KEY, base_url="https://aipipe.org/openai/v1")
    return _fallback_client
