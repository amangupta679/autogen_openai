import os
import logging
import json
import re
import random
import string
import urllib.parse
import subprocess
import asyncio
import git
from typing import Any, Dict
from dotenv import load_dotenv
import openai
# AutoGen imports
import autogen
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"
SONAR_CURL_COMMAND = (
    'curl -u c1666505b66c578ac5e665ee878880b4bf92cf47: '
    '"http://10.11.12.149:9000/api/issues/search?componentKeys=POC_ESQL\u0026resolved=false\u0026types=BUG,CODE_SMELL,VULNERABILITY\u0026ps=500" '
    '-o issues.json'
)
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
ENCODED_TOKEN = urllib.parse.quote(GITLAB_TOKEN)
GIT_REPO_URL = f"https://amgupta:{ENCODED_TOKEN}@gitlab.prolifics.com/InnovationCenter/code-quality-automation/samplecode.git"
GIT_REPO_DIR = "./repo"
GIT_FILE_PATH = "PLM2PDH_DTCPOM.esql"
GIT_OUTPUT_FILE = "PLM2PDH_DTCPOM_ai_autofix.esql"

class ESQLAutoFixAgent:
    def __init__(self):
        self.state = {}
        
    def run(self):
        """Run the complete pipeline synchronously"""
        result1 = self.fetch_sonarqube_issues()
        if result1["status"] == "error":
            return result1
            
        result2 = self.fetch_code_from_gitlab()
        if result2["status"] == "error":
            return result2
            
        result3 = self.correct_code()
        if result3["status"] == "error":
            return result3
            
        result4 = self.commit_corrected_code()
        if result4["status"] == "error":
            return result4
            
        result5 = self.trigger_sonar_scan()
        return result5

    def fetch_sonarqube_issues(self) -> Dict[str, Any]:
        try:
            logger.info("Running SonarQube curl command...")
            subprocess.run(SONAR_CURL_COMMAND, shell=True, check=True)
            logger.info("issues.json downloaded.")

            with open("issues.json", "r", encoding="utf-8") as f:
                issues_data = json.load(f)
                self.state["sonarqube_issues"] = issues_data

            return {"status": "success", "message": "Fetched issues.json."}
        except subprocess.CalledProcessError as e:
            logger.error(f"Error executing curl: {e}")
            return {"status": "error", "message": str(e)}

    def fetch_code_from_gitlab(self) -> Dict[str, Any]:
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
                self.state["uploaded_code"] = code

            return {"status": "success", "message": "Code fetched from GitLab."}
        except Exception as e:
            logger.error(f"GitLab fetch failed: {e}")
            return {"status": "error", "message": str(e)}

    def correct_code(self) -> Dict[str, Any]:
        issues = self.state.get("sonarqube_issues")
        uploaded_code = self.state.get("uploaded_code")

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

        for issue in issues.get("issues", []):
            line_num = issue.get("line")
            message = issue.get("message", "").lower()

            if not line_num or line_num < 1 or line_num > len(code_lines):
                continue

            line_content = code_lines[line_num - 1].strip()

            if "unused" in message or "never used" in message or "useless assignment" in message:
                lines_to_remove.add(line_num)

            elif "code is unreachable" in message or "after this statement" in message:
                has_return_issue = True
                for i in range(line_num + 1, len(code_lines) + 1):
                    lines_to_remove.add(i)

            elif "duplicated condition" in message or "unnecessary if" in message:
                duplicate_conditions.add(line_num)

            elif "magic number" in message:
                for num, const in magic_number_map.items():
                    if re.search(r'\b' + re.escape(num) + r'\b', line_content):
                        code_lines[line_num - 1] = re.sub(r'\b' + re.escape(num) + r'\b', const, code_lines[line_num - 1])

            elif "parse error" in message or "unable to parse" in message or "expecting" in message:
                parsing_error_lines.add(line_num)

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

        for line_num in parsing_error_lines:
            if line_num - 1 < len(code_lines):
                original = code_lines[line_num - 1]
                fixed = original.strip()
                if not fixed.endswith(";"):
                    fixed += ";"
                fixed = fixed.replace("''", "'").replace("\"\"", "\"")
                fixed = re.sub(r"\bTHN\b", "THEN", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bIF\b\s*\(", "IF ", fixed, flags=re.IGNORECASE)
                code_lines[line_num - 1] = fixed

        cleaned_lines = [
            line for idx, line in enumerate(code_lines, start=1)
            if idx not in lines_to_remove
        ]

        final_code = "\n".join(cleaned_lines)
        if "DECLARE HTTP_SUCCESS" not in final_code:
            final_code = (
                "DECLARE HTTP_SUCCESS INTEGER CONSTANT 200;\n"
                "DECLARE HTTP_ERROR INTEGER CONSTANT 500;\n"
                + final_code
            )

        self.state["corrected_code"] = final_code
        return {"status": "success", "message": "Code cleaned and parsing errors fixed."}

    def commit_corrected_code(self) -> Dict[str, Any]:
        corrected_code = self.state.get("corrected_code")
        if not corrected_code:
            return {"status": "error", "message": "Corrected code not found."}

        try:
            full_output_path = os.path.join(GIT_REPO_DIR, GIT_OUTPUT_FILE)
            with open(full_output_path, "w", encoding="utf-8") as f:
                f.write(corrected_code)

            repo = git.Repo(GIT_REPO_DIR)
            origin = repo.remote(name="origin")

            new_branch = self.generate_random_branch_name()
            repo.git.checkout("-b", new_branch)

            repo.git.add(A=True)
            repo.index.commit("Intelligently auto-corrected code using SonarQube issues")
            origin.push(new_branch)

            logger.info(f"Pushed changes to new branch: {new_branch}")

            return {"status": "success", "message": f"Corrected code committed to new branch: {new_branch}"}
        except Exception as e:
            logger.error(f"Git commit/push failed: {e}")
            return {"status": "error", "message": str(e)}

    def trigger_sonar_scan(self) -> Dict[str, Any]:
        try:
            logger.info("Triggering SonarQube scan...")
            result = subprocess.run("sonar-scanner", shell=True, check=True, capture_output=True, text=True)
            logger.info(f"SonarQube scan output:\n{result.stdout}")
            return {"status": "success", "message": "SonarQube scan triggered."}
        except subprocess.CalledProcessError as e:
            logger.error(f"SonarQube scan failed: {e}\n{e.stderr}")
            return {"status": "error", "message": f"SonarQube scan failed: {e.stderr}"}

    def generate_random_branch_name(self, prefix="developer.one"):
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{prefix}-{suffix}"

if __name__ == "__main__":
    agent = ESQLAutoFixAgent()
    asyncio.run(agent.run())