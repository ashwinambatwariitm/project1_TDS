---
title: Project1 TDS Docker Deployment
emoji: 🐳
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
-----

# 🤖 AI Web App Auto-Deployer

This project is a powerful automation tool that uses the Google Gemini API to generate a complete static website from a simple text brief. It then automatically creates a GitHub repository, pushes the generated code, deploys it to **GitHub Pages**, and mirrors the deployment on **Hugging Face Spaces**. The entire process is managed via a FastAPI server, designed to handle both initial deployments and subsequent updates.

## ✨ Core Features

  * **AI-Powered Code Generation**: Leverages Google's Gemini model to generate complete, single-file HTML websites with inline CSS and JavaScript based on a natural language brief.
  * **Automated GitHub Workflow**: Creates a new public GitHub repository for each new task.
  * **Dual Deployment**: Automatically deploys the generated site to both GitHub Pages and Hugging Face Spaces for redundancy and flexibility.
  * **Multi-Round Updates**: Seamlessly handles updates by cloning the existing repository, applying new changes from an updated brief, and re-deploying.
  * **API-Driven**: Built with FastAPI, allowing it to be controlled via simple HTTP requests.
  * **Containerized**: Includes a `Dockerfile` for easy and consistent deployment.

-----

## ⚙️ How It Works

The application operates as a web server that listens for `POST` requests on its `/deploy` endpoint. The workflow is divided into two rounds:

### Round 1: Initial Deployment

1.  The server receives a `POST` request containing a JSON payload with `round: 1`, a project `brief`, and an `evaluation_url`.
2.  It sends the `brief` to the **Gemini API**, which returns a complete HTML file.
3.  Using the GitHub CLI (`gh`), it creates a new public repository on your GitHub account.
4.  It clones the new repository, adds the generated `index.html`, a `README.md`, and a `LICENSE` file.
5.  The files are committed and pushed to the `main` branch.
6.  It enables **GitHub Pages** for the repository.
7.  It creates a static **Hugging Face Space** and uploads the `index.html` file.
8.  Finally, it sends a JSON payload with the new repository URL, GitHub Pages URL, and commit SHA to the `evaluation_url`.

### Round 2: Updating an Existing Project

1.  The server receives a `POST` request with `round: 2`, an updated `brief`, and the name of the `existing_repo_name`.
2.  It clones the specified repository from GitHub.
3.  It sends the new `brief` to the **Gemini API** to get updated HTML content.
4.  It overwrites the `index.html` file with the new content and appends the update details to the `README.md`.
5.  The changes are committed and pushed to the `main` branch, automatically updating the GitHub Pages site.
6.  It sends a new payload with the updated commit SHA to the `evaluation_url`.

-----

## 📂 Project Structure

```
.
├── Dockerfile              # Container configuration for deployment
├── .huggingface.yml        # Hugging Face Spaces configuration
├── main.py                 # Main FastAPI application logic
├── repo_utils.py           # Helper functions for Git & GitHub operations
├── requirements.txt        # Python dependencies
├── sample_request_round1.json  # Example payload for initial deployment
└── sample_request_round2.json  # Example payload for an update
```

-----

## 🚀 Getting Started

Follow these steps to set up and run the project locally or deploy it.

### 1\. Prerequisites

  * Python 3.10+
  * Git
  * [GitHub CLI](https://cli.github.com/) (`gh`)
  * Docker (for containerized deployment)

### 2\. Installation

1.  **Clone the repository:**

    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

2.  **Create a `.env` file:**
    Create a file named `.env` in the root directory and add your credentials.

    ```ini
    # .env file
    GITHUB_USERNAME="your-github-username"
    GITHUB_TOKEN="ghp_YourGitHubPersonalAccessToken"
    GEMINI_API_KEY="YourGoogleGeminiAPIKey"
    HF_UBUNTU_TOKEN="hf_YourHuggingFaceWriteToken"
    SERVER_SECRET="abcd1234" # A custom secret to secure your endpoint
    ```

    > **Important:**

    >   * Your **GitHub Token** needs `repo` and `workflow` permissions.
    >   * Your **Hugging Face Token** needs `write` permissions.

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

### 3\. Usage

You can run the application directly with Uvicorn for development or build a Docker container for production.

#### Running Locally

1.  **Create the environment (we'll name the folder venv)::**

    ```bash
    python3 -m venv venv
    ```
    You will see a new folder named venv in your project directory.

2.  **Activate the environment: The command differs based on your operating system.:**
    ```bash
     python3 -m venv venv
    ```
    ➡️ Verification: After activation, you should see (venv) appear at the beginning of your terminal prompt, indicating that the virtual environment is active.

3. **Now that your environment is active, install all the required Python libraries listed in requirements.txt.**

    ```bash
     uvicorn main:app --host 0.0.0.0 --port 7860 --reload
    ```

The server will be available at `http://localhost:7860`.

#### Running with Docker

1.  **Build the Docker image:**

    ```bash
    docker build -t auto-deployer .
    ```

2.  **Run the Docker container:**
    Make sure to pass your `.env` file to the container.

    ```bash
    docker run --env-file .env -p 7860:7860 auto-deployer
    ```

-----

## 🔌 API Endpoints

### Health Check

  * **Endpoint**: `/`
  * **Method**: `GET`
  * **Description**: A simple endpoint to check if the server is running.
  * **Success Response** (`200 OK`):
    ```json
    {
      "status": "✅ Running",
      "message": "Auto Web Deployer is live."
    }
    ```

### Trigger Deployment

  * **Endpoint**: `/deploy`
  * **Method**: `POST`
  * **Description**: The main endpoint to handle deployment requests for both Round 1 and Round 2.
  * **Request Body** (`application/json`):
      * See `sample_request_round1.json` and `sample_request_round2.json` for examples.
  * **Success Response** (`200 OK`):
    ```json
    // For Round 1
    {
      "status": "✅ Round 1 completed",
      "repo": "SnakeAndLadderGame"
    }

    // For Round 2
    {
      "status": "✅ Round 2 completed",
      "repo": "SnakeAndLadderGame"
    }
    ```

### Example Request (using cURL)

```bash
# Round 1 Request
curl -X POST http://localhost:7860/deploy \
-H "Content-Type: application/json" \
-d @sample_request_round1.json

# Round 2 Request
curl -X POST http://localhost:7860/deploy \
-H "Content-Type: application/json" \
-d @sample_request_round2.json
```

-----

## 📜 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
