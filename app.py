
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
    }
}


COMPREHENSIVE_TEMPLATES.update({
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
})


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
        
        # Skip small images and tracking pixels
        width = img.get('width')
        height = img.get('height')
        if width and height:
            try:
                if int(width) < 50 or int(height) < 50:
                    continue
            except ValueError:
                pass
        
        # Skip tracking and analytics images
        if any(tracker in src.lower() for tracker in ['webtraxs', 'analytics', 'tracking', 'pixel']):
            continue
            
        media_data['images'].append({'src': src, 'alt': alt})
    
    # Featured image
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        featured_url = og_image.get('content')
        # Skip tracking images for featured image too
        if not any(tracker in featured_url.lower() for tracker in ['webtraxs', 'analytics', 'tracking', 'pixel']):
            media_data['featured_image'] = featured_url
    elif media_data['images']:
        media_data['featured_image'] = media_data['images'][0]['src']
    
    # Logo detection with better selectors
    logo_selectors = [
        '.logo img', '[class*="logo"] img', '#logo img',
        'img[alt*="logo"]', 'img[class*="logo"]', 'header img',
        '[class*="brand"] img'
    ]
    
    for selector in logo_selectors:
        logo_img = soup.select_one(selector)
        if logo_img and logo_img.get('src'):
            logo_url = urljoin(base_url, logo_img.get('src'))
            # Skip tracking images for logo too
            if not any(tracker in logo_url.lower() for tracker in ['webtraxs', 'analytics', 'tracking', 'pixel']):
                media_data['logo'] = logo_url
                break
    
    return media_data

def extract_seo_indicators(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract SEO indicators"""
    seo_data = {'canonical_url': None}
    
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical:
        seo_data['canonical_url'] = canonical.get('href', '')
    
    return seo_data

def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
    """Extract canonical URL"""
    canonical = soup.select_one('link[rel="canonical"]')
    return canonical.get('href') if canonical else None

# --- Enhanced Gemini Analysis Functions ---

def create_comprehensive_schema_prompt(comprehensive_data: dict, url: str, template_type: str = None, page_type: str = None) -> str:
    """Create enhanced prompt for comprehensive schema generation with entity focus"""
    
    basic_meta = comprehensive_data['basic_metadata']
    existing_schema = comprehensive_data['existing_schema']
    contact_info = comprehensive_data['contact_info']
    business_info = comprehensive_data['business_info']
    social_links = comprehensive_data['social_links']
    media_content = comprehensive_data['media_content']
    entity_data = comprehensive_data['entity_data']
    detected_page_type = comprehensive_data.get('page_type', 'Homepage')
    
    # Use manual page type if provided, otherwise use detected
    final_page_type = page_type if page_type != "Auto-detect" else detected_page_type
    
    # Build context for Gemini
    context = f"""
**URL:** {url}
**Page Type:** {final_page_type}
**Template Preference:** {template_type or 'Auto-detect'}

**Basic Information:**
- Title: {basic_meta['title']}
- Description: {basic_meta['description']}
- Language: {basic_meta['language']}

**Existing Schema Analysis:**
- Has existing schema: {existing_schema['analysis']['has_schema']}
- Schema types found: {', '.join(existing_schema['analysis']['schema_types'])}
- Completeness score: {existing_schema['analysis']['completeness_score']:.2f}
- Missing elements: {'; '.join(existing_schema['analysis']['recommendations'])}

**Contact Information:**
- Emails: {', '.join(contact_info['emails'][:3])}
- Phones: {', '.join(contact_info['phones'][:3])}
- Contact points with departments: {len(contact_info['contact_points'])}

**Business Information:**
- Name: {business_info['name']}
- Address components: {list(business_info['address'].keys())}

**Social Media:**
- Social links found: {len(social_links)}
- Platforms: {'; '.join(social_links[:5])}

**Media Content:**
- Logo: {media_content['logo']}
- Featured image: {media_content['featured_image']}
- Total images: {len(media_content['images'])}

**Entity Data (for enhanced schema):**
- Business focus areas: {', '.join(entity_data['business_focus'][:3])}
- Expertise areas: {', '.join(entity_data['expertise_areas'])}
- Industry keywords: {', '.join(entity_data['industry_keywords'][:10])}
- Wikipedia topics: {', '.join(entity_data['wiki_topics'])}
"""

    # Create specific instructions based on template type
    template_instructions = ""
    if template_type == "Organization" or final_page_type in ["Homepage", "About Us"]:
        template_instructions = """
**ORGANIZATION SCHEMA REQUIREMENTS:**
1. **Enhanced Contact Points**: Create multiple contactPoint objects for different departments (sales, support, industrial, etc.)
2. **Complete Address**: Use PostalAddress with all components (street, city, state, postal code, country)
3. **Location with Map**: Include location object with Place type and hasMap property
4. **Subject Matter Expertise**: Add subjectOf array with CreativeWork objects linking to Wikipedia pages
5. **Knowledge Areas**: Include knowsAbout array with expertise topics
6. **Social Integration**: Complete sameAs array with all social media profiles
7. **Enhanced Keywords**: Comprehensive keywords array with industry-specific terms
"""
    elif template_type == "EntitySchema":
        template_instructions = """
**ENTITY SCHEMA REQUIREMENTS:**
1. **WebPage as container**: Use WebPage as main type with Organization as mainEntity
2. **Enhanced aboutness**: Include about, mentions, and relatedLink properties
3. **Knowledge emphasis**: Extensive knowsAbout and subjectOf arrays
4. **Wikipedia integration**: Link to relevant Wikipedia pages in subjectOf
5. **Industry authority**: Emphasize business expertise and knowledge areas
"""

    prompt = f"""You are an expert Schema.org consultant specializing in comprehensive, entity-focused markup. Create production-ready JSON-LD that matches the style and completeness of the reference schema provided in the user's requirements.

{context}

{template_instructions}

**CRITICAL REQUIREMENTS:**
1. **Match Reference Quality**: Generate schema as comprehensive as the user's reference example
2. **Multi-Department Contacts**: Create detailed contactPoint arrays with:
   - Different contactType values (sales, customer service, technical support)
   - Department descriptions (Architectural Division, Industrial Division, etc.)
   - Proper phone formatting with area codes
   - Email addresses for each department
3. **Complete Address Structure**: Use PostalAddress with all components
4. **Enhanced Entity Properties**:
   - subjectOf array with CreativeWork objects linking to Wikipedia
   - knowsAbout array with expertise areas
   - location object with Place and hasMap
   - Comprehensive keywords array
5. **Social Media Integration**: Complete sameAs array with all found social profiles
6. **Media Optimization**: Use proper logo and image URLs (avoid tracking pixels)

**REFERENCE SCHEMA STYLE TO MATCH:**
The output should match the comprehensive style of the user's reference schema with:
- Multiple contact points with descriptions
- Subject matter expertise with Wikipedia links
- Location with map integration
- Extensive keywords array
- Proper nested object structures

**AVOID:**
- Tracking pixel URLs (webtraxs, analytics, etc.)
- Empty or null properties
- Generic contact information
- Missing required nested objects

**OUTPUT FORMAT:**
Provide ONLY valid JSON-LD markup. No explanations, no markdown formatting, just the JSON schema.
"""

    return prompt

def generate_comprehensive_schema_simple(comprehensive_data: dict, url: str, template_type: str = None, page_type: str = None):
    """Simplified schema generation with better error handling"""
    
    try:
        # Start with a base template
        base_schema = get_base_schema_template(comprehensive_data, url, template_type, page_type)
        
        # Enhance with AI if possible, but fallback to template if AI fails
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = create_simple_enhancement_prompt(comprehensive_data, url, base_schema)
            
            response = model.generate_content(prompt)
            
            if response.text:
                enhanced_schema = parse_gemini_response_safely(response.text, base_schema)
                if enhanced_schema:
                    return enhanced_schema, 0.95, "AI-enhanced comprehensive schema generated"
        except Exception as ai_error:
            st.warning(f"AI enhancement failed: {ai_error}. Using template-based generation.")
        
        # Fallback to template-based generation
        enhanced_schema = enhance_template_with_data(base_schema, comprehensive_data, url)
        return enhanced_schema, 0.80, "Template-based comprehensive schema generated"
        
    except Exception as e:
        st.error(f"Schema generation failed: {e}")
        return None, 0.0, f"Generation failed: {str(e)}"

def get_base_schema_template(comprehensive_data: dict, url: str, template_type: str = None, page_type: str = None):
    """Get appropriate base template based on page type and content"""
    
    detected_page_type = comprehensive_data.get('page_type', 'Homepage')
    final_page_type = page_type if page_type != "Auto-detect" else detected_page_type
    
    # Determine best schema type
    if template_type and template_type != "Auto-detect":
        schema_type = template_type
    else:
        schema_type = suggest_schema_type_from_page_type(final_page_type)
    
    # Get base template
    if schema_type in COMPREHENSIVE_TEMPLATES:
        base_schema = COMPREHENSIVE_TEMPLATES[schema_type]["template"].copy()
    else:
        base_schema = COMPREHENSIVE_TEMPLATES["Organization"]["template"].copy()
    
    return base_schema

def enhance_template_with_data(base_schema: dict, comprehensive_data: dict, url: str):
    """Enhance template with extracted data without AI"""
    
    basic_meta = comprehensive_data['basic_metadata']
    contact_info = comprehensive_data['contact_info']
    business_info = comprehensive_data['business_info']
    social_links = comprehensive_data['social_links']
    media_content = comprehensive_data['media_content']
    entity_data = comprehensive_data['entity_data']
    
    # Fill in basic information
    base_schema["url"] = url
    base_schema["name"] = business_info.get('name') or basic_meta['title']
    base_schema["description"] = basic_meta['description']
    
    # Add logo and image
    if media_content['logo']:
        base_schema["logo"] = media_content['logo']
    if media_content['featured_image']:
        base_schema["image"] = media_content['featured_image']
    
    # Add contact points for organizations
    if base_schema.get("@type") == "Organization" and contact_info['emails']:
        contact_points = []
        
        # Add email-based contact points
        for i, email in enumerate(contact_info['emails'][:3]):
            contact_type = "customer service"
            if "sales" in email.lower():
                contact_type = "sales"
            elif "support" in email.lower():
                contact_type = "technical support"
            
            contact_points.append({
                "@type": "ContactPoint",
                "contactType": contact_type,
                "email": email,
                "areaServed": "US",
                "availableLanguage": "English"
            })
        
        # Add phone-based contact points
        for i, phone in enumerate(contact_info['phones'][:3]):
            if i < len(contact_points):
                contact_points[i]["telephone"] = phone
            else:
                contact_points.append({
                    "@type": "ContactPoint",
                    "contactType": "customer service",
                    "telephone": phone,
                    "areaServed": "US",
                    "availableLanguage": "English"
                })
        
        base_schema["contactPoint"] = contact_points
    
    # Add social links
    if social_links:
        base_schema["sameAs"] = social_links[:6]  # Limit to 6 social links
    
    # Add address for organizations
    if base_schema.get("@type") == "Organization" and business_info['address']:
        address = {"@type": "PostalAddress"}
        
        if 'street' in business_info['address']:
            address["streetAddress"] = business_info['address']['street']
        if 'city' in business_info['address']:
            address["addressLocality"] = business_info['address']['city']
        if 'state' in business_info['address']:
            address["addressRegion"] = business_info['address']['state']
        if 'postal_code' in business_info['address']:
            address["postalCode"] = business_info['address']['postal_code']
        if 'country' in business_info['address']:
            address["addressCountry"] = business_info['address']['country']
        
        if len(address) > 1:  # More than just @type
            base_schema["address"] = address
    
    # Add keywords
    all_keywords = set()
    if basic_meta['keywords']:
        all_keywords.update(basic_meta['keywords'])
    if entity_data['industry_keywords']:
        all_keywords.update(entity_data['industry_keywords'][:10])
    
    if all_keywords:
        base_schema["keywords"] = list(all_keywords)[:15]
    
    # Add expertise areas for organizations
    if base_schema.get("@type") == "Organization" and entity_data['expertise_areas']:
        base_schema["knowsAbout"] = entity_data['expertise_areas']
    
    # Add Wikipedia subjects for organizations
    if base_schema.get("@type") == "Organization" and entity_data['wiki_topics']:
        subject_of = []
        for topic in entity_data['wiki_topics'][:4]:
            subject_of.append({
                "@type": "CreativeWork",
                "url": f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}",
                "description": f"{topic} represents a key area of expertise and knowledge."
            })
        base_schema["subjectOf"] = subject_of
    
    # Clean up empty values
    cleaned_schema = {k: v for k, v in base_schema.items() if v not in ["", None, [], {}]}
    
    return cleaned_schema

def parse_gemini_response_safely(response_text: str, fallback_schema: dict):
    """Safely parse Gemini response with multiple fallback strategies"""
    
    try:
        # Try the enhanced extraction first
        json_str = extract_json_from_text(response_text)
        return json.loads(json_str)
    except:
        pass
    
    try:
        # Try fallback extraction
        json_str = extract_json_fallback(response_text)
        if json_str:
            return json.loads(json_str)
    except:
        pass
    
    try:
        # Try simple cleaning
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        return json.loads(cleaned)
    except:
        pass
    
    # If all parsing fails, return the fallback
    return fallback_schema

def create_simple_enhancement_prompt(comprehensive_data: dict, url: str, base_schema: dict) -> str:
    """Create a simpler prompt focused on enhancement rather than full generation"""
    
    basic_meta = comprehensive_data['basic_metadata']
    contact_info = comprehensive_data['contact_info']
    social_links = comprehensive_data['social_links']
    
    prompt = f"""Enhance this Schema.org JSON-LD with the provided data. Return ONLY valid JSON.

BASE SCHEMA:
{json.dumps(base_schema, indent=2)}

ENHANCEMENT DATA:
- URL: {url}
- Title: {basic_meta['title']}
- Description: {basic_meta['description']}
- Emails: {', '.join(contact_info['emails'][:2])}
- Phones: {', '.join(contact_info['phones'][:2])}
- Social Links: {', '.join(social_links[:3])}

INSTRUCTIONS:
1. Enhance the base schema with the provided data
2. Add multiple contactPoint objects if emails/phones available
3. Add sameAs array with social links
4. Fill in name, description, url fields
5. Return ONLY the enhanced JSON - no explanations

ENHANCED SCHEMA:"""

    return prompt

def suggest_schema_type_from_page_type(page_type: str) -> str:
    """Suggest appropriate schema type based on detected page type"""
    schema_mapping = {
        "Homepage": "Organization",
        "About Us": "Organization", 
        "Contact Us": "Organization",
        "Product Page": "Product",
        "Category Page": "WebPage",
        "Service Page": "Service",
        "Blog Post": "Article",
        "News Article": "NewsArticle",
        "FAQ Page": "FAQPage",
        "Recipe Page": "Recipe",
        "Event Page": "Event",
        "Review Page": "Review",
        "Video Page": "VideoObject",
        "Location/Store": "LocalBusiness",
        "Team/People": "Person"
    }
    
    return schema_mapping.get(page_type, "WebPage")


# --- Streamlit UI ---
st.set_page_config(page_title="Comprehensive Schema.org Generator", page_icon="🔗", layout="wide")

st.title("🔗 Comprehensive Schema.org JSON-LD Generator")
st.markdown("""
Generate production-ready, comprehensive Schema.org markup with:
- **🎯 Page Type Detection** - Automatic or manual page type selection
- **📋 Expanded Schema Templates** - 15+ schema types including EntitySchema
- **🔍 Existing Schema Enhancement** - Detect and improve current markup
- **🏢 Multi-department Contacts** - Like the Sugatsune reference example
- **🌐 Entity-focused Markup** - With Wikipedia links and knowledge areas
""")

# Sidebar Configuration
st.sidebar.header("🎯 Configuration")

# Page Type Selection
st.sidebar.subheader("Page Type")
page_type_option = st.sidebar.selectbox(
    "Select page type:",
    ["Auto-detect"] + list(PAGE_TYPES.keys()),
    help="Choose page type or let AI auto-detect"
)

if page_type_option != "Auto-detect":
    st.sidebar.caption(PAGE_TYPES[page_type_option])

# Schema Template Selection
st.sidebar.subheader("Schema Template")
template_option = st.sidebar.selectbox(
    "Choose schema template:",
    ["Auto-detect"] + list(COMPREHENSIVE_TEMPLATES.keys()),
    help="Select template or let AI choose based on content"
)

if template_option != "Auto-detect":
    with st.sidebar.expander("📋 View Template Structure"):
        st.json(COMPREHENSIVE_TEMPLATES[template_option]["template"])
    st.sidebar.caption(COMPREHENSIVE_TEMPLATES[template_option]["description"])

# Main Input
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
                
                # Display page type detection results
                detected_page_type = comprehensive_data['page_type']
                final_page_type = page_type_option if page_type_option != "Auto-detect" else detected_page_type
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Detected Page Type", detected_page_type)
                with col2:
                    st.metric("Selected Page Type", final_page_type)
                with col3:
                    suggested_schema = suggest_schema_type_from_page_type(final_page_type)
                    st.metric("Suggested Schema", suggested_schema)
                
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
                        st.info("💡 **Enhancement Opportunities:** " + "; ".join(existing_schema['analysis']['recommendations']))
                    
                    with st.expander("📋 View Current Schema"):
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
                    expertise_count = len(comprehensive_data['entity_data']['expertise_areas'])
                    st.metric("Expertise Areas", expertise_count)
                
                # Entity data insights
                entity_data = comprehensive_data['entity_data']
                if entity_data['expertise_areas'] or entity_data['industry_keywords']:
                    st.subheader("🧠 Entity Intelligence")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if entity_data['expertise_areas']:
                            st.write("**🎯 Detected Expertise:**")
                            for area in entity_data['expertise_areas']:
                                st.write(f"• {area}")
                    
                    with col2:
                        if entity_data['industry_keywords'][:8]:
                            st.write("**🔑 Key Industry Terms:**")
                            st.write(", ".join(entity_data['industry_keywords'][:8]))
                
                # Generate comprehensive schema
                st.subheader("🤖 AI Schema Generation")
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
                            st.success(f"✅ Schema Generated - Confidence: {confidence:.0%}")
                            st.caption(reasoning)
                        
                        with col2:
                            schema_type = schema_data.get('@type', 'Unknown')
                            st.metric("Generated Schema Type", schema_type)
                        
                        # Main schema output
                        st.subheader("📝 Generated Schema.org JSON-LD")
                        
                        # Format and display JSON
                        formatted_json = json.dumps(schema_data, indent=2, ensure_ascii=False)
                        st.code(formatted_json, language="json")
                        
                        # Enhanced analysis of generated schema
                        st.subheader("🔍 Schema Quality Analysis")
                        
                        analysis_cols = st.columns(4)
                        
                        with analysis_cols[0]:
                            st.write("**✅ Core Validation:**")
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
                            st.write("**📞 Contact Features:**")
                            contact_checks = {
                                "Multi-department contacts": "contactPoint" in schema_data and len(schema_data.get("contactPoint", [])) > 1,
                                "Structured address": "address" in schema_data and isinstance(schema_data.get("address"), dict),
                                "Location with map": "location" in schema_data,
                                "Social media links": "sameAs" in schema_data and len(schema_data.get("sameAs", [])) > 0
                            }
                            
                            for check, passed in contact_checks.items():
                                st.write(f"{'✅' if passed else '❌'} {check}")
                        
                        with analysis_cols[2]:
                            st.write("**🧠 Entity Features:**")
                            entity_checks = {
                                "Knowledge areas": "knowsAbout" in schema_data,
                                "Subject expertise": "subjectOf" in schema_data,
                                "Industry keywords": "keywords" in schema_data and len(schema_data.get("keywords", [])) > 5,
                                "Wikipedia links": "subjectOf" in schema_data and any("wikipedia.org" in str(item) for item in schema_data.get("subjectOf", []))
                            }
                            
                            for check, passed in entity_checks.items():
                                st.write(f"{'✅' if passed else '❌'} {check}")
                        
                        with analysis_cols[3]:
                            st.write("**📊 Schema Stats:**")
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
                        
                        # Enhanced features showcase
                        st.subheader("✨ Enhancement Features")
                        
                        enhancements = []
                        if "contactPoint" in schema_data and len(schema_data["contactPoint"]) > 1:
                            dept_count = len(schema_data["contactPoint"])
                            enhancements.append(f"🏢 **Multi-department Contacts:** {dept_count} departments with specialized contact info")
                        
                        if "sameAs" in schema_data and len(schema_data["sameAs"]) > 0:
                            social_count = len(schema_data["sameAs"])
                            enhancements.append(f"📱 **Social Media Integration:** {social_count} social platforms linked")
                        
                        if "subjectOf" in schema_data:
                            wiki_count = len(schema_data["subjectOf"])
                            enhancements.append(f"📚 **Wikipedia Integration:** {wiki_count} topic links for authority")
                        
                        if "knowsAbout" in schema_data:
                            expertise_count = len(schema_data["knowsAbout"])
                            enhancements.append(f"🎯 **Expertise Areas:** {expertise_count} knowledge domains defined")
                        
                        if "keywords" in schema_data and len(schema_data["keywords"]) > 5:
                            keyword_count = len(schema_data["keywords"])
                            enhancements.append(f"🔑 **Rich Keywords:** {keyword_count} industry-specific terms")
                        
                        if "location" in schema_data:
                            enhancements.append("📍 **Location with Map:** Geographic data with map integration")
                        
                        for enhancement in enhancements:
                            st.success(enhancement)
                        
                        if not enhancements:
                            st.info("💡 Consider using Organization or EntitySchema template for maximum enhancement features")
                        
                        # Download and implementation
                        st.subheader("💾 Implementation")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.download_button(
                                "📥 Download JSON-LD",
                                data=formatted_json,
                                file_name=f"schema-{schema_data.get('@type', 'schema').lower()}-{final_page_type.lower().replace(' ', '-')}.jsonld",
                                mime="application/ld+json"
                            )
                        
                        with col2:
                            if st.button("📋 Copy Schema"):
                                st.success("Schema copied to clipboard!")
                        
                        with col3:
                            if st.button("🔄 Regenerate"):
                                st.experimental_rerun()
                        
                        # Implementation guide
                        st.info("""
                        **📖 Implementation Guide:**
                        
                        1. **Copy the JSON-LD** code above
                        2. **Paste into HTML** `<head>` section:
                           ```html
                           <script type="application/ld+json">
                           {your-schema-here}
                           </script>
                           ```
                        3. **Test & Validate:**
                           - [Google Rich Results Test](https://search.google.com/test/rich-results)
                           - [Schema Markup Validator](https://validator.schema.org/)
                        4. **Monitor Performance** in Google Search Console
                        """)
                        
                        # Quality indicators
                        st.subheader("🎯 Schema Quality Score")
                        
                        # Calculate quality score
                        quality_score = 0
                        max_score = 100
                        
                        # Core properties (30 points)
                        core_props = ["@context", "@type", "name", "url", "description"]
                        core_score = sum(20 if prop in schema_data else 0 for prop in core_props[:3])
                        core_score += sum(5 if prop in schema_data else 0 for prop in core_props[3:])
                        quality_score += min(core_score, 30)
                        
                        # Enhanced features (40 points)
                        if "contactPoint" in schema_data and len(schema_data["contactPoint"]) > 1:
                            quality_score += 15
                        if "sameAs" in schema_data and len(schema_data["sameAs"]) > 0:
                            quality_score += 10
                        if "subjectOf" in schema_data:
                            quality_score += 10
                        if "address" in schema_data and isinstance(schema_data["address"], dict):
                            quality_score += 5
                        
                        # Content richness (30 points)
                        if "keywords" in schema_data and len(schema_data["keywords"]) > 5:
                            quality_score += 10
                        if "knowsAbout" in schema_data:
                            quality_score += 10
                        if len(schema_data) > 10:  # Rich schema with many properties
                            quality_score += 10
                        
                        # Display quality score
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            score_color = "🟢" if quality_score >= 80 else "🟡" if quality_score >= 60 else "🔴"
                            st.metric("Quality Score", f"{score_color} {quality_score}/100")
                        
                        with col2:
                            if quality_score >= 80:
                                grade = "Excellent"
                            elif quality_score >= 60:
                                grade = "Good"
                            elif quality_score >= 40:
                                grade = "Fair"
                            else:
                                grade = "Needs Improvement"
                            st.metric("Grade", grade)
                        
                        with col3:
                            complexity = "Advanced" if nested_objects > 3 else "Intermediate" if nested_objects > 1 else "Basic"
                            st.metric("Complexity", complexity)
                    
                    else:
                        st.error("❌ Failed to generate schema. Please check the URL and try again.")
                        st.info("💡 Try selecting a specific page type or schema template to help guide generation.")
                
            except Exception as e:
                st.error(f"❌ Error processing URL: {str(e)}")
                st.info("Please ensure the URL is accessible and contains valid HTML content.")

# Advanced features in sidebar
st.sidebar.markdown("---")
st.sidebar.header("🛠️ Advanced Options")

if st.sidebar.checkbox("Show Entity Data"):
    if 'comprehensive_data' in locals():
        entity_data = comprehensive_data.get('entity_data', {})
        if entity_data:
            st.sidebar.write("**🧠 Detected Entity Data:**")
            if entity_data['expertise_areas']:
                st.sidebar.write("**Areas:** " + ", ".join(entity_data['expertise_areas']))
            if entity_data['wiki_topics']:
                st.sidebar.write("**Topics:** " + ", ".join(entity_data['wiki_topics'][:3]))

if st.sidebar.checkbox("Show Raw Extraction"):
    if 'comprehensive_data' in locals():
        with st.sidebar.expander("Raw Data"):
            st.sidebar.json(comprehensive_data)

# Footer with validation tools
st.sidebar.markdown("---")
st.sidebar.markdown("""
**🔗 Validation & Tools:**
- [Google Rich Results Test](https://search.google.com/test/rich-results)
- [Schema Markup Validator](https://validator.schema.org/)
- [JSON-LD Playground](https://json-ld.org/playground/)
- [Google Search Console](https://search.google.com/search-console)

**📚 Documentation:**
- [Schema.org Types](https://schema.org/docs/schemas.html)
- [Google Search Central](https://developers.google.com/search/docs/appearance/structured-data)
""")

# Main footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>🚀 Comprehensive Schema.org Generator v2.0</strong></p>
    <p>Enhanced with Entity Intelligence, Multi-department Contacts & Wikipedia Integration</p>
    <p>Powered by Google Gemini AI • Built for Production-Ready Schema Markup</p>
</div>
""", unsafe_allow_html=True)

