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

# ===== SEARCH HELPERS =====
def search_tavily(query):
    try:
        results = tavily_client.search(query=query, search_depth="basic", max_results=5)
        processed = []
        for item in results.get("results", []):
            processed.append({
                "title": item.get("title", ""),
                "snippet": (item.get("content", "")[:180] + "...") if item.get("content") else "",
                "url": item.get("url", "")
            })
        if processed:
            print("✅ Tavily Search Success!")
        return processed
    except Exception as e:
        print("❌ Tavily Search Failed:", e)
        return []

def search_duckduckgo(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = f"https://duckduckgo.com/html/?q={requests.utils.quote(query)}"
        response = requests.get(url, headers=headers, timeout=6)
        soup = BeautifulSoup(response.text, "html.parser")

        titles = soup.select("a.result__a")[:5]
        snippets = soup.select("a.result__snippet")[:5]
        results = []

        for i, t in enumerate(titles):
            results.append({
                "title": t.get_text(strip=True),
                "snippet": snippets[i].get_text(strip=True) if i < len(snippets) else "",
                "url": t.get("href", "")
            })
        if results:
            print("✅ DuckDuckGo Success!")
        return results
    except Exception as e:
        print("❌ DuckDuckGo Failed:", e)
        return []

def search_bing(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = f"https://www.bing.com/search?q={requests.utils.quote(query)}"
        response = requests.get(url, headers=headers, timeout=6)
        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        for item in soup.select("li.b_algo")[:5]:
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one("p")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    "url": title_el.get("href", "")
                })
        if results:
            print("✅ Bing Success!")
        return results
    except Exception as e:
        print("❌ Bing Failed:", e)
        return []

def smart_search(query):
    results = search_tavily(query)
    if results: return results, "Tavily"
    results = search_duckduckgo(query)
    if results: return results, "DuckDuckGo"
    results = search_bing(query)
    if results: return results, "Bing"
    print("⚠️ All searches failed")
    return [], "None"

# ===== ROUTES =====
@app.route("/")
def home():
    return jsonify({"status": "Backend is running!"})

@app.route("/search", methods=["POST"])
def search():
    try:
        data = request.json
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"results": []})

        print(f"Search query: {query}")
        results, source = smart_search(query)
        print(f"Search source: {source}, Results: {len(results)}")
        return jsonify({"results": results, "source": source})

    except Exception as e:
        print("Search ERROR:", e)
        return jsonify({"results": [], "error": str(e)}), 500

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question", "").strip()
        if not question:
            return jsonify({"error": "No question provided"}), 400

        web_results, search_source = smart_search(question)
        print(f"Ask - Search Source: {search_source}")

        if web_results:
            results_text = "\n".join([
                f"{i+1}. {r['title']}: {r['snippet']}"
                for i, r in enumerate(web_results)
            ])
            system_prompt = f"""आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप हमेशा हिंदी में जवाब देते हैं — बिल्कुल एक भारतीय गुरुजी की तरह।
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
जवाब देते समय इन बातों का ध्यान रखें:
- हमेशा हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें जैसे क्रिकेट, बॉलीवुड, भारतीय त्योहार आदि
- प्यार से समझाएं जैसे एक गुरुजी समझाते हैं
- जवाब 150 शब्दों से कम रखें
- वर्तमान और updated जानकारी दें
- कभी कभी शाबाश, बहुत बढ़िया जैसे शब्द use करें

Latest Search Results (Source: {search_source}):
{results_text}"""
        else:
            system_prompt = """आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप हमेशा हिंदी में जवाब देते हैं — बिल्कुल एक भारतीय गुरुजी की तरह।
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
- हमेशा हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें
- जवाब 150 शब्दों से कम रखें
- कभी कभी शाबाश, बहुत बढ़िया जैसे शब्द use करें"""

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

if __name__ == "__main__":
    app.run(debug=True)
