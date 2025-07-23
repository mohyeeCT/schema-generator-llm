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
            "author": {
                "@type": "Person",
                "name": "",
                "url": ""
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
            "keywords": [],
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": ""
            }
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
                "affiliation": {
                    "@type": "Organization",
                    "name": ""
                }
            }],
            "publisher": {
                "@type": "Organization",
                "name": ""
            },
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
            "author": {
                "@type": "Person",
                "name": ""
            },
            "datePublished": "",
            "prepTime": "",
            "cookTime": "",
            "totalTime": "",
            "recipeYield": "",
            "recipeCategory": "",
            "recipeCuisine": "",
            "recipeIngredient": [],
            "recipeInstructions": [],
            "nutrition": {
                "@type": "NutritionInformation",
                "calories": ""
            },
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
            "organizer": {
                "@type": "Organization",
                "name": "",
                "url": ""
            },
            "offers": {
                "@type": "Offer",
                "price": "",
                "priceCurrency": "",
                "availability": "",
                "url": ""
            },
            "performer": {
                "@type": "Person",
                "name": ""
            },
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
                "logo": {
                    "@type": "ImageObject",
                    "url": ""
                }
            },
            "creator": {
                "@type": "Person",
                "name": ""
            },
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
            "author": {
                "@type": "Person",
                "name": ""
            },
            "itemReviewed": {
                "@type": "Thing",
                "name": ""
            },
            "datePublished": "",
            "publisher": {
                "@type": "Organization",
                "name": ""
            }
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
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": ""
                }
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
            "worksFor": {
                "@type": "Organization",
                "name": ""
            },
            "sameAs": [],
            "knowsAbout": [],
            "alumniOf": {
                "@type": "Organization",
                "name": ""
            },
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
            "publisher": {
                "@type": "Organization",
                "name": ""
            },
            "datePublished": "",
            "dateModified": "",
            "inLanguage": "",
            "mainEntity": {
                "@type": "Thing",
                "name": ""
            },
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
        "description": "Detailed entity schema emphasizing business expertise and knowledge"
    }
}

# --- Page Type Detection Functions ---

def detect_page_type(soup: BeautifulSoup, url: str) -> str:
    """Detect the type of page based on content and URL patterns"""
    url_lower = url.lower()
    
    # URL-based detection
    url_patterns = {
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
    
    for page_type, patterns in url_patterns.items():
        if any(pattern in url_lower for pattern in patterns if pattern):
            return page_type
    
    # Content-based detection
    page_text = soup.get_text().lower()
    title = soup.title.string.lower() if soup.title else ""
    
    # Check for specific content indicators
    if any(word in page_text for word in ['recipe', 'ingredients', 'cooking time']):
        return "Recipe Page"
    elif any(word in page_text for word in ['event', 'date:', 'location:', 'tickets']):
        return "Event Page"
    elif any(word in page_text for word in ['faq', 'frequently asked', 'questions']):
        return "FAQ Page"
    elif soup.find_all('article') or 'blog' in title:
        return "Blog Post"
    elif any(word in page_text for word in ['contact us', 'get in touch', 'phone:', 'email:']):
        return "Contact Us"
    elif any(word in page_text for word in ['about us', 'our company', 'our story']):
        return "About Us"
    elif any(word in page_text for word in ['price', 'buy now', 'add to cart']):
        return "Product Page"
    
    return "Homepage"

def extract_existing_schema(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract and analyze existing schema markup"""
    existing_schemas = {
        'json_ld': [],
        'microdata': [],
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
    
    # Analyze completeness
    if existing_schemas['json_ld']:
        schema = existing_schemas['json_ld'][0]
        required_props = ['name', 'url', 'description']
        present_props = [prop for prop in required_props if prop in schema]
        existing_schemas['analysis']['completeness_score'] = len(present_props) / len(required_props)
        
        # Enhanced recommendations based on schema type
        schema_type = schema.get('@type', '')
        if schema_type == 'Organization':
            if 'contactPoint' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add multi-department contact points")
            if 'sameAs' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add social media links")
            if 'address' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add structured address")
            if 'subjectOf' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add subject matter expertise")
            if 'knowsAbout' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add knowledge areas")
            if 'location' not in schema:
                existing_schemas['analysis']['recommendations'].append("Add location with map link")
    
    return existing_schemas

def fetch_comprehensive_content(url: str) -> Dict[str, Any]:
    """Enhanced content extraction with page type detection"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        content = {
            'url': url,
            'page_type': detect_page_type(soup, url),
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

        return content

    except requests.exceptions.Timeout:
        raise Exception(f"Request to {url} timed out")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching content: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error during content extraction: {e}")

def extract_entity_data(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Extract entity-related data for enhanced schema markup"""
    entity_data = {
        'business_focus': [],
        'expertise_areas': [],
        'industry_keywords': [],
        'related_topics': [],
        'wiki_topics': []
    }
    
    # Extract business focus from headings and content
    headings = soup.find_all(['h1', 'h2', 'h3'])
    for heading in headings:
        text = heading.get_text(strip=True).lower()
        if any(word in text for word in ['services', 'products', 'solutions', 'expertise']):
            entity_data['business_focus'].append(heading.get_text(strip=True))
    
    # Extract keywords from meta tags and content
    meta_keywords = soup.find("meta", {"name": "keywords"})
    if meta_keywords and meta_keywords.get("content"):
        keywords = [k.strip() for k in meta_keywords.get("content").split(",")]
        entity_data['industry_keywords'].extend(keywords)
    
    # Extract from content analysis
    content_text = soup.get_text().lower()
    
    # Industry-specific keyword extraction
    industry_terms = {
        'technology': ['software', 'digital', 'tech', 'innovation', 'development'],
        'manufacturing': ['precision', 'engineering', 'quality', 'production', 'manufacturing'],
        'healthcare': ['medical', 'health', 'clinical', 'patient', 'treatment'],
        'finance': ['financial', 'investment', 'banking', 'insurance', 'wealth'],
        'education': ['learning', 'education', 'training', 'academic', 'school'],
        'hardware': ['hardware', 'industrial', 'architectural', 'mechanical', 'precision'],
        'construction': ['construction', 'building', 'architecture', 'design', 'materials']
    }
    
    for industry, terms in industry_terms.items():
        if any(term in content_text for term in terms):
            entity_data['expertise_areas'].append(industry.title())
            # Add related Wikipedia topics
            wiki_topics = {
                'technology': ['Technology', 'Software', 'Innovation'],
                'manufacturing': ['Manufacturing', 'Engineering', 'Quality control'],
                'hardware': ['Hardware', 'Industrial design', 'Mechanical engineering'],
                'construction': ['Construction', 'Architecture', 'Building materials']
            }
            if industry in wiki_topics:
                entity_data['wiki_topics'].extend(wiki_topics[industry])
    
    return entity_data

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
    
    # Phone extraction with department detection
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
            # Try to detect department from surrounding text
            parent_text = link.parent.get_text().lower() if link.parent else ""
            department = "customer service"
            if 'sales' in parent_text:
                department = "sales"
            elif 'support' in parent_text:
                department = "technical support"
            elif 'industrial' in parent_text:
                department = "industrial"
            
            contact_info['contact_points'].append({
                'phone': phone,
                'department': department,
                'context': parent_text[:100]
            })
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
        'price_range': None
    }
    
    # Business name extraction with priority
    name_selectors = [
        '[itemprop="name"]',
        'h1',
        '.company-name',
        '.business-name',
        '[class*="name"]',
        '.logo-text'
    ]
    
    for selector in name_selectors:
        elem = soup.select_one(selector)
        if elem:
            name_text = elem.get_text(strip=True)
            if name_text and len(name_text) < 100:  # Reasonable company name length
                business_data['name'] = name_text
                break
    
    # Address extraction with multiple strategies
    address_selectors = {
        'street': ['[itemprop="streetAddress"]', '.street', '.address-line-1', '.street-address'],
        'city': ['[itemprop="addressLocality"]', '.city', '.locality', '.address-city'],
        'state': ['[itemprop="addressRegion"]', '.state', '.region', '.address-state'],
        'postal_code': ['[itemprop="postalCode"]', '.zip', '.postal-code', '.zipcode'],
        'country': ['[itemprop="addressCountry"]', '.country', '.address-country']
    }
    
    for addr_type, selectors in address_selectors.items():
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                addr_text = elem.get_text(strip=True)
                if addr_text:
                    business_data['address'][addr_type] = addr_text
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
                full_address = matches[0].strip()
                if len(full_address) < 200:  # Reasonable address length
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
