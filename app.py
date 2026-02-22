from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import os
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def search_web(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://duckduckgo.com/html/?q={query}"
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        results = soup.find_all("a", class_="result__a", limit=3)
        snippets = soup.find_all("a", class_="result__snippet", limit=3)

        search_text = ""
        for i, snippet in enumerate(snippets):
            search_text += f"{i+1}. {snippet.get_text()}\n"

        return search_text if search_text else ""
    except:
        return ""

@app.route("/")
def home():
    return jsonify({"status": "Backend is running!"})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question", "")

        # Search web for latest info
        web_results = search_web(question)

        # Build prompt with web results
        if web_results:
            system_prompt = f"""You are a friendly AI Teacher named Raju Ram. If anyone asks who you are, your name, or anything about your identity, always reply: I am Raju Ram, your AI Teacher!
You have access to the latest web search results below. Use them to give updated and accurate answers.
Keep answers easy to understand and under 100 words.

Latest Web Search Results:
{web_results}"""
        else:
            system_prompt = """You are a friendly AI Teacher named Raju Ram. If anyone asks who you are, your name, or anything about your identity, always reply: I am Raju Ram, your AI Teacher!
Explain topics clearly and simply like a real teacher. Keep answers easy to understand and under 100 words."""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        )

        answer = response.choices[0].message.content
        return jsonify({"answer": answer})

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
