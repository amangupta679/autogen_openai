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
from typing import Any, Dict, List
from collections import Counter
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns
import numpy as np
from datetime import datetime
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
# Get environment variables for CI/CD
SONAR_TOKEN = os.getenv("SONAR_TOKEN", "c1666505b66c578ac5e665ee878880b4bf92cf47")
SONAR_HOST_URL = os.getenv("SONAR_HOST_URL", "http://10.11.12.149:9000")
CI_PROJECT_KEY = os.getenv("CI_PROJECT_KEY", "POC_ESQL")

SONAR_CURL_COMMAND = (
    f'curl -u {SONAR_TOKEN}: '
    f'"{SONAR_HOST_URL}/api/issues/search?componentKeys={CI_PROJECT_KEY}&resolved=false&types=BUG,CODE_SMELL,VULNERABILITY&ps=500" '
    '-o issues.json'
)

GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
if GITLAB_TOKEN:
    ENCODED_TOKEN = urllib.parse.quote(GITLAB_TOKEN)
    GIT_REPO_URL = f"https://amgupta:{ENCODED_TOKEN}@gitlab.prolifics.com/InnovationCenter/code-quality-automation/samplecode.git"
else:
    # Fallback for CI/CD environment
    GIT_REPO_URL = "https://gitlab.prolifics.com/InnovationCenter/code-quality-automation/samplecode.git"
GIT_REPO_DIR = "./repo"
GIT_FILE_PATH = "PLM2PDH_DTCPOM.esql"
GIT_OUTPUT_FILE = "PLM2PDH_DTCPOM_ai_autofix.esql"

class ESQLAutoFixAgent:
    def __init__(self):
        self.state = {}
        
    def run(self):
        """Run the complete pipeline synchronously with before/after reporting"""
        result1 = self.fetch_sonarqube_issues()
        if result1["status"] == "error":
            return result1
        
        # Generate BEFORE metrics
        logger.info("\n=== ANALYZING BEFORE AI CORRECTION METRICS ===")
        before_metrics = self.analyze_sonarqube_metrics(self.state["sonarqube_issues"], "before")
            
        result2 = self.fetch_code_from_gitlab()
        if result2["status"] == "error":
            return result2
            
        result3 = self.correct_code()
        if result3["status"] == "error":
            return result3
            
        result4 = self.commit_corrected_code()
        if result4["status"] == "error":
            return result4
            
        # Optional: Trigger SonarQube scan (non-blocking)
        result5 = self.trigger_sonar_scan()
        if result5["status"] == "error":
            logger.warning("SonarQube scan failed, but continuing...")
        
        # Fetch post-correction issues for comparison
        logger.info("\n=== FETCHING POST-CORRECTION ISSUES ===")
        post_result = self.fetch_post_correction_issues()
        if post_result["status"] == "success":
            # Generate AFTER metrics
            logger.info("\n=== ANALYZING AFTER AI CORRECTION METRICS ===")
            after_metrics = self.analyze_sonarqube_metrics(self.state["after_correction_issues"], "after")
            
            # Generate comparison report
            logger.info("\n=== GENERATING COMPARISON REPORT ===")
            comparison_result = self.generate_comparison_report(before_metrics, after_metrics)
            
            if comparison_result:
                return {
                    "status": "success", 
                    "message": "AI code correction completed successfully with comprehensive reports",
                    "report_generated": True,
                    "downloads_directory": comparison_result.get('downloads_dir'),
                    "pdf_report": comparison_result.get('pdf_report'),
                    "png_charts": comparison_result.get('png_charts'),
                    "summary_file": comparison_result.get('summary_file'),
                    "improvements": {
                        "issues_resolved": comparison_result['issues_improvement'],
                        "coverage_gained": comparison_result['coverage_improvement'],
                        "effort_saved": comparison_result['effort_reduction']
                    }
                }
        else:
            logger.warning("Could not fetch post-correction issues for comparison")
            
        return {"status": "success", "message": "AI code correction completed successfully"}

    def fetch_sonarqube_issues(self) -> Dict[str, Any]:
        try:
            # Check if issues.json already exists (from CI pipeline)
            if os.path.exists("issues.json"):
                logger.info("Using existing issues.json file (from CI pipeline)")
            else:
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
        except FileNotFoundError:
            logger.error("issues.json file not found")
            return {"status": "error", "message": "issues.json file not found"}

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
    
    def analyze_sonarqube_metrics(self, issues_data: Dict[str, Any], report_name: str = "before") -> Dict[str, Any]:
        """Analyze SonarQube issues and generate metrics"""
        issues = issues_data.get("issues", [])
        
        # Initialize counters
        severities = [issue.get('severity') for issue in issues if issue.get('severity')]
        statuses = [issue.get('status') for issue in issues if issue.get('status')]
        types = [issue.get('type') for issue in issues if issue.get('type')]
        
        # Parse coverage gap and effort time
        coverage_gap_lines = 0
        total_effort_hours = 0
        
        for issue in issues:
            # Extract effort: convert '3h6min' to hours
            effort = issue.get('effort', '')
            match = re.match(r'(?:(\d+)h)?(?:(\d+)min)?', effort)
            if match:
                hours = int(match.group(1)) if match.group(1) else 0
                minutes = int(match.group(2)) if match.group(2) else 0
                total_effort_hours += hours + minutes / 60
        
            # Extract coverage gap lines from the message
            message = issue.get('message', '')
            match_lines = re.search(r'(\d+)\s+more lines', message)
            if match_lines:
                coverage_gap_lines += int(match_lines.group(1))
        
        # Get total lines from uploaded code
        uploaded_code = self.state.get("uploaded_code", "")
        total_code_lines = len(uploaded_code.splitlines()) if uploaded_code else 1000
        
        # Calculate coverage %
        if total_code_lines > 0:
            coverage_percent = ((total_code_lines - coverage_gap_lines) / total_code_lines) * 100
        else:
            coverage_percent = 0
        
        # Count categories
        severity_count = Counter(severities)
        status_count = Counter(statuses)
        type_count = Counter(types)
        
        metrics = {
            'report_name': report_name,
            'total_issues': len(issues),
            'total_code_lines': total_code_lines,
            'coverage_gap_lines': coverage_gap_lines,
            'coverage_percent': round(coverage_percent, 2),
            'total_effort_hours': round(total_effort_hours, 2),
            'severity_count': dict(severity_count),
            'status_count': dict(status_count),
            'type_count': dict(type_count)
        }
        
        logger.info(f"{report_name.upper()} AI CORRECTION METRICS:")
        logger.info(f"Total Issues: {metrics['total_issues']}")
        logger.info(f"Total Code Lines: {metrics['total_code_lines']}")
        logger.info(f"Coverage Gap Lines: {metrics['coverage_gap_lines']}")
        logger.info(f"Code Coverage: {metrics['coverage_percent']}%")
        logger.info(f"Total Effort Hours: {metrics['total_effort_hours']} hrs")
        logger.info(f"Severities: {metrics['severity_count']}")
        logger.info(f"Types: {metrics['type_count']}")
        
        return metrics
    
    def create_downloads_folder(self) -> str:
        """Create downloads folder with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        downloads_dir = f"./downloads/ai_correction_reports_{timestamp}"
        os.makedirs(downloads_dir, exist_ok=True)
        return downloads_dir
    
    def generate_detailed_change_analysis(self, before_issues: List[Dict], after_issues: List[Dict]) -> Dict[str, Any]:
        """Generate detailed analysis of what changed between before and after"""
        # Create issue dictionaries for comparison
        before_issue_dict = {f"{issue.get('component', '')}:{issue.get('line', 0)}:{issue.get('rule', '')}": issue for issue in before_issues}
        after_issue_dict = {f"{issue.get('component', '')}:{issue.get('line', 0)}:{issue.get('rule', '')}": issue for issue in after_issues}
        
        # Find resolved issues
        resolved_issues = []
        for key, issue in before_issue_dict.items():
            if key not in after_issue_dict:
                resolved_issues.append({
                    'line': issue.get('line', 'N/A'),
                    'severity': issue.get('severity', 'N/A'), 
                    'type': issue.get('type', 'N/A'),
                    'rule': issue.get('rule', 'N/A'),
                    'message': issue.get('message', 'N/A')[:100] + '...' if len(issue.get('message', '')) > 100 else issue.get('message', 'N/A')
                })
        
        # Find new issues (if any)
        new_issues = []
        for key, issue in after_issue_dict.items():
            if key not in before_issue_dict:
                new_issues.append({
                    'line': issue.get('line', 'N/A'),
                    'severity': issue.get('severity', 'N/A'),
                    'type': issue.get('type', 'N/A'), 
                    'rule': issue.get('rule', 'N/A'),
                    'message': issue.get('message', 'N/A')[:100] + '...' if len(issue.get('message', '')) > 100 else issue.get('message', 'N/A')
                })
        
        # Categorize resolved issues by type
        resolved_by_type = Counter([issue['type'] for issue in resolved_issues])
        resolved_by_severity = Counter([issue['severity'] for issue in resolved_issues])
        
        return {
            'resolved_issues': resolved_issues,
            'new_issues': new_issues,
            'resolved_by_type': dict(resolved_by_type),
            'resolved_by_severity': dict(resolved_by_severity),
            'total_resolved': len(resolved_issues),
            'total_new': len(new_issues)
        }
    
    def generate_enhanced_charts(self, before_metrics: Dict[str, Any], after_metrics: Dict[str, Any]) -> plt.Figure:
        """Generate enhanced professional charts with detailed metrics"""
        # Set style
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        
        # Calculate improvements
        issues_improvement = before_metrics['total_issues'] - after_metrics['total_issues']
        coverage_improvement = after_metrics['coverage_percent'] - before_metrics['coverage_percent']
        effort_reduction = before_metrics['total_effort_hours'] - after_metrics['total_effort_hours']
        
        # Create figure with enhanced layout
        fig = plt.figure(figsize=(20, 16))
        fig.suptitle('🤖 AI Code Correction - Comprehensive Analysis Dashboard', 
                    fontsize=24, fontweight='bold', y=0.98)
        
        # Color schemes
        colors_before = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        colors_after = ['#00D2D3', '#FF7675', '#A29BFE', '#6C5CE7', '#FD79A8']
        colors_improvement = ['#00B894', '#E17055', '#74B9FF']
        
        # Chart 1: Comprehensive Before vs After Metrics (Top Left)
        ax1 = plt.subplot(3, 3, (1, 2))
        metrics_categories = ['Total\nIssues', 'Code\nCoverage (%)', 'Effort\nRequired (hrs)', 
                             'Critical\nIssues', 'Major\nIssues', 'Minor\nIssues']
        
        critical_before = before_metrics['severity_count'].get('CRITICAL', 0)
        major_before = before_metrics['severity_count'].get('MAJOR', 0) + before_metrics['severity_count'].get('HIGH', 0)
        minor_before = before_metrics['severity_count'].get('MINOR', 0) + before_metrics['severity_count'].get('LOW', 0) + before_metrics['severity_count'].get('INFO', 0)
        
        critical_after = after_metrics['severity_count'].get('CRITICAL', 0)
        major_after = after_metrics['severity_count'].get('MAJOR', 0) + after_metrics['severity_count'].get('HIGH', 0)
        minor_after = after_metrics['severity_count'].get('MINOR', 0) + after_metrics['severity_count'].get('LOW', 0) + after_metrics['severity_count'].get('INFO', 0)
        
        before_values = [before_metrics['total_issues'], before_metrics['coverage_percent'], 
                        before_metrics['total_effort_hours'], critical_before, major_before, minor_before]
        after_values = [after_metrics['total_issues'], after_metrics['coverage_percent'], 
                       after_metrics['total_effort_hours'], critical_after, major_after, minor_after]
        
        x = np.arange(len(metrics_categories))
        width = 0.35
        
        bars1 = ax1.bar(x - width/2, before_values, width, label='🔴 Before AI Correction', 
                        color=colors_before[0], alpha=0.8, edgecolor='black', linewidth=1)
        bars2 = ax1.bar(x + width/2, after_values, width, label='🟢 After AI Correction', 
                        color=colors_after[0], alpha=0.8, edgecolor='black', linewidth=1)
        
        ax1.set_xlabel('📊 Quality Metrics', fontsize=14, fontweight='bold')
        ax1.set_ylabel('📈 Values', fontsize=14, fontweight='bold')
        ax1.set_title('🔍 Comprehensive Code Quality Analysis', fontsize=16, fontweight='bold', pad=20)
        ax1.set_xticks(x)
        ax1.set_xticklabels(metrics_categories, fontsize=10)
        ax1.legend(fontsize=12, loc='upper right')
        ax1.grid(axis='y', linestyle='--', alpha=0.3)
        
        # Add value labels on bars
        for bar in bars1 + bars2:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + max(before_values + after_values) * 0.01,
                    f'{height:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # Chart 2: Issue Type Distribution - Before (Top Right)
        ax2 = plt.subplot(3, 3, 3)
        if before_metrics['type_count']:
            wedges, texts, autotexts = ax2.pie(before_metrics['type_count'].values(), 
                                              labels=before_metrics['type_count'].keys(),
                                              autopct='%1.1f%%', startangle=90, 
                                              colors=colors_before, explode=[0.05]*len(before_metrics['type_count']),
                                              shadow=True, textprops={'fontsize': 10, 'fontweight': 'bold'})
            ax2.set_title('🔴 Issue Types - Before\n(Total: {} issues)'.format(before_metrics['total_issues']), 
                         fontsize=14, fontweight='bold', pad=20)
        else:
            ax2.text(0.5, 0.5, 'No Data\nAvailable', ha='center', va='center', 
                    transform=ax2.transAxes, fontsize=14, fontweight='bold')
            ax2.set_title('🔴 Issue Types - Before', fontsize=14, fontweight='bold')
        
        # Chart 3: Issue Type Distribution - After (Middle Right)
        ax3 = plt.subplot(3, 3, 6)
        if after_metrics['type_count']:
            wedges, texts, autotexts = ax3.pie(after_metrics['type_count'].values(), 
                                              labels=after_metrics['type_count'].keys(),
                                              autopct='%1.1f%%', startangle=90, 
                                              colors=colors_after, explode=[0.05]*len(after_metrics['type_count']),
                                              shadow=True, textprops={'fontsize': 10, 'fontweight': 'bold'})
            ax3.set_title('🟢 Issue Types - After\n(Total: {} issues)'.format(after_metrics['total_issues']), 
                         fontsize=14, fontweight='bold', pad=20)
        else:
            ax3.text(0.5, 0.5, 'No Issues!\n🎉\nPERFECT CODE!', ha='center', va='center', 
                    transform=ax3.transAxes, fontsize=16, fontweight='bold', color='green')
            ax3.set_title('🟢 Issue Types - After\n(ZERO ISSUES!)', fontsize=14, fontweight='bold', color='green')
        
        # Chart 4: Improvement Impact Analysis (Middle Left)
        ax4 = plt.subplot(3, 3, (4, 5))
        improvement_categories = ['Issues\nResolved', 'Coverage\nImproved (%)', 'Effort\nSaved (hrs)']
        improvement_values = [issues_improvement, coverage_improvement, effort_reduction]
        improvement_colors = ['#00B894' if val > 0 else '#E17055' if val < 0 else '#FDCB6E' for val in improvement_values]
        
        bars = ax4.bar(improvement_categories, improvement_values, color=improvement_colors, 
                      alpha=0.8, edgecolor='black', linewidth=2)
        ax4.set_title('🚀 AI Correction Impact Analysis', fontsize=16, fontweight='bold', pad=20)
        ax4.set_ylabel('📊 Improvement Values', fontsize=14, fontweight='bold')
        ax4.grid(axis='y', linestyle='--', alpha=0.3)
        
        # Add value labels and improvement indicators
        for i, (bar, val) in enumerate(zip(bars, improvement_values)):
            height = bar.get_height()
            # Add value label
            ax4.text(bar.get_x() + bar.get_width()/2., height + (0.5 if height >= 0 else -1.5),
                    f'{val:.1f}', ha='center', va='bottom' if height >= 0 else 'top', 
                    fontsize=12, fontweight='bold')
            # Add improvement percentage
            if i == 0 and before_metrics['total_issues'] > 0:  # Issues resolved
                percentage = (val / before_metrics['total_issues']) * 100
                ax4.text(bar.get_x() + bar.get_width()/2., height/2,
                        f'({percentage:.1f}%)', ha='center', va='center', 
                        fontsize=10, fontweight='bold', color='white')
        
        # Chart 5: Severity Comparison (Bottom Left - Horizontal bars)
        ax5 = plt.subplot(3, 3, 7)
        severity_categories = list(set(list(before_metrics['severity_count'].keys()) + list(after_metrics['severity_count'].keys())))
        if not severity_categories:
            severity_categories = ['CRITICAL', 'MAJOR', 'MINOR']
        
        before_severity_values = [before_metrics['severity_count'].get(cat, 0) for cat in severity_categories]
        after_severity_values = [after_metrics['severity_count'].get(cat, 0) for cat in severity_categories]
        
        y_pos = np.arange(len(severity_categories))
        bar_height = 0.35
        
        bars1 = ax5.barh(y_pos - bar_height/2, before_severity_values, bar_height, 
                        label='Before', color='#FF6B6B', alpha=0.8)
        bars2 = ax5.barh(y_pos + bar_height/2, after_severity_values, bar_height, 
                        label='After', color='#4ECDC4', alpha=0.8)
        
        ax5.set_ylabel('🎯 Severity Levels', fontsize=12, fontweight='bold')
        ax5.set_xlabel('📊 Number of Issues', fontsize=12, fontweight='bold')
        ax5.set_title('⚖️ Severity Level Comparison', fontsize=14, fontweight='bold')
        ax5.set_yticks(y_pos)
        ax5.set_yticklabels(severity_categories)
        ax5.legend(fontsize=10)
        ax5.grid(axis='x', linestyle='--', alpha=0.3)
        
        # Add value labels
        for i, (before_val, after_val) in enumerate(zip(before_severity_values, after_severity_values)):
            if before_val > 0:
                ax5.text(before_val/2, i - bar_height/2, str(before_val), 
                        ha='center', va='center', fontweight='bold', color='white')
            if after_val > 0:
                ax5.text(after_val/2, i + bar_height/2, str(after_val), 
                        ha='center', va='center', fontweight='bold', color='white')
        
        # Chart 6: Progress Indicators (Bottom Middle)
        ax6 = plt.subplot(3, 3, 8)
        ax6.axis('off')
        
        # Success rate calculation
        success_rate = (issues_improvement / before_metrics['total_issues'] * 100) if before_metrics['total_issues'] > 0 else 0
        
        # Create progress indicators
        progress_data = [
            ('🎯 Success Rate', success_rate, '%'),
            ('🔧 Issues Resolved', issues_improvement, ''),
            ('📈 Coverage Gain', coverage_improvement, '%'),
            ('⏱️ Time Saved', effort_reduction, 'hrs')
        ]
        
        y_positions = [0.8, 0.6, 0.4, 0.2]
        for i, (label, value, unit) in enumerate(progress_data):
            # Progress bar background
            ax6.barh(y_positions[i], 1, height=0.1, color='lightgray', alpha=0.3)
            
            # Progress bar fill
            fill_percentage = min(abs(value) / 100, 1.0) if 'Rate' in label or '%' in unit else min(abs(value) / 10, 1.0)
            color = '#00B894' if value >= 0 else '#E17055'
            ax6.barh(y_positions[i], fill_percentage, height=0.1, color=color, alpha=0.8)
            
            # Label and value
            ax6.text(-0.05, y_positions[i], label, ha='right', va='center', fontweight='bold', fontsize=11)
            ax6.text(1.05, y_positions[i], f'{value:.1f}{unit}', ha='left', va='center', fontweight='bold', fontsize=11)
        
        ax6.set_xlim(-0.3, 1.3)
        ax6.set_ylim(0, 1)
        ax6.set_title('📊 Key Performance Indicators', fontsize=14, fontweight='bold', y=0.95)
        
        # Chart 7: Summary Statistics (Bottom Right)
        ax7 = plt.subplot(3, 3, 9)
        ax7.axis('off')
        
        # Summary stats
        total_issues_before = before_metrics['total_issues']
        total_issues_after = after_metrics['total_issues']
        resolution_rate = (issues_improvement / total_issues_before * 100) if total_issues_before > 0 else 0
        
        summary_stats = f"""
🏆 CORRECTION SUMMARY
{'='*25}

📊 Issues Analysis:
   • Total Before: {total_issues_before}
   • Total After: {total_issues_after}
   • Resolved: {issues_improvement}
   • Resolution Rate: {resolution_rate:.1f}%

🎯 Quality Metrics:
   • Coverage: {before_metrics['coverage_percent']:.1f}% → {after_metrics['coverage_percent']:.1f}%
   • Effort: {before_metrics['total_effort_hours']:.1f}h → {after_metrics['total_effort_hours']:.1f}h
   • Code Lines: {before_metrics['total_code_lines']}

🚀 AI Impact:
   • Status: {'✅ SUCCESS' if issues_improvement > 0 else '⚠️ REVIEW'}
   • Efficiency: {resolution_rate:.1f}% resolved
   • Time Saved: {effort_reduction:.1f} hours
        """
        
        ax7.text(0.05, 0.95, summary_stats, transform=ax7.transAxes, fontsize=10, 
                verticalalignment='top', fontfamily='monospace', 
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.7))
        
        plt.tight_layout()
        return fig
    
    def generate_comprehensive_pdf_report(self, before_metrics: Dict[str, Any], after_metrics: Dict[str, Any], downloads_dir: str) -> str:
        """Generate comprehensive PDF report with enhanced charts"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pdf_filename = os.path.join(downloads_dir, f"AI_Correction_Detailed_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            
            with PdfPages(pdf_filename) as pdf:
                # Page 1: Executive Summary
                fig = plt.figure(figsize=(11, 8.5))
                fig.suptitle('🤖 AI Code Correction - Executive Summary', fontsize=18, fontweight='bold')
                
                ax = fig.add_subplot(111)
                ax.axis('off')
                
                # Calculate improvements
                issues_improvement = before_metrics['total_issues'] - after_metrics['total_issues']
                coverage_improvement = after_metrics['coverage_percent'] - before_metrics['coverage_percent']
                effort_reduction = before_metrics['total_effort_hours'] - after_metrics['total_effort_hours']
                
                summary_text = f"""
🕒 REPORT GENERATED: {timestamp}
🏢 PROJECT: {CI_PROJECT_KEY}
📄 FILE ANALYZED: {GIT_FILE_PATH}

{'='*70}
🎯 EXECUTIVE SUMMARY
{'='*70}

🚀 OVERALL IMPACT:
   ✅ Issues Resolved: {issues_improvement} ({(issues_improvement/before_metrics['total_issues']*100):.1f}% reduction)
   📈 Code Coverage Improvement: {coverage_improvement:.2f}%
   ⏱️  Development Effort Saved: {effort_reduction:.2f} hours
   🎖️  AI Correction Status: {'🟢 HIGHLY SUCCESSFUL' if issues_improvement > 0 else '🟡 NEEDS REVIEW'}

📊 BEFORE AI CORRECTION:
   🔴 Total Issues: {before_metrics['total_issues']}
   📉 Code Coverage: {before_metrics['coverage_percent']:.2f}%
   ⏳ Estimated Effort: {before_metrics['total_effort_hours']:.2f} hours
   📝 Code Lines: {before_metrics['total_code_lines']}

🎯 AFTER AI CORRECTION:
   🟢 Total Issues: {after_metrics['total_issues']}
   📈 Code Coverage: {after_metrics['coverage_percent']:.2f}%
   ⚡ Estimated Effort: {after_metrics['total_effort_hours']:.2f} hours
   📝 Code Lines: {after_metrics['total_code_lines']}

🔍 DETAILED BREAKDOWN:

   🚨 BEFORE - Issue Severities:
     {', '.join([f'{k}: {v}' for k, v in before_metrics['severity_count'].items()]) if before_metrics['severity_count'] else 'None'}
   
   🛠️  BEFORE - Issue Types:
     {', '.join([f'{k}: {v}' for k, v in before_metrics['type_count'].items()]) if before_metrics['type_count'] else 'None'}

   ✅ AFTER - Issue Severities:
     {', '.join([f'{k}: {v}' for k, v in after_metrics['severity_count'].items()]) if after_metrics['severity_count'] else '🎉 ZERO ISSUES!'}
   
   🎯 AFTER - Issue Types:
     {', '.join([f'{k}: {v}' for k, v in after_metrics['type_count'].items()]) if after_metrics['type_count'] else '🎉 ZERO ISSUES!'}
"""
                
                ax.text(0.05, 0.95, summary_text, transform=ax.transAxes, fontsize=11, 
                       verticalalignment='top', fontfamily='monospace',
                       bbox=dict(boxstyle="round,pad=1", facecolor="lightblue", alpha=0.1))
                
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)
                
                # Page 2: Enhanced Visual Dashboard
                enhanced_fig = self.generate_enhanced_charts(before_metrics, after_metrics)
                pdf.savefig(enhanced_fig, bbox_inches='tight')
                plt.close(enhanced_fig)
                
                # Page 3: Detailed Issue Analysis
                if 'sonarqube_issues' in self.state and 'after_correction_issues' in self.state:
                    change_analysis = self.generate_detailed_change_analysis(
                        self.state['sonarqube_issues'].get('issues', []),
                        self.state['after_correction_issues'].get('issues', [])
                    )
                    
                    fig = plt.figure(figsize=(11, 8.5))
                    fig.suptitle('Detailed Change Analysis', fontsize=16, fontweight='bold')
                    ax = fig.add_subplot(111)
                    ax.axis('off')
                    
                    # Format resolved issues for display
                    resolved_text = "\n📋 RESOLVED ISSUES:\n" + "="*50 + "\n"
                    if change_analysis['resolved_issues']:
                        for i, issue in enumerate(change_analysis['resolved_issues'][:15], 1):  # Show top 15
                            resolved_text += f"{i:2d}. Line {issue['line']:3} | {issue['severity']:8} | {issue['type']:12} | {issue['rule']}\n"
                            resolved_text += f"    Message: {issue['message']}\n\n"
                        
                        if len(change_analysis['resolved_issues']) > 15:
                            resolved_text += f"    ... and {len(change_analysis['resolved_issues']) - 15} more issues resolved\n\n"
                    else:
                        resolved_text += "    No issues were resolved by AI correction.\n\n"
                    
                    # Add new issues if any
                    if change_analysis['new_issues']:
                        resolved_text += "\n⚠️ NEW ISSUES INTRODUCED:\n" + "="*50 + "\n"
                        for i, issue in enumerate(change_analysis['new_issues'][:10], 1):
                            resolved_text += f"{i:2d}. Line {issue['line']:3} | {issue['severity']:8} | {issue['type']:12} | {issue['rule']}\n"
                            resolved_text += f"    Message: {issue['message']}\n\n"
                    
                    ax.text(0.05, 0.95, resolved_text, transform=ax.transAxes, fontsize=8, 
                           verticalalignment='top', fontfamily='monospace')
                    
                    pdf.savefig(fig, bbox_inches='tight')
                    plt.close(fig)
            
            logger.info(f"Comprehensive PDF report saved as: {pdf_filename}")
            return pdf_filename
            
        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}")
            return None
    
    def generate_comparison_report(self, before_metrics: Dict[str, Any], after_metrics: Dict[str, Any]):
        """Generate comprehensive before/after comparison with PDF report"""
        try:
            # Create downloads folder
            downloads_dir = self.create_downloads_folder()
            logger.info(f"Created downloads directory: {downloads_dir}")
            
            # Generate comprehensive PDF report
            pdf_filename = self.generate_comprehensive_pdf_report(before_metrics, after_metrics, downloads_dir)
            
            # Calculate improvements
            issues_improvement = before_metrics['total_issues'] - after_metrics['total_issues']
            coverage_improvement = after_metrics['coverage_percent'] - before_metrics['coverage_percent']
            effort_reduction = before_metrics['total_effort_hours'] - after_metrics['total_effort_hours']
            
            # Also create PNG version for quick viewing
            png_filename = os.path.join(downloads_dir, f"AI_Correction_Charts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            
            # Create the visual comparison chart
            plt.figure(figsize=(15, 10))
            
            # Subplot 1: Before vs After comparison
            plt.subplot(2, 2, 1)
            categories = ['Total Issues', 'Coverage (%)', 'Effort (hrs)']
            before_values = [before_metrics['total_issues'], before_metrics['coverage_percent'], before_metrics['total_effort_hours']]
            after_values = [after_metrics['total_issues'], after_metrics['coverage_percent'], after_metrics['total_effort_hours']]
            
            x = range(len(categories))
            width = 0.35
            
            bars1 = plt.bar([i - width/2 for i in x], before_values, width, label='Before AI Correction', color='red', alpha=0.7)
            bars2 = plt.bar([i + width/2 for i in x], after_values, width, label='After AI Correction', color='green', alpha=0.7)
            
            plt.xlabel('Metrics')
            plt.ylabel('Values')
            plt.title('Before vs After AI Correction Comparison')
            plt.xticks(x, categories)
            plt.legend()
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
            # Add value labels on bars
            for bar in bars1 + bars2:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                        f'{height:.1f}', ha='center', va='bottom')
            
            # Subplot 2: Severity distribution before
            plt.subplot(2, 2, 2)
            if before_metrics['severity_count']:
                plt.pie(before_metrics['severity_count'].values(), 
                       labels=before_metrics['severity_count'].keys(), 
                       autopct='%1.1f%%', startangle=90)
                plt.title('Issue Severity Distribution - Before')
            
            # Subplot 3: Severity distribution after
            plt.subplot(2, 2, 3)
            if after_metrics['severity_count']:
                plt.pie(after_metrics['severity_count'].values(), 
                       labels=after_metrics['severity_count'].keys(), 
                       autopct='%1.1f%%', startangle=90)
                plt.title('Issue Severity Distribution - After')
            else:
                plt.text(0.5, 0.5, 'No Issues!\n🎉', ha='center', va='center', transform=plt.gca().transAxes, fontsize=16, color='green')
                plt.title('Issue Severity Distribution - After')
            
            # Subplot 4: Improvement summary
            plt.subplot(2, 2, 4)
            improvements = ['Issues Resolved', 'Coverage Gained (%)', 'Effort Saved (hrs)']
            improvement_values = [issues_improvement, coverage_improvement, effort_reduction]
            colors = ['green' if val > 0 else 'red' for val in improvement_values]
            
            bars = plt.bar(improvements, improvement_values, color=colors, alpha=0.7)
            plt.title('AI Correction Improvements')
            plt.ylabel('Improvement Values')
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
            # Add value labels
            for bar, val in zip(bars, improvement_values):
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + (0.1 if height > 0 else -0.3),
                        f'{val:.1f}', ha='center', va='bottom' if height > 0 else 'top')
            
            plt.tight_layout()
            plt.savefig(png_filename, dpi=300, bbox_inches='tight')
            plt.close()
            
            # Create summary report file
            summary_filename = os.path.join(downloads_dir, "AI_Correction_Summary.txt")
            with open(summary_filename, 'w', encoding='utf-8') as f:
                f.write(f"""AI CODE CORRECTION SUMMARY REPORT
{'='*50}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Project: {CI_PROJECT_KEY}
File: {GIT_FILE_PATH}

IMPACT SUMMARY:
- Issues Resolved: {issues_improvement}
- Coverage Improvement: {coverage_improvement:.2f}%
- Effort Reduction: {effort_reduction:.2f} hours
- Success Rate: {(issues_improvement/before_metrics['total_issues']*100):.1f}%

FILES GENERATED:
- Detailed PDF Report: {os.path.basename(pdf_filename) if pdf_filename else 'Failed to generate'}
- Visual Charts: {os.path.basename(png_filename)}
- This Summary: {os.path.basename(summary_filename)}

BEFORE AI CORRECTION:
- Total Issues: {before_metrics['total_issues']}
- Code Coverage: {before_metrics['coverage_percent']:.2f}%
- Estimated Effort: {before_metrics['total_effort_hours']:.2f} hours

AFTER AI CORRECTION:
- Total Issues: {after_metrics['total_issues']}
- Code Coverage: {after_metrics['coverage_percent']:.2f}%
- Estimated Effort: {after_metrics['total_effort_hours']:.2f} hours
""")
            
            # Print summary
            logger.info("\n=== AI CORRECTION IMPACT SUMMARY ===")
            logger.info(f"Issues Resolved: {issues_improvement}")
            logger.info(f"Coverage Improvement: {coverage_improvement:.2f}%")
            logger.info(f"Effort Reduction: {effort_reduction:.2f} hours")
            logger.info(f"Overall Improvement: {'Positive' if issues_improvement > 0 else 'Needs Review'}")
            logger.info(f"Reports saved in: {downloads_dir}")
            
            return {
                'downloads_dir': downloads_dir,
                'pdf_report': pdf_filename,
                'png_charts': png_filename,
                'summary_file': summary_filename,
                'issues_improvement': issues_improvement,
                'coverage_improvement': coverage_improvement,
                'effort_reduction': effort_reduction
            }
            
        except Exception as e:
            logger.error(f"Failed to generate comparison report: {e}")
            return None
    
    def fetch_post_correction_issues(self) -> Dict[str, Any]:
        """Fetch SonarQube issues after AI correction"""
        try:
            # Wait a bit for SonarQube to process the new code
            logger.info("Fetching post-correction SonarQube issues...")
            
            post_correction_command = (
                f'curl -u {SONAR_TOKEN}: '
                f'"{SONAR_HOST_URL}/api/issues/search?componentKeys={CI_PROJECT_KEY}&resolved=false&types=BUG,CODE_SMELL,VULNERABILITY&ps=500" '
                '-o issues_after.json'
            )
            
            subprocess.run(post_correction_command, shell=True, check=True)
            
            with open("issues_after.json", "r", encoding="utf-8") as f:
                after_issues_data = json.load(f)
                self.state["after_correction_issues"] = after_issues_data
            
            return {"status": "success", "message": "Post-correction issues fetched."}
            
        except Exception as e:
            logger.error(f"Failed to fetch post-correction issues: {e}")
            return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    agent = ESQLAutoFixAgent()
    result = agent.run()
    print(f"Final result: {result}")
