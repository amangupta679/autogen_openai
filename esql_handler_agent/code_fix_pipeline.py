import os
import json
import logging
def load_issues(issues_path):
    logging.info(f"Loading issues from: {issues_path}")
    with open(issues_path, "r", encoding="utf-8") as f:
        issues = json.load(f)
    return issues.get("issues", [])
def correct_code(code, issues):
    corrected_lines = code.splitlines()
    for issue in issues:
        msg = issue.get("message", "")
        line_number = issue.get("line", None)
        rule = issue.get("rule", "")
        severity = issue.get("severity", "")
        if line_number and 1 <= line_number <= len(corrected_lines):
            original = corrected_lines[line_number - 1]
            comment = f"// SONAR: {msg} | Rule: {rule} | Severity: {severity}" 
            if comment not in original:
                corrected_lines[line_number - 1] = f"{original} {comment}"
    return "\n".join(corrected_lines)
def save_corrected_code(path, code):
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    logging.info(f"Corrected code saved to: {path}")
def main():
    logging.basicConfig(level=logging.INFO)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Updated: Point one level up to find issues.json and .esql source file
    issues_path = os.path.abspath(os.path.join(script_dir, "../issues.json"))
    source_path = os.path.abspath(os.path.join(script_dir, "../PLM2PDH_DTCPOM.esql"))
    output_path = os.path.abspath(os.path.join(script_dir, "../PLM2PDH_DTCPOM_corrected.esql"))
    logging.info(f"Issues file: {issues_path}")
    logging.info(f"Source ESQL file: {source_path}")
    if not os.path.exists(issues_path):
        logging.error("issues.json file not found!")
        return
    if not os.path.exists(source_path):
        logging.error("Source .esql file not found!")
        return
    issues = load_issues(issues_path)
    with open(source_path, "r", encoding="utf-8") as f:
        code = f.read()
    corrected_code = correct_code(code, issues)
    save_corrected_code(output_path, corrected_code)
if __name__ == "__main__":
    main()