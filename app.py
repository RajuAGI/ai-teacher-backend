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

        # Normal search
        results, source = smart_search(query)

        # Wikipedia result ढूंढो
        wiki_result = None
        other_results = []
        for r in results:
            if "wikipedia.org" in r.get("url", "").lower():
                if wiki_result is None:
                    wiki_result = r
            else:
                other_results.append(r)

        # अगर Wikipedia नहीं मिला तो अलग से search करो
        if wiki_result is None:
            wiki_search, _ = smart_search(f"{query} wikipedia")
            for r in wiki_search:
                if "wikipedia.org" in r.get("url", "").lower():
                    wiki_result = r
                    break

        # Wikipedia को पहले रखो
        if wiki_result:
            wiki_result["is_wiki"] = True
            final_results = [wiki_result] + other_results
        else:
            final_results = results

        return jsonify({"results": final_results, "source": source})
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

        system_prompt = """You are an expert quiz maker for Indian competitive exams (UPSC, SSC, NEET, JEE, State PSC).
You generate exactly 15 MCQ questions in Hindi — 5 easy, 5 medium, 5 hard.

STRICT RULES:
1. Every question MUST have EXACTLY ONE correct answer. No ambiguity.
2. All 4 options must be clearly distinct — no overlapping or confusing options.
3. Questions must be factually accurate and verified.
4. Use current/updated facts (e.g., current record holders, latest data).
5. Language must be clear, proper Hindi — no broken or meaningless sentences.
6. Each question should test real knowledge, not trick the user with wordplay.
7. Difficulty levels:
   - आसान: Basic facts, Class 6-8 level
   - माध्यम: Conceptual, Class 9-12 or general knowledge level  
   - कठिन: Advanced, competitive exam level (UPSC/SSC style)
8. Return ONLY a valid JSON array. No markdown, no explanation, no extra text."""

        prompt = f"""Generate exactly 15 high-quality MCQ questions about "{topic}" for Indian competitive exams.

Format: JSON array with exactly 15 objects.
- First 5 objects: level "आसान"
- Next 5 objects: level "माध्यम"  
- Last 5 objects: level "कठिन"

Each object must have:
- "q": clear question in Hindi
- "options": exactly 4 distinct options (array of strings)
- "ans": index of the ONLY correct answer (0, 1, 2, or 3)
- "level": "आसान" or "माध्यम" or "कठिन"
- "explanation": 1-2 sentence explanation of WHY this answer is correct, with source if possible

Example:
[{{"q":"भारतीय संविधान सभा के अध्यक्ष कौन थे?","options":["जवाहरलाल नेहरू","डॉ. राजेन्द्र प्रसाद","डॉ. बी.आर. आम्बेडकर","सरदार वल्लभभाई पटेल"],"ans":1,"level":"आसान","explanation":"डॉ. राजेन्द्र प्रसाद भारतीय संविधान सभा के स्थायी अध्यक्ष थे। वे बाद में भारत के प्रथम राष्ट्रपति भी बने।"}}]

Topic: {topic}
Return ONLY the JSON array with exactly 15 questions."""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=6000,
            temperature=0.3
        )

        raw = response.choices[0].message.content.strip()
        print(f"Raw response length: {len(raw)}")

        raw = re.sub(r'```json\s*', '', raw)
        raw = re.sub(r'```\s*', '', raw)
        raw = raw.strip()

        start = raw.find('[')
        end = raw.rfind(']')
        if start != -1 and end != -1:
            raw = raw[start:end+1]

        questions = json.loads(raw)

        valid = []
        for q in questions:
            if (isinstance(q, dict) and
                "q" in q and "options" in q and "ans" in q and
                isinstance(q["options"], list) and len(q["options"]) == 4 and
                isinstance(q["ans"], int) and 0 <= q["ans"] <= 3 and
                len(str(q["q"]).strip()) > 5):
                valid.append({
                    "q": str(q["q"]).strip(),
                    "options": [str(o).strip() for o in q["options"]],
                    "ans": int(q["ans"]),
                    "level": str(q.get("level", "माध्यम")),
                    "explanation": str(q.get("explanation", "")).strip()
                })

        print(f"Valid questions: {len(valid)}")

        if len(valid) < 5:
            return jsonify({"error": "Quiz generation failed. Please try again."}), 500

        return jsonify({"questions": valid, "topic": topic, "total": len(valid)})

    except json.JSONDecodeError as e:
        print("JSON Parse ERROR:", e)
        return jsonify({"error": "Quiz generate नहीं हो पाई। दोबारा try करो।"}), 500
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
