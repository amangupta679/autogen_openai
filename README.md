1. Go to your project folder
cd C:\Users\amgupta\Downloads\ai\autogen-openai

2. Initialize Git and set up the remote
git init
git remote add origin https://github.com/amangupta679/autogen_openai.git
git branch -M main

3. Make sure .env is ignored (important)
echo .env >> .gitignore

4. Stage and commit all files
git add .
git commit -m "Initial commit with agent files"

5. Push to GitHub
git push -u origin main
