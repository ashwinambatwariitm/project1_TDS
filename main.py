import os
import json
import requests
import time
import base64
import google.generativeai as genai
from dotenv import load_dotenv
from repo_utils import create_and_setup_repo, subprocess_run_safe, wait_for_github_pages
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import shutil
import tempfile

# Import our new module
from huggingface_utils import deploy_to_huggingface

# 1️⃣ Load environment variables
load_dotenv()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_UBUNTU_TOKEN = os.getenv("HF_UBUNTU_TOKEN")

genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------------------------------------------------------
# 🔧 Utility Functions
# ------------------------------------------------------------------------------

def encode_image_to_base64(url):
    """
    (Optional use) Download and encode image as Base64 data URI.
    Currently not used in prompt — but can be used for full embedding.
    """
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        mime_type = r.headers.get("Content-Type", "image/png")
        encoded = base64.b64encode(r.content).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"
    except Exception as e:
        print(f"⚠️ Failed to encode image {url}: {e}")
        return url  # fallback to direct URL


def generate_html_from_brief(brief, checks=None, attachments=None):
    """Generate HTML output using Gemini model (with image-aware prompt)."""
    model = genai.GenerativeModel("gemini-2.5-flash")

    # ---- Handle attachments ----
    attachments_text = ""
    if attachments:
        attachment_lines = []
        for a in attachments:
            url = a.get("url", "")
            name = a.get("name", "unnamed")
            # If it's an image, tell the model to display it
            if url.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                attachment_lines.append(
                    f"- Image: {name} ({url}) — please include this image visually in the web page using <img src='{url}'>."
                )
            else:
                attachment_lines.append(f"- {name}: {url}")
        attachments_text = "\nAttachments:\n" + "\n".join(attachment_lines)

    # ---- Handle evaluation checks ----
    checks_text = ""
    if checks:
        checks_text = "\nEvaluation Checks:\n" + "\n".join(
            [f"- {c}" for c in checks]
        )

    # ---- Build the final prompt ----
    prompt = f"""
    You are an expert web developer.

    Based on the following project brief:
    {brief}

    {attachments_text}

    {checks_text}

    Generate a COMPLETE HTML file (with inline CSS/JS) implementing all required features.

    Make sure:
    - All features mentioned in the brief are functional.
    - Display all image attachments appropriately using <img> or background images.
    - Any non-image attachment (e.g., CSV, JSON, or text) is used appropriately.
    - All evaluation checks will pass.
    - Output only HTML content (no markdown, no Python, no triple backticks).
    """

    # ---- Generate HTML ----
    response = model.generate_content(prompt)
    html_content = response.text.strip()

    # ---- Clean HTML ----
    if "```html" in html_content:
        html_content = html_content.split("```html")[1].split("```")[0].strip()
    elif "```" in html_content:
        html_content = html_content.split("```")[1].split("```")[0].strip()

    return html_content


def post_with_retry(url, payload, max_wait=600):
    """POST payload with exponential backoff for up to 10 minutes."""
    delay = 2
    total_wait = 0
    while total_wait < max_wait:
        try:
            r = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
            if r.status_code == 200:
                print("✅ Evaluation notified successfully.")
                return True
            else:
                print(f"⚠️ Server returned {r.status_code}: {r.text}")
        except Exception as e:
            print(f"❌ POST failed: {e}")
        print(f"⏳ Retrying in {delay}s...")
        time.sleep(delay)
        total_wait += delay
        delay = min(delay * 2, 60)
    print("❌ Gave up after 10 minutes.")
    return False

# ------------------------------------------------------------------------------
# 🧩 Main Processing Logic
# ------------------------------------------------------------------------------

def process_json_request(json_data):
    """Handles both round 1 and round 2 requests."""
    email = json_data.get("email")
    task = json_data.get("task")
    round_num = json_data.get("round", 1)
    nonce = json_data.get("nonce")
    brief = json_data.get("brief")
    evaluation_url = json_data.get("evaluation_url")
    secret = json_data.get("secret")
    checks = json_data.get("checks", [])
    attachments = json_data.get("attachments", [])

    expected_secret = os.getenv("SERVER_SECRET", "abcd1234")
    if secret != expected_secret:
        print("❌ Invalid secret.")
        return {"status": "error", "message": "Unauthorized"}, 401

    print(f"📨 Processing task: {task} (Round {round_num})")

    if round_num == 1:
        repo_name = f"{task}"
        html_output = generate_html_from_brief(brief, checks, attachments)

        repo_dir, pages_url, commit_sha = None, None, "unknown_commit"
        try:
            repo_dir, pages_url, commit_sha = create_and_setup_repo(
                repo_name, html_output, GITHUB_USERNAME, GITHUB_TOKEN
            )

            hf_space_url = deploy_to_huggingface(repo_name, html_output, GITHUB_USERNAME, HF_UBUNTU_TOKEN)

            with open("/tmp/last_round1_repo.txt", "w") as f:
                f.write(repo_name)

            payload = {
                "email": email,
                "task": task,
                "round": 1,
                "nonce": nonce,
                "repo_url": f"https://github.com/{GITHUB_USERNAME}/{repo_name}",
                "commit_sha": commit_sha,
                "pages_url": pages_url,
            }

            print(f"📤 Sending Round 1 payload:\n{json.dumps(payload, indent=2)}")
            post_with_retry(evaluation_url, payload)

        finally:
            if repo_dir and os.path.exists(repo_dir):
                shutil.rmtree(repo_dir)
                print(f"🗑️ Cleaned up local folder: {repo_dir}")

        return {"status": "✅ Round 1 completed", "repo": repo_name}, 200

    elif round_num == 2:
        existing_repo_name = json_data.get("existing_repo_name")
        if not existing_repo_name:
            tmp_repo_file = "/tmp/last_round1_repo.txt"
            if os.path.exists(tmp_repo_file):
                with open(tmp_repo_file) as f:
                    existing_repo_name = f.read().strip()
            else:
                print("❌ Missing 'existing_repo_name' for round 2.")
                return {"status": "error", "message": "existing_repo_name required"}, 400

        print(f"🛠️ Updating repository: {existing_repo_name}")
        repo_dir = tempfile.mkdtemp(prefix=f"{existing_repo_name}_")

        try:
            auth_url = f"https://oauth2:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{existing_repo_name}.git"
            subprocess_run_safe(["git", "clone", auth_url, repo_dir])

            html_output = generate_html_from_brief(brief, checks, attachments)
            with open(os.path.join(repo_dir, "index.html"), "w") as f:
                f.write(html_output)

            readme_path = os.path.join(repo_dir, "README.md")
            with open(readme_path, "a") as f:
                f.write(f"\n\n## Round 2 Update\n- {brief}\n")

            cmds = [
                ["git", "config", "user.name", "Automation Bot"],
                ["git", "config", "user.email", "bot@example.com"],
                ["git", "add", "."],
                ["git", "commit", "-m", "Round 2 feature update"],
                ["git", "push", "origin", "main"],
            ]
            for cmd in cmds:
                subprocess_run_safe(cmd, cwd=repo_dir)

            commit_sha = subprocess_run_safe(["git", "rev-parse", "HEAD"], cwd=repo_dir)
            pages_url = f"https://{GITHUB_USERNAME}.github.io/{existing_repo_name}/"

            print("⏳ Waiting 120 seconds to allow GitHub Pages to refresh...")
            time.sleep(120)
            print("✅ Wait complete. Proceeding with publishing.")

            payload = {
                "email": email,
                "task": task,
                "round": 2,
                "nonce": nonce,
                "repo_url": f"https://github.com/{GITHUB_USERNAME}/{existing_repo_name}",
                "commit_sha": commit_sha or "unknown_commit",
                "pages_url": pages_url,
            }

            print(f"📤 Sending Round 2 payload:\n{json.dumps(payload, indent=2)}")
            post_with_retry(evaluation_url, payload)

        finally:
            if os.path.exists(repo_dir):
                shutil.rmtree(repo_dir)
                print(f"🗑️ Cleaned up local folder: {repo_dir}")

        return {"status": "✅ Round 2 completed", "repo": existing_repo_name}, 200

# ------------------------------------------------------------------------------
# ⚙️ FastAPI Web Server
# ------------------------------------------------------------------------------

app = FastAPI(title="Dynamic Auto Web Deployer (Round 1 + Round 2)")

@app.get("/")
def root():
    return {"status": "✅ Running", "message": "Auto Web Deployer is live."}

@app.post("/deploy")
async def deploy(request: Request):
    try:
        json_data = await request.json()
        result, code = process_json_request(json_data)
        return JSONResponse(result, status_code=code)
    except Exception as e:
        return JSONResponse({"status": "❌ Failed", "error": str(e)}, status_code=500)

@app.post("/evaluate")
async def evaluate(request: Request):
    data = await request.json()
    print("\n📥 Evaluation received:")
    print(json.dumps(data, indent=2))
    return {"status": "ok"}

if __name__ == "__main__":
    sample_file = "sample_request_round1.json"
    if os.path.exists(sample_file):
        with open(sample_file) as f:
            json_data = json.load(f)
        process_json_request(json_data)
