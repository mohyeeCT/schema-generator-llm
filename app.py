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
    PostalAddress
)
from msgspec_schemaorg.utils import parse_iso8601

# --- Configuration ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U")
genai.configure(api_key=GEMINI_API_KEY)

# --- Custom Schema Templates ---
CUSTOM_TEMPLATES = {
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
            "email": ""
        },
        "description": "Comprehensive organization schema with contact points, social media, and address"
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
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": "",
                "longitude": ""
            },
            "telephone": "",
            "email": "",
            "openingHours": [],
            "priceRange": "",
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "",
                "reviewCount": ""
            }
        },
        "description": "Local business with location, hours, and ratings"
    },
    "Article": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": "",
            "description": "",
            "image": "",
            "author": {
                "@type": "Person",
                "name": ""
            },
            "publisher": {
                "@type": "Organization",
                "name": "",
                "logo": {
                    "@type": "ImageObject",
                    "url": ""
                }
            },
            "datePublished": "",
            "dateModified": "",
            "url": "",
            "articleSection": "",
            "wordCount": "",
            "keywords": []
        },
        "description": "Comprehensive article schema with author and publisher details"
    },
    "Product": {
        "template": {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "",
            "description": "",
            "image": [],
            "brand": {
                "@type": "Brand",
                "name": ""
            },
            "manufacturer": {
                "@type": "Organization",
                "name": ""
            },
            "offers": {
                "@type": "Offer",
                "priceCurrency": "",
                "price": "",
                "availability": "",
                "seller": {
                    "@type": "Organization",
                    "name": ""
                }
            },
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "",
                "reviewCount": ""
            },
            "sku": "",
            "mpn": ""
        },
        "description": "Product schema with pricing, ratings, and manufacturer details"
    }
}

# --- Enhanced Content Extraction Functions ---

def extract_existing_schema(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract and analyze existing schema markup"""
    existing_schemas = {
        'json_ld': [],
        'microdata': [],
        'rdfa': [],
        'analysis': {
            'has_schema': False,
            'schema_types': [],
            'completeness_score': 0,
            'recommendations': []
        }
    }
    
    # JSON-LD extraction
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            existing_schemas['json_ld'].append(data)
            existing_schemas['analysis']['has_schema'] = True
            
            # Extract schema types
            if isinstance(data, dict):
                schema_type = data.get('@type')
                if schema_type:
                    existing_schemas['analysis']['schema_types'].append(schema_type)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and '@type' in item:
                        existing_schemas['analysis']['schema_types'].append(item['@type'])
                        
        except (json.JSONDecodeError, AttributeError):
            continue
    
    # Microdata extraction
    microdata_items = soup.find_all(attrs={"itemscope": True})
    for item in microdata_items:
        item_type = item.get("itemtype", "")
        item_props = {}
        
        for prop in item.find_all(attrs={"itemprop": True}):
            prop_name = prop.get("itemprop")
            prop_value = prop.get("content") or prop.get_text(strip=True)
            if prop_name and prop_value:
                item_props[prop_name] = prop_value
        
        if item_type or item_props:
            existing_schemas['microdata'].append({
                'type': item_type,
                'properties': item_props
            })
            existing_schemas['analysis']['has_schema'] = True
    
    # Analyze completeness and provide recommendations
    if existing_schemas['json_ld']:
        schema = existing_schemas['json_ld'][0]  # Analyze first schema
        required_props = ['name', 'url', 'description']
        present_props = [prop for prop in required_props if prop in schema]
        existing_schemas['analysis']['completeness_score'] = len(present_props) / len(required_props)
        
        if 'image' not in schema:
            existing_schemas['analysis']['recommendations'].append("Add image property")
        if 'contactPoint' not in schema and schema.get('@type') == 'Organization':
            existing_schemas['analysis']['recommendations'].append("Add contact information")
        if 'sameAs' not in schema:
            existing_schemas['analysis']['recommendations'].append("Add social media links")
    
    return existing_schemas

def fetch_comprehensive_content(url: str) -> Dict[str, Any]:
    """Enhanced content extraction with schema detection"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        content = {
            'url': url,
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
            'page_structure': analyze_page_structure(soup)
        }

        return content

    except requests.exceptions.Timeout:
        raise Exception(f"Request to {url} timed out")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching content: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error during content extraction: {e}")

def extract_basic_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract basic page metadata"""
    title = ""
    if soup.title and soup.title.string:
        title = str(soup.title.string).strip()
    
    description = ""
    desc_selectors = [
        'meta[name="description"]',
        'meta[property="og:description"]',
        'meta[name="twitter:description"]'
    ]
    
    for selector in desc_selectors:
        desc_tag = soup.select_one(selector)
        if desc_tag and desc_tag.get("content"):
            description = str(desc_tag.get("content")).strip()
            break
    
    keywords = []
    keywords_tag = soup.find("meta", {"name": "keywords"})
    if keywords_tag and keywords_tag.get("content"):
        keywords = [k.strip() for k in keywords_tag.get("content").split(",")]
    
    language = soup.get("lang") or soup.find("html", {"lang": True})
    if language and hasattr(language, 'get'):
        language = language.get("lang")
    
    return {
        'title': title,
        'description': description,
        'keywords': keywords,
        'language': str(language) if language else None,
        'canonical_url': extract_canonical_url(soup)
    }

def extract_social_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract social media metadata"""
    social_data = {'og': {}, 'twitter': {}, 'article': {}}
    
    # Open Graph data
    og_tags = soup.find_all("meta", property=lambda x: x and x.startswith("og:"))
    for tag in og_tags:
        prop = tag.get("property", "").replace("og:", "")
        content = tag.get("content", "")
        if prop and content:
            social_data['og'][prop] = content
    
    # Twitter Card data
    twitter_tags = soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")})
    for tag in twitter_tags:
        name = tag.get("name", "").replace("twitter:", "")
        content = tag.get("content", "")
        if name and content:
            social_data['twitter'][name] = content
    
    return social_data

def extract_comprehensive_contact_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract comprehensive contact information"""
    contact_info = {
        'emails': [],
        'phones': [],
        'fax': [],
        'contact_points': []
    }
    
    # Email extraction
    email_patterns = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    ]
    
    # From mailto links
    email_links = soup.find_all('a', href=lambda x: x and x.startswith('mailto:'))
    for link in email_links:
        email = link.get('href', '').replace('mailto:', '').split('?')[0]
        if email and email not in contact_info['emails']:
            contact_info['emails'].append(email)
    
    # From text content
    page_text = soup.get_text()
    for pattern in email_patterns:
        emails = re.findall(pattern, page_text)
        for email in emails:
            if email not in contact_info['emails']:
                contact_info['emails'].append(email)
    
    # Phone extraction
    phone_patterns = [
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\+\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'
    ]
    
    # From tel links
    phone_links = soup.find_all('a', href=lambda x: x and x.startswith('tel:'))
    for link in phone_links:
        phone = link.get('href', '').replace('tel:', '').replace('+1', '')
        if phone and phone not in contact_info['phones']:
            contact_info['phones'].append(phone)
    
    # From text content
    for pattern in phone_patterns:
        phones = re.findall(pattern, page_text)
        for phone in phones:
            clean_phone = re.sub(r'[^\d+()-]', '', phone)
            if len(clean_phone) >= 10 and clean_phone not in contact_info['phones']:
                contact_info['phones'].append(phone)
    
    return contact_info

def extract_comprehensive_business_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract comprehensive business information"""
    business_data = {
        'name': None,
        'address': {},
        'coordinates': {},
        'hours': [],
        'price_range': None,
        'services': []
    }
    
    # Business name extraction
    name_selectors = [
        '[itemprop="name"]',
        'h1',
        '.company-name',
        '.business-name',
        '[class*="name"]'
    ]
    
    for selector in name_selectors:
        elem = soup.select_one(selector)
        if elem:
            business_data['name'] = elem.get_text(strip=True)
            break
    
    # Address extraction with multiple strategies
    address_selectors = {
        'street': ['[itemprop="streetAddress"]', '.street', '.address-line-1'],
        'city': ['[itemprop="addressLocality"]', '.city', '.locality'],
        'state': ['[itemprop="addressRegion"]', '.state', '.region'],
        'postal_code': ['[itemprop="postalCode"]', '.zip', '.postal-code'],
        'country': ['[itemprop="addressCountry"]', '.country']
    }
    
    for addr_type, selectors in address_selectors.items():
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                business_data['address'][addr_type] = elem.get_text(strip=True)
                break
    
    # Extract full address from text if components not found
    if not any(business_data['address'].values()):
        address_patterns = [
            r'\d+\s+[A-Za-z\s,.]+'  # Street address pattern
        ]
        page_text = soup.get_text()
        for pattern in address_patterns:
            matches = re.findall(pattern, page_text)
            if matches:
                # Simple address parsing
                full_address = matches[0].strip()
                business_data['address']['full'] = full_address
                break
    
    return business_data

def extract_social_links(soup: BeautifulSoup) -> List[str]:
    """Extract social media links"""
    social_links = []
    social_domains = [
        'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com',
        'youtube.com', 'pinterest.com', 'tiktok.com', 'snapchat.com'
    ]
    
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        href = link.get('href', '')
        for domain in social_domains:
            if domain in href and href not in social_links:
                social_links.append(href)
                break
    
    return social_links

def analyze_page_content(soup: BeautifulSoup) -> Dict[str, Any]:
    """Analyze page content structure"""
    content_soup = BeautifulSoup(str(soup), "html.parser")
    
    # Remove non-content elements
    for script in content_soup(["script", "style", "nav", "header", "footer", "aside"]):
        script.decompose()
    
    main_content = ""
    content_selectors = [
        'main', 'article', '[role="main"]', '.content', '#content',
        '.post-content', '.entry-content', '.article-content'
    ]
    
    for selector in content_selectors:
        content_elem = content_soup.select_one(selector)
        if content_elem:
            main_content = content_elem.get_text(strip=True)
            break
    
    if not main_content:
        body = content_soup.find('body')
        if body:
            main_content = body.get_text(strip=True)
    
    return {
        'main_text': main_content[:3000],
        'word_count': len(main_content.split()) if main_content else 0,
        'has_forms': bool(soup.find_all('form')),
        'has_tables': bool(soup.find_all('table'))
    }

def extract_author_information(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract author information"""
    author_info = {'authors': [], 'publisher': None}
    
    author_selectors = [
        '[rel="author"]', '.author', '.byline', '[itemprop="author"]', 'meta[name="author"]'
    ]
    
    authors = set()
    for selector in author_selectors:
        elements = soup.select(selector)
        for elem in elements:
            if elem.name == 'meta':
                author_text = elem.get('content', '')
            else:
                author_text = elem.get_text(strip=True)
            
            if author_text and len(author_text) < 100:
                authors.add(author_text)
    
    author_info['authors'] = list(authors)
    return author_info

def extract_publication_data(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract publication dates"""
    pub_data = {'published_date': None, 'modified_date': None}
    
    date_selectors = [
        'time[datetime]', '[itemprop="datePublished"]', '[itemprop="dateModified"]',
        'meta[property="article:published_time"]', 'meta[property="article:modified_time"]'
    ]
    
    for selector in date_selectors:
        elements = soup.select(selector)
        for elem in elements:
            date_value = None
            
            if elem.name == 'time':
                date_value = elem.get('datetime')
            elif elem.name == 'meta':
                date_value = elem.get('content')
            else:
                date_value = elem.get('datetime') or elem.get_text(strip=True)
            
            if date_value:
                if 'publish' in selector.lower() and not pub_data['published_date']:
                    pub_data['published_date'] = date_value
                elif 'modif' in selector.lower() and not pub_data['modified_date']:
                    pub_data['modified_date'] = date_value
    
    return pub_data

def extract_media_content(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    """Extract media content"""
    media_data = {'images': [], 'featured_image': None, 'logo': None}
    
    # Images
    for img in soup.find_all('img', src=True):
        src = urljoin(base_url, img.get('src'))
        alt = img.get('alt', '')
        
        # Skip small images
        width = img.get('width')
        height = img.get('height')
        if width and height:
            try:
                if int(width) < 50 or int(height) < 50:
                    continue
            except ValueError:
                pass
        
        media_data['images'].append({'src': src, 'alt': alt})
    
    # Featured image
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        media_data['featured_image'] = og_image.get('content')
    elif media_data['images']:
        media_data['featured_image'] = media_data['images'][0]['src']
    
    # Logo detection
    logo_selectors = [
        '.logo img', '[class*="logo"] img', '#logo img',
        'img[alt*="logo"]', 'img[class*="logo"]'
    ]
    
    for selector in logo_selectors:
        logo_img = soup.select_one(selector)
        if logo_img and logo_img.get('src'):
            media_data['logo'] = urljoin(base_url, logo_img.get('src'))
            break
    
    return media_data

def extract_seo_indicators(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract SEO indicators"""
    seo_data = {'canonical_url': None}
    
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical:
        seo_data['canonical_url'] = canonical.get('href', '')
    
    return seo_data

def analyze_page_structure(soup: BeautifulSoup) -> Dict[str, Any]:
    """Analyze page structure for schema hints"""
    structure = {
        'has_article_structure': False,
        'has_organization_structure': False,
        'has_business_structure': False,
        'content_type': 'webpage'
    }
    
    # Organization/Business indicators
    org_indicators = soup.select('.company, .organization, .business, [itemprop="organization"]')
    contact_indicators = soup.select('.contact, .phone, .email, .address')
    
    if org_indicators or contact_indicators or soup.select('a[href^="mailto:"]') or soup.select('a[href^="tel:"]'):
        structure['has_organization_structure'] = True
        structure['content_type'] = 'organization'
    
    # Article indicators
    article_indicators = soup.select('article, .post, .entry, [itemprop="blogPost"]')
    if article_indicators or soup.select('time, .byline, .author'):
        structure['has_article_structure'] = True
        if structure['content_type'] == 'webpage':
            structure['content_type'] = 'article'
    
    return structure

def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
    """Extract canonical URL"""
    canonical = soup.select_one('link[rel="canonical"]')
    return canonical.get('href') if canonical else None

# --- Enhanced Gemini Analysis ---
def create_comprehensive_schema_prompt(comprehensive_data: dict, url: str, template_type: str = None) -> str:
    """Create enhanced prompt for comprehensive schema generation"""
    
    basic_meta = comprehensive_data['basic_metadata']
    existing_schema = comprehensive_data['existing_schema']
    contact_info = comprehensive_data['contact_info']
    business_info = comprehensive_data['business_info']
    social_links = comprehensive_data['social_links']
    media_content = comprehensive_data['media_content']
    page_structure = comprehensive_data['page_structure']
    
    # Build context for Gemini
    context = f"""
**URL:** {url}
**Page Type:** {page_structure['content_type']}

**Basic Information:**
- Title: {basic_meta['title']}
- Description: {basic_meta['description']}
- Language: {basic_meta['language']}

**Existing Schema Analysis:**
- Has existing schema: {existing_schema['analysis']['has_schema']}
- Schema types found: {', '.join(existing_schema['analysis']['schema_types'])}
- Completeness score: {existing_schema['analysis']['completeness_score']:.2f}
- Recommendations: {'; '.join(existing_schema['analysis']['recommendations'])}

**Contact Information:**
- Emails: {', '.join(contact_info['emails'][:3])}
- Phones: {', '.join(contact_info['phones'][:3])}

**Business Information:**
- Name: {business_info['name']}
- Address: {business_info['address']}

**Social Media:**
- Social links found: {len(social_links)}
- Links: {'; '.join(social_links[:5])}

**Media Content:**
- Featured image: {media_content['featured_image']}
- Logo: {media_content['logo']}
- Total images: {len(media_content['images'])}

**Template Preference:** {template_type or 'Auto-detect'}
"""

    prompt = f"""You are an expert Schema.org consultant. Create comprehensive, production-ready JSON-LD markup.

{context}

**REQUIREMENTS:**
1. **Comprehensive Coverage**: Include ALL relevant properties, not just basic ones
2. **Contact Points**: For organizations, create detailed contactPoint arrays with different departments/purposes
3. **Social Media**: Include complete sameAs array with all social profiles found
4. **Address**: Use proper PostalAddress structure with all components
5. **Enhanced Properties**: Add keywords, subjectOf, location, etc. where relevant
6. **Nested Objects**: Use proper nested structures (ContactPoint, PostalAddress, etc.)

**EXAMPLE COMPREHENSIVE OUTPUT STYLE:**
```json
{{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Company Name",
  "url": "https://example.com",
  "logo": "https://example.com/logo.jpg",
  "description": "...",
  "image": "https://example.com/image.jpg",
  "contactPoint": [
    {{
      "@type": "ContactPoint",
      "contactType": "sales",
      "areaServed": "US",
      "availableLanguage": "English",
      "email": "sales@example.com",
      "telephone": "(800) 123-4567",
      "description": "Sales Department"
    }}
  ],
  "sameAs": [
    "https://www.facebook.com/company",
    "https://twitter.com/company"
  ],
  "address": {{
    "@type": "PostalAddress",
    "streetAddress": "123 Main St",
    "addressLocality": "City",
    "addressRegion": "State",
    "postalCode": "12345",
    "addressCountry": "US"
  }},
  "keywords": ["keyword1", "keyword2"],
  "telephone": "+1-800-123-4567"
}}
```

**OUTPUT ONLY VALID JSON - NO EXPLANATIONS OR MARKDOWN**
"""

    return prompt

def generate_comprehensive_schema(comprehensive_data: dict, url: str, template_type: str = None):
    """Generate comprehensive schema using enhanced Gemini analysis"""
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = create_comprehensive_schema_prompt(comprehensive_data, url, template_type)
        
        response = model.generate_content(prompt)
        
        if not response.text:
            raise ValueError("Gemini returned an empty response")
        
        # Clean response
        raw_json_str = response.text.strip()
        
        # Remove markdown formatting
        if raw_json_str.startswith("```json"):
            json_str = raw_json_str[len("```json"):].strip()
            if json_str.endswith("```"):
                json_str = json_str[:-len("```")].strip()
        elif raw_json_str.startswith("```"):
            json_str = raw_json_str[3:].strip()
            if json_str.endswith("```"):
                json_str = json_str[:-3].strip()
        else:
            json_str = raw_json_str
        
        # Parse and validate JSON
        parsed_schema = json.loads(json_str)
        
        # Ensure required fields
        if "@context" not in parsed_schema:
            parsed_schema["@context"] = "https://schema.org"
        
        return parsed_schema, 0.95, "Comprehensive schema generated successfully"
        
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse Gemini JSON output: {e}")
        return None, 0.0, f"JSON parsing failed: {str(e)}"
    except Exception as e:
        st.error(f"Error generating schema: {e}")
        return None, 0.0, f"Generation failed: {str(e)}"

# --- Streamlit UI ---
st.set_page_config(page_title="Comprehensive Schema.org Generator", page_icon="🔗", layout="wide")

st.title("🔗 Comprehensive Schema.org JSON-LD Generator")
st.markdown("""
Generate production-ready, comprehensive Schema.org markup with:
- **Existing Schema Detection & Enhancement**
- **Custom Templates** for different content types
- **Comprehensive Contact & Social Media Integration**  
- **Multi-department Contact Points** (like the Sugatsune example)
""")

# Sidebar for template selection
st.sidebar.header("🎯 Schema Templates")
template_option = st.sidebar.selectbox(
    "Choose template type:",
    ["Auto-detect"] + list(CUSTOM_TEMPLATES.keys())
)

if template_option != "Auto-detect":
    st.sidebar.json(CUSTOM_TEMPLATES[template_option]["template"])
    st.sidebar.caption(CUSTOM_TEMPLATES[template_option]["description"])

# Main input
url = st.text_input("Enter URL to analyze:", placeholder="https://www.example.com")

if st.button("🚀 Generate Comprehensive Schema", type="primary"):
    if not url:
        st.warning("Please enter a URL")
    elif not url.startswith(("http://", "https://")):
        st.warning("Please enter a valid URL starting with http:// or https://")
    else:
        with st.spinner("Extracting comprehensive content..."):
            try:
                comprehensive_data = fetch_comprehensive_content(url)
                
                # Display existing schema analysis
                existing_schema = comprehensive_data['existing_schema']
                if existing_schema['analysis']['has_schema']:
                    st.success("✅ Existing Schema Found")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Schema Types", len(existing_schema['analysis']['schema_types']))
                    with col2:
                        st.metric("Completeness", f"{existing_schema['analysis']['completeness_score']:.0%}")
                    with col3:
                        st.metric("Recommendations", len(existing_schema['analysis']['recommendations']))
                    
                    if existing_schema['analysis']['recommendations']:
                        st.info("💡 **Enhancement Recommendations:** " + "; ".join(existing_schema['analysis']['recommendations']))
                    
                    with st.expander("📋 View Existing Schema"):
                        for i, schema in enumerate(existing_schema['json_ld']):
                            st.json(schema)
                else:
                    st.info("ℹ️ No existing schema found - generating from scratch")
                
                # Content analysis summary
                st.subheader("📊 Content Analysis")
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
                    st.metric("Content Type", comprehensive_data['page_structure']['content_type'].title())
                
                # Generate comprehensive schema
                st.subheader("🤖 AI Schema Generation")
                with st.spinner("Generating comprehensive schema..."):
                    template_type = template_option if template_option != "Auto-detect" else None
                    schema_data, confidence, reasoning = generate_comprehensive_schema(
                        comprehensive_data, url, template_type
                    )
                    
                    if schema_data:
                        # Display results
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.success(f"✅ Schema Generated - Confidence: {confidence:.0%}")
                            st.caption(reasoning)
                        
                        with col2:
                            schema_type = schema_data.get('@type', 'Unknown')
                            st.metric("Schema Type", schema_type)
                        
                        # Main schema output
                        st.subheader("📝 Generated Schema.org JSON-LD")
                        
                        # Format and display JSON
                        formatted_json = json.dumps(schema_data, indent=2, ensure_ascii=False)
                        st.code(formatted_json, language="json")
                        
                        # Analysis of generated schema
                        st.subheader("🔍 Schema Analysis")
                        
                        analysis_cols = st.columns(3)
                        
                        with analysis_cols[0]:
                            st.write("**✅ Validation Checks:**")
                            checks = {
                                "Has @context": "@context" in schema_data,
                                "Has @type": "@type" in schema_data,
                                "Has name": "name" in schema_data,
                                "Has URL": "url" in schema_data,
                                "Has description": "description" in schema_data,
                                "Has contact info": "contactPoint" in schema_data or "telephone" in schema_data,
                                "Has social links": "sameAs" in schema_data,
                                "Has address": "address" in schema_data
                            }
                            
                            for check, passed in checks.items():
                                st.write(f"{'✅' if passed else '❌'} {check}")
                        
                        with analysis_cols[1]:
                            st.write("**📊 Schema Properties:**")
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
                        
                        with analysis_cols[2]:
                            st.write("**🎯 Enhancement Features:**")
                            enhancements = []
                            
                            if "contactPoint" in schema_data:
                                enhancements.append("Multi-department contacts")
                            if "sameAs" in schema_data and len(schema_data["sameAs"]) > 0:
                                enhancements.append("Social media integration")
                            if "address" in schema_data and isinstance(schema_data["address"], dict):
                                enhancements.append("Structured address")
                            if "keywords" in schema_data:
                                enhancements.append("SEO keywords")
                            if "logo" in schema_data:
                                enhancements.append("Brand logo")
                            
                            for enhancement in enhancements:
                                st.write(f"✨ {enhancement}")
                        
                        # Download and implementation
                        st.subheader("💾 Implementation")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.download_button(
                                "📥 Download JSON-LD",
                                data=formatted_json,
                                file_name=f"schema-{schema_data.get('@type', 'schema').lower()}.jsonld",
                                mime="application/ld+json"
                            )
                        
                        with col2:
                            if st.button("📋 Copy to Clipboard"):
                                st.write("JSON-LD copied to clipboard!")
                        
                        # Implementation instructions
                        st.info("""
                        **📖 Implementation Instructions:**
                        1. Copy the JSON-LD code above
                        2. Paste it into a `<script type="application/ld+json">` tag in your HTML `<head>`
                        3. Test with [Google Rich Results Test](https://search.google.com/test/rich-results)
                        4. Validate with [Schema Markup Validator](https://validator.schema.org/)
                        """)
                        
                        # Comparison with existing schema
                        if existing_schema['analysis']['has_schema'] and existing_schema['json_ld']:
                            st.subheader("🔄 Before vs After Comparison")
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write("**📋 Original Schema:**")
                                original_schema = existing_schema['json_ld'][0]
                                st.code(json.dumps(original_schema, indent=2), language="json", height=300)
                                st.caption(f"Properties: {len(original_schema) - 2}")
                            
                            with col2:
                                st.write("**✨ Enhanced Schema:**")
                                st.code(formatted_json, language="json", height=300)
                                st.caption(f"Properties: {total_props}")
                            
                            # Improvement metrics
                            improvements = []
                            if total_props > len(original_schema) - 2:
                                improvements.append(f"Added {total_props - (len(original_schema) - 2)} properties")
                            if "contactPoint" in schema_data and "contactPoint" not in original_schema:
                                improvements.append("Added structured contact information")
                            if "sameAs" in schema_data and "sameAs" not in original_schema:
                                improvements.append("Added social media links")
                            if "address" in schema_data and "address" not in original_schema:
                                improvements.append("Added structured address")
                            
                            if improvements:
                                st.success("🎉 **Improvements Made:** " + "; ".join(improvements))
                    
                    else:
                        st.error("❌ Failed to generate schema. Please check the URL and try again.")
                
            except Exception as e:
                st.error(f"❌ Error processing URL: {str(e)}")
                st.info("Please ensure the URL is accessible and contains valid HTML content.")

# Additional features in sidebar
st.sidebar.markdown("---")
st.sidebar.header("🛠️ Advanced Features")

if st.sidebar.checkbox("Show Raw Extraction Data"):
    if 'comprehensive_data' in locals():
        st.sidebar.json(comprehensive_data)

st.sidebar.markdown("---")
st.sidebar.markdown("""
**🔗 Validation Tools:**
- [Google Rich Results Test](https://search.google.com/test/rich-results)
- [Schema Markup Validator](https://validator.schema.org/)
- [JSON-LD Playground](https://json-ld.org/playground/)

**📚 Resources:**
- [Schema.org Documentation](https://schema.org/)
- [Google Search Central](https://developers.google.com/search/docs/appearance/structured-data)
""")

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>🚀 <strong>Comprehensive Schema.org Generator</strong> | Built with Google Gemini AI</p>
    <p>Generate production-ready, comprehensive JSON-LD markup with multi-department contacts, social integration, and enhanced properties.</p>
</div>
""", unsafe_allow_html=True)
