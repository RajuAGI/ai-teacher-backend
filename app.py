from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from gtts import gTTS
from tavily import TavilyClient
import os
import io
import base64
import requests
import json
import re
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
        results, source = smart_search(query)
        return jsonify({"results": results, "source": source})
    except Exception as e:
        print("Search ERROR:", e)
        return jsonify({"results": [], "error": str(e)}), 500

# ===== QUIZ GENERATION ROUTE =====
@app.route("/quiz", methods=["POST"])
def generate_quiz():
    try:
        data = request.json
        topic = data.get("topic", "").strip()
        if not topic:
            return jsonify({"error": "Topic required"}), 400

        print(f"Generating quiz for topic: {topic}")

        prompt = f"""Generate exactly 50 multiple choice questions about "{topic}" in Hindi.
Mix of difficulty:
- Questions 1-15: Easy (आसान)
- Questions 16-35: Medium (माध्यम)  
- Questions 36-50: Hard (कठिन)

Return ONLY a valid JSON array. No explanation, no markdown, no code blocks.
Each question object must have exactly these fields:
- "q": question text in Hindi
- "options": array of exactly 4 strings (options in Hindi)
- "ans": index of correct answer (0, 1, 2, or 3)
- "level": "आसान" or "माध्यम" or "कठिन"
- "explanation": brief explanation of correct answer in Hindi (1-2 sentences)

Example format:
[{{"q":"भारत की राजधानी क्या है?","options":["मुंबई","नई दिल्ली","कोलकाता","चेन्नई"],"ans":1,"level":"आसान","explanation":"नई दिल्ली 1911 से भारत की राजधानी है।"}}]

Generate 50 unique, interesting questions. Make sure all 50 are different."""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a quiz generator. Return only valid JSON arrays. No markdown, no explanation."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=8000,
            temperature=0.8
        )

        raw = response.choices[0].message.content.strip()
        print(f"Raw response length: {len(raw)}")

        # JSON extract करो
        # markdown code blocks हटाओ
        raw = re.sub(r'```json\s*', '', raw)
        raw = re.sub(r'```\s*', '', raw)
        raw = raw.strip()

        # JSON array ढूंढो
        start = raw.find('[')
        end = raw.rfind(']')
        if start != -1 and end != -1:
            raw = raw[start:end+1]

        questions = json.loads(raw)

        # Validate करो
        valid = []
        for q in questions:
            if (isinstance(q, dict) and
                "q" in q and "options" in q and "ans" in q and
                isinstance(q["options"], list) and len(q["options"]) == 4 and
                isinstance(q["ans"], int) and 0 <= q["ans"] <= 3):
                valid.append({
                    "q": str(q["q"]),
                    "options": [str(o) for o in q["options"]],
                    "ans": int(q["ans"]),
                    "level": str(q.get("level", "माध्यम")),
                    "explanation": str(q.get("explanation", ""))
                })

        print(f"Valid questions: {len(valid)}")

        if len(valid) < 10:
            return jsonify({"error": "Quiz generation failed. Please try again."}), 500

        return jsonify({"questions": valid, "topic": topic, "total": len(valid)})

    except json.JSONDecodeError as e:
        print("JSON Parse ERROR:", e)
        print("Raw was:", raw[:500])
        return jsonify({"error": "AI response format error. Please try again."}), 500
    except Exception as e:
        print("Quiz ERROR:", e)
        return jsonify({"error": str(e)}), 500

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
