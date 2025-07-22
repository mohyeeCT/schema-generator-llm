import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import msgspec.json
from msgspec_schemaorg.models import Article
from msgspec_schemaorg.utils import parse_iso8601

# --- config ---
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# --- functions ---
def fetch_content(url):
    r = requests.get(url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.string if soup.title else ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc = desc_tag["content"] if desc_tag else ""
    dates = [time["datetime"] for time in soup.find_all("time", datetime=True)]
    images = [img["src"] for img in soup.find_all("img", src=True)][:5]
    return {"title": title, "description": desc, "dates": dates, "images": images}

def call_llm(content):
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = (
        "You are a Schema.org expert. Given page data:\n"
        f"title: {content['title']}\n"
        f"description: {content['description']}\n"
        f"dates: {content['dates']}\n"
        f"images: {content['images']}\n"
        "Choose @type (e.g., Article) and output JSON with fields matching msgspec_schemaorg Article model:"
    )
    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are schema.org expert."},
                  {"role": "user", "content": prompt}],
        temperature=0,
        format="json"
    )
    return resp.choices[0].message.content

def build_schema_llm(raw):
    j = call_llm(raw)
    obj = Article(
        name=raw["title"],
        headline=raw["title"],
        description=raw["description"],
        image=raw["images"][0] if raw["images"] else None,
        datePublished=parse_iso8601(raw["dates"][0]) if raw["dates"] else None,
        id=None,
        context="https://schema.org"
    )
    return msgspec.json.decode(msgspec.json.encode(obj), type=Article)

def to_jsonld(obj):
    return msgspec.json.encode(obj, indent=2).decode()

# --- UI ---
st.title("Schema.org JSON‑LD Generator")
url = st.text_input("Enter a URL")
if st.button("Generate Schema"):
    with st.spinner("Analyzing..."):
        raw = fetch_content(url)
        schema_obj = build_schema_llm(raw)
        jsonld = to_jsonld(schema_obj)
    st.subheader("Generated JSON‑LD")
    st.code(jsonld, language="json")
    st.download_button("Download JSON‑LD", jsonld, file_name="schema.jsonld")
    st.markdown("[Validate using Schema Markup Validator](https://validator.schema.org)", unsafe_allow_html=True)
