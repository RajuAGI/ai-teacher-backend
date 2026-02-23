from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from gtts import gTTS
from tavily import TavilyClient
import os
import io
import base64
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

# ===== Search 1: Tavily =====
def search_tavily(query):
    try:
        results = tavily_client.search(
            query=query,
            search_depth="basic",
            max_results=5
        )
        search_text = ""
        for i, result in enumerate(results["results"]):
            title = result.get("title", "")
            content = result.get("content", "")
            search_text += f"{i+1}. {title}: {content}\n"
        if search_text:
            print("✅ Tavily Search Success!")
            return search_text
        return ""
    except Exception as e:
        print("❌ Tavily Failed:", str(e))
        return ""

# ===== Search 2: DuckDuckGo (Free & Unlimited) =====
def search_duckduckgo(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://duckduckgo.com/html/?q={query}"
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        snippets = soup.find_all("a", class_="result__snippet", limit=5)
        search_text = ""
        for i, snippet in enumerate(snippets):
            search_text += f"{i+1}. {snippet.get_text()}\n"
        if search_text:
            print("✅ DuckDuckGo Search Success!")
            return search_text
        return ""
    except Exception as e:
        print("❌ DuckDuckGo Failed:", str(e))
        return ""

# ===== Search 3: Bing (Free) =====
def search_bing(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://www.bing.com/search?q={query}"
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        results = soup.find_all("p", limit=5)
        search_text = ""
        for i, result in enumerate(results):
            text = result.get_text().strip()
            if text:
                search_text += f"{i+1}. {text}\n"
        if search_text:
            print("✅ Bing Search Success!")
            return search_text
        return ""
    except Exception as e:
        print("❌ Bing Failed:", str(e))
        return ""

# ===== Smart Search — सभी try करो =====
def search_web(query):
    # पहले Tavily try करो
    result = search_tavily(query)
    if result:
        return result, "Tavily"

    # फिर DuckDuckGo try करो
    result = search_duckduckgo(query)
    if result:
        return result, "DuckDuckGo"

    # फिर Bing try करो
    result = search_bing(query)
    if result:
        return result, "Bing"

    # कोई भी काम नहीं किया
    print("⚠️ All searches failed — using AI knowledge")
    return "", "None"

@app.route("/")
def home():
    return jsonify({"status": "Backend is running!"})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question", "")

        # Smart Search करो
        web_results, search_source = search_web(question)
        print(f"Search Source: {search_source}")

        if web_results:
            system_prompt = f"""आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप सामान्यतः हिंदी में जवाब देते हैं
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
जवाब देते समय इन बातों का ध्यान रखें:
- हमेशा हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें जैसे क्रिकेट, बॉलीवुड, भारतीय त्योहार आदि
- जवाब 1000 शब्दों से कम रखें
- वर्तमान और updated जानकारी दें

Latest Search Results (Source: {search_source}):
{web_results}"""
        else:
            system_prompt = """आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप सामान्यतः हिंदी में जवाब देते हैं 
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
- हमेशा हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें
- जवाब 1000 शब्दों से कम रखें"""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        )

        answer = response.choices[0].message.content

        audio_text = answer.replace("।", " ").replace("...", " ").replace("..", " ")

        tts = gTTS(text=audio_text, lang="hi", slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)

        audio_base64 = base64.b64encode(audio_buffer.read()).decode("utf-8")

        return jsonify({
            "answer": answer,
            "audio": audio_base64
        })

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
