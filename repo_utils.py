import os
import subprocess
import tempfile

def subprocess_run_safe(command, cwd=None, env=None, input_data=None):
    """Execute subprocess command with complete error output."""
    if env is None:
        env = os.environ.copy()
    print(f"🔧 Running: {' '.join(command)}")
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode == 0:
        if result.stdout.strip():
            print(f"✅ STDOUT:\n{result.stdout.strip()}")
        return result.stdout.strip()
    else:
        print(f"\n[ERROR] Command failed: {' '.join(command)}")
        print(f"🔴 Exit Code: {result.returncode}")
        if result.stdout.strip():
            print(f"📤 STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip():
            print(f"📥 STDERR:\n{result.stderr.strip()}")
        return None


def create_and_setup_repo(repo_name, html_content, username, token):
    """Creates new GitHub repo, pushes HTML file, enables GitHub Pages, and returns repo path, pages URL, and commit SHA."""
    print(f"🚀 Creating repository: {repo_name}")
    env = os.environ.copy()
    env["GH_TOKEN"] = token

    # Step 1: Create repo (public, no clone)
    repo_create_output = subprocess_run_safe(
        ["gh", "repo", "create", f"{username}/{repo_name}", "--public", "--clone=false"],
        env=env
    )
    if not repo_create_output:
        print("❌ Repo creation failed.")
        return None, None, None

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, repo_name)
        auth_url = f"https://oauth2:{token}@github.com/{username}/{repo_name}.git"
        print(f"🔗 Cloning from: {auth_url}")

        # Step 2: Clone repo
        clone_result = subprocess_run_safe(
            ["git", "clone", auth_url, repo_dir],
            env=env
        )
        if clone_result is None:
            print("❌ Git clone failed.")
            return None, None, None

        # Step 3: Write index.html
        with open(os.path.join(repo_dir, "index.html"), "w") as f:
            f.write(html_content)

        # Step 4: Add LICENSE
        with open(os.path.join(repo_dir, "LICENSE"), "w") as f:
            f.write("MIT License\n\nCopyright (c) 2025 Ram Verma")

        # Step 5: Add README.md
        with open(os.path.join(repo_dir, "README.md"), "w") as f:
            f.write(f"# {repo_name}\n\nAuto-generated web app using Gemini 2.5 Flash.\n")

        # Step 6: Git push
        cmds = [
            ["git", "config", "user.name", "Automation Bot"],
            ["git", "config", "user.email", "bot@example.com"],
            ["git", "add", "."],
            ["git", "commit", "-m", "Initial commit"],
            ["git", "push", "origin", "main"]
        ]
        for cmd in cmds:
            if subprocess_run_safe(cmd, cwd=repo_dir, env=env) is None:
                print("❌ Git command failed. Aborting.")
                return None, None, None

        # Step 7: Enable GitHub Pages
        payload = '{"source": {"branch": "main", "path": "/"}}'
        if subprocess_run_safe(
            ["gh", "api", "--method", "POST", f"repos/{username}/{repo_name}/pages", "--input", "-"],
            input_data=payload,
            env=env
        ) is None:
            print("❌ Enabling GitHub Pages failed.")
            return None, None

        # After last git push, still inside the tempdir
        commit_sha = subprocess_run_safe(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=env)
        if commit_sha is None:
            commit_sha = "unknown_commit"
    
        # Success → return repo_dir and pages URL
        pages_url = f"https://{username}.github.io/{repo_name}/"
        return repo_dir, pages_url, commit_sha
