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
# Learn more here: https://docs.streamlit.io/deploy/streamlit-cloud/secrets-management
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
    # Define the example JSON output as a simple string containing ONLY the JSON.
    # No markdown backticks here.
    example_json_content = """{
  "type": "Article",
  "properties": {
    "name": "<Page Title>",
    "headline": "<Page Title>",
    "description": "<Page Description>",
    "image": "<First Image URL>",
    "datePublished": "<First Date/Time>",
    "url": "<Original Page URL>"
  }
}"""

    # Define the prompt template by concatenating multiple single-quoted strings.
    # This avoids any issues with nested triple-quotes.
    prompt_template = (
        "You are an expert in Schema.org JSON-LD markup.\n"
        "Based on the following web page content and URL, your task is to identify the single most appropriate primary Schema.org `@type` "
        "(e.g., WebPage, Article, Product, Event, LocalBusiness, Organization, Person, Recipe).\n"
        "Then, list the most relevant Schema.org properties for that specific `@type`, along with the corresponding data extracted directly from the provided page context.\n"
        "\n"
        "**Output Format:**\n"
        "* Strictly output a single JSON object.\n"
        "* The top-level object must have two keys:\n"
        "    * `\"type\"`: A string representing the chosen Schema.org `@type` (e.g., \"WebPage\", \"Article\").\n"
        "    * `\"properties\"`: A JSON object (dictionary) where keys are standard Schema.org property names (in camelCase, e.g., \"name\", \"headline\", \"description\", \"image\", \"datePublished\", \"url\", \"price\", \"brand\"). Values should be the extracted data.\n"
        "* If a property value is not available, is \"N/A\", or is an empty string, **omit that property entirely** from the \"properties\" dictionary.\n"
        "* Ensure the `\"url\"` property within the `\"properties\"` dictionary is always populated with the `Original Page URL`.\n"
        "* Do NOT include any additional text, explanations, or markdown outside the single JSON code block.\n"
        "\n"
        "**Provided Page Content:**\n"
        "Page Title: {page_title}\n"
        "Page Description: {page_description}\n"
        "First available date/time (if any): {first_date}\n"
        "First 5 image URLs: {image_urls}\n"
        "Original Page URL: {original_url}\n"
        "\n"
        "Example of expected JSON output:\n"
        "```json\n" # Markdown code block start
        "{json_example}\n" # Insert the raw JSON content here
        "```\n" # Markdown code block end
        "\n"
        "Now, generate the JSON output for the provided page content:\n"
    )

    # Use .format() to populate the template
    prompt = prompt_template.format(
        page_title=context['title'],
        page_description=context['description'],
        first_date=context['dates'][0] if context['dates'] else 'N/A',
        image_urls=', '.join(context['images']) if context['images'] else 'N/A',
        original_url=url,
        json_example=example_json_content # Insert the raw JSON string here
    )

    model = genai.GenerativeModel("gemini-1.5-flash") # Use a stable and fast model
    try:
        response = model.generate_content(prompt)
        # Ensure that the response text is not empty or malformed before stripping
        if not response.text:
            raise ValueError("Gemini returned an empty response.")
            
        raw_json_str = response.text.strip()
        
        # Robustly extract JSON from potential markdown code block
        if raw_json_str.startswith("```json"):
            json_str = raw_json_str[len("```json"):].strip()
            if json_str.endswith("```"):
                json_str = json_str[:-len("```")].strip()
            else: # Fallback if it starts with 3 but doesn't end cleanly
                json_str = raw_json_str # Treat as raw JSON, hope for the best
        else:
            json_str = raw_json_str # Assume it's just raw JSON if no markdown block

        parsed_gemini_output = json.loads(json_str) # Use json_str from above logic

        inferred_type = parsed_gemini_output.get("type", "WebPage").strip()
        inferred_properties = parsed_gemini_output.get("properties", {})

        # Basic validation of inferred type
        if not inferred_type:
            inferred_type = "WebPage" # Default if Gemini somehow provides empty type

        return inferred_type, inferred_properties

    except json.JSONDecodeError as e:
        st.error(f"Gemini output was not valid JSON. Error: {e}")
        st.code(f"Raw Gemini Output:\n{raw_json_str}", language="text") # Show raw output for debugging
        return "WebPage", {} # Fallback to default
    except Exception as e:
        st.error(f"An error occurred during Gemini schema inference: {e}")
        return "WebPage", {} # Fallback

# --- Schema.org Model Mapping ---
# This dictionary maps a string Schema.org type (as suggested by Gemini)
# to the corresponding msgspec_schemaorg model class.
SCHEMA_MODEL_MAP = {
    "Article": Article,
    "WebPage": WebPage,
    "Product": Product,
    "Event": Event,
    "Organization": Organization,
    "Person": Person,
    "Place": Place,
    "LocalBusiness": LocalBusiness,
    "Service": Service,
    "Recipe": Recipe,
    "Review": Review,
    "ImageObject": ImageObject,
    "VideoObject": VideoObject,
    "NewsArticle": NewsArticle,
    "BlogPosting": BlogPosting,
    "CreativeWork": CreativeWork, # More generic if specific type fails
    "Thing": Thing, # Most generic fallback
}

# --- Schema Object Builder Function ---
def build_schema_obj_from_inferred(inferred_type: str, inferred_properties: dict, original_url: str):
    """
    Constructs a msgspec_schemaorg object based on Gemini's inference,
    with robust type handling and fallbacks.
    """
    # Properties that will be passed directly to the SchemaModel constructor
    model_properties = {}

    # Get the appropriate msgspec_schemaorg model from the map.
    SchemaModel = SCHEMA_MODEL_MAP.get(inferred_type)
    if not SchemaModel:
         st.warning(f"Schema.org type '{inferred_type}' is not explicitly supported by the application. Defaulting to WebPage.")
         SchemaModel = WebPage
         # If falling back, ensure the @type in the final JSON matches the fallback model
         inferred_type = "WebPage" 

    # Add 'url' property as it's common and always present
    model_properties["url"] = original_url
    
    # Use inferred 'id' or default to URL, and add to model_properties if exists
    # Note: 'id' is a Python keyword, msgspec_schemaorg uses 'id_' or expects it for specific types.
    # For now, let's keep it simple and ensure the output JSON has an '@id'.
    # The msgspec_schemaorg models usually don't have an 'id' constructor argument directly.
    # It's part of the JSON-LD context.

    # Iterate through inferred properties and add them to model_properties,
    # applying type conversions and validations.
    for prop_name, prop_value in inferred_properties.items():
        # Skip properties that are None, empty strings, or placeholders like "N/A"
        if prop_value is None or (isinstance(prop_value, str) and prop_value.strip() in ["", "N/A"]):
            continue

        try:
            # --- Type-specific handling for common Schema.org properties ---
            if prop_name in ["datePublished", "dateModified", "startDate", "endDate"]:
                if isinstance(prop_value, str) and prop_value:
                    # msgspec_schemaorg date fields typically accept datetime objects
                    model_properties[prop_name] = parse_iso8601(prop_value)
                else:
                    st.warning(f"Invalid date format for '{prop_name}': '{prop_value}'. Omitting.")
                    continue
            elif prop_name == "image":
                # 'image' can be a URL string or an ImageObject. For simplicity, we expect URL here.
                if isinstance(prop_value, str) and prop_value:
                    model_properties[prop_name] = prop_value
                else:
                    st.warning(f"Invalid image URL format for '{prop_name}': '{prop_value}'. Omitting.")
                    continue
            elif prop_name in ["price", "ratingValue", "reviewCount", "aggregateRating.ratingValue", "aggregateRating.reviewCount"]:
                # Attempt to convert to float or int for numerical properties
                try:
                    if isinstance(prop_value, str):
                        prop_value = prop_value.replace(',', '') # Handle comma as thousands separator
                    
                    if '.' in str(prop_value): # Check if it looks like a float
                        model_properties[prop_name] = float(prop_value)
                    else: # Assume int otherwise
                        model_properties[prop_name] = int(prop_value)
                except ValueError:
                    st.warning(f"Invalid number format for '{prop_name}': '{prop_value}'. Omitting.")
                    continue
            # Add more specific type handling for other properties if needed (e.g., duration, geo)
            else:
                # For all other properties, assume string or direct value is fine
                model_properties[prop_name] = prop_value

        except Exception as e:
            st.warning(f"Failed to process property '{prop_name}' with value '{prop_value}': {e}. Omitting.")
            continue # Continue to next property if one is problematic

    try:
        # Instantiate the Schema.org model with the prepared properties.
        # msgspec_schemaorg models are msgspec.Structs and expect keyword arguments.
        schema_instance = SchemaModel(**model_properties)
        
        # Manually set @context and @type for serialization purposes, if not handled by msgspec_schemaorg directly
        # The to_jsonld function should add @context. @type is implicit in the model.
        # However, if msgspec_schemaorg model doesn't automatically add @context/@type during encoding,
        # we might need to include it in a custom encoder or wrapper.
        # For now, let's rely on msgspec.json.encode doing its job for basic @type.
        
        return schema_instance
    except Exception as e:
        # This catch is for validation errors raised by msgspec_schemaorg itself during instantiation
        st.error(f"Schema.org model validation failed for '{inferred_type}' type with properties {model_properties}: {e}")
        st.warning("Attempting to generate a generic WebPage schema as a fallback due to model validation issues.")
        # Provide a more robust fallback if the specific model fails to instantiate
        return WebPage(
            name=model_properties.get("name", context.get("title", "Generated WebPage")),
            description=model_properties.get("description", context.get("description", "")),
            url=original_url # Fallback always includes URL
        )

# --- JSON-LD Serialization Function ---
def to_jsonld(obj):
    """
    Converts a msgspec_schemaorg object (which is a msgspec.Struct)
    to a pretty-printed JSON-LD string, ensuring @context and @type are present.
    """
    try:
        # msgspec.json.encode directly handles msgspec.Struct objects efficiently.
        raw_bytes = msgspec.json.encode(obj)
        
        # Decode the bytes to a UTF-8 string, then load into a standard Python dict
        data = json.loads(raw_bytes.decode('utf-8'))
        
        # Manually ensure @context and @type are at the top, if not already handled perfectly by msgspec
        # msgspec_schemaorg models generally output @type correctly.
        # @context might need explicit addition if not automatically present.
        if "@context" not in data:
            data["@context"] = "https://schema.org"
        
        # Reorder keys to put @context and @type first for standard JSON-LD appearance
        ordered_data = {"@context": data.pop("@context")}
        if "@type" in data: # Ensure @type comes after @context
            ordered_data["@type"] = data.pop("@type")
        ordered_data.update(data) # Add remaining properties

        return json.dumps(ordered_data, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Critical error during final JSON-LD serialization: {e}")
        st.exception(e)
        return "Error: Could not generate final JSON-LD output."

# --- Streamlit UI ---
st.set_page_config(page_title="Schema.org JSON-LD Generator", page_icon="📘", layout="centered")

st.title("📘 Schema.org JSON‑LD Generator (Gemini Hybrid)")
st.markdown("""
This tool uses a robust hybrid approach to generate Schema.org JSON-LD markup:

1.  **Content Scraping**: Fetches key metadata (title, description, dates, images) from the provided URL.
2.  **AI Inference (Google Gemini)**: Analyzes the scraped content to intelligently infer the most appropriate Schema.org `@type` (e.g., `Article`, `WebPage`, `Product`) and suggests a list of relevant properties with their values in a structured format.
3.  **Code-Driven Construction & Validation**: Uses Python's `msgspec_schemaorg` library to build the JSON-LD object. This step ensures syntactic correctness, validates data types, and mitigates common "hallucinations" or malformations from the AI's raw output.
""")

url = st.text_input("Enter a URL", placeholder="e.g., https://www.example.com/blog-post-about-ai", key="url_input")

if st.button("Generate Schema", key="generate_button"):
    if not url:
        st.warning("Please enter a URL to proceed.")
    elif not url.startswith(("http://", "https://")):
        st.warning("Please enter a valid URL, starting with `http://` or `https://`.")
    else:
        with st.spinner("Processing... This might take a moment, especially for complex pages."):
            raw_data = fetch_content(url)

            # Check if any meaningful content was fetched. A title or description is usually expected.
            if not raw_data["title"] and not raw_data["description"]:
                st.error("Could not fetch any meaningful content from the provided URL. "
                         "This might be due to a blocked request, an invalid URL, or a page with very little accessible text content.")
                st.info("Ensure the URL is publicly accessible and contains standard HTML with a `<title>` tag or a `<meta name='description'>` tag.")
            else:
                # Step 1: Gemini infers type and properties based on scraped data
                inferred_type, inferred_properties = gemini_infer_schema_details(raw_data, url)

                # Step 2: Build and validate the Schema.org object using the inferred details
                # Pass raw_data['title'] and raw_data['description'] as context for better fallback naming
                schema_obj = build_schema_obj_from_inferred(inferred_type, inferred_properties, url)
                
                # Step 3: Serialize the validated object to pretty-printed JSON-LD
                jsonld_output = to_jsonld(schema_obj)

                st.subheader("💡 Gemini's Inferred Type")
                st.write(f"The primary Schema.org type identified by Gemini is: **`{inferred_type}`**")
                
                st.subheader("🔍 Gemini's Inferred Properties (for debugging purposes)")
                # Display the raw dictionary Gemini provided before code-based validation
                st.json(inferred_properties) 

                st.subheader("✅ Final Generated JSON‑LD Output")
                st.code(jsonld_output, language="json")

                # Offer download button only if JSON-LD generation was successful
                if "Error" not in jsonld_output:
                    st.download_button(
                        "📥 Download JSON‑LD",
                        data=jsonld_output,
                        file_name="schema.jsonld",
                        mime="application/ld+json",
                        key="download_button"
                    )

                st.markdown(
                    "---" # Horizontal rule for separation
                    "**Validation Tools:**"
                    "<ul>"
                    "<li>🔗 <a href='https://search.google.com/test/rich-results' target='_blank'>Google's Rich Results Test</a> "
                    "(Recommended for checking Google's interpretation and rich result eligibility)</li>"
                    "<li>🔗 <a href='https://validator.schema.org/' target='_blank'>Schema Markup Validator</a> "
                    "(For general Schema.org compliance and syntax)</li>"
                    "</ul>"
                    , unsafe_allow_html=True
                )

st.markdown(
    """
    ---
    *Built with ❤️ using Google Gemini and `msgspec_schemaorg`.*
    """
)
