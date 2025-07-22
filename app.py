import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from msgspec.json import encode
from msgspec_schemaorg.models import Article
from msgspec_schemaorg.utils import parse_iso8601

# — Replace with your actual Gemini API key —
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
genai.configure(api_key=GEMINI_API_KEY)  # :contentReference[oaicite:1]{index=1}

# — Scrape raw page content —
def fetch_content(url):
    r = requests.get(url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.string if soup.title else ""
    desc = soup.find("meta", {"name": "description"})["content"] if soup.find("meta", {"name": "description"}) else ""
    dates = [t["datetime"] for t in soup.find_all("time", datetime=True)]
    images = [img["src"] for img in soup.find_all("img", src=True)][:5]
    return {"title": title, "description": desc, "dates": dates, "images": images}

# — Ask Gemini for schema type and content —
def gemini_generate_schema(context):
    prompt = (
        "You are a Schema.org expert. Page data:\n"
        f"- title: {context['title']}\n"
        f"- description: {context['description']}\n"
        f"- dates: {context['dates']}\n"
        f"- images: {context['images']}\n\n"
        "Pick the best @type (e.g., Article) and list fields needed in JSON, "
        "but do NOT output full JSON-LD—just tell me the main type to build."
    )
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content(prompt=prompt)
    return resp.text

def build_schema_obj(raw):
    # Default to Article; improve later by parsing Gemini's answer
    return Article(
        name=raw["title"],
        headline=raw["title"],
        description=raw["description"] or None,
        image=raw["images"][0] if raw["images"] else None,
        datePublished=parse_iso8601(raw["dates"][0]) if raw["dates"] else None,
        id=None,
        context="https://schema.org"
    )

def to_jsonld(obj):
    return encode(obj, indent=2).decode()

# — Streamlit UI —
st.title("💡 Schema Generator via Gemini")
url = st.text_input("Enter a URL to analyze")
if st.button("Generate Schema"):
    with st.spinner("Fetching & analyzing..."):
        raw = fetch_content(url)
        gemini_suggestion = gemini_generate_schema(raw)
        schema_obj = build_schema_obj(raw)
        jsonld = to_jsonld(schema_obj)

    st.subheader("🧠 Gemini Suggestion")
    st.write(gemini_suggestion)
    st.subheader("Generated JSON‑LD")
    st.code(jsonld, language="json")
    st.download_button("Download JSON‑LD", jsonld, file_name="schema.jsonld")
    st.markdown("[Validate in Schema Markup Validator](https://validator.schema.org)", unsafe_allow_html=True)
