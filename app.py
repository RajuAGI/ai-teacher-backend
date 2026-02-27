from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from gtts import gTTS
from tavily import TavilyClient
import os, io, base64, requests, json, re
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

groq_client   = Groq(api_key=os.environ.get("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

# ===== SEARCH HELPERS =====
def search_tavily(query):
    try:
        results = tavily_client.search(query=query, search_depth="basic", max_results=5)
        processed = []
        for item in results.get("results", []):
            processed.append({"title": item.get("title",""), "snippet": (item.get("content","")[:180]+"..."), "url": item.get("url","")})
        if processed: print("✅ Tavily Search Success!")
        return processed
    except Exception as e:
        print("❌ Tavily Failed:", e); return []

def search_duckduckgo(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(f"https://duckduckgo.com/html/?q={requests.utils.quote(query)}", headers=headers, timeout=6)
        soup = BeautifulSoup(response.text, "html.parser")
        titles   = soup.select("a.result__a")[:5]
        snippets = soup.select("a.result__snippet")[:5]
        results  = [{"title": t.get_text(strip=True), "snippet": snippets[i].get_text(strip=True) if i < len(snippets) else "", "url": t.get("href","")} for i,t in enumerate(titles)]
        if results: print("✅ DuckDuckGo Success!")
        return results
    except Exception as e:
        print("❌ DuckDuckGo Failed:", e); return []

def search_bing(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(f"https://www.bing.com/search?q={requests.utils.quote(query)}", headers=headers, timeout=6)
        soup     = BeautifulSoup(response.text, "html.parser")
        results  = []
        for item in soup.select("li.b_algo")[:5]:
            t = item.select_one("h2 a"); s = item.select_one("p")
            if t: results.append({"title": t.get_text(strip=True), "snippet": s.get_text(strip=True) if s else "", "url": t.get("href","")})
        if results: print("✅ Bing Success!")
        return results
    except Exception as e:
        print("❌ Bing Failed:", e); return []

def smart_search(query):
    for fn, name in [(search_tavily,"Tavily"),(search_duckduckgo,"DuckDuckGo"),(search_bing,"Bing")]:
        r = fn(query)
        if r: return r, name
    return [], "None"

def make_audio(text):
    try:
        clean = text.replace("।"," ").replace("...","").strip()[:400]
        tts   = gTTS(text=clean, lang="hi", slow=False)
        buf   = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
    except: return ""

# ===== ROUTES =====
@app.route("/")
def home():
    return jsonify({"status": "AI Teacher Backend Running! 🚀"})

@app.route("/ping")
def ping():
    return jsonify({"status": "awake"})

@app.route("/search", methods=["POST"])
def search():
    try:
        query = request.json.get("query","").strip()
        if not query: return jsonify({"results":[]})
        results, source = smart_search(query)
        wiki  = [r for r in results if "wikipedia.org" in r.get("url","").lower()]
        other = [r for r in results if "wikipedia.org" not in r.get("url","").lower()]
        if not wiki:
            w2, _ = smart_search(f"{query} wikipedia")
            wiki  = [r for r in w2 if "wikipedia.org" in r.get("url","").lower()][:1]
        if wiki: wiki[0]["is_wiki"] = True
        return jsonify({"results": wiki+other, "source": source})
    except Exception as e:
        return jsonify({"results":[], "error":str(e)}), 500

# ✅ FIX: /ask mein audio NAHI bhejte — response fast rahega
@app.route("/ask", methods=["POST"])
def ask():
    try:
        question = request.json.get("question","").strip()
        if not question: return jsonify({"error":"No question provided"}), 400

        web_results, search_source = smart_search(question)
        web_text = "\n".join([f"{i+1}. {r['title']}: {r['snippet']}" for i,r in enumerate(web_results)]) if web_results else ""

        system = f"""आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
हमेशा हिंदी में जवाब दें — एक भारतीय गुरुजी की तरह।
सरल भाषा, भारतीय उदाहरण, जवाब 150 शब्दों से कम।
{f'Latest Web Results ({search_source}): {web_text}' if web_text else ''}"""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"system","content":system},{"role":"user","content":question}],
            max_tokens=500
        )
        answer = response.choices[0].message.content
        # ✅ Audio NAHI bhej rahe — /tts endpoint pe alag se aayega
        return jsonify({"answer": answer, "source": search_source})

    except Exception as e:
        print("Ask ERROR:", e)
        return jsonify({"error": str(e)}), 500

# ✅ NEW: Alag TTS endpoint — frontend alag se call karega
@app.route("/tts", methods=["POST"])
def tts():
    try:
        text  = request.json.get("text","").strip()
        audio = make_audio(text)
        return jsonify({"audio": audio})
    except Exception as e:
        return jsonify({"audio":"", "error":str(e)})

@app.route("/quiz", methods=["POST"])
def generate_quiz():
    try:
        topic = request.json.get("topic","").strip()
        if not topic: return jsonify({"error":"Topic required"}), 400
        print(f"Generating quiz: {topic}")

        system_prompt = """You are a senior question paper setter for Indian competitive exams (UPSC, SSC, NEET, JEE, Railways).
Generate exactly 15 bilingual MCQ questions.
BILINGUAL FORMAT: Write every question in BOTH Hindi AND English: "हिंदी प्रश्न? (English question?)"
Write every option in both: "हिंदी विकल्प (English option)"
QUALITY: All 4 options same category. No 'उपरोक्त सभी'. Hard questions must be 2-3 lines long.
Randomize correct answer position (mix of 0,1,2,3).
Return ONLY valid JSON array. No other text."""

        prompt = f"""Topic: "{topic}"
First 5: level "आसान/Easy" | Next 5: level "मध्यम/Medium" | Last 5: level "कठिन/Hard"
JSON format:
[{{"q":"हिंदी? (English?)","options":["A हिंदी (English)","B","C","D"],"ans":1,"level":"मध्यम/Medium","explanation":"Hindi. English."}}]
Return ONLY the JSON array."""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"system","content":system_prompt},{"role":"user","content":prompt}],
            max_tokens=6000, temperature=0.4
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'```json\s*','',raw); raw = re.sub(r'```\s*','',raw).strip()
        s = raw.find('['); e = raw.rfind(']')
        if s!=-1 and e!=-1: raw = raw[s:e+1]

        questions = json.loads(raw)
        valid = []
        for q in questions:
            if (isinstance(q,dict) and "q" in q and "options" in q and "ans" in q
                and isinstance(q["options"],list) and len(q["options"])==4
                and isinstance(q["ans"],int) and 0<=q["ans"]<=3):
                valid.append({"q":str(q["q"]).strip(),"options":[str(o).strip() for o in q["options"]],
                              "ans":int(q["ans"]),"level":str(q.get("level","मध्यम")),"explanation":str(q.get("explanation",""))})
        print(f"Valid questions: {len(valid)}")
        if len(valid) < 5: return jsonify({"error":"Quiz generate नहीं हो पाई। दोबारा try करो।"}), 500
        return jsonify({"questions":valid,"topic":topic,"total":len(valid)})

    except json.JSONDecodeError:
        return jsonify({"error":"Quiz parse error। दोबारा try करो।"}), 500
    except Exception as e:
        print("Quiz ERROR:", e); return jsonify({"error":str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
    
