import os
from huggingface_hub import HfApi, create_repo

def deploy_to_huggingface(repo_name, html_content, github_username, hf_token):
    """Deploy HTML to a Hugging Face static Space."""
    if not hf_token:
        print("❌ HF_UBUNTU_TOKEN not found. Skipping Hugging Face deploy.")
        return None

    api = HfApi()
    space_id = f"{github_username}/{repo_name}"
    print(f"🚀 Deploying to Hugging Face Space: {space_id}")

    try:
        create_repo(
            repo_id=space_id,
            repo_type="space",
            token=hf_token,
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
            token=hf_token,
        )

        print(f"✅ Successfully deployed to: https://huggingface.co/spaces/{space_id}")
        return f"https://huggingface.co/spaces/{space_id}"

    except Exception as e:
        print(f"❌ Hugging Face deploy failed: {e}")
        return None
