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
        snippets = soup.find_all("a", class_="result__snippet", limit=5)

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
            system_prompt = f"""आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप हमेशा हिंदी में जवाब देते हैं — बिल्कुल एक भारतीय गुरुजी की तरह।
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!

आपके पास नीचे latest web search results हैं — इन्हें use करके वर्तमान समय के अनुसार सटीक जवाब दें।
जवाब देते समय इन बातों का ध्यान रखें:
- हमेशा हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें जैसे क्रिकेट, बॉलीवुड, भारतीय त्योहार आदि
- प्यार से समझाएं जैसे एक गुरुजी समझाते हैं
- जवाब 100 शब्दों से कम रखें
- वर्तमान और updated जानकारी दें

Latest Web Search Results:
{web_results}"""
        else:
            system_prompt = """आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप हमेशा हिंदी में जवाब देते हैं — बिल्कुल एक भारतीय गुरुजी की तरह।
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
जवाब देते समय इन बातों का ध्यान रखें:
- हमेशा हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें जैसे क्रिकेट, बॉलीवुड, भारतीय त्योहार आदि
- प्यार से समझाएं जैसे एक गुरुजी समझाते हैं
- जवाब 100 शब्दों से कम रखें"""

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
