import os
import json
import requests
import time
import google.generativeai as genai
from dotenv import load_dotenv
from repo_utils import create_and_setup_repo
from datetime import datetime
import subprocess
from huggingface_hub import HfApi, create_repo

def deploy_to_huggingface(repo_name, html_content):
    """
    Deploy the generated HTML app to a new Hugging Face Space.
    It creates (or updates) a Space named <repo_name> and pushes HTML there.
    """
    hf_token = os.getenv("HF_UBUNTU_TOKEN")
    if not hf_token:
        print("❌ HF_UBUNTU_TOKEN not found in .env. Please set your Hugging Face token.")
        return None

    api = HfApi()

    # Create or reuse a space
    space_id = f"{GITHUB_USERNAME}/{repo_name}"
    print(f"🚀 Deploying to Hugging Face Space: {space_id}")

    try:
        create_repo(
            repo_id=space_id,
            repo_type="space",
            token=hf_token,
            space_sdk="static",  # 'static' = pure HTML/CSS/JS app
            exist_ok=True
        )

        # Push index.html to space
        tmp_path = "/tmp/index.html"
        with open(tmp_path, "w") as f:
            f.write(html_content)


        api.upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo="index.html",
            repo_id=space_id,
            repo_type="space",
            token=hf_token
        )

        print(f"✅ Successfully deployed to: https://huggingface.co/spaces/{space_id}")
        return f"https://huggingface.co/spaces/{space_id}"

    except Exception as e:
        print(f"❌ Failed to deploy to Hugging Face: {e}")
        return None

# 1️⃣ Load environment variables
load_dotenv()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)


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
    
    html_content = response.text
    if "```html" in html_content:
        html_content = html_content.split("```html")[1].split("```")[0].strip()
    elif "```" in html_content:
        html_content = html_content.split("```")[1].split("```")[0].strip()
    return html_content


def get_latest_commit_sha(repo_name):
    """Return latest commit SHA from the local repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_name,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "unknown_commit"
    except Exception:
        return "unknown_commit"


def post_with_retry(url, payload, max_wait=600):
    """POST payload with exponential backoff until success or 10 minutes."""
    delay = 1
    total_wait = 0
    headers = {"Content-Type": "application/json"}

    while total_wait < max_wait:
        try:
            r = requests.post(url, json=payload, headers=headers)
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
        delay *= 2  # exponential backoff

    print("❌ Gave up after 10 minutes without success.")
    return False


def process_json_request(json_data):
    """Main pipeline for processing TDS server JSON."""
    email = json_data["email"]
    task = json_data["task"]
    round_num = json_data["round"]
    nonce = json_data["nonce"]
    brief = json_data["brief"]
    evaluation_url = json_data["evaluation_url"]

    print(f"📨 Processing task: {task}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    repo_name = f"{task.replace('-', '_')}_{timestamp}"

    print(f"🚀 Using repository: {repo_name}")

    # Step 1: Generate HTML
    html_output = generate_html_from_brief(brief)

    # Step 2: Create repo and deploy
    repo_path, pages_url, commit_sha = create_and_setup_repo(
        repo_name, html_output, GITHUB_USERNAME, GITHUB_TOKEN
    )
    if repo_path is None:
        print("❌ Repository setup failed. Aborting.")
        return

    # Step 2.5: Deploy app to Hugging Face Space
    hf_space_url = deploy_to_huggingface(repo_name, html_output)
    if hf_space_url:
        print(f"🌐 Hugging Face deployment URL: {hf_space_url}")
    else:
        print("⚠️ Hugging Face deployment skipped or failed.")

    # Step 3: Use commit_sha returned from create_and_setup_repo
    payload = {
        "email": email,
        "task": task,
        "round": round_num,
        "nonce": nonce,
        "repo_url": f"https://github.com/{GITHUB_USERNAME}/{repo_name}",
        "commit_sha": commit_sha,
        "pages_url": pages_url,
    }

    print(f"📤 Sending payload to evaluation URL:\n{json.dumps(payload, indent=2)}")
    post_with_retry(evaluation_url, payload)


from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Dynamic Auto Web Deployer")

@app.get("/")
def root():
    """Check if app is alive"""
    return {"status": "✅ Running", "message": "Auto Web Deployer is live on Hugging Face."}


@app.post("/deploy")
async def deploy(request: Request):
    """
    Receive a JSON request with:
    {
      "email": "...",
      "task": "...",
      "round": 1,
      "nonce": "...",
      "brief": "...",
      "evaluation_url": "..."
    }
    """
    try:
        json_data = await request.json()
        process_json_request(json_data)
        return JSONResponse({"status": "✅ Task started successfully", "details": json_data["task"]})
    except Exception as e:
        return JSONResponse({"status": "❌ Failed", "error": str(e)}, status_code=500)


if __name__ == "__main__":
    # For local testing
    with open("sample_request.json") as f:
        json_data = json.load(f)
    process_json_request(json_data)
