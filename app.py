import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
from typing import Dict, List, Optional, Any

# --- Configuration ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U")
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
            "author": {"@type": "Person", "name": ""},
            "publisher": {"@type": "Organization", "name": "", "logo": {"@type": "ImageObject", "url": ""}},
            "datePublished": "",
            "dateModified": "",
            "url": "",
            "keywords": []
        },
        "description": "Article schema for blog posts and news"
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
            "location": {"@type": "Place", "name": "", "address": {}, "hasMap": ""},
            "knowsAbout": []
        },
        "description": "Comprehensive organization schema"
    },
    "LocalBusiness": {
        "template": {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": "",
            "url": "",
            "image": "",
            "description": "",
            "address": {"@type": "PostalAddress", "streetAddress": "", "addressLocality": "", "addressRegion": "", "postalCode": "", "addressCountry": ""},
            "geo": {"@type": "GeoCoordinates", "latitude": "", "longitude": ""},
            "telephone": "",
            "email": "",
            "openingHours": [],
            "priceRange": "",
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "", "reviewCount": ""}
        },
        "description": "Local business with location and ratings"
    },
    "Product": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "",
            "description": "",
            "image": [],
            "brand": {"@type": "Brand", "name": ""},
            "offers": {"@type": "Offer", "priceCurrency": "", "price": "", "availability": ""},
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "", "reviewCount": ""},
            "sku": "",
            "category": ""
        },
        "description": "Product schema with pricing and ratings"
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
            "recipeYield": "",
            "recipeIngredient": [],
            "recipeInstructions": []
        },
        "description": "Recipe with ingredients and instructions"
    },
    "Event": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": "",
            "description": "",
            "startDate": "",
            "endDate": "",
            "location": {"@type": "Place", "name": "", "address": {"@type": "PostalAddress"}},
            "organizer": {"@type": "Organization", "name": ""}
        },
        "description": "Event with date and location"
    },
    "EntitySchema": {
        "template": {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "",
            "description": "",
            "url": "",
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
            "about": []
        },
        "description": "Entity schema emphasizing business expertise"
    }
}

# --- Content Extraction Functions ---

def detect_page_type(soup: BeautifulSoup, url: str) -> str:
    """Detect page type based on URL and content"""
    url_lower = url.lower()
    
    url_patterns = {
        "Homepage": ['/', '/home', '/index'],
        "About Us": ['/about', '/company'],
        "Contact Us": ['/contact'],
        "Product Page": ['/product/', '/item/'],
        "Blog Post": ['/blog/', '/post/'],
        "News Article": ['/news/', '/press/'],
        "FAQ Page": ['/faq', '/help']
    }
    
    for page_type, patterns in url_patterns.items():
        if any(pattern in url_lower for pattern in patterns):
            return page_type
    
    page_text = soup.get_text().lower()
    if any(word in page_text for word in ['about us', 'our company']):
        return "About Us"
    elif any(word in page_text for word in ['contact us', 'get in touch']):
        return "Contact Us"
    
    return "Homepage"

def extract_existing_schema(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract existing schema markup"""
    existing_schemas = {
        'json_ld': [],
        'analysis': {
            'has_schema': False,
            'schema_types': [],
            'completeness_score': 0,
            'recommendations': []
        }
    }
    
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            existing_schemas['json_ld'].append(data)
            existing_schemas['analysis']['has_schema'] = True
            
            if isinstance(data, dict):
                schema_type = data.get('@type')
                if schema_type:
                    existing_schemas['analysis']['schema_types'].append(schema_type)
        except (json.JSONDecodeError, AttributeError):
            continue
    
    if existing_schemas['json_ld']:
        schema = existing_schemas['json_ld'][0]
        required_props = ['name', 'url', 'description']
        present_props = [prop for prop in required_props if prop in schema]
        existing_schemas['analysis']['completeness_score'] = len(present_props) / len(required_props)
        
        schema_type = schema.get('@type', '')
        if schema_type == 'Organization':
            if 'contactPoint' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add multi-department contact points")
            if 'sameAs' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add social media links")
            if 'subjectOf' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add subject matter expertise")
    
    return existing_schemas

def extract_basic_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract basic page metadata"""
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    
    description = ""
    desc_selectors = ['meta[name="description"]', 'meta[property="og:description"]']
    for selector in desc_selectors:
        desc_tag = soup.select_one(selector)
        if desc_tag and desc_tag.get("content"):
            description = desc_tag.get("content").strip()
            break
    
    keywords = []
    keywords_tag = soup.find("meta", {"name": "keywords"})
    if keywords_tag and keywords_tag.get("content"):
        keywords = [k.strip() for k in keywords_tag.get("content").split(",")]
    
    language = soup.get("lang") or "en"
    
    return {
        'title': title,
        'description': description,
        'keywords': keywords,
        'language': language
    }

def extract_contact_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract contact information"""
    contact_info = {'emails': [], 'phones': []}
    
    # Extract emails
    email_links = soup.find_all('a', href=lambda x: x and x.startswith('mailto:'))
    for link in email_links:
        email = link.get('href', '').replace('mailto:', '').split('?')[0]
        if email and email not in contact_info['emails']:
            contact_info['emails'].append(email)
    
    # Extract phones
    phone_links = soup.find_all('a', href=lambda x: x and x.startswith('tel:'))
    for link in phone_links:
        phone = link.get('href', '').replace('tel:', '')
        if phone and phone not in contact_info['phones']:
            contact_info['phones'].append(phone)
    
    # Extract from text using patterns
    page_text = soup.get_text()
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, page_text)
    for email in emails[:3]:  # Limit to 3
        if email not in contact_info['emails']:
            contact_info['emails'].append(email)
    
    return contact_info

def extract_business_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract business information"""
    business_data = {'name': None, 'address': {}}
    
    # Business name
    name_selectors = ['[itemprop="name"]', 'h1', '.company-name']
    for selector in name_selectors:
        elem = soup.select_one(selector)
        if elem:
            business_data['name'] = elem.get_text(strip=True)
            break
    
    # Address components
    address_selectors = {
        'street': ['[itemprop="streetAddress"]', '.street'],
        'city': ['[itemprop="addressLocality"]', '.city'],
        'state': ['[itemprop="addressRegion"]', '.state'],
        'postal_code': ['[itemprop="postalCode"]', '.zip'],
        'country': ['[itemprop="addressCountry"]', '.country']
    }
    
    for addr_type, selectors in address_selectors.items():
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                business_data['address'][addr_type] = elem.get_text(strip=True)
                break
    
    return business_data

def extract_social_links(soup: BeautifulSoup) -> List[str]:
    """Extract social media links"""
    social_links = []
    social_domains = ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'pinterest.com']
    
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        href = link.get('href', '')
        for domain in social_domains:
            if domain in href and href not in social_links:
                social_links.append(href)
                break
    
    return social_links

def extract_media_content(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    """Extract media content"""
    media_data = {'images': [], 'featured_image': None, 'logo': None}
    
    # Images
    for img in soup.find_all('img', src=True):
        src = urljoin(base_url, img.get('src'))
        if not any(tracker in src.lower() for tracker in ['webtraxs', 'analytics', 'tracking']):
            media_data['images'].append({'src': src, 'alt': img.get('alt', '')})
    
    # Featured image
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        media_data['featured_image'] = og_image.get('content')
    elif media_data['images']:
        media_data['featured_image'] = media_data['images'][0]['src']
    
    # Logo
    logo_selectors = ['.logo img', '[class*="logo"] img', 'img[alt*="logo"]']
    for selector in logo_selectors:
        logo_img = soup.select_one(selector)
        if logo_img and logo_img.get('src'):
            logo_url = urljoin(base_url, logo_img.get('src'))
            if not any(tracker in logo_url.lower() for tracker in ['webtraxs', 'analytics']):
                media_data['logo'] = logo_url
                break
    
    return media_data

def extract_entity_data(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract entity data for enhanced markup"""
    entity_data = {
        'expertise_areas': [],
        'industry_keywords': [],
        'wiki_topics': []
    }
    
    content_text = soup.get_text().lower()
    
    industry_terms = {
        'technology': ['software', 'digital', 'tech', 'innovation'],
        'manufacturing': ['precision', 'engineering', 'quality', 'production'],
        'hardware': ['hardware', 'industrial', 'architectural', 'mechanical'],
        'construction': ['construction', 'building', 'architecture', 'design']
    }
    
    wiki_topics = {
        'technology': ['Technology', 'Software', 'Innovation'],
        'manufacturing': ['Manufacturing', 'Engineering'],
        'hardware': ['Hardware', 'Industrial design'],
        'construction': ['Construction', 'Architecture']
    }
    
    for industry, terms in industry_terms.items():
        if any(term in content_text for term in terms):
            entity_data['expertise_areas'].append(industry.title())
            if industry in wiki_topics:
                entity_data['wiki_topics'].extend(wiki_topics[industry])
    
    # Extract keywords from meta tags
    meta_keywords = soup.find("meta", {"name": "keywords"})
    if meta_keywords and meta_keywords.get("content"):
        keywords = [k.strip() for k in meta_keywords.get("content").split(",")]
        entity_data['industry_keywords'].extend(keywords)
    
    return entity_data

def fetch_comprehensive_content(url: str) -> Dict[str, Any]:
    """Main content extraction function"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        content = {
            'url': url,
            'page_type': detect_page_type(soup, url),
            'basic_metadata': extract_basic_metadata(soup),
            'existing_schema': extract_existing_schema(soup),
            'contact_info': extract_contact_info(soup),
            'business_info': extract_business_info(soup),
            'social_links': extract_social_links(soup),
            'media_content': extract_media_content(soup, url),
            'entity_data': extract_entity_data(soup)
        }

        return content

    except Exception as e:
        raise Exception(f"Error fetching content: {e}")

# --- AI Generation Functions ---

def extract_json_from_text(text: str) -> str:
    """Extract valid JSON from text"""
    start_pos = text.find('{')
    if start_pos == -1:
        raise ValueError("No JSON object found")
    
    brace_count = 0
    end_pos = start_pos
    
    for i, char in enumerate(text[start_pos:], start_pos):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_pos = i + 1
                break
    
    return text[start_pos:end_pos]

def generate_comprehensive_schema(comprehensive_data: dict, url: str, template_type: str = None, page_type: str = None):
    """Generate comprehensive schema with robust error handling"""
    
    try:
        # Get base template first
        base_schema = get_base_template(comprehensive_data, template_type, page_type)
        
        # Try AI enhancement
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = create_schema_prompt(comprehensive_data, url, template_type, page_type)
            
            response = model.generate_content(prompt)
            
            if response.text:
                # Clean and parse response
                raw_text = response.text.strip()
                
                # Remove markdown formatting
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()
                
                # Extract JSON
                json_str = extract_json_from_text(raw_text)
                parsed_schema = json.loads(json_str)
                
                # Ensure required fields
                if "@context" not in parsed_schema:
                    parsed_schema["@context"] = "https://schema.org"
                
                # Enhance with extracted data
                enhanced_schema = enhance_schema_with_data(parsed_schema, comprehensive_data, url)
                return enhanced_schema, 0.95, "AI-enhanced schema generated successfully"
                
        except Exception as ai_error:
            st.warning(f"AI enhancement failed, using template-based generation: {str(ai_error)}")
        
        # Fallback to template-based enhancement
        enhanced_schema = enhance_template_with_data(base_schema, comprehensive_data, url)
        return enhanced_schema, 0.80, "Template-based schema generated successfully"
        
    except Exception as e:
        st.error(f"Schema generation failed: {e}")
        return None, 0.0, f"Generation failed: {str(e)}"

def get_base_template(comprehensive_data: dict, template_type: str = None, page_type: str = None):
    """Get appropriate base template"""
    detected_page_type = comprehensive_data.get('page_type', 'Homepage')
    final_page_type = page_type if page_type != "Auto-detect" else detected_page_type
    
    if template_type and template_type != "Auto-detect":
        schema_type = template_type
    else:
        schema_mapping = {
            "Homepage": "Organization",
            "About Us": "Organization", 
            "Contact Us": "Organization",
            "Product Page": "Product",
            "Blog Post": "Article",
            "Event Page": "Event",
            "Recipe Page": "Recipe"
        }
        schema_type = schema_mapping.get(final_page_type, "Organization")
    
    if schema_type in COMPREHENSIVE_TEMPLATES:
        return COMPREHENSIVE_TEMPLATES[schema_type]["template"].copy()
    else:
        return COMPREHENSIVE_TEMPLATES["Organization"]["template"].copy()

def enhance_template_with_data(base_schema: dict, comprehensive_data: dict, url: str):
    """Enhance template with extracted data"""
    basic_meta = comprehensive_data['basic_metadata']
    contact_info = comprehensive_data['contact_info']
    business_info = comprehensive_data['business_info']
    social_links = comprehensive_data['social_links']
    media_content = comprehensive_data['media_content']
    entity_data = comprehensive_data['entity_data']
    
    # Fill basic information
    base_schema["url"] = url
    base_schema["name"] = business_info.get('name') or basic_meta['title']
    base_schema["description"] = basic_meta['description']
    
    # Add media
    if media_content['logo']:
        base_schema["logo"] = media_content['logo']
    if media_content['featured_image']:
        base_schema["image"] = media_content['featured_image']
    
    # Add contact points for organizations
    if base_schema.get("@type") == "Organization" and (contact_info['emails'] or contact_info['phones']):
        contact_points = []
        
        for i, email in enumerate(contact_info['emails'][:3]):
            contact_type = "sales" if "sales" in email.lower() else "customer service"
            contact_point = {
                "@type": "ContactPoint",
                "contactType": contact_type,
                "email": email,
                "areaServed": "US",
                "availableLanguage": "English"
            }
            
            if i < len(contact_info['phones']):
                contact_point["telephone"] = contact_info['phones'][i]
            
            contact_points.append(contact_point)
        
        # Add remaining phones
        for i in range(len(contact_info['emails']), len(contact_info['phones'])):
            if i < 3:  # Limit total contact points
                contact_points.append({
                    "@type": "ContactPoint",
                    "contactType": "customer service",
                    "telephone": contact_info['phones'][i],
                    "areaServed": "US",
                    "availableLanguage": "English"
                })
        
        if contact_points:
            base_schema["contactPoint"] = contact_points
    
    # Add social links
    if social_links:
        base_schema["sameAs"] = social_links[:6]
    
    # Add address for organizations
    if base_schema.get("@type") == "Organization" and business_info['address']:
        address = {"@type": "PostalAddress"}
        
        addr_mapping = {
            'street': 'streetAddress',
            'city': 'addressLocality',
            'state': 'addressRegion',
            'postal_code': 'postalCode',
            'country': 'addressCountry'
        }
        
        for key, schema_key in addr_mapping.items():
            if key in business_info['address']:
                address[schema_key] = business_info['address'][key]
        
        if len(address) > 1:
            base_schema["address"] = address
    
    # Add keywords
    all_keywords = set()
    if basic_meta['keywords']:
        all_keywords.update(basic_meta['keywords'])
    if entity_data['industry_keywords']:
        all_keywords.update(entity_data['industry_keywords'][:10])
    
    if all_keywords:
        base_schema["keywords"] = list(all_keywords)[:15]
    
    # Add entity enhancements for organizations
    if base_schema.get("@type") == "Organization":
        if entity_data['expertise_areas']:
            base_schema["knowsAbout"] = entity_data['expertise_areas']
        
        if entity_data['wiki_topics']:
            subject_of = []
            for topic in entity_data['wiki_topics'][:4]:
                subject_of.append({
                    "@type": "CreativeWork",
                    "url": f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}",
                    "description": f"{topic} represents a key area of expertise."
                })
            base_schema["subjectOf"] = subject_of
    
    # Clean up empty values
    return {k: v for k, v in base_schema.items() if v not in ["", None, [], {}]}

def enhance_schema_with_data(schema: dict, comprehensive_data: dict, url: str) -> dict:
    """Enhance AI-generated schema with extracted data"""
    # Ensure URL is correct
    schema["url"] = url
    
    # Add missing contact points if needed
    if schema.get("@type") == "Organization" and "contactPoint" not in schema:
        contact_info = comprehensive_data['contact_info']
        if contact_info['emails'] or contact_info['phones']:
            schema = enhance_template_with_data(schema, comprehensive_data, url)
    
    return schema

def create_schema_prompt(comprehensive_data: dict, url: str, template_type: str = None, page_type: str = None) -> str:
    """Create prompt for schema generation"""
    basic_meta = comprehensive_data['basic_metadata']
    contact_info = comprehensive_data['contact_info']
    business_info = comprehensive_data['business_info']
    social_links = comprehensive_data['social_links']
    entity_data = comprehensive_data['entity_data']
    
    context = f"""
URL: {url}
Page Type: {page_type or comprehensive_data.get('page_type', 'Homepage')}
Title: {basic_meta['title']}
Description: {basic_meta['description']}
Business Name: {business_info.get('name', 'N/A')}
Emails: {', '.join(contact_info['emails'][:2])}
Phones: {', '.join(contact_info['phones'][:2])}
Social Links: {', '.join(social_links[:3])}
Expertise Areas: {', '.join(entity_data['expertise_areas'])}
"""

    prompt = f"""Create comprehensive Schema.org JSON-LD markup for this website.

{context}

Requirements:
1. Use appropriate schema type based on page content
2. Include multiple contactPoint objects with different departments if contact info available
3. Add sameAs array with social media links
4. Include subjectOf array with Wikipedia links for expertise areas
5. Add comprehensive keywords array
6. Use proper nested structures for address, contact points, etc.

Return ONLY valid JSON-LD markup. Start with {{ and end with }}. No explanations."""

    return prompt

# --- Streamlit UI ---
st.set_page_config(page_title="Comprehensive Schema.org Generator", page_icon="🔗", layout="wide")

st.title(" Schema.org JSON-LD Generator")

# Sidebar Configuration
st.sidebar.header(" Configuration")

# Page Type Selection
page_type_option = st.sidebar.selectbox(
    "Select page type:",
    ["Auto-detect"] + list(PAGE_TYPES.keys()),
    help="Choose page type or let AI auto-detect"
)

# Schema Template Selection
template_option = st.sidebar.selectbox(
    "Choose schema template:",
    ["Auto-detect"] + list(COMPREHENSIVE_TEMPLATES.keys()),
    help="Select template or let AI choose based on content"
)

if template_option != "Auto-detect":
    with st.sidebar.expander(" View Template"):
        st.json(COMPREHENSIVE_TEMPLATES[template_option]["template"])

# Main Input
url = st.text_input("Enter URL to analyze:", placeholder="https://www.example.com")

if st.button(" Generate Comprehensive Schema", type="primary"):
    if not url:
        st.warning("Please enter a URL")
    elif not url.startswith(("http://", "https://")):
        st.warning("Please enter a valid URL starting with http:// or https://")
    else:
        with st.spinner("Extracting comprehensive content..."):
            try:
                comprehensive_data = fetch_comprehensive_content(url)
                
                # Display page type detection
                detected_page_type = comprehensive_data['page_type']
                final_page_type = page_type_option if page_type_option != "Auto-detect" else detected_page_type
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Detected Page Type", detected_page_type)
                with col2:
                    st.metric("Selected Page Type", final_page_type)
                with col3:
                    st.metric("Template", template_option)
                
                # Display existing schema analysis
                existing_schema = comprehensive_data['existing_schema']
                if existing_schema['analysis']['has_schema']:
                    st.success(" Existing Schema Found")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Schema Types", len(existing_schema['analysis']['schema_types']))
                    with col2:
                        st.metric("Completeness", f"{existing_schema['analysis']['completeness_score']:.0%}")
                    
                    if existing_schema['analysis']['recommendations']:
                        st.info("💡 **Enhancement Opportunities:** " + "; ".join(existing_schema['analysis']['recommendations']))
                else:
                    st.info("ℹ️ No existing schema found - generating from scratch")
                
                # Content analysis
                st.subheader("Content Analysis")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Contact Methods", 
                             len(comprehensive_data['contact_info']['emails']) + 
                             len(comprehensive_data['contact_info']['phones']))
                
                with col2:
                    st.metric("Social Links", len(comprehensive_data['social_links']))
                
                with col3:
                    st.metric("Images Found", len(comprehensive_data['media_content']['images']))
                
                with col4:
                    expertise_count = len(comprehensive_data['entity_data']['expertise_areas'])
                    st.metric("Expertise Areas", expertise_count)
                
                # Entity data insights
                entity_data = comprehensive_data['entity_data']
                if entity_data['expertise_areas']:
                    st.subheader(" Entity Intelligence")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("** Detected Expertise:**")
                        for area in entity_data['expertise_areas']:
                            st.write(f"• {area}")
                    
                    with col2:
                        if entity_data['industry_keywords']:
                            st.write("**🔑 Industry Keywords:**")
                            st.write(", ".join(entity_data['industry_keywords'][:8]))
                
                # Generate schema
                st.subheader(" AI Schema Generation")
                with st.spinner("Generating comprehensive schema..."):
                    final_template_type = template_option if template_option != "Auto-detect" else None
                    final_page_type_param = page_type_option if page_type_option != "Auto-detect" else None
                    
                    schema_data, confidence, reasoning = generate_comprehensive_schema(
                        comprehensive_data, url, final_template_type, final_page_type_param
                    )
                    
                    if schema_data:
                        # Display results
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.success(f" Schema Generated - Confidence: {confidence:.0%}")
                            st.caption(reasoning)
                        
                        with col2:
                            schema_type = schema_data.get('@type', 'Unknown')
                            st.metric("Generated Schema Type", schema_type)
                        
                        # Main schema output
                        st.subheader("Generated Schema.org JSON-LD")
                        
                        # Format and display JSON
                        formatted_json = json.dumps(schema_data, indent=2, ensure_ascii=False)
                        st.code(formatted_json, language="json")
                        
                        # Schema quality analysis
                        st.subheader("Schema Quality Analysis")
                        
                        analysis_cols = st.columns(4)
                        
                        with analysis_cols[0]:
                            st.write("**Core Validation:**")
                            core_checks = {
                                "Has @context": "@context" in schema_data,
                                "Has @type": "@type" in schema_data,
                                "Has name": "name" in schema_data,
                                "Has URL": "url" in schema_data,
                                "Has description": "description" in schema_data
                            }
                            
                            for check, passed in core_checks.items():
                                st.write(f"{'✅' if passed else '❌'} {check}")
                        
                        with analysis_cols[1]:
                            st.write("**Contact Features:**")
                            contact_checks = {
                                "Multi-department contacts": "contactPoint" in schema_data and len(schema_data.get("contactPoint", [])) > 1,
                                "Structured address": "address" in schema_data and isinstance(schema_data.get("address"), dict),
                                "Social media links": "sameAs" in schema_data and len(schema_data.get("sameAs", [])) > 0,
                                "Location data": "location" in schema_data
                            }
                            
                            for check, passed in contact_checks.items():
                                st.write(f"{'✅' if passed else '❌'} {check}")
                        
                        with analysis_cols[2]:
                            st.write("**Entity Features:**")
                            entity_checks = {
                                "Knowledge areas": "knowsAbout" in schema_data,
                                "Subject expertise": "subjectOf" in schema_data,
                                "Industry keywords": "keywords" in schema_data and len(schema_data.get("keywords", [])) > 3,
                                "Wikipedia links": "subjectOf" in schema_data and any("wikipedia.org" in str(item) for item in schema_data.get("subjectOf", []))
                            }
                            
                            for check, passed in entity_checks.items():
                                st.write(f"{'✅' if passed else '❌'} {check}")
                        
                        with analysis_cols[3]:
                            st.write("**Schema Stats:**")
                            total_props = len(schema_data) - 2  # Exclude @context and @type
                            st.metric("Total Properties", total_props)
                            
                            # Count nested objects
                            nested_objects = 0
                            for value in schema_data.values():
                                if isinstance(value, dict) and "@type" in value:
                                    nested_objects += 1
                                elif isinstance(value, list):
                                    nested_objects += sum(1 for item in value if isinstance(item, dict) and "@type" in item)
                            
                            st.metric("Nested Objects", nested_objects)
                            
                            # Array properties
                            array_props = sum(1 for value in schema_data.values() if isinstance(value, list))
                            st.metric("Array Properties", array_props)
                        
                        # Enhancement features showcase
                        st.subheader("Enhancement Features")
                        
                        enhancements = []
                        if "contactPoint" in schema_data and len(schema_data["contactPoint"]) > 1:
                            dept_count = len(schema_data["contactPoint"])
                            enhancements.append(f" **Multi-department Contacts:** {dept_count} departments")
                        
                        if "sameAs" in schema_data and len(schema_data["sameAs"]) > 0:
                            social_count = len(schema_data["sameAs"])
                            enhancements.append(f" **Social Media Integration:** {social_count} platforms")
                        
                        if "subjectOf" in schema_data:
                            wiki_count = len(schema_data["subjectOf"])
                            enhancements.append(f" **Wikipedia Integration:** {wiki_count} topic links")
                        
                        if "knowsAbout" in schema_data:
                            expertise_count = len(schema_data["knowsAbout"])
                            enhancements.append(f" **Expertise Areas:** {expertise_count} knowledge domains")
                        
                        if "keywords" in schema_data and len(schema_data["keywords"]) > 5:
                            keyword_count = len(schema_data["keywords"])
                            enhancements.append(f" **Rich Keywords:** {keyword_count} terms")
                        
                        for enhancement in enhancements:
                            st.success(enhancement)
                        
                        if not enhancements:
                            st.info("Consider using Organization template for maximum enhancement features")
                        
                        # Download and implementation
                        st.subheader("Implementation")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.download_button(
                                "Download JSON-LD",
                                data=formatted_json,
                                file_name=f"schema-{schema_data.get('@type', 'schema').lower()}.jsonld",
                                mime="application/ld+json"
                            )
                        
                        with col2:
                            if st.button("Copy Schema"):
                                st.success("Ready to copy!")
                        
                        with col3:
                            if st.button("Regenerate"):
                                st.experimental_rerun()
                        
                        # Download and implementation helpers
                        # Download and copy buttons provided above
                        
                        # Quality score
                        st.subheader("Schema Quality Score")
                        
                        quality_score = 0
                        
                        # Core properties (30 points)
                        core_props = ["@context", "@type", "name", "url", "description"]
                        for prop in core_props:
                            if prop in schema_data:
                                quality_score += 6
                        
                        # Enhanced features (40 points)
                        if "contactPoint" in schema_data and len(schema_data["contactPoint"]) > 1:
                            quality_score += 15
                        if "sameAs" in schema_data and len(schema_data["sameAs"]) > 0:
                            quality_score += 10
                        if "subjectOf" in schema_data:
                            quality_score += 10
                        if "address" in schema_data:
                            quality_score += 5
                        
                        # Content richness (30 points)
                        if "keywords" in schema_data and len(schema_data["keywords"]) > 5:
                            quality_score += 10
                        if "knowsAbout" in schema_data:
                            quality_score += 10
                        if len(schema_data) > 8:
                            quality_score += 10
                        
                        # Display quality score
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Quality Score", f"{quality_score}/100")
                        
                        with col2:
                            if quality_score >= 80:
                                grade = "Excellent"
                            elif quality_score >= 60:
                                grade = "Good"
                            else:
                                grade = "Fair"
                            st.metric("Grade", grade)
                        
                        with col3:
                            complexity = "Advanced" if nested_objects > 3 else "Intermediate" if nested_objects > 1 else "Basic"
                            st.metric("Complexity", complexity)
                    
                    else:
                        st.error("❌ Failed to generate schema. Please try again or contact support.")
                
            except Exception as e:
                st.error(f"❌ Error processing URL: {str(e)}")
                st.info("Please ensure the URL is accessible and contains valid HTML content.")

# Sidebar advanced options
st.sidebar.markdown("---")
st.sidebar.header("Advanced Options")

if st.sidebar.checkbox("Show Entity Data"):
    if 'comprehensive_data' in locals():
        entity_data = comprehensive_data.get('entity_data', {})
        if entity_data:
            st.sidebar.write("**Detected Entity Data:**")
            if entity_data['expertise_areas']:
                st.sidebar.write("**Areas:** " + ", ".join(entity_data['expertise_areas']))

if st.sidebar.checkbox("Show Raw Data"):
    if 'comprehensive_data' in locals():
        with st.sidebar.expander("Raw Extraction Data"):
            st.sidebar.json(comprehensive_data)

