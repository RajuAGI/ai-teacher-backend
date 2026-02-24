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

# ===== Search Helpers =====
def search_tavily(query):
    try:
        results = tavily_client.search(query=query, search_depth="basic", max_results=5)
        processed = []
        for item in results.get("results", []):
            processed.append({
                "title": item.get("title", ""),
                "snippet": (item.get("content","")[:150] + "...") if item.get("content") else "",
                "url": item.get("url","")
            })
        return processed
    except Exception as e:
        print("❌ Tavily Search Failed:", e)
        return []

def search_duckduckgo(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://duckduckgo.com/html/?q={query}"
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        
        titles = soup.select("a.result__a")[:5]
        snippets = soup.select("a.result__snippet")[:5]
        results = []

        for i, t in enumerate(titles):
            results.append({
                "title": t.get_text(strip=True),
                "snippet": snippets[i].get_text(strip=True) if i < len(snippets) else "",
                "url": t.get("href")
            })
        return results
    except Exception as e:
        print("❌ DuckDuckGo Search Failed:", e)
        return []

# ===== Smart Web Search =====
def search_web(query):
    results = search_tavily(query)
    if results:
        return results, "Tavily"
    results = search_duckduckgo(query)
    if results:
        return results, "DuckDuckGo"
    return [], "None"

# ===== Routes =====
@app.route("/")
def home():
    return jsonify({"status": "Backend is running!"})

# ===== Google / Web Search Route (fixed) =====
@app.route("/search", methods=["POST"])
def search():
    try:
        data = request.json
        query = data.get("query", "")
        if not query:
            return jsonify({"results": []})

        results = search_tavily(query)
        if not results:
            results = search_duckduckgo(query)
        
        return jsonify({"results": results})
    except Exception as e:
        print("Search ERROR:", e)
        return jsonify({"results": [], "error": str(e)}), 500

# ===== AI Teacher Ask Route (unchanged) =====
@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question", "")

        # Smart Search
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
{''.join([f'{i+1}. {r["title"]}: {r["snippet"]}\n' for i,r in enumerate(web_results)])}"""
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

        # TTS
        audio_text = answer.replace("।", " ").replace("...", " ").replace("..", " ")
        tts = gTTS(text=audio_text, lang="hi", slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        audio_base64 = base64.b64encode(audio_buffer.read()).decode("utf-8")

        return jsonify({"answer": answer, "audio": audio_base64})

    except Exception as e:
        print("Ask ERROR:", e)
        return jsonify({"error": str(e)}), 500

# ===== Run =====
if __name__ == "__main__":
    app.run(debug=True)
