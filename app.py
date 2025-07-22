import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import msgspec.json
from msgspec_schemaorg.models import Article, WebPage, Product, Event, Organization, Person, Place, CreativeWork, Thing # Import relevant models
from msgspec_schemaorg.utils import parse_iso8601
from datetime import datetime # Import datetime for type checking

# --- Configuration ---
# IMPORTANT: For production, use Streamlit's secrets management for API keys:
# https://docs.streamlit.io/deploy/streamlit-cloud/secrets-management
# GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GEMINI_API_KEY = "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U" # Placeholder for direct testing
genai.configure(api_key=GEMINI_API_KEY)

# --- Web Scraping Function ---
def fetch_content(url):
    """Fetches content from a URL and extracts title, description, dates, and images."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(r.text, "html.parser")

        # Explicitly convert to str() to avoid NavigableString issues
        title = str(soup.title.string) if soup.title else ""
        desc_tag = soup.find("meta", {"name": "description"})
        desc = str(desc_tag.get("content", "")) if desc_tag and desc_tag.get("content") else ""

        # Get all datetime attributes from <time> tags, ensure they are strings
        dates = [str(t.get("datetime")) for t in soup.find_all("time", datetime=True) if t.get("datetime")]
        # Get up to 5 image src attributes, also ensure they are strings
        images = [str(img["src"]) for img in soup.find_all("img", src=True) if img.get("src")][:5]
        
        return {"title": title, "description": desc, "dates": dates, "images": images}
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching content from URL: {e}")
        return {"title": "", "description": "", "dates": [], "images": []}
    except Exception as e:
        st.error(f"An unexpected error occurred during content fetching: {e}")
        return {"title": "", "description": "", "dates": [], "images": []}

# --- Gemini Inference Function ---
def gemini_infer_schema_details(context: dict, url: str):
    """
    Prompts Gemini to infer the best Schema.org type and relevant properties,
    structured for easy parsing.
    """
    prompt = f"""
You are a Schema.org expert. Based on the following web page content, identify the single most appropriate primary Schema.org @type (e.g., WebPage, Article, Product, Event, LocalBusiness, Organization, Person).
Then, list the most relevant Schema.org properties for that type, along with the specific data from the page that would fill them.
Output only a JSON object. Ensure the 'type' is a string and 'properties' is a dictionary where keys are standard Schema.org property names (camelCase) and values are the corresponding data extracted from the page context.
If a property value is not available or not applicable, omit it from the 'properties' dictionary.
Ensure the 'url' property in the 'properties' dictionary is populated with the Original Page URL.
Do NOT include any additional text or explanations outside the JSON block.

Page Title: {context['title']}
Page Description: {context['description']}
First available date/time (if any): {context['dates'][0] if context['dates'] else 'N/A'}
First 5 image URLs: {', '.join(context['images']) if context['images'] else 'N/A'}
Original Page URL: {url}

Example of expected JSON output:
```json
{{
  "type": "Article",
  "properties": {{
    "name": "{context['title']}",
    "headline": "{context['title']}",
    "description": "{context['description']}",
    "image": "{context['images'][0] if context['images'] else ''}",
    "datePublished": "{context['dates'][0] if context['dates'] else ''}",
    "url": "{url}"
  }}
}}
