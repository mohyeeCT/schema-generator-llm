import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json, msgspec.json
from msgspec_schemaorg.models import Article
from msgspec_schemaorg.utils import parse_iso8601
from datetime import datetime # Import datetime for type checking

# Configure Gemini API
GEMINI_API_KEY = "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U" # Consider using st.secrets for production
genai.configure(api_key=GEMINI_API_KEY)

def fetch_content(url):
    """Fetches content from a URL and extracts title, description, dates, and images."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string if soup.title else ""
        desc = (soup.find("meta", {"name": "description"}) or {}).get("content", "")
        # Get all datetime attributes from <time> tags
        dates = [t.get("datetime") for t in soup.find_all("time", datetime=True) if t.get("datetime")]
        # Get up to 5 image src attributes
        images = [img["src"] for img in soup.find_all("img", src=True)][:5]
        return {"title": title, "description": desc, "dates": dates, "images": images}
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching content from URL: {e}")
        return {"title": "", "description": "", "dates": [], "images": []}
    except Exception as e:
        st.error(f"An unexpected error occurred during content fetching: {e}")
        return {"title": "", "description": "", "dates": [], "images": []}

def gemini_suggest_type(context):
    """Uses Gemini to suggest the best Schema.org type for the page content."""
    prompt = (
        "You are a Schema.org expert. Based on the following page data, "
        "which single Schema.org @type (e.g., Article, Product, Event, WebPage) "
        "best fits this page? Just respond with the @type name, nothing else. "
        "If it's ambiguous, pick the most general relevant type.\n\n"
        f"- title: {context['title']}\n"
        f"- description: {context['description']}\n"
        f"- dates: {', '.join(context['dates']) if context['dates'] else 'None'}\n"
        f"- images: {', '.join(context['images']) if context['images'] else 'None'}\n\n"
    )
    model = genai.GenerativeModel("gemini-1.5-flash") # Use a stable model
    try:
        response = model.generate_content(prompt)
        # Access response.text directly
        return response.text.strip()
    except Exception as e:
        st.warning(f"Could not get type suggestion from Gemini: {e}")
        return "Not Suggested (API Error)"

def build_schema_obj(raw):
    """Builds a Schema.org Article object from raw extracted data."""
    # Ensure date parsing handles potential errors or missing dates gracefully
    published_date = None
    if raw["dates"]:
        try:
            # parse_iso8601 returns a datetime object
            published_date = parse_iso8601(raw["dates"][0])
        except ValueError:
            st.warning(f"Could not parse date: {raw['dates'][0]}. Skipping datePublished.")

    return Article(
        name=raw["title"],
        headline=raw["title"],
        description=raw["description"] or None,
        image=raw["images"][0] if raw["images"] else None,
        datePublished=published_date, # Pass datetime object directly
        # For @id and @context, these are usually defined by the library or can be explicitly set.
        # msgspec_schemaorg handles @context automatically if you import from models.
        # id should be a URL or a unique identifier for the entity
        id=None, # You might want to generate a canonical URL here if applicable
    )

def to_jsonld(obj: Article):
    """Converts a msgspec_schemaorg object to a pretty-printed JSON-LD string."""
    try:
        # Manually construct a dictionary from the Article object
        # This gives us fine-grained control over serialization, especially for datetime
        data_to_serialize = {
            "@context": "https://schema.org", # Explicitly set context
            "@type": "Article", # Explicitly set type for clarity, though it might be inferred by msgspec_schemaorg
            "name": obj.name,
            "headline": obj.headline,
            "description": obj.description,
            "image": obj.image,
            # Convert datetime object to ISO 8601 string
            "datePublished": obj.datePublished.isoformat() if isinstance(obj.datePublished, datetime) else obj.datePublished,
            # 'id' is often a URI, if you want it to be part of the JSON-LD, include it.
            # Assuming obj.id is None or a string/URI.
            "identifier": obj.id if obj.id else None # Use 'identifier' for id if it's a URI, or just omit if None
        }

        # Remove keys with None values to keep the JSON-LD clean
        data_to_serialize = {k: v for k, v in data_to_serialize.items() if v is not None}

        # 1) Raw encode the dictionary with msgspec
        # msgspec is highly optimized for encoding dictionaries
        raw_bytes = msgspec.json.encode(data_to_serialize)

        # 2) Decode to string and then load into Python dict for pretty printing
        # This step is mainly for pretty-printing, as msgspec.json.encode
        # directly gives you the compact JSON byte string.
        data = json.loads(raw_bytes.decode('utf-8'))

        # 3) Pretty-print with indent
        return json.dumps(data, indent=2)
    except Exception as e:
        st.error(f"Error converting object to JSON-LD: {e}")
        return "Error: Could not generate JSON-LD"


# Streamlit UI
st.title("📘 Schema.org JSON‑LD Generator (Gemini)")
st.markdown("Enter a URL to generate Schema.org JSON-LD markup and get a Schema.org type suggestion from Gemini.")

url = st.text_input("Enter a URL", placeholder="e.g., https://www.example.com/article")

if st.button("Generate Schema"):
    if not url:
        st.warning("Please enter a URL to proceed.")
    else:
        with st.spinner("Processing... This might take a moment."):
            raw_data = fetch_content(url)

            if raw_data["title"] or raw_data["description"]: # Only proceed if some content was successfully fetched
                suggested_type = gemini_suggest_type(raw_data)
                schema_obj = build_schema_obj(raw_data)
                jsonld = to_jsonld(schema_obj)

                st.subheader("💡 Gemini Suggests")
                st.write(f"The suggested Schema.org type is: **`{suggested_type}`**")

                st.subheader("✅ JSON‑LD Output")
                st.code(jsonld, language="json")

                # Only offer download if JSON-LD was successfully generated
                if "Error" not in jsonld:
                    st.download_button("📥 Download JSON‑LD", jsonld, file_name="schema.jsonld", mime="application/ld+json")

                st.markdown(
                    "---" # Horizontal rule for separation
                    "🔗 **[Validate with Google's Rich Results Test](https://search.google.com/test/rich-results)** "
                    "(Recommended for checking Google's interpretation)"
                    "<br>"
                    "🔗 **[Validate with Schema Markup Validator](https://validator.schema.org)** "
                    "(For general Schema.org compliance)"
                    , unsafe_allow_html=True
                )
            else:
                st.error("Could not fetch meaningful content from the provided URL. Please check the URL and try again.")

st.markdown(
    """
    ---
    This tool uses Gemini to suggest Schema.org types and `msgspec_schemaorg` to help structure the JSON-LD.
    """
)
