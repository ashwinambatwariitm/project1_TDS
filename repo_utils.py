import os
import subprocess
import tempfile

def subprocess_run_safe(command, cwd=None, env=None, input_data=None):
    """Execute subprocess command safely with proper error handling."""
    if env is None:
        env = os.environ.copy()
    try:
        result = subprocess.run(
            command,
            check=True,
            cwd=cwd,
            env=env,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {' '.join(command)}\n{e.stderr}")
        return None


def create_and_setup_repo(repo_name, html_content, username, token):
    """Creates new GitHub repo, pushes HTML file, enables GitHub Pages."""
    print(f"🚀 Creating repository: {repo_name}")
    env = os.environ.copy()
    env["GH_TOKEN"] = token

    # Create repo (public)
    if not subprocess_run_safe(["gh", "repo", "create", f"{username}/{repo_name}", "--public", "--clone=false"], env=env):
        print("❌ Repo creation failed.")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, repo_name)
        auth_url = f"https://oauth2:{token}@github.com/{username}/{repo_name}.git"

        subprocess_run_safe(["git", "clone", auth_url, repo_dir], env=env)

        # Write index.html
        with open(os.path.join(repo_dir, "index.html"), "w") as f:
            f.write(html_content)

        # Add MIT License
        with open(os.path.join(repo_dir, "LICENSE"), "w") as f:
            f.write("MIT License\n\nCopyright (c) 2025 Ram Verma")

        # Add README.md
        with open(os.path.join(repo_dir, "README.md"), "w") as f:
            f.write(f"# {repo_name}\n\nAuto-generated web app using Gemini 2.5 Flash.\n")

        # Git push steps
        cmds = [
            ["git", "config", "user.name", "Automation Bot"],
            ["git", "config", "user.email", "bot@example.com"],
            ["git", "add", "."],
            ["git", "commit", "-m", "Initial commit"],
            ["git", "push", "origin", "main"]
        ]
        for cmd in cmds:
            subprocess_run_safe(cmd, cwd=repo_dir, env=env)

        # Enable GitHub Pages
        payload = '{"source": {"branch": "main", "path": "/"}}'
        subprocess_run_safe(
            ["gh", "api", "--method", "POST", f"repos/{username}/{repo_name}/pages", "--input", "-"],
            input_data=payload,
            env=env
        )

    pages_url = f"https://{username}.github.io/{repo_name}/"
    print(f"✅ GitHub Pages deployed: {pages_url}")
    return pages_url
