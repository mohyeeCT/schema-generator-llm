import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json, msgspec.json
# Import more Schema.org models
from msgspec_schemaorg.models import Article, WebPage, Product, Event, Organization, Person, Place, CreativeWork, Thing
from msgspec_schemaorg.utils import parse_iso8601
from datetime import datetime # Import datetime for type checking

# Configure Gemini API
# It's highly recommended to use Streamlit's secrets management for API keys:
# https://docs.streamlit.io/deploy/streamlit-cloud/secrets-management
# GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GEMINI_API_KEY = "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U" # For direct testing, but use secrets in deployment!
genai.configure(api_key=GEMINI_API_KEY)

def fetch_content(url):
    """Fetches content from a URL and extracts title, description, dates, and images."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(r.text, "html.parser")

        # Explicitly convert to str() to avoid NavigableString issues
        title = str(soup.title.string) if soup.title else ""
        desc_tag = soup.find("meta", {"name": "description"})
        desc = str(desc_tag.get("content", "")) if desc_tag else ""

        # Get all datetime attributes from <time> tags
        dates = [t.get("datetime") for t in soup.find_all("time", datetime=True) if t.get("datetime")]
        # Get up to 5 image src attributes, also ensure they are strings
        images = [str(img["src"]) for img in soup.find_all("img", src=True)][:5]
        
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
        # Access response.text directly and clean it
        suggested_type = response.text.strip()
        # Basic validation/correction for common Gemini outputs
        if "Article" in suggested_type: return "Article"
        if "WebPage" in suggested_type: return "WebPage"
        if "Product" in suggested_type: return "Product"
        if "Event" in suggested_type: return "Event"
        if "Organization" in suggested_type: return "Organization"
        if "Person" in suggested_type: return "Person"
        if "Place" in suggested_type: return "Place"
        # Fallback to a common type if Gemini gives something unexpected
        return "WebPage"
    except Exception as e:
        st.warning(f"Could not get type suggestion from Gemini: {e}")
        return "WebPage" # Default to WebPage if Gemini fails

# Mapping of suggested types to msgspec_schemaorg models and their relevant properties
SCHEMA_TYPE_MAPPING = {
    "Article": {
        "model": Article,
        "properties": {
            "name": "title",
            "headline": "title",
            "description": "description",
            "image": lambda r: r["images"][0] if r["images"] else None,
            "datePublished": lambda r: parse_iso8601(r["dates"][0]) if r["dates"] else None,
        }
    },
    "WebPage": {
        "model": WebPage,
        "properties": {
            "name": "title",
            "description": "description",
            "image": lambda r: r["images"][0] if r["images"] else None,
            # WebPage typically doesn't have a datePublished in the same way an Article does
            # We can use dateModified if available, or omit.
            "dateModified": lambda r: parse_iso8601(r["dates"][0]) if r["dates"] else None,
        }
    },
    "Product": {
        "model": Product,
        "properties": {
            "name": "title",
            "description": "description",
            "image": lambda r: r["images"][0] if r["images"] else None,
            # Products might have offers, brand, etc., which are not in raw_data
            # You'd need more sophisticated scraping for these.
        }
    },
    # Add more mappings as needed
    # "Event": { "model": Event, "properties": {...} },
    # "Organization": { "model": Organization, "properties": {...} },
    # "Person": { "model": Person, "properties": {...} },
}

def build_schema_obj(raw: dict, suggested_type: str):
    """
    Builds a Schema.org object based on the suggested_type and raw extracted data.
    """
    model_info = SCHEMA_TYPE_MAPPING.get(suggested_type)
    if not model_info:
        st.warning(f"Unsupported Schema.org type '{suggested_type}'. Defaulting to WebPage.")
        model_info = SCHEMA_TYPE_MAPPING["WebPage"] # Fallback if suggestion is not mapped

    SchemaModel = model_info["model"]
    properties = {}
    for schema_prop, raw_key_or_func in model_info["properties"].items():
        if callable(raw_key_or_func):
            value = raw_key_or_func(raw)
        else:
            value = raw.get(raw_key_or_func)

        # Handle datetime conversion for date properties within the mapping
        if isinstance(value, datetime):
            value = value.isoformat()

        if value is not None:
            properties[schema_prop] = value

    # Add common properties that might apply to most types
    properties["@context"] = "https://schema.org"
    properties["@type"] = suggested_type # Ensure the @type matches the chosen model
    properties["id"] = None # Still keeping this as None unless you have a specific URI

    try:
        # Create an instance of the chosen Schema.org model
        # Using **properties to unpack the dictionary into arguments
        schema_instance = SchemaModel(**properties)
        return schema_instance
    except Exception as e:
        st.error(f"Error creating Schema.org object for {suggested_type}: {e}")
        # Fallback to a generic WebPage if the specific model creation fails
        st.warning("Attempting to generate a generic WebPage schema instead.")
        return WebPage(
            name=raw["title"],
            description=raw["description"],
            image=raw["images"][0] if raw["images"] else None,
            context="https://schema.org"
        )


def to_jsonld(obj):
    """Converts a msgspec_schemaorg object to a pretty-printed JSON-LD string."""
    try:
        # Since we are now building the dict directly in build_schema_obj,
        # we can ensure that the object 'obj' is already a msgspec.Struct instance
        # that *should* be directly encodable by msgspec.json.encode().
        # If it's a manually constructed dict from build_schema_obj fallback,
        # msgspec.json.encode handles it too.

        # The previous error "Encoding objects of type NavigableString is unsupported"
        # was fixed in fetch_content.
        # The previous error "'Article' object has no attribute 'dict'" was due to my bad suggestion.
        # Now, `obj` should be a clean msgspec_schemaorg model instance.
        raw_bytes = msgspec.json.encode(obj)

        # Decode to string and then load into Python dict for pretty printing
        data = json.loads(raw_bytes.decode('utf-8'))

        # Pretty-print with indent
        return json.dumps(data, indent=2)
    except Exception as e:
        st.error(f"Error converting object to JSON-LD: {e}")
        st.exception(e) # Display full traceback for debugging
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

            # Check if any content was actually extracted before proceeding
            if not any(raw_data.values()): # If all values are empty or default
                st.error("Could not fetch any meaningful content from the provided URL. Please check the URL and try again.")
                st.info("Ensure the URL is publicly accessible and contains standard HTML with title/description/image tags.")
            else:
                suggested_type = gemini_suggest_type(raw_data)
                # Pass the suggested_type to the builder
                schema_obj = build_schema_obj(raw_data, suggested_type)
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

st.markdown(
    """
    ---
    This tool uses Gemini to suggest Schema.org types and `msgspec_schemaorg` to help structure the JSON-LD.
    """
)
