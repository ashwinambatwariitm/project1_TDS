import os
import json
import requests
from dotenv import load_dotenv
from google import genai
from repo_utils import create_and_setup_repo
from datetime import datetime

# 1️⃣ Load environment variables
load_dotenv()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# genai.configure(api_key=GEMINI_API_KEY)
genai.Client(api_key=GEMINI_API_KEY)


# Only for testing secrets loading (do NOT print actual keys!)
if __name__ == "__main__":
    # Check if the environment variables exist
    secrets = ["GITHUB_USERNAME", "GITHUB_TOKEN", "GEMINI_API_KEY"]
    for secret in secrets:
        if os.getenv(secret):
            print(f"✅ {secret} is set")
        else:
            print(f"❌ {secret} is NOT set")


def generate_html_from_brief(brief):
    """Send task brief to Gemini 2.5 Flash and get HTML output."""
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""
    You are an expert web app developer. Based on the following project brief:
    {brief}

    Generate only a COMPLETE HTML file (with inline CSS/JS) that fulfills the brief.
    Do not generate Python code. Use responsive modern design.
    """
    response = model.generate_content(prompt)
    
    html_content =  response.text
    if "```html" in html_content:
        html_content = html_content.split("```html")[1].split("```")[0].strip()
    elif "```" in html_content:
        html_content = html_content.split("```")[1].split("```")[0].strip()
        
    return html_content


def generate_html_from_brief_fixed(brief):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
        You are an expert web app developer. Based on the following project brief:
        {brief}

        Generate only a COMPLETE HTML file (with inline CSS/JS) that fulfills the brief.
        Do not generate Python code. Use responsive modern design.
        """

    return client.models.generate_content(model="gemini-2.5-flash", contents=prompt)


def process_json_request(json_data):
    """Extract details, call Gemini, create GitHub repo, notify evaluation URL."""
    email = json_data["email"]
    task = json_data["task"]
    round_num = json_data["round"]
    nonce = json_data["nonce"]
    brief = json_data["brief"]
    evaluation_url = json_data["evaluation_url"]

    print(f"📨 Processing task: {task}")
    # Current datetime string, e.g., 20251007_1430
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Base repo name
    repo_name = f"{task.replace('-', '_')}_webapp"

    # Append timestamp only for first round
    if round_num == 1:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        repo_name = f"{repo_name}_{timestamp}"

    print(f"🚀 Using repository: {repo_name}")

    # Generate HTML output
    html_output = generate_html_from_brief_fixed(brief)

    # Create child repo & deploy
    pages_url = create_and_setup_repo(
        repo_name, html_output, GITHUB_USERNAME, GITHUB_TOKEN
    )

    # Notify evaluation URL
    payload = {
        "email": email,
        "task": task,
        "round": round_num,
        "nonce": nonce,
        "repo_url": f"https://github.com/{GITHUB_USERNAME}/{repo_name}",
        "commit_sha": "auto_commit_sha",  # Optional - can extract via subprocess if needed
        "pages_url": pages_url,
    }

    try:
        r = requests.post(
            evaluation_url, json=payload, headers={"Content-Type": "application/json"}
        )
        if r.status_code == 200:
            print("✅ Evaluation notified successfully.")
        else:
            print(f"⚠️ Evaluation notify failed: {r.status_code}")
    except Exception as e:
        print(f"❌ Error notifying evaluation: {e}")


if __name__ == "__main__":
    # Example of reading JSON from local file or TDS request
    with open("sample_request.json") as f:
        json_data = json.load(f)
    process_json_request(json_data)
