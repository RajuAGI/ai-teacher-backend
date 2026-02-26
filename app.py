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
from datetime import datetime

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

# ===== CONFIG =====
TEAMCOIN_BACKEND = "https://teamcoin-backend.onrender.com"
QUIZ_SECRET      = os.environ.get("QUIZ_SECRET", "quiz_bridge_2025")

# ===== SCORES STORAGE =====
SCORES_FILE = "scores.json"

def load_scores():
    try:
        if os.path.exists(SCORES_FILE):
            with open(SCORES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return []

def save_scores_file(scores):
    try:
        with open(SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Score save error:", e)

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
    return jsonify({"status": "AI Teacher Backend Running!"})

@app.route("/search", methods=["POST"])
def search():
    try:
        data = request.json
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"results": []})

        results, source = smart_search(query)

        wiki_result = None
        other_results = []
        for r in results:
            if "wikipedia.org" in r.get("url", "").lower():
                if wiki_result is None:
                    wiki_result = r
            else:
                other_results.append(r)

        if wiki_result is None:
            wiki_search, _ = smart_search(f"{query} wikipedia")
            for r in wiki_search:
                if "wikipedia.org" in r.get("url", "").lower():
                    wiki_result = r
                    break

        if wiki_result:
            wiki_result["is_wiki"] = True
            final_results = [wiki_result] + other_results
        else:
            final_results = results

        return jsonify({"results": final_results, "source": source})
    except Exception as e:
        print("Search ERROR:", e)
        return jsonify({"results": [], "error": str(e)}), 500


# ===== SAVE SCORE =====
@app.route("/save-score", methods=["POST"])
def save_score():
    """Quiz khatam hone ke baad score save karo."""
    try:
        data    = request.json
        name    = str(data.get("name",  "")).strip()
        score   = int(data.get("score", 0))
        total   = int(data.get("total", 15))
        topic   = str(data.get("topic", "")).strip()

        if not name:
            return jsonify({"error": "Name required"}), 400

        scores = load_scores()
        found  = False
        for entry in scores:
            if entry["name"].lower() == name.lower():
                if score > entry["best_score"]:
                    entry["best_score"]  = score
                    entry["best_total"]  = total
                    entry["best_topic"]  = topic
                    entry["last_played"] = datetime.now().strftime("%d-%m-%Y")
                entry["games_played"] = entry.get("games_played", 0) + 1
                found = True
                break

        if not found:
            scores.append({
                "name":         name,
                "best_score":   score,
                "best_total":   total,
                "best_topic":   topic,
                "games_played": 1,
                "last_played":  datetime.now().strftime("%d-%m-%Y")
            })

        save_scores_file(scores)
        print(f"✅ Score saved: {name} → {score}/{total}")
        return jsonify({"success": True, "message": "Score save ho gaya!"})

    except Exception as e:
        print("Save Score ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ===== LEADERBOARD =====
@app.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    """Top 20 students by best quiz score."""
    try:
        scores = load_scores()
        scores.sort(key=lambda x: (-x["best_score"], x["name"]))
        top20  = scores[:20]
        for entry in top20:
            t = entry.get("best_total", 15)
            entry["percentage"] = round(entry["best_score"] / t * 100) if t > 0 else 0
        return jsonify({"leaderboard": top20, "total_players": len(scores)})
    except Exception as e:
        print("Leaderboard ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ===== CLAIM QUIZ COINS (bridge to TeamCoin backend) =====
@app.route("/claim-quiz-coins", methods=["POST"])
def claim_quiz_coins():
    """
    Frontend se call aata hai.
    TeamCoin backend ko securely call karta hai (secret server-side rahta hai).
    Body: { "username": "raju", "score": 12, "total": 15, "topic": "इतिहास" }
    """
    try:
        data     = request.json
        username = str(data.get("username", "")).strip()
        score    = int(data.get("score",    0))
        total    = int(data.get("total",    15))
        topic    = str(data.get("topic",    "")).strip()

        if not username:
            return jsonify({"error": "TeamCoin username डालो!"}), 400

        # Coins calculate karo
        coins = score * 2          # har sahi jawab = 2 coins
        if total > 0 and score / total >= 0.8:
            coins += 10            # 80%+ score pe bonus

        # TeamCoin backend ko call karo
        resp = requests.post(
            f"{TEAMCOIN_BACKEND}/award-quiz-coins",
            json={
                "username": username,
                "coins":    coins,
                "score":    score,
                "total":    total,
                "topic":    topic,
                "secret":   QUIZ_SECRET
            },
            timeout=15
        )
        result = resp.json()
        return jsonify(result), resp.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "TeamCoin backend respond नहीं कर रहा। थोड़ी देर बाद try करो।"}), 504
    except Exception as e:
        print("Claim coins ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ===== QUIZ GENERATION =====
@app.route("/quiz", methods=["POST"])
def generate_quiz():
    try:
        data  = request.json
        topic = data.get("topic", "").strip()
        if not topic:
            return jsonify({"error": "Topic required"}), 400

        print(f"Generating quiz for topic: {topic}")

        system_prompt = """You are a senior question paper setter with 20+ years of experience in Indian competitive exams (UPSC, SSC CGL, NEET, JEE, State PSC, Railways RRB).

Your job is to generate exactly 15 high-quality MCQ questions.

LANGUAGE RULES:
- Science/Math topics: Questions in Hindi, technical terms in English (e.g., "Photosynthesis", "Newton's Law")
- History/Geography/Polity/GK: Pure Hindi preferred
- Numbers always in English digits (1, 2, 3 — never १, २, ३)

QUESTION QUALITY RULES:
1. Test CONCEPTUAL understanding — not just surface-level memory recall.
2. Questions should NOT be answerable by common sense alone. A student who hasn't studied should struggle.
3. DISTRACTOR QUALITY is the most important part:
   - All 4 options must belong to the same category (e.g., if answer is a year, all 4 must be years)
   - Wrong options must be plausible and tempting — not obviously wrong
   - Never use "उपरोक्त सभी", "इनमें से कोई नहीं", "a और b दोनों" as options
4. Exactly ONE correct answer per question — factually verified.
5. No trick questions, no double negatives, no wordplay-based questions.
6. Questions must come from the standard syllabus of the relevant competitive exam.

DIFFICULTY RULES:
- आसान (5 questions): Class 8-10 level. Basic facts a regular student should know.
- मध्यम (5 questions): Class 11-12 or 1-2 years of competitive exam prep required.
- कठिन (5 questions): Deep knowledge needed. Only a serious UPSC/JEE/NEET aspirant can answer.

ANSWER POSITION RULE:
- Correct answer index (0/1/2/3) must be RANDOMLY distributed.
- Ensure roughly equal distribution: some at 0, some at 1, some at 2, some at 3.

OUTPUT RULES:
- Return ONLY a valid JSON array. No markdown, no explanation, no text before or after.
- Any text outside the JSON array will crash the system."""

        prompt = f"""Topic: "{topic}"
Exam Context: Indian competitive exams (UPSC/SSC/NEET/JEE/Railways — whichever fits this topic best)

Generate exactly 15 MCQs:
- Questions 1 to 5:  level "आसान"
- Questions 6 to 10: level "मध्यम"
- Questions 11 to 15: level "कठिन"

Guidelines:
- Focus on real facts, dates, names, formulas that actually appear in competitive exam papers
- Each difficulty level must feel NOTICEABLY harder than the previous
- Wrong options should make even a prepared student think twice

Return a JSON array of exactly 15 objects. Each object:
{{
  "q": "Question text in Hindi",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "ans": 2,
  "level": "मध्यम",
  "explanation": "Specific reason why this answer is correct, with relevant fact/year/source."
}}

CRITICAL:
- "ans" = index (0/1/2/3) of the correct option in the options array
- Randomize correct answer position — don't always put it at index 1
- Explanation must be specific — not vague like "यह सही है"
- Return ONLY the JSON array. Nothing else.

Topic: {topic}"""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt}
            ],
            max_tokens=6000,
            temperature=0.4
        )

        raw = response.choices[0].message.content.strip()
        print(f"Raw response length: {len(raw)}")

        raw = re.sub(r'```json\s*', '', raw)
        raw = re.sub(r'```\s*',     '', raw)
        raw = raw.strip()

        start = raw.find('[')
        end   = raw.rfind(']')
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
                    "q":           str(q["q"]).strip(),
                    "options":     [str(o).strip() for o in q["options"]],
                    "ans":         int(q["ans"]),
                    "level":       str(q.get("level", "मध्यम")),
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


# ===== ASK =====
@app.route("/ask", methods=["POST"])
def ask():
    try:
        data     = request.json
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
आप हमेशा हिंदी या अंग्रेजी में पूछे जाने पर अंग्रेजी में जवाब देते हैं — बिल्कुल एक भारतीय गुरुजी की तरह।
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें जैसे क्रिकेट, बॉलीवुड, भारतीय त्योहार आदि
- प्यार से समझाएं जैसे एक गुरुजी समझाते हैं
- जवाब 150 शब्दों से कम रखें
- वर्तमान और updated जानकारी दें

Latest Search Results (Source: {search_source}):
{results_text}"""
        else:
            system_prompt = """आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप हमेशा हिंदी या अंग्रेजी में पूछे जाने पर अंग्रेजी में जवाब देते हैं — बिल्कुल एक भारतीय गुरुजी की तरह।
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें
- जवाब 150 शब्दों से कम रखें"""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": question}
            ]
        )

        answer     = response.choices[0].message.content
        audio_text = answer.replace("।", " ").replace("...", " ").replace("..", " ")
        tts        = gTTS(text=audio_text, lang="hi", slow=False)
        audio_buf  = io.BytesIO()
        tts.write_to_fp(audio_buf)
        audio_buf.seek(0)
        audio_b64 = base64.b64encode(audio_buf.read()).decode("utf-8")

        return jsonify({"answer": answer, "audio": audio_b64})

    except Exception as e:
        print("Ask ERROR:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
