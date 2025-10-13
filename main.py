import os
import json
import requests
import time
import google.generativeai as genai
from dotenv import load_dotenv
from repo_utils import create_and_setup_repo, subprocess_run_safe
from datetime import datetime
import subprocess
from huggingface_hub import HfApi, create_repo
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import sys

# 1️⃣ Load environment variables
load_dotenv()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_UBUNTU_TOKEN = os.getenv("HF_UBUNTU_TOKEN")
SERVER_SECRET = os.getenv("SERVER_SECRET", "abcd1234")

genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------------------------------------------------------
# 🔧 Utility Functions
# ------------------------------------------------------------------------------

def deploy_to_huggingface(repo_name, html_content):
    """Deploy HTML to a Hugging Face static Space."""
    if not HF_UBUNTU_TOKEN:
        print("❌ HF_UBUNTU_TOKEN not found. Skipping Hugging Face deploy.")
        return None

    api = HfApi()
    space_id = f"{GITHUB_USERNAME}/{repo_name}"
    print(f"🚀 Deploying to Hugging Face Space: {space_id}")

    try:
        create_repo(
            repo_id=space_id,
            repo_type="space",
            token=HF_UBUNTU_TOKEN,
            space_sdk="static",
            exist_ok=True,
        )

        tmp_path = "/tmp/index.html"
        with open(tmp_path, "w") as f:
            f.write(html_content)

        api.upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo="index.html",
            repo_id=space_id,
            repo_type="space",
            token=HF_UBUNTU_TOKEN,
        )

        print(f"✅ Successfully deployed to: https://huggingface.co/spaces/{space_id}")
        return f"https://huggingface.co/spaces/{space_id}"

    except Exception as e:
        print(f"❌ Hugging Face deploy failed: {e}")
        return None


def generate_html_from_brief(brief):
    """Generate HTML output using Gemini model."""
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""
    You are an expert web developer. Based on the following project brief:
    {brief}

    Generate a COMPLETE HTML file (with inline CSS/JS) implementing the requested feature(s).
    Do not include Python code or explanations.
    """
    response = model.generate_content(prompt)
    html_content = response.text

    # Extract HTML safely
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

    if secret != SERVER_SECRET:
        print("❌ Invalid secret.")
        return {"status": "error", "message": "Unauthorized"}, 401

    print(f"📨 Processing task: {task} (Round {round_num})")

    if round_num == 1:
        # Round 1 → Full site creation
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        repo_name = f"{task}_{timestamp}"

        html_output = generate_html_from_brief(brief)
        repo_path, pages_url, commit_sha = create_and_setup_repo(
            repo_name, html_output, GITHUB_USERNAME, GITHUB_TOKEN
        )
        hf_space_url = deploy_to_huggingface(repo_name, html_output)

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

        return {"status": "✅ Round 1 completed", "repo": repo_name}, 200

    elif round_num == 2:
        # Round 2 → Modify existing repo and redeploy
        existing_repo_name = json_data.get("existing_repo_name")
        if not existing_repo_name:
            print("❌ Missing 'existing_repo_name' for round 2.")
            return {"status": "error", "message": "existing_repo_name required"}, 400

        print(f"🛠️ Updating repository: {existing_repo_name}")

        # Clone repo
        auth_url = f"https://oauth2:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{existing_repo_name}.git"
        subprocess_run_safe(["git", "clone", auth_url, existing_repo_name])
        repo_dir = os.path.join(os.getcwd(), existing_repo_name)

        # Generate updated HTML
        html_output = generate_html_from_brief(brief)
        with open(os.path.join(repo_dir, "index.html"), "w") as f:
            f.write(html_output)

        # Update README.md
        readme_path = os.path.join(repo_dir, "README.md")
        with open(readme_path, "a") as f:
            f.write(f"\n\n## Round 2 Update\n- {brief}\n")

        # Commit and push updates
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

        payload = {
            "email": email,
            "task": task,
            "round": 2,
            "nonce": nonce,
            "repo_url": f"https://github.com/{GITHUB_USERNAME}/{existing_repo_name}",
            "commit_sha": commit_sha or "unknown_commit",
            "pages_url": pages_url,
        }

        # Print payload for round 2 like round 1
        print(f"📤 Sending Round 2 payload:\n{json.dumps(payload, indent=2)}")
        post_with_retry(evaluation_url, payload)

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
    """Main endpoint for both round 1 and round 2."""
    try:
        json_data = await request.json()
        result, code = process_json_request(json_data)
        return JSONResponse(result, status_code=code)
    except Exception as e:
        return JSONResponse({"status": "❌ Failed", "error": str(e)}, status_code=500)

# ------------------------------------------------------------------------------
# ⚡ Local Testing
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Please provide JSON request file as argument, e.g.: python3 main.py sample_request_round1.json")
        sys.exit(1)

    json_file = sys.argv[1]
    with open(json_file) as f:
        json_data = json.load(f)
    process_json_request(json_data)
