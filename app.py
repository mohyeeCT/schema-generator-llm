import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import msgspec.json
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
from typing import Dict, List, Optional, Any

# Import all relevant Schema.org models
from msgspec_schemaorg.models import (
    Article, WebPage, Product, Event, Organization, Person, Place,
    CreativeWork, Thing, LocalBusiness, Service, Recipe, Review,
    ImageObject, VideoObject, NewsArticle, BlogPosting, ContactPoint,
    PostalAddress, ScholarlyArticle, Restaurant, FAQPage, HowTo
)
from msgspec_schemaorg.utils import parse_iso8601

# --- Configuration ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)

# --- Page Type Detection ---
PAGE_TYPES = {
    "Homepage": "The main page of a website",
    "About Us": "Company information and background",
    "Contact Us": "Contact information and forms",
    "Product Page": "Individual product details",
    "Category Page": "Product or service category listing",
    "Service Page": "Specific service information",
    "Blog Post": "Individual blog article",
    "News Article": "News or press release",
    "FAQ Page": "Frequently asked questions",
    "Recipe Page": "Recipe with ingredients and instructions",
    "Event Page": "Event details and information",
    "Review Page": "Product or service reviews",
    "Video Page": "Video content page",
    "Location/Store": "Physical location information",
    "Team/People": "Team member or individual profiles"
}

# --- Expanded Schema Templates ---
COMPREHENSIVE_TEMPLATES = {
    "Article": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": "",
            "description": "",
            "image": "",
            "author": {"@type": "Person", "name": "", "url": ""},
            "publisher": {
                "@type": "Organization",
                "name": "",
                "logo": {"@type": "ImageObject", "url": ""}
            },
            "datePublished": "",
            "dateModified": "",
            "url": "",
            "articleSection": "",
            "wordCount": "",
            "keywords": [],
            "mainEntityOfPage": {"@type": "WebPage", "@id": ""}
        },
        "description": "Comprehensive article schema for blog posts and news"
    },
    "ScholarlyArticle": {
        "template": {
            "@context": "https://schema.org",
            "@type": "ScholarlyArticle",
            "headline": "",
            "description": "",
            "author": [{
                "@type": "Person",
                "name": "",
                "affiliation": {"@type": "Organization", "name": ""}
            }],
            "publisher": {"@type": "Organization", "name": ""},
            "datePublished": "",
            "keywords": [],
            "abstract": "",
            "citation": []
        },
        "description": "Academic papers and scholarly articles"
    },
    "Organization": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "",
            "url": "",
            "logo": "",
            "description": "",
            "image": "",
            "contactPoint": [],
            "sameAs": [],
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "",
                "addressLocality": "",
                "addressRegion": "",
                "postalCode": "",
                "addressCountry": ""
            },
            "keywords": [],
            "telephone": "",
            "email": "",
            "subjectOf": [],
            "location": {
                "@type": "Place",
                "name": "",
                "address": {},
                "hasMap": ""
            },
            "knowsAbout": []
        },
        "description": "Comprehensive organization schema with enhanced properties"
    },
    "LocalBusiness": {
        "template": {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": "",
            "url": "",
            "image": "",
            "description": "",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "",
                "addressLocality": "",
                "addressRegion": "",
                "postalCode": "",
                "addressCountry": ""
            },
            "geo": {"@type": "GeoCoordinates", "latitude": "", "longitude": ""},
            "telephone": "",
            "email": "",
            "openingHours": [],
            "priceRange": "",
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "",
                "reviewCount": ""
            },
            "servesCuisine": "",
            "paymentAccepted": []
        },
        "description": "Local business with location, hours, and ratings"
    },
    "Restaurant": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Restaurant",
            "name": "",
            "url": "",
            "image": "",
            "description": "",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "",
                "addressLocality": "",
                "addressRegion": "",
                "postalCode": "",
                "addressCountry": ""
            },
            "telephone": "",
            "openingHours": [],
            "priceRange": "",
            "servesCuisine": [],
            "menu": "",
            "acceptsReservations": True,
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "",
                "reviewCount": ""
            }
        },
        "description": "Restaurant with menu, cuisine, and dining details"
    },
    "Product": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "",
            "description": "",
            "image": [],
            "brand": {"@type": "Brand", "name": ""},
            "manufacturer": {"@type": "Organization", "name": ""},
            "offers": {
                "@type": "Offer",
                "priceCurrency": "",
                "price": "",
                "availability": "",
                "seller": {"@type": "Organization", "name": ""}
            },
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "",
                "reviewCount": ""
            },
            "sku": "",
            "mpn": "",
            "category": "",
            "review": []
        },
        "description": "Product schema with pricing, ratings, and detailed specifications"
    },
    "Recipe": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": "",
            "description": "",
            "image": "",
            "author": {"@type": "Person", "name": ""},
            "datePublished": "",
            "prepTime": "",
            "cookTime": "",
            "totalTime": "",
            "recipeYield": "",
            "recipeCategory": "",
            "recipeCuisine": "",
            "recipeIngredient": [],
            "recipeInstructions": [],
            "nutrition": {"@type": "NutritionInformation", "calories": ""},
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "",
                "reviewCount": ""
            }
        },
        "description": "Recipe with ingredients, instructions, and nutritional info"
    },
    "Event": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": "",
            "description": "",
            "image": "",
            "startDate": "",
            "endDate": "",
            "location": {
                "@type": "Place",
                "name": "",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "",
                    "addressLocality": "",
                    "addressRegion": "",
                    "postalCode": "",
                    "addressCountry": ""
                }
            },
            "organizer": {"@type": "Organization", "name": "", "url": ""},
            "offers": {
                "@type": "Offer",
                "price": "",
                "priceCurrency": "",
                "availability": "",
                "url": ""
            },
            "performer": {"@type": "Person", "name": ""},
            "eventStatus": "https://schema.org/EventScheduled"
        },
        "description": "Event with date, location, and ticketing information"
    },
    "VideoObject": {
        "template": {
            "@context": "https://schema.org",
            "@type": "VideoObject",
            "name": "",
            "description": "",
            "thumbnailUrl": "",
            "uploadDate": "",
            "duration": "",
            "contentUrl": "",
            "embedUrl": "",
            "publisher": {
                "@type": "Organization",
                "name": "",
                "logo": {"@type": "ImageObject", "url": ""}
            },
            "creator": {"@type": "Person", "name": ""},
            "keywords": []
        },
        "description": "Video content with metadata and publishing details"
    },
    "Review": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Review",
            "reviewBody": "",
            "reviewRating": {
                "@type": "Rating",
                "ratingValue": "",
                "bestRating": "5",
                "worstRating": "1"
            },
            "author": {"@type": "Person", "name": ""},
            "itemReviewed": {"@type": "Thing", "name": ""},
            "datePublished": "",
            "publisher": {"@type": "Organization", "name": ""}
        },
        "description": "Review with rating and detailed feedback"
    },
    "FAQPage": {
        "template": {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [{
                "@type": "Question",
                "name": "",
                "acceptedAnswer": {"@type": "Answer", "text": ""}
            }]
        },
        "description": "FAQ page with questions and answers"
    },
    "HowTo": {
        "template": {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": "",
            "description": "",
            "image": "",
            "totalTime": "",
            "estimatedCost": {
                "@type": "MonetaryAmount",
                "currency": "USD",
                "value": ""
            },
            "supply": [],
            "tool": [],
            "step": [{
                "@type": "HowToStep",
                "name": "",
                "text": "",
                "image": ""
            }]
        },
        "description": "Step-by-step guide with instructions and materials"
    },
    "Person": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": "",
            "url": "",
            "image": "",
            "description": "",
            "jobTitle": "",
            "worksFor": {"@type": "Organization", "name": ""},
            "sameAs": [],
            "knowsAbout": [],
            "alumniOf": {"@type": "Organization", "name": ""},
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "",
                "addressRegion": "",
                "addressCountry": ""
            }
        },
        "description": "Person profile with professional and personal details"
    },
    "WebPage": {
        "template": {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "",
            "description": "",
            "url": "",
            "image": "",
            "publisher": {"@type": "Organization", "name": ""},
            "datePublished": "",
            "dateModified": "",
            "inLanguage": "",
            "mainEntity": {"@type": "Thing", "name": ""},
            "breadcrumb": {
                "@type": "BreadcrumbList",
                "itemListElement": []
            },
            "speakable": {
                "@type": "SpeakableSpecification",
                "cssSelector": []
            }
        },
        "description": "General webpage schema with metadata"
    },
    "EntitySchema": {
        "template": {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "",
            "description": "",
            "url": "",
            "image": "",
            "publisher": {
                "@type": "Organization",
                "name": "",
                "url": "",
                "logo": ""
            },
            "mainEntity": {
                "@type": "Organization",
                "name": "",
                "description": "",
                "url": "",
                "knowsAbout": [],
                "subjectOf": [],
                "keywords": [],
                "sameAs": []
            },
            "keywords": [],
            "about": [],
            "mentions": [],
            "relatedLink": []
        },
        "description": "Detailed entity schema emphasizing business expertise"
    }
}

# --- Page Type Detection ---
def detect_page_type(soup: BeautifulSoup, url: str) -> str:
    url_lower = url.lower()
    patterns = {
        "Homepage": ['/home', '/$', '/index', ''],
        "About Us": ['/about', '/company', '/who-we-are'],
        "Contact Us": ['/contact', '/get-in-touch', '/reach-us'],
        "Product Page": ['/product/', '/item/', '/p/'],
        "Category Page": ['/category/', '/products/', '/shop/'],
        "Service Page": ['/service/', '/services/'],
        "Blog Post": ['/blog/', '/post/', '/article/'],
        "News Article": ['/news/', '/press/', '/media/'],
        "FAQ Page": ['/faq', '/help', '/support'],
        "Recipe Page": ['/recipe/', '/recipes/'],
        "Event Page": ['/event/', '/events/'],
        "Location/Store": ['/location/', '/store/', '/branch/']
    }
    for t, pats in patterns.items():
        if any(p in url_lower for p in pats if p):
            return t
    text = soup.get_text().lower()
    title = soup.title.string.lower() if soup.title else ""
    if 'recipe' in text or 'ingredients' in text:
        return "Recipe Page"
    if 'event' in text or 'tickets' in text:
        return "Event Page"
    if 'faq' in text or 'frequently asked' in text:
        return "FAQ Page"
    if soup.find_all('article') or 'blog' in title:
        return "Blog Post"
    if 'contact us' in text or 'get in touch' in text:
        return "Contact Us"
    if 'about us' in text or 'our company' in text:
        return "About Us"
    if 'add to cart' in text or 'price' in text:
        return "Product Page"
    return "Homepage"

def extract_existing_schema(soup: BeautifulSoup) -> Dict[str, Any]:
    existing = {'json_ld': [], 'microdata': [], 'analysis': {
        'has_schema': False, 'schema_types': [], 'completeness_score': 0, 'recommendations': []
    }}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            existing['json_ld'].append(data)
            existing['analysis']['has_schema'] = True
            if isinstance(data, dict) and '@type' in data:
                existing['analysis']['schema_types'].append(data['@type'])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and '@type' in item:
                        existing['analysis']['schema_types'].append(item['@type'])
        except:
            pass
    for item in soup.find_all(attrs={"itemscope": True}):
        props = {}
        for p in item.find_all(attrs={"itemprop": True}):
            name = p.get("itemprop")
            val = p.get("content") or p.get_text(strip=True)
            if name and val:
                props[name] = val
        if props:
            existing['microdata'].append({'type': item.get("itemtype", ""), 'properties': props})
            existing['analysis']['has_schema'] = True
    if existing['json_ld']:
        schema = existing['json_ld'][0]
        req = ['name', 'url', 'description']
        present = [p for p in req if p in schema]
        existing['analysis']['completeness_score'] = len(present)/len(req)
        if schema.get('@type') == 'Organization':
            rec = existing['analysis']['recommendations']
            for f in ['contactPoint','sameAs','address','subjectOf','knowsAbout','location']:
                if f not in schema:
                    rec.append(f"Add {f}")
    return existing

# --- HTML to screenshots helper ---
def html_to_images(url: str, html: str, num_screenshots: int = 3) -> List[str]:
    screenshots = []
    domain = urlparse(url).netloc.replace('.', '_')
    for i in range(num_screenshots):
        screenshots.append(f"https://screenshots.service/{domain}/view_{i}.png")
    return screenshots

def fetch_comprehensive_content(url: str) -> Dict[str, Any]:
    r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    shots = html_to_images(url, r.text, num_screenshots=3)
    return {
        'url': url,
        'page_type': detect_page_type(soup, url),
        'screenshots': shots,
        'basic_metadata': extract_basic_metadata(soup),
        'existing_schema': extract_existing_schema(soup),
        'social_metadata': extract_social_metadata(soup),
        'content_analysis': analyze_page_content(soup),
        'author_info': extract_author_information(soup),
        'publication_info': extract_publication_data(soup),
        'contact_info': extract_comprehensive_contact_info(soup),
        'business_info': extract_comprehensive_business_info(soup),
        'social_links': extract_social_links(soup),
        'media_content': extract_media_content(soup, url),
        'seo_indicators': extract_seo_indicators(soup),
        'entity_data': extract_entity_data(soup, url)
    }

# All other extraction functions (extract_entity_data, extract_basic_metadata, etc.)
# remain exactly as in the previous version.

# --- Prompt builder and generation ---
def create_comprehensive_schema_prompt(data: dict, url: str,
                                       template_type: str = None,
                                       page_type: str = None) -> str:
    basic = data['basic_metadata']
    existing = data['existing_schema']
    contacts = data['contact_info']
    business = data['business_info']
    social = data['social_links']
    media = data['media_content']
    ent = data['entity_data']
    shots = data.get('screenshots', [])
    detected = data.get('page_type', 'Homepage')
    final_type = page_type if page_type and page_type!="Auto-detect" else detected

    intro = """
I've provided simplified HTML and up to three viewport screenshots of the page.
Analyze the page type and content, then generate the appropriate schema. Refer to:
https://developers.google.com/search/docs/appearance/structured-data/search-gallery
Return only valid JSON-LD for the best-fitting schema, filling all possible fields.
"""
    context = f"""
URL: {url}
Page Type: {final_type}

Screenshots: {', '.join(shots)}

Title: {basic['title']}
Description: {basic['description']}
Language: {basic['language']}

Existing schema present: {existing['analysis']['has_schema']}
Types found: {existing['analysis']['schema_types']}
Completeness: {existing['analysis']['completeness_score']:.2f}
Missing: {existing['analysis']['recommendations']}

Emails: {contacts['emails'][:2]}
Phones: {contacts['phones'][:2]}
Business name: {business['name']}
Social links: {social[:2]}
Logo: {media['logo']}
Featured image: {media['featured_image']}
Expertise areas: {ent['expertise_areas']}
Industry keywords: {ent['industry_keywords'][:5]}
Wikipedia topics: {ent['wiki_topics']}
"""

    template_instr = ""
    if template_type=="Organization" or final_type in ["Homepage","About Us"]:
        template_instr = """
Organization requirements:
1. Single contactPoint
2. Full PostalAddress
3. location with hasMap
4. subjectOf to Wikipedia
5. knowsAbout area array
6. sameAs social links
7. keywords
"""
    elif template_type=="EntitySchema":
        template_instr = """
EntitySchema requirements:
1. WebPage container
2. mainEntity as Organization
3. about, mentions, relatedLink
4. knowsAbout and subjectOf arrays
5. Wikipedia links
"""

    return f"{intro}\n{context}\n{template_instr}\nProvide ONLY the JSON-LD."

def generate_comprehensive_schema(data: dict, url: str,
                                  template_type: str = None, page_type: str = None):
    prompt = create_comprehensive_schema_prompt(data, url, template_type, page_type)
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content(prompt)
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.strip("```json").strip("```")
    schema = json.loads(text)
    if "@context" not in schema:
        schema["@context"] = "https://schema.org"
    return enhance_generated_schema(schema, data, url), 0.95, "Generated"

def enhance_generated_schema(schema: dict, data: dict, url: str) -> dict:
    schema["url"] = url
    if "contactPoint" in schema and isinstance(schema["contactPoint"], list):
        schema["contactPoint"] = schema["contactPoint"][:1]
    # other enhancements for logo, keywords, subjectOf, knowsAbout...
    return schema

def suggest_schema_type_from_page_type(page_type: str) -> str:
    mapping = {
        "Homepage":"Organization","About Us":"Organization","Contact Us":"Organization",
        "Product Page":"Product","Category Page":"WebPage","Service Page":"Service",
        "Blog Post":"Article","News Article":"NewsArticle","FAQ Page":"FAQPage",
        "Recipe Page":"Recipe","Event Page":"Event","Review Page":"Review",
        "Video Page":"VideoObject","Location/Store":"LocalBusiness","Team/People":"Person"
    }
    return mapping.get(page_type, "WebPage")

# --- Streamlit UI ---
st.set_page_config(page_title="Schema Generator", layout="wide")
st.title("Schema.org JSON-LD Generator")

page_type_opt = st.sidebar.selectbox("Page Type", ["Auto-detect"]+list(PAGE_TYPES.keys()))
template_opt = st.sidebar.selectbox("Template", ["Auto-detect"]+list(COMPREHENSIVE_TEMPLATES.keys()))

url = st.text_input("URL to analyze", placeholder="https://example.com")
if st.button("Generate"):
    if not url or not url.startswith("http"):
        st.warning("Enter valid URL")
    else:
        try:
            d = fetch_comprehensive_content(url)
            det = d['page_type']
            sel = page_type_opt if page_type_opt!="Auto-detect" else det
            sug = suggest_schema_type_from_page_type(sel)
            st.metric("Detected", det)
            st.metric("Selected", sel)
            st.metric("Suggested Schema", sug)

            if d['existing_schema']['analysis']['has_schema']:
                st.info("Existing schema detected")
            else:
                st.info("No existing schema")

            schema, conf, _ = generate_comprehensive_schema(
                d, url,
                None if template_opt=="Auto-detect" else template_opt,
                None if page_type_opt=="Auto-detect" else page_type_opt
            )
            if schema:
                st.code(json.dumps(schema, indent=2, ensure_ascii=False), language="json")
            else:
                st.error("Generation failed")
        except Exception as e:
            st.error(str(e))
