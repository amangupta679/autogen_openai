#!/usr/bin/env python3
"""
GitLab Webhook Listener for SonarQube Issues Auto-Fix
This service listens for GitLab webhooks and triggers the autogen_agent
when issues.json file is modified in the repository.
"""

import os
import json
import logging
import subprocess
import threading
from flask import Flask, request, jsonify
from datetime import datetime
from autogen_agent import ESQLAutoFixAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
WEBHOOK_SECRET = os.getenv('GITLAB_WEBHOOK_SECRET', 'your-secret-here')
TARGET_FILE = 'issues.json'
REPO_NAME = 'samplecode'  # Your GitLab repository name

def verify_webhook_signature(request_data, signature):
    """Verify GitLab webhook signature"""
    # In production, implement proper HMAC signature verification
    # For now, we'll use a simple secret check
    return signature == WEBHOOK_SECRET

def trigger_autofix_async():
    """Run the autofix agent asynchronously"""
    try:
        logger.info("Starting automated code fixing process...")
        agent = ESQLAutoFixAgent()
        result = agent.run()
        logger.info(f"Autofix completed with result: {result}")
    except Exception as e:
        logger.error(f"Error during autofix process: {e}")

@app.route('/webhook', methods=['POST'])
def gitlab_webhook():
    """Handle GitLab webhook events"""
    
    # Verify webhook signature
    signature = request.headers.get('X-Gitlab-Token', '')
    if not verify_webhook_signature(request.data, signature):
        logger.warning("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    try:
        payload = request.json
        
        # Check if this is a push event
        if payload.get('object_kind') != 'push':
            logger.info(f"Ignoring non-push event: {payload.get('object_kind')}")
            return jsonify({"message": "Event ignored"}), 200
        
        # Check if the repository matches
        repo_name = payload.get('project', {}).get('name', '')
        if repo_name != REPO_NAME:
            logger.info(f"Ignoring event from different repository: {repo_name}")
            return jsonify({"message": "Repository ignored"}), 200
        
        # Check if issues.json was modified
        commits = payload.get('commits', [])
        issues_json_modified = False
        
        for commit in commits:
            modified_files = commit.get('modified', []) + commit.get('added', [])
            if TARGET_FILE in modified_files:
                issues_json_modified = True
                logger.info(f"Detected {TARGET_FILE} modification in commit: {commit.get('id', '')}")
                break
        
        if not issues_json_modified:
            logger.info("No issues.json modifications detected")
            return jsonify({"message": "No relevant file changes"}), 200
        
        # Trigger the autofix process in a separate thread
        logger.info("Triggering automated code fixing process...")
        thread = threading.Thread(target=trigger_autofix_async)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "message": "Automated code fixing triggered successfully",
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route('/trigger', methods=['POST'])
def manual_trigger():
    """Manual trigger endpoint for testing"""
    logger.info("Manual trigger received")
    thread = threading.Thread(target=trigger_autofix_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "message": "Manual trigger initiated",
        "timestamp": datetime.now().isoformat()
    }), 200

if __name__ == '__main__':
    # Configuration
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting webhook listener on port {port}")
    logger.info(f"Target file: {TARGET_FILE}")
    logger.info(f"Target repository: {REPO_NAME}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
