import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import msgspec.json
from openai import OpenAI
from msgspec_schemaorg.models import Article
from msgspec_schemaorg.utils import parse_iso8601

# — Insert your actual Gemini API key here —
GEMINI_API_KEY = "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U"
client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

def fetch_content(url):
    r = requests.get(url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.string if soup.title else ""
    desc_tag = soup.find("meta", {"name": "description"})
    desc = desc_tag["content"] if desc_tag else ""
    dates = [t.get("datetime") for t in soup.find_all("time", datetime=True)]
    images = [img["src"] for img in soup.find_all("img", src=True)][:5]
    return {"title": title, "description": desc, "dates": dates, "images": images}

def gemini_suggest_type(context):
    prompt = (
        "You are a Schema.org expert. Page data:\n"
        f"- title: {context['title']}\n"
        f"- description: {context['description']}\n"
        f"- dates: {context['dates']}\n"
        f"- images: {context['images']}\n\n"
        "Which @type (Article, Product, Event, etc.) best fits this page?"
    )
    resp = client.chat.completions.create(
        model="gemini-2.0-flash",
        messages=[
            {"role": "system", "content": "You are a Schema.org expert."},
            {"role": "user", "content": prompt}
        ]
    )
    return resp.choices[0].message.content.strip()

def build_schema_obj(raw):
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
    # Step 1: raw encoding with msgspec (no indent support)
    raw_bytes = msgspec.json.encode(obj)
    # Step 2: parse and Step 3: pretty-print with built-in json
    return json.dumps(json.loads(raw_bytes.decode()), indent=2)

# — Streamlit UI —
st.title("📘 Schema.org JSON‑LD Generator (Gemini)")
url = st.text_input("Enter a URL")
if st.button("Generate Schema"):
    with st.spinner("Processing..."):
        raw_data = fetch_content(url)
        suggested_type = gemini_suggest_type(raw_data)
        schema_obj = build_schema_obj(raw_data)
        jsonld = to_jsonld(schema_obj)

    st.subheader("💡 Gemini Suggests")
    st.write(suggested_type)
    st.subheader("✅ JSON‑LD Output")
    st.code(jsonld, language="json")
    st.download_button("📥 Download JSON‑LD", jsonld, file_name="schema.jsonld")
    st.markdown(
        "[🔗 Validate with Schema Markup Validator](https://validator.schema.org)",
        unsafe_allow_html=True
    )
