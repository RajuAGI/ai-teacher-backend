from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from gtts import gTTS
from tavily import TavilyClient
import os
import io
import base64

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

def search_web(query):
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

        print("Search Results:", search_text)
        return search_text if search_text else ""
    except Exception as e:
        print("Search Error:", str(e))
        return ""

@app.route("/")
def home():
    return jsonify({"status": "Backend is running!"})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.json
        question = data.get("question", "")

        # Tavily से web search करो
        web_results = search_web(question)

        if web_results:
            system_prompt = f"""आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप सामान्यतः हिंदी में जवाब देते हैं 
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
जवाब देते समय इन बातों का ध्यान रखें:
-  हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें जैसे क्रिकेट, बॉलीवुड, भारतीय त्योहार आदि
- 
- जवाब 100 शब्दों से कम रखें
- वर्तमान और updated जानकारी दें
- 

Latest Search Results:
{web_results}"""
        else:
            system_prompt = """आप एक दोस्ताना AI Teacher हैं जिनका नाम राजू राम है।
आप सामान्यतः हिंदी में जवाब देते हैं
अगर कोई पूछे आप कौन हैं तो जवाब दें: मैं राजू राम हूं, आपका AI Teacher!
- हिंदी में जवाब दें
- सरल और आसान भाषा use करें
- भारतीय उदाहरण दें
- जवाब 100 शब्दों से कम रखें"""

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
