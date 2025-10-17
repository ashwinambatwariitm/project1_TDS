import os
import json
import requests
import time
import base64
import shutil
import tempfile
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from repo_utils import create_and_setup_repo, subprocess_run_safe, wait_for_github_pages
from huggingface_utils import deploy_to_huggingface
from config import (
    GITHUB_USERNAME, GITHUB_TOKEN, SERVER_SECRET,
    validate_config, get_gemini_client, get_fallback_client
)

# ----------------------------
# 🔧 Initialize environment
# ----------------------------
load_dotenv()
validate_config()

HF_UBUNTU_TOKEN = os.getenv("HF_UBUNTU_TOKEN")

# ----------------------------
# ⚡ Utility: encode image to Base64 (optional)
# ----------------------------
def encode_image_to_base64(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        mime_type = r.headers.get("Content-Type", "image/png")
        encoded = base64.b64encode(r.content).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"
    except Exception as e:
        print(f"⚠️ Failed to encode image {url}: {e}")
        return url  # fallback to direct URL

# ----------------------------
# ⚡ Generate HTML (fallback-aware)
# ----------------------------
def generate_html_from_brief(brief, attachments=None, checks=None, use_fallback=False):
    attachments = attachments or []
    checks = checks or []

    # ---- Format attachments ----
    attachments_text = ""
    if attachments:
        lines = []
        for a in attachments:
            name = a.get("filename") or a.get("name") or "attachment"
            url = a.get("url") or a.get("content") or ""
            url_preview = (url[:60] + "...") if isinstance(url, str) and len(url) > 60 else url
            if url.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                lines.append(f"- Image: {name} ({url_preview}) — include visually using <img src='{url}'>")
            else:
                lines.append(f"- {name}: {url_preview}")
        attachments_text = "\nAttachments:\n" + "\n".join(lines)

    # ---- Format checks ----
    checks_text = ""
    if checks:
        checks_text = "\nEvaluation Checks:\n" + "\n".join([f"- {c}" for c in checks])

    # ---- Build prompt ----
    prompt = f"""
You are an expert web developer.

Based on the following project brief:
{brief}

{attachments_text}

{checks_text}

Generate a COMPLETE HTML file (inline CSS/JS) implementing all required features.
- All features must work as described.
- Display images correctly using <img> or background images.
- Use non-image attachments (CSV, JSON, text) appropriately.
- All evaluation checks must pass.
- Output ONLY HTML content (no markdown or Python code, no backticks).
"""

    # ---- Choose client ----
    client = get_fallback_client() if use_fallback else get_gemini_client()

    try:
        model = client.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        html_content = response.text.strip()
    except Exception as e:
        if not use_fallback:
            print(f"⚠️ Primary Gemini API failed: {e}. Trying fallback...")
            return generate_html_from_brief(brief, attachments, checks, use_fallback=True)
        else:
            raise RuntimeError(f"Both primary and fallback Gemini APIs failed: {e}")

    # ---- Clean HTML fences ----
    if "```html" in html_content:
        html_content = html_content.split("```html")[1].split("```")[0].strip()
    elif "```" in html_content:
        html_content = html_content.split("```")[1].split("```")[0].strip()

    return html_content

# ----------------------------
# ⚡ POST with retry
# ----------------------------
def post_with_retry(url, payload, max_wait=600):
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

# ----------------------------
# ⚡ Main JSON processing
# ----------------------------
def process_json_request(json_data):
    email = json_data.get("email")
    task = json_data.get("task")
    round_num = json_data.get("round", 1)
    nonce = json_data.get("nonce")
    brief = json_data.get("brief")
    evaluation_url = json_data.get("evaluation_url")
    secret = json_data.get("secret")
    checks = json_data.get("checks", [])
    attachments = json_data.get("attachments", [])

    if secret != SERVER_SECRET:
        print("❌ Invalid secret.")
        return {"status": "error", "message": "Unauthorized"}, 401

    repo_name = json_data.get("existing_repo_name") or f"{task}"
    print(f"📨 Processing task: {task} (Round {round_num})")

    if round_num == 1:
        html_output = generate_html_from_brief(brief, attachments, checks)
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
            "hf_space_url": hf_space_url,
        }
        print(f"📤 Sending Round 1 payload:\n{json.dumps(payload, indent=2)}")
        post_with_retry(evaluation_url, payload)

        if repo_dir and os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
            print(f"🗑️ Cleaned up local folder: {repo_dir}")

        return {"status": "✅ Round 1 completed", "repo": repo_name}, 200

    elif round_num == 2:
        if not repo_name:
            tmp_repo_file = "/tmp/last_round1_repo.txt"
            if os.path.exists(tmp_repo_file):
                with open(tmp_repo_file) as f:
                    repo_name = f.read().strip()
            else:
                print("❌ Missing 'existing_repo_name' for round 2.")
                return {"status": "error", "message": "existing_repo_name required"}, 400

        repo_dir = tempfile.mkdtemp(prefix=f"{repo_name}_")
        auth_url = f"https://oauth2:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        subprocess_run_safe(["git", "clone", auth_url, repo_dir])

        html_output = generate_html_from_brief(brief, attachments, checks)
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
        pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
        print("⏳ Waiting 120s for GitHub Pages refresh...")
        time.sleep(120)

        payload = {
            "email": email,
            "task": task,
            "round": 2,
            "nonce": nonce,
            "repo_url": f"https://github.com/{GITHUB_USERNAME}/{repo_name}",
            "commit_sha": commit_sha or "unknown_commit",
            "pages_url": pages_url,
        }
        print(f"📤 Sending Round 2 payload:\n{json.dumps(payload, indent=2)}")
        post_with_retry(evaluation_url, payload)

        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
            print(f"🗑️ Cleaned up local folder: {repo_dir}")

        return {"status": "✅ Round 2 completed", "repo": repo_name}, 200

# ----------------------------
# ⚡ FastAPI server
# ----------------------------
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

@app.get


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Server is healthy"}

if __name__ == "__main__":
    sample_file = "sample_request_round1.json"
    if os.path.exists(sample_file):
        with open(sample_file) as f:
            json_data = json.load(f)
        process_json_request(json_data)

