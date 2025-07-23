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

# Import all relevant Schema.org models you might expect Gemini to suggest
from msgspec_schemaorg.models import (
    Article, WebPage, Product, Event, Organization, Person, Place,
    CreativeWork, Thing, LocalBusiness, Service, Recipe, Review,
    ImageObject, VideoObject, NewsArticle, BlogPosting
)
from msgspec_schemaorg.utils import parse_iso8601

# --- Configuration ---
# IMPORTANT: For production deployments (e.g., Streamlit Community Cloud),
# ALWAYS use Streamlit's secrets management for API keys.
# Learn more here: https://docs.streamlit.io/deploy/streamlit-cloud/secrets-management
# Example: GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
# For local testing, you can keep it directly or load from an environment variable.
GEMINI_API_KEY = "AIzaSyDwxh1DQStRDUra_Nu9KUkxDVrSNb7p42U"  # Replace with your actual key or st.secrets
genai.configure(api_key=GEMINI_API_KEY)

# --- Enhanced Content Extraction Functions ---

def fetch_comprehensive_content(url: str) -> Dict[str, Any]:
    """
    Enhanced content extraction that scrapes comprehensive data for schema generation.
    Returns a detailed dictionary with all relevant metadata and content.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Initialize comprehensive content dictionary
        content = {
            'url': url,
            'basic_metadata': extract_basic_metadata(soup),
            'social_metadata': extract_social_metadata(soup),
            'structured_data': extract_existing_structured_data(soup),
            'content_analysis': analyze_page_content(soup),
            'author_info': extract_author_information(soup),
            'publication_info': extract_publication_data(soup),
            'product_data': extract_product_information(soup),
            'event_data': extract_event_information(soup),
            'business_info': extract_business_information(soup),
            'media_content': extract_media_content(soup, url),
            'navigation_structure': extract_navigation_structure(soup),
            'page_structure': analyze_page_structure(soup),
            'seo_indicators': extract_seo_indicators(soup),
            'contact_info': extract_contact_information(soup)
        }

        return content

    except requests.exceptions.Timeout:
        raise Exception(f"Request to {url} timed out")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching content: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error during content extraction: {e}")

def extract_basic_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract basic page metadata (title, description, etc.)"""
    title = ""
    if soup.title and soup.title.string:
        title = str(soup.title.string).strip()
    
    # Try multiple description sources
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
    
    # Extract keywords
    keywords = []
    keywords_tag = soup.find("meta", {"name": "keywords"})
    if keywords_tag and keywords_tag.get("content"):
        keywords = [k.strip() for k in keywords_tag.get("content").split(",")]
    
    # Extract language
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
    """Extract Open Graph, Twitter Cards, and other social metadata"""
    social_data = {
        'og': {},
        'twitter': {},
        'article': {}
    }
    
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
    
    # Article-specific meta tags
    article_tags = soup.find_all("meta", property=lambda x: x and x.startswith("article:"))
    for tag in article_tags:
        prop = tag.get("property", "").replace("article:", "")
        content = tag.get("content", "")
        if prop and content:
            social_data['article'][prop] = content
    
    return social_data

def extract_existing_structured_data(soup: BeautifulSoup) -> Dict[str, List]:
    """Extract existing structured data (JSON-LD, microdata, RDFa)"""
    structured_data = {
        'json_ld': [],
        'microdata': [],
        'rdfa': []
    }
    
    # JSON-LD extraction
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            structured_data['json_ld'].append(data)
        except (json.JSONDecodeError, AttributeError):
            continue
    
    # Microdata extraction (basic)
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
            structured_data['microdata'].append({
                'type': item_type,
                'properties': item_props
            })
    
    return structured_data

def analyze_page_content(soup: BeautifulSoup) -> Dict[str, Any]:
    """Analyze the main content structure and extract key information"""
    
    # Create a copy for content analysis to avoid modifying original
    content_soup = BeautifulSoup(str(soup), "html.parser")
    
    # Remove script and style elements
    for script in content_soup(["script", "style", "nav", "header", "footer", "aside"]):
        script.decompose()
    
    # Extract main content
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
        # Fallback: get body text excluding common non-content elements
        body = content_soup.find('body')
        if body:
            for elem in body.find_all(['nav', 'header', 'footer', 'aside', 'script', 'style']):
                elem.decompose()
            main_content = body.get_text(strip=True)
    
    # Extract headings structure from original soup
    headings = []
    for i in range(1, 7):
        for heading in soup.find_all(f'h{i}'):
            headings.append({
                'level': i,
                'text': heading.get_text(strip=True),
                'id': heading.get('id')
            })
    
    return {
        'main_text': main_content[:5000],  # Limit to first 5000 chars
        'word_count': len(main_content.split()) if main_content else 0,
        'headings': headings,
        'paragraphs_count': len(soup.find_all('p')),
        'has_forms': bool(soup.find_all('form')),
        'has_tables': bool(soup.find_all('table'))
    }

def extract_author_information(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract author and byline information"""
    author_info = {
        'authors': [],
        'byline': None,
        'publisher': None
    }
    
    # Common author selectors
    author_selectors = [
        '[rel="author"]',
        '.author',
        '.byline',
        '[itemprop="author"]',
        'meta[name="author"]'
    ]
    
    authors = set()  # Use set to avoid duplicates
    
    for selector in author_selectors:
        elements = soup.select(selector)
        for elem in elements:
            if elem.name == 'meta':
                author_text = elem.get('content', '')
            else:
                author_text = elem.get_text(strip=True)
            
            if author_text and len(author_text) < 100:  # Reasonable author name length
                authors.add(author_text)
    
    author_info['authors'] = list(authors)
    
    # Look for publisher information
    publisher_selectors = [
        '[itemprop="publisher"]',
        'meta[property="article:publisher"]',
        'meta[name="publisher"]'
    ]
    
    for selector in publisher_selectors:
        elem = soup.select_one(selector)
        if elem:
            if elem.name == 'meta':
                author_info['publisher'] = elem.get('content', '')
            else:
                author_info['publisher'] = elem.get_text(strip=True)
            break
    
    return author_info

def extract_publication_data(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract publication dates and related information"""
    pub_data = {
        'published_date': None,
        'modified_date': None,
        'dates_found': []
    }
    
    # Look for publication dates in various formats
    date_selectors = [
        'time[datetime]',
        '[itemprop="datePublished"]',
        '[itemprop="dateModified"]',
        'meta[property="article:published_time"]',
        'meta[property="article:modified_time"]',
        'meta[name="publish-date"]',
        'meta[name="date"]'
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
                pub_data['dates_found'].append({
                    'selector': selector,
                    'value': date_value,
                    'element': elem.name
                })
                
                # Try to identify specific date types
                if 'publish' in selector.lower() and not pub_data['published_date']:
                    pub_data['published_date'] = date_value
                elif 'modif' in selector.lower() and not pub_data['modified_date']:
                    pub_data['modified_date'] = date_value
    
    return pub_data

def extract_product_information(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract product-specific information (prices, ratings, etc.)"""
    product_data = {
        'prices': [],
        'ratings': [],
        'availability': None,
        'brand': None,
        'model': None,
        'sku': None
    }
    
    # Price extraction
    price_selectors = [
        '[itemprop="price"]',
        '.price',
        '.cost',
        '[class*="price"]',
        'meta[property="product:price"]'
    ]
    
    for selector in price_selectors:
        elements = soup.select(selector)
        for elem in elements:
            price_text = elem.get('content') if elem.name == 'meta' else elem.get_text(strip=True)
            if price_text and re.search(r'\d+\.?\d*', price_text):
                product_data['prices'].append(price_text)
    
    # Rating extraction
    rating_selectors = [
        '[itemprop="ratingValue"]',
        '.rating',
        '.stars',
        '[class*="rating"]'
    ]
    
    for selector in rating_selectors:
        elements = soup.select(selector)
        for elem in elements:
            rating_text = elem.get('content') if elem.name == 'meta' else elem.get_text(strip=True)
            if rating_text:
                product_data['ratings'].append(rating_text)
    
    # Brand, model, SKU
    brand_elem = soup.select_one('[itemprop="brand"], meta[property="product:brand"]')
    if brand_elem:
        product_data['brand'] = brand_elem.get('content') or brand_elem.get_text(strip=True)
    
    model_elem = soup.select_one('[itemprop="model"], meta[property="product:model"]')
    if model_elem:
        product_data['model'] = model_elem.get('content') or model_elem.get_text(strip=True)
    
    sku_elem = soup.select_one('[itemprop="sku"], meta[property="product:retailer_item_id"]')
    if sku_elem:
        product_data['sku'] = sku_elem.get('content') or sku_elem.get_text(strip=True)
    
    return product_data

def extract_event_information(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract event-specific information"""
    event_data = {
        'start_date': None,
        'end_date': None,
        'location': None,
        'organizer': None,
        'event_type': None
    }
    
    # Event dates
    start_date_elem = soup.select_one('[itemprop="startDate"], meta[property="event:start_time"]')
    if start_date_elem:
        event_data['start_date'] = start_date_elem.get('content') or start_date_elem.get('datetime')
    
    end_date_elem = soup.select_one('[itemprop="endDate"], meta[property="event:end_time"]')
    if end_date_elem:
        event_data['end_date'] = end_date_elem.get('content') or end_date_elem.get('datetime')
    
    # Location
    location_elem = soup.select_one('[itemprop="location"], [itemprop="address"]')
    if location_elem:
        event_data['location'] = location_elem.get_text(strip=True)
    
    return event_data

def extract_business_information(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract local business information"""
    business_data = {
        'name': None,
        'address': {},
        'phone': None,
        'hours': [],
        'coordinates': {}
    }
    
    # Business name
    name_elem = soup.select_one('[itemprop="name"], h1')
    if name_elem:
        business_data['name'] = name_elem.get_text(strip=True)
    
    # Address components
    address_selectors = {
        'street': '[itemprop="streetAddress"]',
        'city': '[itemprop="addressLocality"]',
        'state': '[itemprop="addressRegion"]',
        'postal_code': '[itemprop="postalCode"]',
        'country': '[itemprop="addressCountry"]'
    }
    
    for addr_type, selector in address_selectors.items():
        elem = soup.select_one(selector)
        if elem:
            business_data['address'][addr_type] = elem.get_text(strip=True)
    
    # Phone number
    phone_elem = soup.select_one('[itemprop="telephone"], [href^="tel:"]')
    if phone_elem:
        business_data['phone'] = phone_elem.get('href', '').replace('tel:', '') or phone_elem.get_text(strip=True)
    
    return business_data

def extract_media_content(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    """Extract and categorize media content"""
    media_data = {
        'images': [],
        'videos': [],
        'featured_image': None
    }
    
    # Images
    for img in soup.find_all('img', src=True):
        src = urljoin(base_url, img.get('src'))
        alt = img.get('alt', '')
        title = img.get('title', '')
        
        # Skip very small images (likely icons/logos)
        width = img.get('width')
        height = img.get('height')
        if width and height:
            try:
                if int(width) < 50 or int(height) < 50:
                    continue
            except ValueError:
                pass
        
        media_data['images'].append({
            'src': src,
            'alt': alt,
            'title': title,
            'width': width,
            'height': height
        })
    
    # Featured image from meta tags
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        media_data['featured_image'] = og_image.get('content')
    elif media_data['images']:
        # Use first substantial image as featured
        media_data['featured_image'] = media_data['images'][0]['src']
    
    # Videos
    for video in soup.find_all('video', src=True):
        media_data['videos'].append({
            'src': urljoin(base_url, video.get('src')),
            'type': video.get('type', ''),
            'poster': video.get('poster', '')
        })
    
    return media_data

def extract_navigation_structure(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract navigation and breadcrumb information"""
    nav_data = {
        'breadcrumbs': [],
        'main_navigation': [],
        'pagination': {}
    }
    
    # Breadcrumbs
    breadcrumb_selectors = [
        '[itemtype*="BreadcrumbList"]',
        '.breadcrumb',
        '.breadcrumbs',
        'nav[aria-label*="breadcrumb"]'
    ]
    
    for selector in breadcrumb_selectors:
        breadcrumb_container = soup.select_one(selector)
        if breadcrumb_container:
            links = breadcrumb_container.find_all('a')
            for link in links:
                nav_data['breadcrumbs'].append({
                    'text': link.get_text(strip=True),
                    'url': link.get('href', '')
                })
            break
    
    return nav_data

def analyze_page_structure(soup: BeautifulSoup) -> Dict[str, Any]:
    """Analyze overall page structure for schema type hints"""
    structure = {
        'has_article_structure': False,
        'has_product_structure': False,
        'has_event_structure': False,
        'has_business_structure': False,
        'content_indicators': []
    }
    
    # Article indicators
    article_indicators = soup.select('article, .post, .entry, [itemprop="blogPost"]')
    if article_indicators or soup.select('time, .byline, .author'):
        structure['has_article_structure'] = True
        structure['content_indicators'].append('article')
    
    # Product indicators
    product_indicators = soup.select('.price, [itemprop="price"], .add-to-cart, .buy-now')
    if product_indicators:
        structure['has_product_structure'] = True
        structure['content_indicators'].append('product')
    
    # Event indicators
    event_indicators = soup.select('[itemprop="startDate"], .event-date, .calendar')
    if event_indicators:
        structure['has_event_structure'] = True
        structure['content_indicators'].append('event')
    
    # Business indicators
    business_indicators = soup.select('[itemprop="address"], .address, .phone, .hours')
    if business_indicators:
        structure['has_business_structure'] = True
        structure['content_indicators'].append('business')
    
    return structure

def extract_seo_indicators(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract SEO-related indicators that help with schema type detection"""
    seo_data = {
        'meta_robots': None,
        'canonical_url': None,
        'hreflang': [],
        'schema_hints': []
    }
    
    # Meta robots
    robots_tag = soup.select_one('meta[name="robots"]')
    if robots_tag:
        seo_data['meta_robots'] = robots_tag.get('content', '')
    
    # Canonical URL
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical:
        seo_data['canonical_url'] = canonical.get('href', '')
    
    # Hreflang
    hreflang_tags = soup.select('link[rel="alternate"][hreflang]')
    for tag in hreflang_tags:
        seo_data['hreflang'].append({
            'lang': tag.get('hreflang'),
            'url': tag.get('href')
        })
    
    return seo_data

def extract_contact_information(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract contact information"""
    contact_data = {
        'emails': [],
        'phones': [],
        'social_links': []
    }
    
    # Email addresses
    email_links = soup.find_all('a', href=lambda x: x and x.startswith('mailto:'))
    for link in email_links:
        email = link.get('href', '').replace('mailto:', '')
        if email:
            contact_data['emails'].append(email)
    
    # Phone numbers
    phone_links = soup.find_all('a', href=lambda x: x and x.startswith('tel:'))
    for link in phone_links:
        phone = link.get('href', '').replace('tel:', '')
        if phone:
            contact_data['phones'].append(phone)
    
    # Social media links
    social_domains = ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com']
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        for domain in social_domains:
            if domain in href:
                contact_data['social_links'].append({
                    'platform': domain.split('.')[0],
                    'url': href
                })
                break
    
    return contact_data

def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
    """Extract canonical URL"""
    canonical = soup.select_one('link[rel="canonical"]')
    return canonical.get('href') if canonical else None

# --- Enhanced Web Scraping Function ---
def fetch_content(url):
    """
    Legacy function maintained for backward compatibility.
    Returns simplified structure matching original format.
    """
    try:
        comprehensive_data = fetch_comprehensive_content(url)
        
        # Extract basic data in original format for compatibility
        title = comprehensive_data['basic_metadata']['title']
        description = comprehensive_data['basic_metadata']['description']
        
        # Get dates from comprehensive extraction
        dates = []
        if comprehensive_data['publication_info']['published_date']:
            dates.append(comprehensive_data['publication_info']['published_date'])
        if comprehensive_data['publication_info']['modified_date']:
            dates.append(comprehensive_data['publication_info']['modified_date'])
        
        # Add dates from comprehensive extraction
        for date_info in comprehensive_data['publication_info']['dates_found']:
            if date_info['value'] not in dates:
                dates.append(date_info['value'])
        
        # Get images from comprehensive extraction
        images = [img['src'] for img in comprehensive_data['media_content']['images'][:5]]
        
        return {
            "title": title,
            "description": description, 
            "dates": dates,
            "images": images,
            "comprehensive_data": comprehensive_data  # Include full data for advanced processing
        }
        
    except Exception as e:
        st.error(f"Error during content extraction: {e}")
        return {"title": "", "description": "", "dates": [], "images": [], "comprehensive_data": None}

# --- Enhanced Gemini Inference Function ---

def analyze_url_patterns(url: str) -> str:
    """Analyze URL patterns to provide hints about content type"""
    url_lower = url.lower()
    
    patterns = {
        'product': ['/product/', '/item/', '/buy/', '/shop/', '/store/'],
        'article': ['/article/', '/post/', '/blog/', '/news/', '/story/'],
        'event': ['/event/', '/calendar/', '/conference/', '/meeting/'],
        'business': ['/about/', '/contact/', '/location/', '/store-locator/'],
        'recipe': ['/recipe/', '/cooking/', '/food/'],
        'review': ['/review/', '/rating/'],
        'job': ['/job/', '/career/', '/hiring/']
    }
    
    detected_patterns = []
    for content_type, url_patterns in patterns.items():
        if any(pattern in url_lower for pattern in url_patterns):
            detected_patterns.append(content_type)
    
    return ', '.join(detected_patterns) if detected_patterns else 'generic'

def format_address(address_dict: dict) -> str:
    """Format address dictionary into readable string"""
    if not address_dict:
        return 'None'
    
    components = []
    for key in ['street', 'city', 'state', 'postal_code', 'country']:
        if address_dict.get(key):
            components.append(address_dict[key])
    
    return ', '.join(components) if components else 'None'

def extract_existing_types(existing_schema: dict) -> str:
    """Extract existing schema types from structured data"""
    types = []
    
    for json_ld in existing_schema['json_ld']:
        if isinstance(json_ld, dict):
            schema_type = json_ld.get('@type') or json_ld.get('type')
            if schema_type:
                if isinstance(schema_type, list):
                    types.extend(schema_type)
                else:
                    types.append(schema_type)
    
    for microdata in existing_schema['microdata']:
        if microdata.get('type'):
            types.append(microdata['type'].split('/')[-1])  # Get last part of URL
    
    return ', '.join(set(types)) if types else 'None'

def gemini_infer_schema_details_enhanced(comprehensive_data: dict, url: str):
    """
    Enhanced Gemini inference using comprehensive extracted data for better schema detection.
    """
    
    # Extract key information from comprehensive data
    basic_meta = comprehensive_data['basic_metadata']
    social_meta = comprehensive_data['social_metadata']
    content_analysis = comprehensive_data['content_analysis']
    author_info = comprehensive_data['author_info']
    pub_info = comprehensive_data['publication_info']
    product_data = comprehensive_data['product_data']
    event_data = comprehensive_data['event_data']
    business_info = comprehensive_data['business_info']
    page_structure = comprehensive_data['page_structure']
    existing_schema = comprehensive_data['structured_data']
    
    # Build context summary for Gemini
    context_summary = {
        'url_analysis': analyze_url_patterns(url),
        'content_indicators': page_structure['content_indicators'],
        'has_existing_schema': bool(existing_schema['json_ld']),
        'content_length': content_analysis['word_count'],
        'has_author': bool(author_info['authors']),
        'has_publication_date': bool(pub_info['published_date']),
        'has_product_indicators': bool(product_data['prices']),
        'has_event_indicators': bool(event_data['start_date']),
        'has_business_indicators': bool(business_info['address'])
    }
    
    # Create enhanced prompt
    prompt = f"""You are an expert in Schema.org JSON-LD markup. Analyze this comprehensive web page data to determine the most appropriate Schema.org type and properties.

**URL:** {url}
**URL Pattern Analysis:** {context_summary['url_analysis']}

**Page Content Analysis:**
- Title: {basic_meta['title']}
- Description: {basic_meta['description']}
- Content Length: {content_analysis['word_count']} words
- Main Content Preview: {content_analysis['main_text'][:500]}...
- Content Indicators: {', '.join(context_summary['content_indicators'])}

**Author & Publication Info:**
- Authors: {', '.join(author_info['authors']) if author_info['authors'] else 'None'}
- Publisher: {author_info['publisher'] or 'None'}
- Published Date: {pub_info['published_date'] or 'None'}
- Modified Date: {pub_info['modified_date'] or 'None'}

**Product Information (if applicable):**
- Prices Found: {', '.join(product_data['prices'][:3]) if product_data['prices'] else 'None'}
- Brand: {product_data['brand'] or 'None'}
- Ratings: {', '.join(product_data['ratings'][:2]) if product_data['ratings'] else 'None'}

**Event Information (if applicable):**
- Start Date: {event_data['start_date'] or 'None'}
- Location: {event_data['location'] or 'None'}

**Business Information (if applicable):**
- Business Name: {business_info['name'] or 'None'}
- Address: {format_address(business_info['address'])}
- Phone: {business_info['phone'] or 'None'}

**Media Content:**
- Featured Image: {comprehensive_data['media_content']['featured_image'] or 'None'}
- Total Images: {len(comprehensive_data['media_content']['images'])}

**Social Media Metadata:**
- Open Graph Type: {social_meta['og'].get('type', 'None')}
- Article Tags: {', '.join([f"{k}: {v}" for k, v in social_meta['article'].items()][:3]) if social_meta['article'] else 'None'}

**Existing Structured Data:**
- Has JSON-LD: {bool(existing_schema['json_ld'])}
- Existing Types: {extract_existing_types(existing_schema)}

**Page Structure Indicators:**
- Has Article Structure: {page_structure['has_article_structure']}
- Has Product Structure: {page_structure['has_product_structure']}
- Has Event Structure: {page_structure['has_event_structure']}
- Has Business Structure: {page_structure['has_business_structure']}

Based on this comprehensive analysis, determine:
1. The SINGLE most appropriate primary Schema.org @type
2. All relevant properties with their values extracted from the data above

**IMPORTANT INSTRUCTIONS:**
- Consider URL patterns, content indicators, and existing structured data
- For articles: include author, publisher, datePublished, headline, articleBody summary
- For products: include price, brand, availability, ratings if found
- For events: include startDate, location, organizer if found  
- For businesses: include address components, phone, openingHours if found
- Always include: name, description, url, image (if available)
- If multiple schema types seem applicable, choose the MOST SPECIFIC one
- Omit properties with no meaningful data

**Output Format - JSON Only:**
```json
{{
  "type": "SchemaType",
  "confidence_score": 0.95,
  "reasoning": "Brief explanation of why this type was chosen",
  "properties": {{
    "name": "Page title or item name",
    "description": "Page description", 
    "url": "{url}",
    "image": "featured image URL or first image",
    // Include all other relevant properties based on the schema type
  }}
}}
```

Generate the JSON response now:"""

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        
        if not response.text:
            raise ValueError("Gemini returned an empty response")
            
        raw_json_str = response.text.strip()
        
        # Extract JSON from markdown code block
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

        parsed_response = json.loads(json_str)
        
        inferred_type = parsed_response.get("type", "WebPage").strip()
        confidence_score = parsed_response.get("confidence_score", 0.5)
        reasoning = parsed_response.get("reasoning", "No reasoning provided")
        inferred_properties = parsed_response.get("properties", {})

        return inferred_type, inferred_properties, confidence_score, reasoning

    except json.JSONDecodeError as e:
        st.error(f"Gemini output was not valid JSON. Error: {e}")
        st.code(f"Raw Gemini Output:\n{raw_json_str}", language="text")
        return "WebPage", {}, 0.0, "Failed to parse Gemini response"
    except Exception as e:
        st.error(f"Error during Gemini schema inference: {e}")
        return "WebPage", {}, 0.0, f"Error: {str(e)}"

# --- Original Gemini Inference Function (for backward compatibility) ---
def gemini_infer_schema_details(context: dict, url: str):
    """
    Original Gemini inference function maintained for backward compatibility.
    """
    # Use enhanced function if comprehensive data is available
    if 'comprehensive_data' in context and context['comprehensive_data']:
        return gemini_infer_schema_details_enhanced(context['comprehensive_data'], url)
    
    # Fallback to original simple inference
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
        "```json\n"
        "{json_example}\n"
        "```\n"
        "\n"
        "Now, generate the JSON output for the provided page content:\n"
    )

    prompt = prompt_template.format(
        page_title=context['title'],
        page_description=context['description'],
        first_date=context['dates'][0] if context['dates'] else 'N/A',
        image_urls=', '.join(context['images']) if context['images'] else 'N/A',
        original_url=url,
        json_example=example_json_content
    )

    model = genai.GenerativeModel("gemini-1.5-flash")
    try:
        response = model.generate_content(prompt)
        if not response.text:
            raise ValueError("Gemini returned an empty response.")
            
        raw_json_str = response.text.strip()
        
        if raw_json_str.startswith("```json"):
            json_str = raw_json_str[len("```json"):].strip()
            if json_str.endswith("```"):
                json_str = json_str[:-len("```")].strip()
            else:
                json_str = raw_json_str
        else:
            json_str = raw_json_str

        parsed_gemini_output = json.loads(json_str)

        inferred_type = parsed_gemini_output.get("type", "WebPage").strip()
        inferred_properties = parsed_gemini_output.get("properties", {})

        if not inferred_type:
            inferred_type = "WebPage"

        return inferred_type, inferred_properties

    except json.JSONDecodeError as e:
        st.error(f"Gemini output was not valid JSON. Error: {e}")
        st.code(f"Raw Gemini Output:\n{raw_json_str}", language="text")
        return "WebPage", {}
    except Exception as e:
        st.error(f"An error occurred during Gemini schema inference: {e}")
        return "WebPage", {}

# --- Schema.org Model Mapping ---
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
    "CreativeWork": CreativeWork,
    "Thing": Thing,
}

# --- Schema Object Builder Function ---
def build_schema_obj_from_inferred(inferred_type: str, inferred_properties: dict, original_url: str):
    """
    Constructs a msgspec_schemaorg object based on Gemini's inference,
    with robust type handling and fallbacks.
    """
    model_properties = {}

    SchemaModel = SCHEMA_MODEL_MAP.get(inferred_type)
    if not SchemaModel:
         st.warning(f"Schema.org type '{inferred_type}' is not explicitly supported by the application. Defaulting to WebPage.")
         SchemaModel = WebPage
         inferred_type = "WebPage" 

    model_properties["url"] = original_url
    
    for prop_name, prop_value in inferred_properties.items():
        if prop_value is None or (isinstance(prop_value, str) and prop_value.strip() in ["", "N/A"]):
            continue

        try:
            if prop_name in ["datePublished", "dateModified", "startDate", "endDate"]:
                if isinstance(prop_value, str) and prop_value:
                    model_properties[prop_name] = parse_iso8601(prop_value)
                else:
                    st.warning(f"Invalid date format for '{prop_name}': '{prop_value}'. Omitting.")
                    continue
            elif prop_name == "image":
                if isinstance(prop_value, str) and prop_value:
                    model_properties[prop_name] = prop_value
                else:
                    st.warning(f"Invalid image URL format for '{prop_name}': '{prop_value}'. Omitting.")
                    continue
            elif prop_name in ["price", "ratingValue", "reviewCount", "aggregateRating.ratingValue", "aggregateRating.reviewCount"]:
                try:
                    if isinstance(prop_value, str):
                        prop_value = prop_value.replace(',', '')
                    
                    if '.' in str(prop_value):
                        model_properties[prop_name] = float(prop_value)
                    else:
                        model_properties[prop_name] = int(prop_value)
                except ValueError:
                    st.warning(f"Invalid number format for '{prop_name}': '{prop_value}'. Omitting.")
                    continue
            else:
                model_properties[prop_name] = prop_value

        except Exception as e:
            st.warning(f"Failed to process property '{prop_name}' with value '{prop_value}': {e}. Omitting.")
            continue

    try:
        schema_instance = SchemaModel(**model_properties)
        return schema_instance
    except Exception as e:
        st.error(f"Schema.org model validation failed for '{inferred_type}' type with properties {model_properties}: {e}")
        st.warning("Attempting to generate a generic WebPage schema as a fallback due to model validation issues.")
        return WebPage(
            name=model_properties.get("name", "Generated WebPage"),
            description=model_properties.get("description", ""),
            url=original_url
        )

# --- JSON-LD Serialization Function ---
def to_jsonld(obj):
    """
    Converts a msgspec_schemaorg object to a pretty-printed JSON-LD string,
    ensuring @context and @type are present.
    """
    try:
        raw_bytes = msgspec.json.encode(obj)
        data = json.loads(raw_bytes.decode('utf-8'))
        
        if "@context" not in data:
            data["@context"] = "https://schema.org"
        
        ordered_data = {"@context": data.pop("@context")}
        if "@type" in data:
            ordered_data["@type"] = data.pop("@type")
        ordered_data.update(data)

        return json.dumps(ordered_data, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Critical error during final JSON-LD serialization: {e}")
        st.exception(e)
        return "Error: Could not generate final JSON-LD output."

# --- Streamlit UI ---
st.set_page_config(page_title="Schema.org JSON-LD Generator", page_icon="📘", layout="centered")

st.title("📘 Schema.org JSON‑LD Generator (Enhanced)")
st.markdown("""
This enhanced tool uses a comprehensive hybrid approach to generate Schema.org JSON-LD markup:

1.  **Advanced Content Scraping**: Extracts 15+ categories of metadata including social media tags, existing structured data, author info, product details, and more.
2.  **AI-Powered Analysis (Google Gemini)**: Uses comprehensive extracted data to intelligently determine the most appropriate Schema.org type with confidence scoring.
3.  **Robust Construction & Validation**: Builds validated JSON-LD using Python's `msgspec_schemaorg` library with comprehensive error handling.

**New Features:**
- 📊 Comprehensive content analysis with tabbed interface
- 🎯 Multi-signal schema type detection 
- 📈 Confidence scoring for AI recommendations
- 🔍 Detailed extraction reporting
- ✅ Built-in validation checks
""")

url = st.text_input("Enter a URL", placeholder="e.g., https://www.example.com/blog-post-about-ai", key="url_input")

if st.button("Generate Schema", key="generate_button"):
    if not url:
        st.warning("Please enter a URL to proceed.")
    elif not url.startswith(("http://", "https://")):
        st.warning("Please enter a valid URL, starting with `http://` or `https://`.")
    else:
        with st.spinner("Extracting comprehensive content... This may take a moment."):
            # Use the backward-compatible fetch_content function
            raw_data = fetch_content(url)
            comprehensive_data = raw_data.get('comprehensive_data')

            if not comprehensive_data:
                st.error("Could not fetch comprehensive content from the provided URL.")
                st.info("Ensure the URL is publicly accessible and contains standard HTML content.")
            else:
                # Display comprehensive extraction results
                st.subheader("🔍 Comprehensive Content Analysis")
                
                # Create tabs for different data categories
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["📄 Basic Info", "🏗️ Structure", "📊 Content Analysis", "🎯 Schema Hints", "🔧 Raw Data"])
                
                with tab1:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Basic Metadata:**")
                        basic_meta = comprehensive_data['basic_metadata']
                        st.write(f"• **Title:** {basic_meta['title']}")
                        st.write(f"• **Description:** {basic_meta['description'][:200]}{'...' if len(basic_meta['description']) > 200 else ''}")
                        st.write(f"• **Language:** {basic_meta['language'] or 'Not specified'}")
                        st.write(f"• **Keywords:** {', '.join(basic_meta['keywords'][:5]) if basic_meta['keywords'] else 'None found'}")
                        
                        st.write("**Publication Info:**")
                        pub_info = comprehensive_data['publication_info']
                        st.write(f"• **Published:** {pub_info['published_date'] or 'Not found'}")
                        st.write(f"• **Modified:** {pub_info['modified_date'] or 'Not found'}")
                        
                        st.write("**Author Information:**")
                        author_info = comprehensive_data['author_info']
                        st.write(f"• **Authors:** {', '.join(author_info['authors']) if author_info['authors'] else 'Not found'}")
                        st.write(f"• **Publisher:** {author_info['publisher'] or 'Not found'}")
                    
                    with col2:
                        st.write("**Media Content:**")
                        media_content = comprehensive_data['media_content']
                        st.write(f"• **Images found:** {len(media_content['images'])}")
                        st.write(f"• **Videos found:** {len(media_content['videos'])}")
                        if media_content['featured_image']:
                            st.write("• **Featured Image:**")
                            try:
                                st.image(media_content['featured_image'], width=200)
                            except:
                                st.write(f"  {media_content['featured_image']}")
                        
                        st.write("**Social Media Metadata:**")
                        social_meta = comprehensive_data['social_metadata']
                        if social_meta['og']:
                            st.write(f"• **Open Graph type:** {social_meta['og'].get('type', 'Not specified')}")
                            st.write(f"• **OG title:** {social_meta['og'].get('title', 'Not found')}")
                        if social_meta['twitter']:
                            st.write(f"• **Twitter card:** {social_meta['twitter'].get('card', 'Not found')}")

                with tab2:
                    st.write("**Page Structure Analysis:**")
                    structure = comprehensive_data['page_structure']
                    content_analysis = comprehensive_data['content_analysis']
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Content Type Indicators:**")
                        st.write(f"• Article structure: {'✅' if structure['has_article_structure'] else '❌'}")
                        st.write(f"• Product structure: {'✅' if structure['has_product_structure'] else '❌'}")
                        st.write(f"• Event structure: {'✅' if structure['has_event_structure'] else '❌'}")
                        st.write(f"• Business structure: {'✅' if structure['has_business_structure'] else '❌'}")
                        
                        st.write("**Content Metrics:**")
                        st.write(f"• Word count: {content_analysis['word_count']:,}")
                        st.write(f"• Paragraphs: {content_analysis['paragraphs_count']}")
                        st.write(f"• Headings: {len(content_analysis['headings'])}")
                        st.write(f"• Has forms: {'Yes' if content_analysis['has_forms'] else 'No'}")
                        st.write(f"• Has tables: {'Yes' if content_analysis['has_tables'] else 'No'}")
                    
                    with col2:
                        if content_analysis['headings']:
                            st.write("**Heading Structure:**")
                            for heading in content_analysis['headings'][:8]:  # Show first 8 headings
                                indent = "  " * (heading['level'] - 1)
                                st.write(f"{indent}H{heading['level']}: {heading['text'][:60]}{'...' if len(heading['text']) > 60 else ''}")

                with tab3:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Product data
                        product_data = comprehensive_data['product_data']
                        if any(product_data.values()):
                            st.write("**Product Information:**")
                            if product_data['prices']:
                                st.write(f"• **Prices:** {', '.join(product_data['prices'][:3])}")
                            if product_data['brand']:
                                st.write(f"• **Brand:** {product_data['brand']}")
                            if product_data['ratings']:
                                st.write(f"• **Ratings:** {', '.join(product_data['ratings'][:2])}")
                        
                        # Event data
                        event_data = comprehensive_data['event_data']
                        if any(event_data.values()):
                            st.write("**Event Information:**")
                            if event_data['start_date']:
                                st.write(f"• **Start Date:** {event_data['start_date']}")
                            if event_data['location']:
                                st.write(f"• **Location:** {event_data['location']}")
                    
                    with col2:
                        # Business data
                        business_info = comprehensive_data['business_info']
                        if any(business_info.values()) and business_info['address']:
                            st.write("**Business Information:**")
                            if business_info['name']:
                                st.write(f"• **Name:** {business_info['name']}")
                            if business_info['address']:
                                formatted_address = format_address(business_info['address'])
                                if formatted_address != 'None':
                                    st.write(f"• **Address:** {formatted_address}")
                            if business_info['phone']:
                                st.write(f"• **Phone:** {business_info['phone']}")
                        
                        # Contact info
                        contact_info = comprehensive_data['contact_info']
                        if any(contact_info.values()):
                            st.write("**Contact Information:**")
                            if contact_info['emails']:
                                st.write(f"• **Emails:** {', '.join(contact_info['emails'][:2])}")
                            if contact_info['social_links']:
                                platforms = [link['platform'] for link in contact_info['social_links'][:3]]
                                st.write(f"• **Social Media:** {', '.join(platforms)}")

                with tab4:
                    st.write("**Schema.org Detection Hints:**")
                    
                    # URL analysis
                    url_patterns = analyze_url_patterns(url)
                    st.write(f"**URL Pattern Analysis:** {url_patterns}")
                    
                    # Existing structured data
                    existing_schema = comprehensive_data['structured_data']
                    if existing_schema['json_ld']:
                        st.write("**Existing JSON-LD found:**")
                        for i, schema in enumerate(existing_schema['json_ld'][:2]):  # Show first 2
                            schema_type = schema.get('@type', 'Unknown')
                            st.write(f"• Schema {i+1}: {schema_type}")
                    
                    if existing_schema['microdata']:
                        st.write("**Existing Microdata found:**")
                        for item in existing_schema['microdata'][:3]:  # Show first 3
                            st.write(f"• Type: {item.get('type', 'Unknown')}")
                    
                    # Content indicators
                    st.write(f"**Content Type Indicators:** {', '.join(structure['content_indicators'])}")

                with tab5:
                    st.write("**Raw Comprehensive Data (for debugging):**")
                    st.json(comprehensive_data)

                # Enhanced Gemini inference
                st.subheader("🤖 AI-Powered Schema Analysis")
                
                with st.spinner("Analyzing content with Gemini AI..."):
                    inferred_type, inferred_properties, confidence_score, reasoning = gemini_infer_schema_details_enhanced(
                        comprehensive_data, url
                    )

                # Display AI analysis results
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Schema Type", inferred_type)
                with col2:
                    st.metric("Confidence Score", f"{confidence_score:.2f}")
                with col3:
                    st.metric("Properties Found", len(inferred_properties))

                st.write(f"**AI Reasoning:** {reasoning}")

                # Build and display final schema
                st.subheader("✅ Generated Schema.org JSON-LD")
                
                # Use the enhanced inference results
                schema_obj = build_schema_obj_from_inferred(inferred_type, inferred_properties, url)
                jsonld_output = to_jsonld(schema_obj)

                st.code(jsonld_output, language="json")

                # Enhanced download and validation section
                col1, col2 = st.columns(2)
                with col1:
                    if "Error" not in jsonld_output:
                        st.download_button(
                            "📥 Download JSON-LD",
                            data=jsonld_output,
                            file_name=f"schema-{inferred_type.lower()}.jsonld",
                            mime="application/ld+json",
                            key="download_button"
                        )

                with col2:
                    st.write("**Quick Validation:**")
                    # Basic validation checks
                    try:
                        parsed_json = json.loads(jsonld_output)
                        checks = {
                            "Valid JSON": "✅",
                            "Has @context": "✅" if "@context" in parsed_json else "❌",
                            "Has @type": "✅" if "@type" in parsed_json else "❌",
                            "Has name": "✅" if "name" in parsed_json else "❌",
                            "Has URL": "✅" if "url" in parsed_json else "❌"
                        }
                        for check, status in checks.items():
                            st.write(f"{status} {check}")
                    except:
                        st.write("❌ Invalid JSON structure")

                st.markdown(
                    """
                    ---
                    **🔧 Validation Tools:**
                    
                    • [Google Rich Results Test](https://search.google.com/test/rich-results) - Test for Google Search
                    • [Schema Markup Validator](https://validator.schema.org/) - Official Schema.org validator
                    • [JSON-LD Playground](https://json-ld.org/playground/) - Test JSON-LD syntax
                    """
                )

st.markdown(
    """
    ---
    *Built with ❤️ using Google Gemini, msgspec_schemaorg, and comprehensive web scraping.*
    
    **Enhanced Features:**
    - 🔍 15+ categories of content extraction
    - 🤖 AI-powered schema type detection with confidence scoring
    - 📊 Comprehensive analysis dashboard
    - ✅ Built-in validation and quality checks
    """
)
