from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question", "")

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a friendly AI Teacher. Explain topics clearly and simply like a real teacher. Keep answers easy to understand."},
            {"role": "user", "content": question}
        ]
    )

    answer = response.choices[0].message.content
    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(debug=True)
