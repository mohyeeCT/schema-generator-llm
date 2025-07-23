import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import re
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Any

# Import Schema.org models (assuming you have this package)
from msgspec_schemaorg.models import (
    Article, WebPage, Product, Event, Organization, Person, Place,
    CreativeWork, Thing, LocalBusiness, Service, Recipe, Review,
    ImageObject, VideoObject, NewsArticle, BlogPosting, ContactPoint,
    PostalAddress, ScholarlyArticle, Restaurant, FAQPage, HowTo
)
from msgspec_schemaorg.utils import parse_iso8601

# Configure your Gemini API key here or in Streamlit secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)

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

COMPREHENSIVE_TEMPLATES = {
    "Article": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": "",
            "description": "",
            "image": "",
            "author": {"@type": "Person", "name": "", "url": ""},
            "publisher": {"@type": "Organization", "name": "", "logo": {"@type": "ImageObject", "url": ""}},
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
            "address": {"@type": "PostalAddress", "streetAddress": "", "addressLocality": "", "addressRegion": "", "postalCode": "", "addressCountry": ""},
            "keywords": [],
            "telephone": "",
            "email": "",
            "subjectOf": [],
            "location": {"@type": "Place", "name": "", "address": {}, "hasMap": ""},
            "knowsAbout": []
        },
        "description": "Comprehensive organization schema with enhanced properties"
    },
    # Other templates can be added here as needed
}

def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
    link = soup.select_one("link[rel=canonical]")
    return link.get("href") if link else None

def extract_basic_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    description = ""
    for sel in ('meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]'):
        tag = soup.select_one(sel)
        if tag and tag.get("content"):
            description = tag["content"].strip()
            break
    keywords = []
    ktag = soup.find("meta", {"name": "keywords"})
    if ktag and ktag.get("content"):
        keywords = [k.strip() for k in ktag["content"].split(",")]
    lang = None
    html_tag = soup.find("html", lang=True)
    if html_tag:
        lang = html_tag["lang"]
    return {"title": title, "description": description, "keywords": keywords, "language": lang, "canonical_url": extract_canonical_url(soup)}

def extract_social_metadata(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    out = {"og": {}, "twitter": {}}
    for tag in soup.find_all("meta", property=lambda p: p and p.startswith("og:")):
        prop = tag["property"][3:]
        out["og"][prop] = tag.get("content", "")
    for tag in soup.find_all("meta", attrs={"name": lambda n: n and n.startswith("twitter:")}):
        name = tag["name"][8:]
        out["twitter"][name] = tag.get("content", "")
    return out

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
        except Exception:
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
        existing['analysis']['completeness_score'] = len(present) / len(req)
        if schema.get('@type') == 'Organization':
            rec = existing['analysis']['recommendations']
            for f in ['contactPoint','sameAs','address','subjectOf','knowsAbout','location']:
                if f not in schema:
                    rec.append(f"Add {f}")
    return existing

def extract_comprehensive_contact_info(soup: BeautifulSoup) -> Dict[str, Any]:
    info = {"emails": [], "phones": [], "contact_points": []}
    text = soup.get_text()
    for a in soup.select('a[href^="mailto:"]'):
        email = a["href"].split("mailto:")[1].split("?")[0]
        if email not in info["emails"]:
            info["emails"].append(email)
    for e in re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text):
        if e not in info["emails"]:
            info["emails"].append(e)
    for a in soup.select('a[href^="tel:"]'):
        num = a["href"].split("tel:")[1]
        if num not in info["phones"]:
            info["phones"].append(num)
    for m in re.findall(r'\+?\d[\d\-\s]{7,}\d', text):
        if m not in info["phones"]:
            info["phones"].append(m)
    for p in info["phones"]:
        info["contact_points"].append({"@type": "ContactPoint", "telephone": p, "contactType": "customer service"})
    return info

def extract_comprehensive_business_info(soup: BeautifulSoup) -> Dict[str, Any]:
    biz = {"name": None, "address": {}}
    for sel in ('[itemprop=name]', 'h1', '.company-name', '.business-name'):
        e = soup.select_one(sel)
        if e and e.get_text(strip=True):
            biz["name"] = e.get_text(strip=True)
            break
    addr_selectors = {
        "street": ['[itemprop=streetAddress]'],
        "city": ['[itemprop=addressLocality]'],
        "region": ['[itemprop=addressRegion]'],
        "postalCode": ['[itemprop=postalCode]'],
        "country": ['[itemprop=addressCountry]']
    }
    for field, sels in addr_selectors.items():
        for sel in sels:
            e = soup.select_one(sel)
            if e and e.get_text(strip=True):
                biz["address"][field] = e.get_text(strip=True)
                break
    return biz

def extract_social_links(soup: BeautifulSoup) -> List[str]:
    domains = ["facebook.com","twitter.com","linkedin.com","instagram.com","youtube.com"]
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        for d in domains:
            if d in href and href not in out:
                out.append(href)
    return out

def analyze_page_content(soup: BeautifulSoup) -> Dict[str, Any]:
    tmp = BeautifulSoup(str(soup), "html.parser")
    for tag in tmp.select("nav, footer, header, aside, script, style"):
        tag.decompose()
    main = tmp.select_one("main, article") or tmp.body
    txt = main.get_text(" ", strip=True)[:3000]
    return {"main_text": txt, "word_count": len(txt.split())}

def extract_author_information(soup: BeautifulSoup) -> Dict[str, List[str]]:
    authors = set()
    for sel in ('[rel=author]', '.author', '[itemprop=author]'):
        for e in soup.select(sel):
            text = e.get_text(strip=True)
            if text:
                authors.add(text)
    return {"authors": list(authors)}

def extract_publication_data(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    pub, mod = None, None
    for e in soup.select("time[datetime], meta[property='article:published_time']"):
        dt = e.get("datetime") or e.get("content")
        if dt and not pub:
            pub = dt
    for e in soup.select("meta[property='article:modified_time']"):
        dt = e.get("content")
        if dt and not mod:
            mod = dt
    return {"published_date": pub, "modified_date": mod}

def extract_media_content(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    images, logo = [], None
    for img in soup.find_all("img", src=True):
        src = urljoin(base_url, img["src"])
        alt = img.get("alt","").lower()
        if "logo" in alt:
            logo = src
        else:
            images.append(src)
    og = soup.select_one("meta[property='og:image']")
    featured = og.get("content") if og else None
    return {"images": images, "featured_image": featured, "logo": logo}

def extract_seo_indicators(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    c = soup.select_one("link[rel=canonical]")
    return {"canonical_url": c.get("href") if c else None}

def extract_entity_data(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    text = soup.get_text().lower()
    areas, kws, wiki = [], [], []
    terms = {"Technology": ["software","innovation"], "Finance": ["bank","investment"]}
    for k, v in terms.items():
        if any(t in text for t in v):
            areas.append(k)
            wiki.append(k.replace(" ", "_"))
    meta = soup.find("meta", {"name":"keywords"})
    if meta and meta.get("content"):
        kws = [x.strip() for x in meta["content"].split(",")]
    return {"expertise_areas": areas, "industry_keywords": kws, "wiki_topics": wiki}

def html_to_images(url: str, html: str, num_screenshots: int = 3) -> List[str]:
    screenshots = []
    domain = urlparse(url).netloc.replace(".", "_")
    for i in range(num_screenshots):
        screenshots.append(f"https://screenshots.service/{domain}/view_{i}.png")
    return screenshots

def detect_page_type(soup: BeautifulSoup, url: str) -> str:
    url_l = url.lower()
    patterns = {
        "Homepage": ['/home','/index',''],
        "About Us": ['/about','/company'],
        "Contact Us": ['/contact','/reach-us'],
        "Product Page": ['/product/','/item/'],
        "Blog Post": ['/blog/','/article/']
    }
    for t, pats in patterns.items():
        if any(p in url_l for p in pats if p):
            return t
    text = soup.get_text().lower()
    if 'faq' in text:
        return "FAQ Page"
    if 'recipe' in text:
        return "Recipe Page"
    return "Homepage"

def fetch_comprehensive_content(url: str) -> Dict[str, Any]:
    r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    shots = html_to_images(url, r.text, 3)
    return {
        "url": url,
        "page_type": detect_page_type(soup, url),
        "screenshots": shots,
        "basic_metadata": extract_basic_metadata(soup),
        "existing_schema": extract_existing_schema(soup),
        "social_metadata": extract_social_metadata(soup),
        "content_analysis": analyze_page_content(soup),
        "author_info": extract_author_information(soup),
        "publication_info": extract_publication_data(soup),
        "contact_info": extract_comprehensive_contact_info(soup),
        "business_info": extract_comprehensive_business_info(soup),
        "social_links": extract_social_links(soup),
        "media_content": extract_media_content(soup, url),
        "seo_indicators": extract_seo_indicators(soup),
        "entity_data": extract_entity_data(soup, url)
    }

def create_comprehensive_schema_prompt(data: dict, url: str,
                                       template_type: str = None,
                                       page_type: str = None) -> str:
    basic = data["basic_metadata"]
    existing = data["existing_schema"]
    contacts = data["contact_info"]
    business = data["business_info"]
    social = data["social_links"]
    media = data["media_content"]
    ent = data["entity_data"]
    shots = data.get("screenshots", [])
    detected = data.get("page_type", "Homepage")
    final = page_type if page_type and page_type!="Auto-detect" else detected

    intro = """
I've provided simplified HTML main text and three viewport screenshots.
Analyze the page type and content, then generate the appropriate schema.
Refer to the Google search gallery documentation for schema types.
Return only valid JSON-LD, filling all possible fields.
"""

    context = f"""
URL: {url}
Page Type: {final}
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
Keywords: {ent['industry_keywords'][:5]}
Wikipedia topics: {ent['wiki_topics']}
"""

    instructions = ""
    if template_type=="Organization" or final in ["Homepage","About Us"]:
        instructions = """
Organization schema requirements:
1. Single contactPoint
2. Full PostalAddress
3. location with hasMap
4. subjectOf linking to Wikipedia
5. knowsAbout expertise areas
6. sameAs social links
7. keywords array
"""
    return f"{intro}\n{context}\n{instructions}\nProvide ONLY JSON-LD."

def generate_comprehensive_schema(data: dict, url: str,
                                  template_type: str = None, page_type: str = None):
    prompt = create_comprehensive_schema_prompt(data, url, template_type, page_type)
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content(prompt)
    text = resp.text.strip().lstrip("```json").rstrip("```")
    schema = json.loads(text)
    if "@context" not in schema:
        schema["@context"] = "https://schema.org"
    return enhance_generated_schema(schema, data, url), 0.95, "Generated"

def enhance_generated_schema(schema: dict, data: dict, url: str) -> dict:
    schema["url"] = url
    if "contactPoint" in schema and isinstance(schema["contactPoint"], list):
        schema["contactPoint"] = schema["contactPoint"][:1]
    # other enhancements can be added here
    return schema

def suggest_schema_type_from_page_type(page_type: str) -> str:
    mapping = {
        "Homepage": "Organization",
        "About Us": "Organization",
        "Contact Us": "Organization",
        "Product Page": "Product",
        "Blog Post": "Article",
        "FAQ Page": "FAQPage",
        "Recipe Page": "Recipe"
    }
    return mapping.get(page_type, "WebPage")

# Streamlit UI
st.set_page_config(page_title="Schema.org Generator", layout="wide")
st.title("Schema.org JSON-LD Generator")

pt_opt = st.sidebar.selectbox("Page Type", ["Auto-detect"]+list(PAGE_TYPES.keys()))
tpl_opt = st.sidebar.selectbox("Template", ["Auto-detect"]+list(COMPREHENSIVE_TEMPLATES.keys()))

url = st.text_input("Enter URL to analyze", placeholder="https://example.com")
if st.button("Generate Schema"):
    if not url.startswith("http"):
        st.warning("Enter a valid URL")
    else:
        try:
            data = fetch_comprehensive_content(url)
            det = data["page_type"]
            sel = pt_opt if pt_opt!="Auto-detect" else det
            sug = suggest_schema_type_from_page_type(sel)
            st.metric("Detected Type", det)
            st.metric("Selected Type", sel)
            st.metric("Suggested Schema", sug)

            schema, conf, _ = generate_comprehensive_schema(
                data, url,
                None if tpl_opt=="Auto-detect" else tpl_opt,
                None if pt_opt=="Auto-detect" else pt_opt
            )
            if schema:
                st.code(json.dumps(schema, indent=2, ensure_ascii=False), language="json")
            else:
                st.error("Schema generation failed")
        except Exception as e:
            st.error(str(e))
