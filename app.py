import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import msgspec.json
# Import all relevant Schema.org models you might expect Gemini to suggest
from msgspec_schemaorg.models import (
    Article, WebPage, Product, Event, Organization, Person, Place,
    CreativeWork, Thing, LocalBusiness, Service, Recipe, Review,
    ImageObject, VideoObject, NewsArticle, BlogPosting
)
from msgspec_schemaorg.utils import parse_iso8601
from datetime import datetime

# --- Configuration ---
# IMPORTANT: For production deployments (e.g., Streamlit Community Cloud),
# ALWAYS use Streamlit's secrets management for API keys.
# Learn more here: https://docs.streamlit.io/deploy/streamlit-cloud/secrets-analysis.md
# Example: GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
# For local testing, you can keep it directly or load from an environment variable.
GEMINI_API_KEY = "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U" # Replace with your actual key or st.secrets
genai.configure(api_key=GEMINI_API_KEY)

# --- Web Scraping Function ---
def fetch_content(url):
    """
    Fetches content from a URL and extracts common metadata (title, description, dates, images).
    Ensures all extracted text is plain string to avoid BeautifulSoup NavigableString issues.
    """
    try:
        r = requests.get(url, timeout=10) # Set a reasonable timeout
        r.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(r.text, "html.parser")

        # Extract title, converting to string and handling potential None
        title = str(soup.title.string).strip() if soup.title and soup.title.string else ""

        # Extract description meta tag content, converting to string and handling potential None
        desc_tag = soup.find("meta", {"name": "description"})
        description = str(desc_tag.get("content", "")).strip() if desc_tag and desc_tag.get("content") else ""

        # Extract datetime attributes from <time> tags, converting to string
        dates = [str(t.get("datetime")).strip() for t in soup.find_all("time", datetime=True) if t.get("datetime")]

        # Extract up to 5 image src attributes, converting to string
        images = [str(img["src"]).strip() for img in soup.find_all("img", src=True) if img.get("src")][:5]
        
        return {"title": title, "description": description, "dates": dates, "images": images}
    except requests.exceptions.Timeout:
        st.error(f"Error: Request to {url} timed out. The server took too long to respond.")
        return {"title": "", "description": "", "dates": [], "images": []}
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching content from URL: {e}. Please check the URL and your internet connection.")
        return {"title": "", "description": "", "dates": [], "images": []}
    except Exception as e:
        st.error(f"An unexpected error occurred during content extraction: {e}")
        return {"title": "", "description": "", "dates": [], "images": []}

# --- Gemini Inference Function ---
def gemini_infer_schema_details(context: dict, url: str):
    """
    Prompts Gemini to infer the best Schema.org type and relevant properties,
    structured for easy parsing by the application.
    """
    # Define the example JSON output using single triple quotes (''')
    # and use raw string (r) to avoid backslash issues.
    # This prevents conflict with the """ inside the markdown code block.
    example_json_output = r'''
```json
{
  "type": "Article",
  "properties": {
    "name": "<Page Title>",
    "headline": "<Page Title>",
    "description": "<Page Description>",
    "image": "<First Image URL>",
    "datePublished": "<First Date/Time>",
    "url": "<Original Page URL>"
  }
}
