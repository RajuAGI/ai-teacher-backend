from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import os

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

@app.route("/")
def home():
    return jsonify({"status": "Backend is running!"})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question", "")

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a friendly AI Teacher named Raju Ram. If anyone asks who you are, your name, or anything about your identity, always reply: I am Raju Ram, your AI Teacher! Explain topics clearly and simply like a real teacher. Keep answers easy to understand. Keep answers under 100 words."},
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
