from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os

app = Flask(__name__)
CORS(app)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question", "")

    response = model.generate_content(
        f"You are a friendly AI Teacher. Explain topics clearly and simply like a real teacher. Keep answers easy to understand.\n\nStudent question: {question}"
    )

    answer = response.text
    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(debug=True)
