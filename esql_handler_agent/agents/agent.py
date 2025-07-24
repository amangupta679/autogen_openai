import os
import logging
import random
import string
import subprocess
import json
import git
import re
from typing import Any, Dict
from dotenv import load_dotenv
import openai
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
import urllib.parse

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"

# SonarQube curl command to fetch issues
SONAR_CURL_COMMAND = (
    'curl -u c1666505b66c578ac5e665ee878880b4bf92cf47: '
    '"http://10.11.12.149:9000/api/issues/search?componentKeys=POC_ESQL&resolved=false&types=BUG,CODE_SMELL,VULNERABILITY&ps=500" '
    '-o issues.json'
)

# GitLab config
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
ENCODED_TOKEN = urllib.parse.quote(GITLAB_TOKEN)
GIT_REPO_URL = f"https://amgupta:{ENCODED_TOKEN}@gitlab.prolifics.com/InnovationCenter/code-quality-automation/samplecode.git"
GIT_REPO_DIR = "./repo"
GIT_FILE_PATH = "PLM2PDH_DTCPOM.esql"
GIT_OUTPUT_FILE = "PLM2PDH_DTCPOM_ai_autofix.esql"

# Step 1: Fetch issues.json from SonarQube
def fetch_sonarqube_issues(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        logger.info("Running SonarQube curl command...")
        subprocess.run(SONAR_CURL_COMMAND, shell=True, check=True)
        logger.info("issues.json downloaded.")

        with open("issues.json", "r", encoding="utf-8") as f:
            issues_data = json.load(f)
            state["sonarqube_issues"] = issues_data

        return {"status": "success", "message": "Fetched issues.json."}
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing curl: {e}")
        return {"status": "error", "message": str(e)}
# Step 2: Clone/pull repo and extract the source code
async def fetch_code_from_gitlab(tool_context: ToolContext) -> Dict[str, Any]:
    try:
        if os.path.exists(GIT_REPO_DIR):
            logger.info("Pulling latest code from GitLab...")
            repo = git.Repo(GIT_REPO_DIR)
            repo.git.reset('--hard')
            repo.remotes.origin.pull()
        else:
            logger.info("Cloning GitLab repo...")
            git.Repo.clone_from(GIT_REPO_URL, GIT_REPO_DIR)

        full_file_path = os.path.join(GIT_REPO_DIR, GIT_FILE_PATH)
        with open(full_file_path, "r", encoding="utf-8") as f:
            code = f.read()
            tool_context.state["uploaded_code"] = code

        return {"status": "success", "message": "Code fetched from GitLab."}
    except Exception as e:
        logger.error(f"GitLab fetch failed: {e}")
        return {"status": "error", "message": str(e)}

# Step 3: Intelligently correct code using SonarQube issues
async def correct_code(tool_context: ToolContext) -> Dict[str, Any]:
    issues = tool_context.state.get("sonarqube_issues")
    uploaded_code = tool_context.state.get("uploaded_code")

    if not issues or not uploaded_code:
        return {"status": "error", "message": "Missing data to correct code."}

    code_lines = uploaded_code.splitlines()
    lines_to_remove = set()
    parsing_error_lines = set()
    magic_number_map = {
        "200": "HTTP_SUCCESS",
        "500": "HTTP_ERROR"
    }

    duplicate_conditions = set()
    has_return_issue = False

    # Step 1: Analyze SonarQube issues
    for issue in issues.get("issues", []):
        line_num = issue.get("line")
        message = issue.get("message", "").lower()

        if not line_num or line_num < 1 or line_num > len(code_lines):
            continue

        line_content = code_lines[line_num - 1].strip()

        # Unused variable or useless assignments
        if "unused" in message or "never used" in message or "useless assignment" in message:
            lines_to_remove.add(line_num)

        # Unreachable code after return
        elif "code is unreachable" in message or "after this statement" in message:
            has_return_issue = True
            for i in range(line_num + 1, len(code_lines) + 1):
                lines_to_remove.add(i)

        # Unnecessary IF or duplicated condition
        elif "duplicated condition" in message or "unnecessary if" in message:
            duplicate_conditions.add(line_num)

        # Magic numbers
        elif "magic number" in message:
            for num, const in magic_number_map.items():
                if re.search(r'\b' + re.escape(num) + r'\b', line_content):
                    code_lines[line_num - 1] = re.sub(r'\b' + re.escape(num) + r'\b', const, code_lines[line_num - 1])

        # Parsing error detection
        elif "parse error" in message or "unable to parse" in message or "expecting" in message:
            parsing_error_lines.add(line_num)

    # Step 2: Handle duplicate IF blocks
    seen_conditions = set()
    for line_num in sorted(duplicate_conditions):
        line = code_lines[line_num - 1]
        match = re.search(r'IF\s+(.*?)\s+THEN', line, re.IGNORECASE)
        if match:
            condition = match.group(1).strip()
            if condition in seen_conditions:
                lines_to_remove.add(line_num)
            else:
                seen_conditions.add(condition)

    # Step 3: Attempt auto-fixes for parsing errors
    for line_num in parsing_error_lines:
        if line_num - 1 < len(code_lines):
            original = code_lines[line_num - 1]
            # Basic cleanup to fix missing semicolons or unbalanced quotes/brackets
            fixed = original.strip()
            if not fixed.endswith(";"):
                fixed += ";"
            fixed = fixed.replace("''", "'").replace("\"\"", "\"")
            fixed = re.sub(r"\bTHN\b", "THEN", fixed, flags=re.IGNORECASE)
            fixed = re.sub(r"\bIF\b\s*\(", "IF ", fixed, flags=re.IGNORECASE)
            code_lines[line_num - 1] = fixed

    # Step 4: Remove marked lines
    cleaned_lines = [
        line for idx, line in enumerate(code_lines, start=1)
        if idx not in lines_to_remove
    ]

    # Step 5: Add constant declarations if missing
    final_code = "\n".join(cleaned_lines)
    if "DECLARE HTTP_SUCCESS" not in final_code:
        final_code = (
            "DECLARE HTTP_SUCCESS INTEGER CONSTANT 200;\n"
            "DECLARE HTTP_ERROR INTEGER CONSTANT 500;\n"
            + final_code
        )

    tool_context.state["corrected_code"] = final_code
    return {"status": "success", "message": "Code cleaned and parsing errors fixed."}

# Step 4: Save corrected code and commit back to GitLab
def generate_random_branch_name(prefix="developer.one"):
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}-{suffix}"

# Step 4: Save corrected code and commit back to GitLab
async def commit_corrected_code(tool_context: ToolContext) -> Dict[str, Any]:
    corrected_code = tool_context.state.get("corrected_code")
    if not corrected_code:
        return {"status": "error", "message": "Corrected code not found."}

    try:
        full_output_path = os.path.join(GIT_REPO_DIR, GIT_OUTPUT_FILE)
        with open(full_output_path, "w", encoding="utf-8") as f:
            f.write(corrected_code)

        repo = git.Repo(GIT_REPO_DIR)
        origin = repo.remote(name="origin")

        # Create a new random branch
        new_branch = generate_random_branch_name()
        repo.git.checkout("-b", new_branch)

        repo.git.add(A=True)
        repo.index.commit("Intelligently auto-corrected code using SonarQube issues")
        origin.push(new_branch)

        logger.info(f"Pushed changes to new branch: {new_branch}")

        return {"status": "success", "message": f"Corrected code committed to new branch: {new_branch}"}
    except Exception as e:
        logger.error(f"Git commit/push failed: {e}")
        return {"status": "error", "message": str(e)}

# Step 5: Trigger SonarQube scan
async def trigger_sonar_scan(tool_context: ToolContext) -> Dict[str, Any]:
    try:
        logger.info("Triggering SonarQube scan...")
        result = subprocess.run("sonar-scanner", shell=True, check=True, capture_output=True, text=True)
        logger.info(f"SonarQube scan output:\n{result.stdout}")
        return {"status": "success", "message": "SonarQube scan triggered."}
    except subprocess.CalledProcessError as e:
        logger.error(f"SonarQube scan failed: {e}\n{e.stderr}")
        return {"status": "error", "message": f"SonarQube scan failed: {e.stderr}"}

# Sequential pipeline
code_fix_pipeline = SequentialAgent(
    name="code_fix_pipeline",
    description="End-to-end agent: fetch code, apply intelligent SonarQube fixes, commit, and trigger scan.",
    sub_agents=[
        LlmAgent(name="fetch_issues", model=GEMINI_MODEL, instruction="Fetch issues from SonarQube", tools=[fetch_sonarqube_issues]),
        LlmAgent(name="get_code", model=GEMINI_MODEL, instruction="Clone GitLab repo and fetch code", tools=[fetch_code_from_gitlab]),
        LlmAgent(name="correct_code", model=GEMINI_MODEL, instruction="Intelligently fix code using SonarQube issues", tools=[correct_code]),
        LlmAgent(name="commit_code", model=GEMINI_MODEL, instruction="Commit corrected code to GitLab", tools=[commit_corrected_code]),
        LlmAgent(name="trigger_scan", model=GEMINI_MODEL, instruction="Run sonar-scanner to analyze latest commit", tools=[trigger_sonar_scan])
    ]
)

# Root agent
root_agent = Agent(
    name="hn_root_agent",
    model=GEMINI_MODEL,
    description="Root agent to automate SonarQube fixes from GitLab to GitLab.",
    sub_agents=[code_fix_pipeline]
)
