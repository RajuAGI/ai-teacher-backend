from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
import traceback

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

@app.route("/")
def home():
    return jsonify({"status": "Backend is running!"})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question", "")

        response = model.generate_content(
            f"You are a friendly AI Teacher. Explain topics clearly and simply like a real teacher. Keep answers easy to understand.\n\nStudent question: {question}"
        )

        answer = response.candidates[0].content.parts[0].text
        return jsonify({"answer": answer})

    except Exception as e:
        error_details = traceback.format_exc()
        print("FULL ERROR:", error_details)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
