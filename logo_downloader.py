import os
import sys
import requests
import json
import time
import io
import re
import base64
import tempfile
import threading
import queue
import random
import uuid
import sqlite3
import logging
import configparser
import hashlib
from datetime import datetime
from urllib.parse import quote, urlparse, urljoin
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops
from bs4 import BeautifulSoup
import tldextract

# GUI imports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar, 
                            QTextEdit, QFileDialog, QGroupBox, QRadioButton, QButtonGroup,
                            QScrollArea, QMessageBox, QGridLayout, QFrame, QTabWidget,
                            QSlider, QComboBox, QSpinBox, QSplitter, QListWidget, QListWidgetItem,
                            QToolButton, QMenu, QAction, QDialog, QWizard, QWizardPage,
                            QTableWidget, QTableWidgetItem, QHeaderView, QSystemTrayIcon,
                            QStatusBar, QToolBar, QDockWidget, QCalendarWidget, QStackedWidget,
                            QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsDropShadowEffect,
                            QStyle, QSizePolicy, QFormLayout, QInputDialog, QColorDialog, QCompleter,
                            QDialogButtonBox)
from PyQt5.QtGui import (QPixmap, QImage, QFont, QIcon, QColor, QPalette, QCursor, 
                        QPainter, QBrush, QPen, QLinearGradient, QRadialGradient, 
                        QConicalGradient, QTransform, QKeySequence, QFontDatabase)
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QSize, QUrl, QTimer, QRect, QBuffer,
                         QPoint, QPointF, QRectF, QPropertyAnimation, QEasingCurve,
                         QSettings, QByteArray, QEvent, QMimeData, QProcess, QDir, QObject)

# Optional imports - try to import but don't fail if not available
try:
    import cairosvg
    SVG_SUPPORT = True
    print("CairoSVG support enabled")
except ImportError:
    SVG_SUPPORT = False
    print("CairoSVG support disabled - SVG to PNG conversion will not be available")

try:
    import cv2
    CV2_SUPPORT = True
    print("OpenCV support enabled")
except ImportError:
    CV2_SUPPORT = False
    print("OpenCV support disabled - some image processing features will be limited")

try:
    # Try to import rembg with a more robust error handling
    try:
        from rembg import remove as remove_bg
        REMBG_SUPPORT = True
        print("Rembg support enabled")
    except (ImportError, KeyError, Exception) as e:
        # Catch broader exceptions including Numba-related errors
        REMBG_SUPPORT = False
        print(f"Rembg support disabled due to error: {str(e)}")
except:
    REMBG_SUPPORT = False
    print("Rembg support disabled - advanced background removal will not be available")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logo_downloader.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("LogoDownloader")

# Application version
APP_VERSION = "1.0.0"
APP_NAME = "Logo Downloader Pro"

# Constants
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
]

# Logo sources with priority and quality scores
LOGO_SOURCES = [
    {"name": "SimpleIcons", "priority": 5, "base_quality": 80, "enabled": True},
    {"name": "Brandfetch", "priority": 10, "base_quality": 90, "enabled": True},
    {"name": "Clearbit", "priority": 8, "base_quality": 75, "enabled": True},
    {"name": "Wikipedia", "priority": 7, "base_quality": 85, "enabled": True},
    {"name": "BrandDB", "priority": 6, "base_quality": 70, "enabled": True},
    {"name": "CompanyWebsite", "priority": 9, "base_quality": 85, "enabled": True},
    {"name": "SocialMedia", "priority": 4, "base_quality": 75, "enabled": True},
    {"name": "GoogleSearch", "priority": 3, "base_quality": 65, "enabled": True},
    {"name": "BingSearch", "priority": 2, "base_quality": 60, "enabled": True},
    {"name": "DuckDuckGo", "priority": 1, "base_quality": 60, "enabled": True},
    {"name": "VectorDB", "priority": 5, "base_quality": 80, "enabled": True}
]

# Default settings
DEFAULT_SETTINGS = {
    "general": {
        "output_directory": os.path.join(os.path.expanduser("~"), "Downloads", "Logos"),
        "max_results": 10,
        "search_all_sources": True,
        "download_png": True,
        "download_svg": True,
        "remove_background": False,
        "enhance_logo": False,
        "auto_save": False,
        "theme": "system",  # system, light, dark
        "language": "en",
        "check_updates": True
    },
    "advanced": {
        "timeout": 15,
        "max_retries": 3,
        "concurrent_searches": 3,
        "cache_expiry_days": 30,
        "proxy_enabled": False,
        "proxy_url": "",
        "user_agent_rotation": True,
        "respect_robots_txt": True
    },
    "api_keys": {
        "google_api_key": "",
        "google_cx": "",
        "bing_api_key": "",
        "brandfetch_api_key": ""
    }
}

class Database:
    """SQLite database for caching and history"""
    def __init__(self, db_path="logo_downloader.db"):
        self.db_path = db_path
        self.conn = None
        self.init_db()
    
    def init_db(self):
        """Initialize the database and create tables if they don't exist"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # Create cache table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS logo_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                source TEXT NOT NULL,
                format_type TEXT NOT NULL,
                image_data BLOB,
                image_url TEXT,
                width INTEGER,
                height INTEGER,
                score INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_name, source, format_type)
            )
            ''')
            
            # Create history table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                results_count INTEGER,
                UNIQUE(company_name)
            )
            ''')
            
            # Create favorites table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                image_data BLOB,
                format_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_name)
            )
            ''')
            
            self.conn.commit()
            logger.info("Database initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {str(e)}")
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
    
    def add_to_cache(self, logo_result):
        """Add a logo result to the cache"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO logo_cache 
            (company_name, source, format_type, image_data, image_url, width, height, score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                logo_result.company_name,
                logo_result.source,
                logo_result.format_type,
                logo_result.image_data,
                logo_result.image_url,
                logo_result.width,
                logo_result.height,
                logo_result.score
            ))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding to cache: {str(e)}")
            return False
    
    def get_from_cache(self, company_name, max_age_days=30):
        """Get logo results from cache for a company"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT id, company_name, source, format_type, image_data, image_url, width, height, score
            FROM logo_cache
            WHERE company_name = ? AND datetime(timestamp) > datetime('now', ?)
            ORDER BY score DESC
            ''', (company_name, f"-{max_age_days} days"))
            
            results = []
            for row in cursor.fetchall():
                result = LogoResult(
                    company_name=row[1],
                    image_data=row[4],
                    image_url=row[5],
                    source=row[2],
                    format_type=row[3],
                    width=row[6],
                    height=row[7],
                    score=row[8]
                )
                results.append(result)
            
            return results
        except sqlite3.Error as e:
            logger.error(f"Error getting from cache: {str(e)}")
            return []
    
    def add_to_history(self, company_name, results_count):
        """Add a search to the history"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO search_history 
            (company_name, timestamp, results_count)
            VALUES (?, CURRENT_TIMESTAMP, ?)
            ''', (company_name, results_count))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding to history: {str(e)}")
            return False
    
    def get_history(self, limit=100):
        """Get search history"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT company_name, timestamp, results_count
            FROM search_history
            ORDER BY timestamp DESC
            LIMIT ?
            ''', (limit,))
            
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting history: {str(e)}")
            return []
    
    def add_to_favorites(self, logo_result):
        """Add a logo to favorites"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO favorites 
            (company_name, image_data, format_type, timestamp)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                logo_result.company_name,
                logo_result.image_data,
                logo_result.format_type
            ))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding to favorites: {str(e)}")
            return False
    
    def get_favorites(self):
        """Get favorite logos"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            SELECT company_name, image_data, format_type, timestamp
            FROM favorites
            ORDER BY timestamp DESC
            ''')
            
            results = []
            for row in cursor.fetchall():
                result = LogoResult(
                    company_name=row[0],
                    image_data=row[1],
                    format_type=row[2]
                )
                results.append(result)
            
            return results
        except sqlite3.Error as e:
            logger.error(f"Error getting favorites: {str(e)}")
            return []
    
    def remove_from_favorites(self, company_name):
        """Remove a logo from favorites"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            DELETE FROM favorites
            WHERE company_name = ?
            ''', (company_name,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error removing from favorites: {str(e)}")
            return False
    
    def clear_cache(self, max_age_days=None):
        """Clear the cache, optionally only clearing entries older than max_age_days"""
        try:
            cursor = self.conn.cursor()
            if max_age_days is not None:
                cursor.execute('''
                DELETE FROM logo_cache
                WHERE datetime(timestamp) < datetime('now', ?)
                ''', (f"-{max_age_days} days",))
            else:
                cursor.execute('DELETE FROM logo_cache')
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error clearing cache: {str(e)}")
            return False


class LogoResult:
    """Class to store logo search results"""
    def __init__(self, company_name, image_data=None, image_url=None, source=None, format_type=None, 
                 width=None, height=None, file_path=None, score=0):
        self.company_name = company_name
        self.image_data = image_data  # Binary image data
        self.image_url = image_url    # Source URL
        self.source = source          # Which source found it
        self.format_type = format_type  # PNG, SVG, etc.
        self.width = width
        self.height = height
        self.file_path = file_path    # Local file path if saved
        self.score = score            # Quality score (higher is better)
        self.pixmap = None            # QPixmap for display
        self.id = str(uuid.uuid4())   # Unique identifier
        self.metadata = {}            # Additional metadata
    
    def get_pixmap(self, size=None):
        """Get a QPixmap for display, optionally resized"""
        if self.pixmap is None and self.image_data:
            try:
                if self.format_type == 'svg' and SVG_SUPPORT:
                    # Convert SVG to PNG for display
                    png_data = io.BytesIO()
                    cairosvg.svg2png(bytestring=self.image_data, write_to=png_data, output_width=512, output_height=512)
                    pixmap = QPixmap()
                    pixmap.loadFromData(png_data.getvalue())
                else:
                    pixmap = QPixmap()
                    pixmap.loadFromData(self.image_data)
                
                self.pixmap = pixmap
                
                # Update width and height if not set
                if not self.width or not self.height:
                    self.width = pixmap.width()
                    self.height = pixmap.height()
            except Exception as e:
                logger.error(f"Error creating pixmap: {str(e)}")
                return None
        
        if size and self.pixmap and not self.pixmap.isNull():
            return self.pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        return self.pixmap
    
    def save_to_file(self, output_dir, file_name=None):
        """Save the logo to a file"""
        if not self.image_data:
            return None
            
        if not file_name:
            clean_name = self.company_name.lower().replace(' ', '_')
            extension = self.format_type.lower() if self.format_type else 'png'
            file_name = f"{clean_name}_logo.{extension}"
            
        file_path = os.path.join(output_dir, file_name)
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
            with open(file_path, 'wb') as f:
                f.write(self.image_data)
            self.file_path = file_path
            return file_path
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            return None
    
    def get_image(self):
        """Get a PIL Image object from the image data"""
        if not self.image_data:
            return None
        
        try:
            if self.format_type == 'svg' and SVG_SUPPORT:
                # Convert SVG to PNG for processing
                png_data = io.BytesIO()
                cairosvg.svg2png(bytestring=self.image_data, write_to=png_data)
                return Image.open(png_data)
            else:
                return Image.open(io.BytesIO(self.image_data))
        except Exception as e:
            logger.error(f"Error creating PIL Image: {str(e)}")
            return None
    
    def update_image_data(self, image):
        """Update the image data from a PIL Image object"""
        if not image:
            return False
        
        try:
            output = io.BytesIO()
            image.save(output, format='PNG')
            self.image_data = output.getvalue()
            self.format_type = 'png'
            self.pixmap = None  # Reset pixmap so it will be regenerated
            return True
        except Exception as e:
            logger.error(f"Error updating image data: {str(e)}")
            return False
    
    def to_dict(self):
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'company_name': self.company_name,
            'source': self.source,
            'format_type': self.format_type,
            'image_url': self.image_url,
            'width': self.width,
            'height': self.height,
            'score': self.score,
            'file_path': self.file_path,
            'metadata': self.metadata
        }


class LogoSearchWorker(QThread):
    """Worker thread for searching a specific source"""
    progress_update = pyqtSignal(str)
    search_result = pyqtSignal(LogoResult)
    search_complete = pyqtSignal(str, bool)  # Source name, success
    
    def __init__(self, source, company_name, domains, settings):
        super().__init__()
        self.source = source
        self.company_name = company_name
        self.domains = domains
        self.settings = settings
        self.session = requests.Session()
        
        # Set up proxy if enabled
        if settings.get('proxy_enabled', False) and settings.get('proxy_url'):
            self.session.proxies = {
                'http': settings['proxy_url'],
                'https': settings['proxy_url']
            }
        
        # Set user agent
        if settings.get('user_agent_rotation', True):
            self.session.headers.update({
                'User-Agent': random.choice(USER_AGENTS)
            })
        else:
            self.session.headers.update({
                'User-Agent': USER_AGENTS[0]
            })
    
    def run(self):
        """Run the search for this source"""
        source_name = self.source['name']
        self.progress_update.emit(f"Searching {source_name}...")
        
        try:
            # Call the appropriate search method based on the source
            method_name = f"search_{source_name.lower()}"
            if hasattr(self, method_name) and callable(getattr(self, method_name)):
                search_method = getattr(self, method_name)
                success = search_method()
                self.search_complete.emit(source_name, success)
            else:
                self.progress_update.emit(f"❌ Search method not implemented for {source_name}")
                self.search_complete.emit(source_name, False)
        except Exception as e:
            logger.error(f"Error searching {source_name}: {str(e)}")
            self.progress_update.emit(f"❌ Error searching {source_name}: {str(e)}")
            self.search_complete.emit(source_name, False)
    
    def add_result(self, result):
        """Add a result and emit a signal"""
        # Add the base quality score from the source
        result.score += self.source['base_quality']
        
        # Add additional score based on format type
        if result.format_type == 'svg':
            result.score += 10  # SVG gets a bonus
        
        # Add source to metadata
        result.metadata['source'] = self.source['name']
        result.metadata['found_time'] = datetime.now().isoformat()
        
        self.search_result.emit(result)
    
    def search_simpleicons(self):
        """Search for logos in the Simple Icons repository"""
        # Try different variations of the company name
        variations = [
            self.company_name.lower().replace(' ', ''),  # nospaces
            self.company_name.lower().replace(' ', '-'),  # with-hyphens
            ''.join(word[0] for word in self.company_name.lower().split())  # acronym
        ]
        
        success = False
        for slug in variations:
            # Remove any special characters
            slug = ''.join(c for c in slug if c.isalnum() or c == '-')
            
            # Try to get the SVG from jsDelivr CDN
            url = f"https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/{slug}.svg"
            
            try:
                response = self.session.get(url, timeout=self.settings.get('timeout', 15))
                if response.status_code == 200:
                    # We found an SVG
                    svg_content = response.content
                    
                    # Create a result
                    result = LogoResult(
                        company_name=self.company_name,
                        image_data=svg_content,
                        image_url=url,
                        source="SimpleIcons",
                        format_type="svg",
                        score=10  # Base score, will be added to source base quality
                    )
                    
                    self.add_result(result)
                    self.progress_update.emit(f"✅ Found logo in Simple Icons repository")
                    success = True
            except Exception as e:
                logger.error(f"Error with Simple Icons: {str(e)}")
        
        return success
    
    def search_brandfetch(self):
        """Search for logos using Brandfetch API"""
        success = False
        api_key = self.settings.get('brandfetch_api_key', '')
        
        # If we have an API key, use the authenticated API
        if api_key:
            headers = {
                'Authorization': f'Bearer {api_key}'
            }
            
            for domain in self.domains[:3]:  # Limit to first 3 domains
                try:
                    # Clean the domain
                    parsed = tldextract.extract(domain)
                    if parsed.domain and parsed.suffix:
                        clean_domain = f"{parsed.domain}.{parsed.suffix}"
                        
                        # Use the Brandfetch API
                        brand_url = f"https://api.brandfetch.io/v2/brands/{clean_domain}"
                        brand_response = self.session.get(brand_url, headers=headers, timeout=self.settings.get('timeout', 15))
                        
                        if brand_response.status_code == 200:
                            brand_data = brand_response.json()
                            logos = brand_data.get('logos', [])
                            
                            if logos and len(logos) > 0:
                                # Process each logo
                                for logo in logos:
                                    if logo.get('type') == 'logo' and logo.get('formats'):
                                        formats = logo.get('formats')
                                        
                                        # Look for PNG
                                        for fmt in formats:
                                            if fmt.get('format') == 'png' and fmt.get('src') and self.settings.get('download_png', True):
                                                png_url = fmt.get('src')
                                                png_response = self.session.get(png_url, timeout=self.settings.get('timeout', 15))
                                                
                                                if png_response.status_code == 200:
                                                    result = LogoResult(
                                                        company_name=self.company_name,
                                                        image_data=png_response.content,
                                                        image_url=png_url,
                                                        source="Brandfetch",
                                                        format_type="png",
                                                        score=15  # Higher base score for authenticated API
                                                    )
                                                    self.add_result(result)
                                                    self.progress_update.emit(f"✅ Found PNG logo from Brandfetch API")
                                                    success = True
                                        
                                        # Look for SVG
                                        for fmt in formats:
                                            if fmt.get('format') == 'svg' and fmt.get('src') and self.settings.get('download_svg', True):
                                                svg_url = fmt.get('src')
                                                svg_response = self.session.get(svg_url, timeout=self.settings.get('timeout', 15))
                                                
                                                if svg_response.status_code == 200:
                                                    result = LogoResult(
                                                        company_name=self.company_name,
                                                        image_data=svg_response.content,
                                                        image_url=svg_url,
                                                        source="Brandfetch",
                                                        format_type="svg",
                                                        score=20  # Higher score for SVG
                                                    )
                                                    self.add_result(result)
                                                    self.progress_update.emit(f"✅ Found SVG logo from Brandfetch API")
                                                    success = True
                except Exception as e:
                    logger.error(f"Error with Brandfetch API: {str(e)}")
        else:
            # Use the public API (limited functionality)
            for domain in self.domains[:3]:
                try:
                    # Use the Brandfetch autocomplete API to find the domain
                    search_url = f"https://api.brandfetch.io/v2/search/{quote(domain)}"
                    
                    response = self.session.get(search_url, timeout=self.settings.get('timeout', 15))
                    if response.status_code == 200:
                        data = response.json()
                        if data and len(data) > 0:
                            found_domain = data[0].get('domain')
                            if found_domain:
                                # Now get the brand data
                                brand_url = f"https://api.brandfetch.io/v2/brands/{found_domain}"
                                brand_response = self.session.get(brand_url, timeout=self.settings.get('timeout', 15))
                                
                                if brand_response.status_code == 200:
                                    brand_data = brand_response.json()
                                    logos = brand_data.get('logos', [])
                                    
                                    if logos and len(logos) > 0:
                                        # Process each logo
                                        for logo in logos:
                                            if logo.get('type') == 'logo' and logo.get('formats'):
                                                formats = logo.get('formats')
                                                
                                                # Look for PNG
                                                for fmt in formats:
                                                    if fmt.get('format') == 'png' and fmt.get('src') and self.settings.get('download_png', True):
                                                        png_url = fmt.get('src')
                                                        png_response = self.session.get(png_url, timeout=self.settings.get('timeout', 15))
                                                        
                                                        if png_response.status_code == 200:
                                                            result = LogoResult(
                                                                company_name=self.company_name,
                                                                image_data=png_response.content,
                                                                image_url=png_url,
                                                                source="Brandfetch",
                                                                format_type="png",
                                                                score=10
                                                            )
                                                            self.add_result(result)
                                                            self.progress_update.emit(f"✅ Found PNG logo from Brandfetch")
                                                            success = True
                                                
                                                # Look for SVG
                                                for fmt in formats:
                                                    if fmt.get('format') == 'svg' and fmt.get('src') and self.settings.get('download_svg', True):
                                                        svg_url = fmt.get('src')
                                                        svg_response = self.session.get(svg_url, timeout=self.settings.get('timeout', 15))
                                                        
                                                        if svg_response.status_code == 200:
                                                            result = LogoResult(
                                                                company_name=self.company_name,
                                                                image_data=svg_response.content,
                                                                image_url=svg_url,
                                                                source="Brandfetch",
                                                                format_type="svg",
                                                                score=15  # Higher score for SVG
                                                            )
                                                            self.add_result(result)
                                                            self.progress_update.emit(f"✅ Found SVG logo from Brandfetch")
                                                            success = True
                except Exception as e:
                    logger.error(f"Error with Brandfetch: {str(e)}")
        
        return success
    
    def search_clearbit(self):
        """Search for logos using Clearbit Logo API"""
        success = False
        
        for domain in self.domains:
            try:
                # Clean the domain
                parsed = tldextract.extract(domain)
                if parsed.domain and parsed.suffix:
                    clean_domain = f"{parsed.domain}.{parsed.suffix}"
                    
                    url = f"https://logo.clearbit.com/{clean_domain}?size=512"
                    response = self.session.get(url, timeout=self.settings.get('timeout', 15))
                    
                    if response.status_code == 200:
                        # Create a result
                        result = LogoResult(
                            company_name=self.company_name,
                            image_data=response.content,
                            image_url=url,
                            source="Clearbit",
                            format_type="png",
                            score=5  # Base score
                        )
                        
                        self.add_result(result)
                        self.progress_update.emit(f"✅ Found logo from Clearbit ({clean_domain})")
                        success = True
            except Exception as e:
                logger.debug(f"Error with Clearbit for domain {domain}: {str(e)}")
        
        return success
    
    def search_wikipedia(self):
        """Search for logos on Wikipedia"""
        try:
            # First, search for the Wikipedia page
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(self.company_name)}&format=json"
            search_response = self.session.get(search_url, timeout=self.settings.get('timeout', 15))
            
            if search_response.status_code == 200:
                search_data = search_response.json()
                if 'query' in search_data and 'search' in search_data['query'] and len(search_data['query']['search']) > 0:
                    page_title = search_data['query']['search'][0]['title']
                    
                    # Now get the page content
                    page_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=images&titles={quote(page_title)}&format=json"
                    page_response = self.session.get(page_url, timeout=self.settings.get('timeout', 15))
                    
                    if page_response.status_code == 200:
                        page_data = page_response.json()
                        pages = page_data.get('query', {}).get('pages', {})
                        
                        # Find the first page (there should only be one)
                        for page_id in pages:
                            page = pages[page_id]
                            if 'images' in page:
                                # Look for logo images
                                logo_images = [img for img in page['images'] if 'logo' in img['title'].lower() or 'icon' in img['title'].lower()]
                                
                                if logo_images:
                                    # Get the first logo image
                                    image_title = logo_images[0]['title']
                                    
                                    # Get the image URL
                                    img_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=imageinfo&iiprop=url&titles={quote(image_title)}&format=json"
                                    img_response = self.session.get(img_url, timeout=self.settings.get('timeout', 15))
                                    
                                    if img_response.status_code == 200:
                                        img_data = img_response.json()
                                        img_pages = img_data.get('query', {}).get('pages', {})
                                        
                                        for img_page_id in img_pages:
                                            img_page = img_pages[img_page_id]
                                            if 'imageinfo' in img_page and len(img_page['imageinfo']) > 0:
                                                image_url = img_page['imageinfo'][0]['url']
                                                
                                                # Download the image
                                                img_content_response = self.session.get(image_url, timeout=self.settings.get('timeout', 15))
                                                
                                                if img_content_response.status_code == 200:
                                                    # Determine format type
                                                    format_type = 'png'  # Default
                                                    if image_url.lower().endswith('.svg'):
                                                        format_type = 'svg'
                                                    elif image_url.lower().endswith('.jpg') or image_url.lower().endswith('.jpeg'):
                                                        format_type = 'jpg'
                                                    
                                                    # Create a result
                                                    result = LogoResult(
                                                        company_name=self.company_name,
                                                        image_data=img_content_response.content,
                                                        image_url=image_url,
                                                        source="Wikipedia",
                                                        format_type=format_type,
                                                        score=10  # Base score
                                                    )
                                                    
                                                    self.add_result(result)
                                                    self.progress_update.emit(f"✅ Found logo from Wikipedia")
                                                    return True
        except Exception as e:
            logger.error(f"Error with Wikipedia: {str(e)}")
        
        return False
    
    def search_branddb(self):
        """Search for logos in various brand databases"""
        # This is a placeholder for searching in brand databases
        # In a real implementation, you would integrate with various brand databases
        return False
    
    def search_companywebsite(self):
        """Search for logos on the company's website"""
        success = False
        
        for domain in self.domains[:3]:  # Limit to first 3 domains to avoid too many requests
            try:
                # Clean the domain
                if not domain.startswith('http'):
                    domain = f"https://{domain}"
                
                # Get the website content
                response = self.session.get(domain, timeout=self.settings.get('timeout', 15))
                
                if response.status_code == 200:
                    # Parse the HTML
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Look for logo in common locations
                    logo_candidates = []
                    
                    # Look for images with 'logo' in the class, id, or alt text
                    for img in soup.find_all('img'):
                        score = 0
                        
                        # Check class
                        img_class = img.get('class', [])
                        if isinstance(img_class, list):
                            img_class = ' '.join(img_class)
                        if 'logo' in img_class.lower():
                            score += 20
                        
                        # Check id
                        img_id = img.get('id', '')
                        if 'logo' in img_id.lower():
                            score += 20
                        
                        # Check alt text
                        alt_text = img.get('alt', '')
                        if 'logo' in alt_text.lower():
                            score += 15
                        
                        # Check src
                        src = img.get('src', '')
                        if 'logo' in src.lower():
                            score += 10
                        
                        # Check size (logos are usually small)
                        width = img.get('width', '')
                        height = img.get('height', '')
                        if width and height:
                            try:
                                w = int(width)
                                h = int(height)
                                if 20 <= w <= 400 and 20 <= h <= 200:
                                    score += 10
                            except ValueError:
                                pass
                        
                        # If the image has a reasonable score, add it to candidates
                        if score >= 20:
                            logo_candidates.append((img, score))
                    
                    # Sort candidates by score
                    logo_candidates.sort(key=lambda x: x[1], reverse=True)
                    
                    # Process the top candidates
                    for img, score in logo_candidates[:3]:
                        src = img.get('src', '')
                        if src:
                            # Make the URL absolute if it's relative
                            if not src.startswith('http'):
                                if src.startswith('//'):
                                    src = f"https:{src}"
                                elif src.startswith('/'):
                                    src = f"{domain.rstrip('/')}{src}"
                                else:
                                    src = f"{domain.rstrip('/')}/{src}"
                            
                            # Download the image
                            try:
                                img_response = self.session.get(src, timeout=self.settings.get('timeout', 15))
                                
                                if img_response.status_code == 200:
                                    # Determine format type
                                    format_type = 'png'  # Default
                                    if src.lower().endswith('.svg'):
                                        format_type = 'svg'
                                    elif src.lower().endswith('.jpg') or src.lower().endswith('.jpeg'):
                                        format_type = 'jpg'
                                    
                                    # Create a result
                                    result = LogoResult(
                                        company_name=self.company_name,
                                        image_data=img_response.content,
                                        image_url=src,
                                        source="CompanyWebsite",
                                        format_type=format_type,
                                        score=score / 10  # Convert candidate score to result score
                                    )
                                    
                                    self.add_result(result)
                                    self.progress_update.emit(f"✅ Found logo on company website")
                                    success = True
                            except Exception as e:
                                logger.debug(f"Error downloading image from company website: {str(e)}")
            except Exception as e:
                logger.debug(f"Error with company website {domain}: {str(e)}")
        
        return success
    
    def search_socialmedia(self):
        """Search for logos on social media profiles"""
        # This is a placeholder for searching on social media
        # In a real implementation, you would integrate with various social media APIs
        return False
    
    def search_googlesearch(self):
        """Search for logos using Google Custom Search API"""
        api_key = self.settings.get('google_api_key', '')
        cx = self.settings.get('google_cx', '')
        
        if not api_key or not cx:
            self.progress_update.emit("⚠️ Google Search API key or CX not configured")
            return False
        
        try:
            # Construct the search query
            query = f"{self.company_name} logo filetype:png OR filetype:svg"
            
            # Make the API request
            url = f"https://www.googleapis.com/customsearch/v1?q={quote(query)}&key={api_key}&cx={cx}&searchType=image&num=5"
            response = self.session.get(url, timeout=self.settings.get('timeout', 15))
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                if items:
                    success = False
                    for item in items:
                        image_url = item.get('link')
                        if not image_url:
                            continue
                        
                        # Download the image
                        try:
                            img_response = self.session.get(image_url, timeout=self.settings.get('timeout', 15))
                            
                            if img_response.status_code == 200:
                                # Determine format type
                                format_type = 'png'  # Default
                                if image_url.lower().endswith('.svg'):
                                    format_type = 'svg'
                                elif image_url.lower().endswith('.jpg') or image_url.lower().endswith('.jpeg'):
                                    format_type = 'jpg'
                                
                                # Create a result
                                result = LogoResult(
                                    company_name=self.company_name,
                                    image_data=img_response.content,
                                    image_url=image_url,
                                    source="GoogleSearch",
                                    format_type=format_type,
                                    score=5  # Base score
                                )
                                
                                self.add_result(result)
                                self.progress_update.emit(f"✅ Found logo from Google Search")
                                success = True
                        except Exception as e:
                            logger.debug(f"Error downloading image from Google Search: {str(e)}")
                    
                    return success
        except Exception as e:
            logger.error(f"Error with Google Search: {str(e)}")
        
        return False
    
    def search_bingsearch(self):
        """Search for logos using Bing Image Search API"""
        api_key = self.settings.get('bing_api_key', '')
        
        if not api_key:
            self.progress_update.emit("⚠️ Bing Search API key not configured")
            return False
        
        try:
            # Construct the search query
            query = f"{self.company_name} logo filetype:png OR filetype:svg"
            
            # Make the API request
            url = f"https://api.bing.microsoft.com/v7.0/images/search?q={quote(query)}&count=5"
            headers = {"Ocp-Apim-Subscription-Key": api_key}
            response = self.session.get(url, headers=headers, timeout=self.settings.get('timeout', 15))
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('value', [])
                
                if items:
                    success = False
                    for item in items:
                        image_url = item.get('contentUrl')
                        if not image_url:
                            continue
                        
                        # Download the image
                        try:
                            img_response = self.session.get(image_url, timeout=self.settings.get('timeout', 15))
                            
                            if img_response.status_code == 200:
                                # Determine format type
                                format_type = 'png'  # Default
                                if image_url.lower().endswith('.svg'):
                                    format_type = 'svg'
                                elif image_url.lower().endswith('.jpg') or image_url.lower().endswith('.jpeg'):
                                    format_type = 'jpg'
                                
                                # Create a result
                                result = LogoResult(
                                    company_name=self.company_name,
                                    image_data=img_response.content,
                                    image_url=image_url,
                                    source="BingSearch",
                                    format_type=format_type,
                                    score=5  # Base score
                                )
                                
                                self.add_result(result)
                                self.progress_update.emit(f"✅ Found logo from Bing Search")
                                success = True
                        except Exception as e:
                            logger.debug(f"Error downloading image from Bing Search: {str(e)}")
                    
                    return success
        except Exception as e:
            logger.error(f"Error with Bing Search: {str(e)}")
        
        return False
    
    def search_duckduckgo(self):
        """Search for logos using DuckDuckGo"""
        search_term = f"{self.company_name} official logo"
        if self.settings.get('download_svg', True):
            search_term += " filetype:svg"
        elif self.settings.get('download_png', True):
            search_term += " filetype:png"
        
        try:
            # Use DuckDuckGo search API
            url = f"https://duckduckgo.com/i.js?q={quote(search_term)}&o=json"
            
            response = self.session.get(url, timeout=self.settings.get('timeout', 15))
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'results' in data and len(data['results']) > 0:
                        # Process the top results
                        success = False
                        for img_result in data['results'][:5]:
                            image_url = img_result.get('image')
                            if not image_url:
                                continue
                            
                            # Download the image
                            try:
                                img_response = self.session.get(image_url, timeout=self.settings.get('timeout', 15))
                                
                                if img_response.status_code == 200:
                                    # Determine format type
                                    format_type = 'png'  # Default
                                    if image_url.lower().endswith('.svg'):
                                        format_type = 'svg'
                                    elif image_url.lower().endswith('.jpg') or image_url.lower().endswith('.jpeg'):
                                        format_type = 'jpg'
                                    
                                    # Create a result
                                    result = LogoResult(
                                        company_name=self.company_name,
                                        image_data=img_response.content,
                                        image_url=image_url,
                                        source="DuckDuckGo",
                                        format_type=format_type,
                                        score=5  # Base score
                                    )
                                    
                                    self.add_result(result)
                                    self.progress_update.emit(f"✅ Found logo from DuckDuckGo search")
                                    success = True
                            except Exception as e:
                                logger.debug(f"Error downloading image from DuckDuckGo: {str(e)}")
                        
                        return success
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.error(f"Error with DuckDuckGo search: {str(e)}")
        
        return False
    
    def search_vectordb(self):
        """Search for logos in vector databases"""
        # This is a placeholder for searching in vector databases like The Noun Project
        # In a real implementation, you would integrate with various vector databases
        return False


class LogoSearchManager(QObject):
    """Manager for coordinating multiple search workers"""
    progress_update = pyqtSignal(str)
    search_result = pyqtSignal(LogoResult)
    search_complete = pyqtSignal(bool, list)  # Success, list of LogoResult objects
    
    def __init__(self, company_name, settings, db):
        super().__init__()
        self.company_name = company_name
        self.settings = settings
        self.db = db
        self.results = []
        self.workers = []
        self.completed_sources = set()
        self.active_workers = 0
        self.max_concurrent = settings.get('concurrent_searches', 3)
        self.search_queue = queue.Queue()
        self.domains = self.generate_company_domains(company_name)
    
    def start_search(self):
        """Start the search process"""
        # Check cache first
        cache_results = self.db.get_from_cache(self.company_name, self.settings.get('cache_expiry_days', 30))
        
        if cache_results:
            self.progress_update.emit(f"Found {len(cache_results)} logos in cache")
            for result in cache_results:
                self.results.append(result)
                self.search_result.emit(result)
            
            # If we have enough results from cache and don't need to search all sources, we can return
            if len(cache_results) >= self.settings.get('max_results', 10) and not self.settings.get('search_all_sources', True):
                self.search_complete.emit(True, self.results)
                return
        
        # Queue up all enabled sources
        for source in LOGO_SOURCES:
            if source['enabled']:
                self.search_queue.put(source)
        
        # Start the initial batch of workers
        self.start_workers()
    
    def start_workers(self):
        """Start worker threads up to the maximum concurrent limit"""
        while not self.search_queue.empty() and self.active_workers < self.max_concurrent:
            source = self.search_queue.get()
            self.start_worker(source)
    
    def start_worker(self, source):
        """Start a worker thread for a specific source"""
        worker = LogoSearchWorker(source, self.company_name, self.domains, self.settings)
        worker.progress_update.connect(self.handle_progress_update)
        worker.search_result.connect(self.handle_search_result)
        worker.search_complete.connect(self.handle_search_complete)
        
        self.workers.append(worker)
        self.active_workers += 1
        worker.start()
    
    def handle_progress_update(self, message):
        """Handle progress updates from workers"""
        self.progress_update.emit(message)
    
    def handle_search_result(self, result):
        """Handle search results from workers"""
        # Add to results list
        self.results.append(result)
        
        # Add to cache
        self.db.add_to_cache(result)
        
        # Emit the result
        self.search_result.emit(result)
        
        # Check if we have enough results and should stop
        if len(self.results) >= self.settings.get('max_results', 10) and not self.settings.get('search_all_sources', True):
            # Stop all workers
            for worker in self.workers:
                if worker.isRunning():
                    worker.terminate()
            
            # Complete the search
            self.search_complete.emit(True, self.results)
    
    def handle_search_complete(self, source_name, success):
        """Handle search completion from a worker"""
        self.completed_sources.add(source_name)
        self.active_workers -= 1
        
        # Start the next worker if available
        self.start_workers()
        
        # Check if all sources have completed
        if self.active_workers == 0 and self.search_queue.empty():
            # Add to search history
            self.db.add_to_history(self.company_name, len(self.results))
            
            # Complete the search
            self.search_complete.emit(len(self.results) > 0, self.results)
    
    def generate_company_domains(self, company_name):
        """Generate possible domains for the company"""
        domains = []
        
        # Clean the company name
        clean_name = company_name.lower()
        
        # Remove common legal suffixes
        legal_suffixes = [' inc', ' corp', ' llc', ' ltd', ' limited', ' gmbh', ' co', ' company', ' corporation']
        for suffix in legal_suffixes:
            if clean_name.endswith(suffix):
                clean_name = clean_name[:-len(suffix)]
        
        # Remove special characters
        clean_name = re.sub(r'[^\w\s]', '', clean_name)
        
        # Generate domain variations
        name_parts = clean_name.split()
        
        # Full name with no spaces
        domains.append(''.join(name_parts))
        
        # Full name with hyphens
        domains.append('-'.join(name_parts))
        
        # First letter of each word + last word
        if len(name_parts) > 1:
            acronym = ''.join(part[0] for part in name_parts[:-1]) + name_parts[-1]
            domains.append(acronym)
        
        # Acronym only if more than one word
        if len(name_parts) > 1:
            acronym = ''.join(part[0] for part in name_parts)
            domains.append(acronym)
        
        # Add TLDs
        result = []
        for domain in domains:
            result.append(f"{domain}.com")
            result.append(f"{domain}.org")
            result.append(f"{domain}.io")
            result.append(f"{domain}.co")
            result.append(f"{domain}.net")
            
        # Add the original company name
        result.append(company_name)
        
        # Special cases for well-known companies
        if 'google' in clean_name:
            result.append('google.com')
        elif 'microsoft' in clean_name:
            result.append('microsoft.com')
        elif 'amazon' in clean_name:
            result.append('amazon.com')
        elif 'facebook' in clean_name or 'meta' in clean_name:
            result.append('facebook.com')
            result.append('meta.com')
        elif 'apple' in clean_name:
            result.append('apple.com')
        
        return list(set(result))  # Remove duplicates


class ImageProcessor:
    """Class for processing logo images"""
    @staticmethod
    def remove_background(image):
        """Remove the background from an image"""
        if REMBG_SUPPORT:
            # Use rembg if available
            try:
                return remove_bg(image)
            except Exception as e:
                logger.error(f"Error removing background with rembg: {str(e)}")
        
        # Fallback to a simpler method
        try:
            # Convert to RGBA if not already
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Create a mask based on edge detection
            edges = image.filter(ImageFilter.FIND_EDGES)
            edges = edges.convert('L')
            edges = ImageEnhance.Contrast(edges).enhance(2.0)
            
            # Create a new image with transparent background
            result = Image.new('RGBA', image.size, (0, 0, 0, 0))
            
            # Copy the original image, using the edge mask
            result.paste(image, (0, 0), edges)
            
            return result
        except Exception as e:
            logger.error(f"Error removing background: {str(e)}")
            return image
    
    @staticmethod
    def enhance_logo(image):
        """Enhance the logo image"""
        try:
            # Convert to RGBA if not already
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.5)
            
            # Resize to a standard size while maintaining aspect ratio
            image.thumbnail((512, 512), Image.LANCZOS)
            
            return image
        except Exception as e:
            logger.error(f"Error enhancing logo: {str(e)}")
            return image
    
    @staticmethod
    def convert_to_format(image, format_type):
        """Convert an image to a specific format"""
        try:
            if format_type.lower() == 'png':
                output = io.BytesIO()
                image.save(output, format='PNG')
                return output.getvalue()
            elif format_type.lower() == 'jpg' or format_type.lower() == 'jpeg':
                # Convert to RGB (remove alpha channel)
                if image.mode == 'RGBA':
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[3])  # 3 is the alpha channel
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=95)
                return output.getvalue()
            elif format_type.lower() == 'webp':
                output = io.BytesIO()
                image.save(output, format='WEBP', quality=95)
                return output.getvalue()
            else:
                raise ValueError(f"Unsupported format: {format_type}")
        except Exception as e:
            logger.error(f"Error converting image format: {str(e)}")
            return None
    
    @staticmethod
    def resize_image(image, width, height, maintain_aspect_ratio=True):
        """Resize an image to the specified dimensions"""
        try:
            if maintain_aspect_ratio:
                image.thumbnail((width, height), Image.LANCZOS)
                return image
            else:
                return image.resize((width, height), Image.LANCZOS)
        except Exception as e:
            logger.error(f"Error resizing image: {str(e)}")
            return image
    
    @staticmethod
    def extract_dominant_colors(image, num_colors=5):
        """Extract the dominant colors from an image"""
        try:
            # Resize image to speed up processing
            img = image.copy()
            img.thumbnail((100, 100))
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get pixels
            pixels = list(img.getdata())
            
            # Count colors
            color_count = {}
            for pixel in pixels:
                if pixel in color_count:
                    color_count[pixel] += 1
                else:
                    color_count[pixel] = 1
            
            # Sort by count
            sorted_colors = sorted(color_count.items(), key=lambda x: x[1], reverse=True)
            
            # Return the top colors
            return [{'color': f'#{r:02x}{g:02x}{b:02x}', 'count': count} for (r, g, b), count in sorted_colors[:num_colors]]
        except Exception as e:
            logger.error(f"Error extracting dominant colors: {str(e)}")
            return []


class SettingsDialog(QDialog):
    """Dialog for configuring application settings"""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()  # Work with a copy
        self.initUI()
    
    def initUI(self):
        """Initialize the user interface"""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        # Create tabs
        tabs = QTabWidget()
        
        # General settings tab
        general_tab = QWidget()
        general_layout = QFormLayout()
        
        # Output directory
        self.output_dir_input = QLineEdit(self.settings['general']['output_directory'])
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_output_dir)
        
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.output_dir_input)
        dir_layout.addWidget(browse_button)
        
        general_layout.addRow("Output Directory:", dir_layout)
        
        # Max results
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 100)
        self.max_results_spin.setValue(self.settings['general']['max_results'])
        general_layout.addRow("Maximum Results:", self.max_results_spin)
        
        # Search all sources
        self.search_all_checkbox = QCheckBox("Search All Sources")
        self.search_all_checkbox.setChecked(self.settings['general']['search_all_sources'])
        general_layout.addRow("Search All Sources:", self.search_all_checkbox)
        
        # Format options
        self.png_checkbox = QCheckBox("PNG")
        self.png_checkbox.setChecked(self.settings['general']['download_png'])
        self.svg_checkbox = QCheckBox("SVG")
        self.svg_checkbox.setChecked(self.settings['general']['download_svg'])
        
        format_layout = QHBoxLayout()
        format_layout.addWidget(self.png_checkbox)
        format_layout.addWidget(self.svg_checkbox)
        
        general_layout.addRow("Format:", format_layout)
        
        # Image processing
        self.remove_bg_checkbox = QCheckBox("Remove Background")
        self.remove_bg_checkbox.setChecked(self.settings['general']['remove_background'])
        self.enhance_checkbox = QCheckBox("Enhance Logo")
        self.enhance_checkbox.setChecked(self.settings['general']['enhance_logo'])
        
        processing_layout = QHBoxLayout()
        processing_layout.addWidget(self.remove_bg_checkbox)
        processing_layout.addWidget(self.enhance_checkbox)
        
        general_layout.addRow("Processing:", processing_layout)
        
        # Auto save
        self.auto_save_checkbox = QCheckBox("Auto Save")
        self.auto_save_checkbox.setChecked(self.settings['general']['auto_save'])
        general_layout.addRow("Auto Save:", self.auto_save_checkbox)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Light", "Dark"])
        theme_index = {"system": 0, "light": 1, "dark": 2}.get(self.settings['general']['theme'].lower(), 0)
        self.theme_combo.setCurrentIndex(theme_index)
        general_layout.addRow("Theme:", self.theme_combo)
        
        # Check for updates
        self.updates_checkbox = QCheckBox("Check for Updates")
        self.updates_checkbox.setChecked(self.settings['general']['check_updates'])
        general_layout.addRow("Check for Updates:", self.updates_checkbox)
        
        general_tab.setLayout(general_layout)
        tabs.addTab(general_tab, "General")
        
        # Advanced settings tab
        advanced_tab = QWidget()
        advanced_layout = QFormLayout()
        
        # Timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setValue(self.settings['advanced']['timeout'])
        advanced_layout.addRow("Request Timeout (seconds):", self.timeout_spin)
        
        # Max retries
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(self.settings['advanced']['max_retries'])
        advanced_layout.addRow("Maximum Retries:", self.retries_spin)
        
        # Concurrent searches
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.settings['advanced']['concurrent_searches'])
        advanced_layout.addRow("Concurrent Searches:", self.concurrent_spin)
        
        # Cache expiry
        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(1, 365)
        self.cache_spin.setValue(self.settings['advanced']['cache_expiry_days'])
        advanced_layout.addRow("Cache Expiry (days):", self.cache_spin)
        
        # Proxy settings
        self.proxy_checkbox = QCheckBox("Enable Proxy")
        self.proxy_checkbox.setChecked(self.settings['advanced']['proxy_enabled'])
        advanced_layout.addRow("Enable Proxy:", self.proxy_checkbox)
        
        self.proxy_input = QLineEdit(self.settings['advanced']['proxy_url'])
        advanced_layout.addRow("Proxy URL:", self.proxy_input)
        
        # User agent rotation
        self.ua_rotation_checkbox = QCheckBox("Rotate User Agents")
        self.ua_rotation_checkbox.setChecked(self.settings['advanced']['user_agent_rotation'])
        advanced_layout.addRow("Rotate User Agents:", self.ua_rotation_checkbox)
        
        # Respect robots.txt
        self.robots_checkbox = QCheckBox("Respect robots.txt")
        self.robots_checkbox.setChecked(self.settings['advanced']['respect_robots_txt'])
        advanced_layout.addRow("Respect robots.txt:", self.robots_checkbox)
        
        advanced_tab.setLayout(advanced_layout)
        tabs.addTab(advanced_tab, "Advanced")
        
        # API Keys tab
        api_tab = QWidget()
        api_layout = QFormLayout()
        
        # Google API
        self.google_api_input = QLineEdit(self.settings['api_keys']['google_api_key'])
        self.google_api_input.setEchoMode(QLineEdit.Password)
        api_layout.addRow("Google API Key:", self.google_api_input)
        
        self.google_cx_input = QLineEdit(self.settings['api_keys']['google_cx'])
        api_layout.addRow("Google Custom Search ID:", self.google_cx_input)
        
        # Bing API
        self.bing_api_input = QLineEdit(self.settings['api_keys']['bing_api_key'])
        self.bing_api_input.setEchoMode(QLineEdit.Password)
        api_layout.addRow("Bing API Key:", self.bing_api_input)
        
        # Brandfetch API
        self.brandfetch_api_input = QLineEdit(self.settings['api_keys']['brandfetch_api_key'])
        self.brandfetch_api_input.setEchoMode(QLineEdit.Password)
        api_layout.addRow("Brandfetch API Key:", self.brandfetch_api_input)
        
        api_tab.setLayout(api_layout)
        tabs.addTab(api_tab, "API Keys")
        
        layout.addWidget(tabs)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self.reset_defaults)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        save_button.setDefault(True)
        
        button_layout.addWidget(reset_button)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def browse_output_dir(self):
        """Open a dialog to select the output directory"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_dir_input.setText(dir_path)
    
    def reset_defaults(self):
        """Reset settings to defaults"""
        if QMessageBox.question(self, "Reset Settings", 
                               "Are you sure you want to reset all settings to defaults?",
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.settings = DEFAULT_SETTINGS.copy()
            self.initUI()  # Reinitialize the UI with default settings
    
    def get_settings(self):
        """Get the updated settings"""
        # Update settings from UI
        self.settings['general']['output_directory'] = self.output_dir_input.text()
        self.settings['general']['max_results'] = self.max_results_spin.value()
        self.settings['general']['search_all_sources'] = self.search_all_checkbox.isChecked()
        self.settings['general']['download_png'] = self.png_checkbox.isChecked()
        self.settings['general']['download_svg'] = self.svg_checkbox.isChecked()
        self.settings['general']['remove_background'] = self.remove_bg_checkbox.isChecked()
        self.settings['general']['enhance_logo'] = self.enhance_checkbox.isChecked()
        self.settings['general']['auto_save'] = self.auto_save_checkbox.isChecked()
        self.settings['general']['theme'] = ["system", "light", "dark"][self.theme_combo.currentIndex()]
        self.settings['general']['check_updates'] = self.updates_checkbox.isChecked()
        
        self.settings['advanced']['timeout'] = self.timeout_spin.value()
        self.settings['advanced']['max_retries'] = self.retries_spin.value()
        self.settings['advanced']['concurrent_searches'] = self.concurrent_spin.value()
        self.settings['advanced']['cache_expiry_days'] = self.cache_spin.value()
        self.settings['advanced']['proxy_enabled'] = self.proxy_checkbox.isChecked()
        self.settings['advanced']['proxy_url'] = self.proxy_input.text()
        self.settings['advanced']['user_agent_rotation'] = self.ua_rotation_checkbox.isChecked()
        self.settings['advanced']['respect_robots_txt'] = self.robots_checkbox.isChecked()
        
        self.settings['api_keys']['google_api_key'] = self.google_api_input.text()
        self.settings['api_keys']['google_cx'] = self.google_cx_input.text()
        self.settings['api_keys']['bing_api_key'] = self.bing_api_input.text()
        self.settings['api_keys']['brandfetch_api_key'] = self.brandfetch_api_input.text()
        
        return self.settings


class LogoPreviewWidget(QWidget):
    """Widget for displaying and editing a logo"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logo_result = None
        self.initUI()
    
    def initUI(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Preview area
        self.preview_label = QLabel("No logo selected")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(300, 300)
        self.preview_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd;")
        
        # Add a drop shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(5, 5)
        self.preview_label.setGraphicsEffect(shadow)
        
        layout.addWidget(self.preview_label)
        
        # Info panel
        info_group = QGroupBox("Logo Information")
        info_layout = QFormLayout()
        
        self.company_label = QLabel("")
        info_layout.addRow("Company:", self.company_label)
        
        self.source_label = QLabel("")
        info_layout.addRow("Source:", self.source_label)
        
        self.format_label = QLabel("")
        info_layout.addRow("Format:", self.format_label)
        
        self.size_label = QLabel("")
        info_layout.addRow("Size:", self.size_label)
        
        self.score_label = QLabel("")
        info_layout.addRow("Quality Score:", self.score_label)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Edit tools
        edit_group = QGroupBox("Edit Tools")
        edit_layout = QHBoxLayout()
        
        self.remove_bg_button = QPushButton("Remove Background")
        self.remove_bg_button.clicked.connect(self.remove_background)
        self.remove_bg_button.setEnabled(False)
        
        self.enhance_button = QPushButton("Enhance")
        self.enhance_button.clicked.connect(self.enhance_logo)
        self.enhance_button.setEnabled(False)
        
        self.resize_button = QPushButton("Resize")
        self.resize_button.clicked.connect(self.resize_logo)
        self.resize_button.setEnabled(False)
        
        self.convert_button = QPushButton("Convert Format")
        self.convert_button.clicked.connect(self.convert_format)
        self.convert_button.setEnabled(False)
        
        edit_layout.addWidget(self.remove_bg_button)
        edit_layout.addWidget(self.enhance_button)
        edit_layout.addWidget(self.resize_button)
        edit_layout.addWidget(self.convert_button)
        
        edit_group.setLayout(edit_layout)
        layout.addWidget(edit_group)
        
        # Export tools
        export_group = QGroupBox("Export")
        export_layout = QHBoxLayout()
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_logo)
        self.save_button.setEnabled(False)
        
        self.copy_button = QPushButton("Copy to Clipboard")
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        self.copy_button.setEnabled(False)
        
        self.favorite_button = QPushButton("Add to Favorites")
        self.favorite_button.clicked.connect(self.add_to_favorites)
        self.favorite_button.setEnabled(False)
        
        export_layout.addWidget(self.save_button)
        export_layout.addWidget(self.copy_button)
        export_layout.addWidget(self.favorite_button)
        
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        
        self.setLayout(layout)
    
    def set_logo(self, logo_result):
        """Set the logo to display"""
        self.logo_result = logo_result
        
        if logo_result:
            # Update preview
            pixmap = logo_result.get_pixmap()
            if pixmap and not pixmap.isNull():
                # Scale the pixmap to fit the preview label while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.preview_label.width(), 
                    self.preview_label.height(), 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled_pixmap)
                self.preview_label.setText("")
            else:
                self.preview_label.setText(f"Preview not available for {logo_result.format_type.upper()} format")
            
            # Update info
            self.company_label.setText(logo_result.company_name)
            self.source_label.setText(logo_result.source)
            self.format_label.setText(logo_result.format_type.upper())
            
            if logo_result.width and logo_result.height:
                self.size_label.setText(f"{logo_result.width}x{logo_result.height}")
            else:
                self.size_label.setText("Unknown")
            
            self.score_label.setText(str(logo_result.score))
            
            # Enable buttons
            self.remove_bg_button.setEnabled(True)
            self.enhance_button.setEnabled(True)
            self.resize_button.setEnabled(True)
            self.convert_button.setEnabled(True)
            self.save_button.setEnabled(True)
            self.copy_button.setEnabled(True)
            self.favorite_button.setEnabled(True)
        else:
            # Clear preview
            self.preview_label.setText("No logo selected")
            self.preview_label.setPixmap(QPixmap())
            
            # Clear info
            self.company_label.setText("")
            self.source_label.setText("")
            self.format_label.setText("")
            self.size_label.setText("")
            self.score_label.setText("")
            
            # Disable buttons
            self.remove_bg_button.setEnabled(False)
            self.enhance_button.setEnabled(False)
            self.resize_button.setEnabled(False)
            self.convert_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.copy_button.setEnabled(False)
            self.favorite_button.setEnabled(False)
    
    def remove_background(self):
        """Remove the background from the logo"""
        if not self.logo_result:
            return
        
        # Get the image
        image = self.logo_result.get_image()
        if not image:
            QMessageBox.warning(self, "Error", "Could not process the image")
            return
        
        # Remove background
        processed_image = ImageProcessor.remove_background(image)
        
        # Update the logo result
        self.logo_result.update_image_data(processed_image)
        
        # Update the preview
        self.set_logo(self.logo_result)
        
        QMessageBox.information(self, "Success", "Background removed successfully")
    
    def enhance_logo(self):
        """Enhance the logo"""
        if not self.logo_result:
            return
        
        # Get the image
        image = self.logo_result.get_image()
        if not image:
            QMessageBox.warning(self, "Error", "Could not process the image")
            return
        
        # Enhance the image
        processed_image = ImageProcessor.enhance_logo(image)
        
        # Update the logo result
        self.logo_result.update_image_data(processed_image)
        
        # Update the preview
        self.set_logo(self.logo_result)
        
        QMessageBox.information(self, "Success", "Logo enhanced successfully")
    
    def resize_logo(self):
        """Resize the logo"""
        if not self.logo_result:
            return
        
        # Get the current dimensions
        width = self.logo_result.width or 200
        height = self.logo_result.height or 200
        
        # Ask for new dimensions
        dialog = QDialog(self)
        dialog.setWindowTitle("Resize Logo")
        
        layout = QFormLayout()
        
        width_spin = QSpinBox()
        width_spin.setRange(10, 2000)
        width_spin.setValue(width)
        layout.addRow("Width:", width_spin)
        
        height_spin = QSpinBox()
        height_spin.setRange(10, 2000)
        height_spin.setValue(height)
        layout.addRow("Height:", height_spin)
        
        maintain_aspect = QCheckBox("Maintain Aspect Ratio")
        maintain_aspect.setChecked(True)
        layout.addRow("", maintain_aspect)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            # Get the image
            image = self.logo_result.get_image()
            if not image:
                QMessageBox.warning(self, "Error", "Could not process the image")
                return
            
            # Resize the image
            new_width = width_spin.value()
            new_height = height_spin.value()
            maintain = maintain_aspect.isChecked()
            
            processed_image = ImageProcessor.resize_image(image, new_width, new_height, maintain)
            
            # Update the logo result
            self.logo_result.update_image_data(processed_image)
            self.logo_result.width = processed_image.width
            self.logo_result.height = processed_image.height
            
            # Update the preview
            self.set_logo(self.logo_result)
            
            QMessageBox.information(self, "Success", "Logo resized successfully")
    
    def convert_format(self):
        """Convert the logo to a different format"""
        if not self.logo_result:
            return
        
        # Ask for the new format
        formats = ["PNG", "JPG", "WEBP"]
        if SVG_SUPPORT:
            formats.append("SVG")
        
        format_type, ok = QInputDialog.getItem(
            self, "Convert Format", "Select format:", formats, 0, False
        )
        
        if ok and format_type:
            # Get the image
            image = self.logo_result.get_image()
            if not image:
                QMessageBox.warning(self, "Error", "Could not process the image")
                return
            
            # Convert the image
            format_type = format_type.lower()
            image_data = ImageProcessor.convert_to_format(image, format_type)
            
            if not image_data:
                QMessageBox.warning(self, "Error", f"Could not convert to {format_type.upper()}")
                return
            
            # Update the logo result
            self.logo_result.image_data = image_data
            self.logo_result.format_type = format_type
            self.logo_result.pixmap = None  # Reset pixmap so it will be regenerated
            
            # Update the preview
            self.set_logo(self.logo_result)
            
            QMessageBox.information(self, "Success", f"Logo converted to {format_type.upper()} successfully")
    
    def save_logo(self):
        """Save the logo to a file"""
        if not self.logo_result:
            return
        
        # Ask for the file name
        default_name = f"{self.logo_result.company_name.lower().replace(' ', '_')}_logo"
        if self.logo_result.format_type == 'svg':
            file_filter = "SVG Files (*.svg)"
            default_ext = ".svg"
        elif self.logo_result.format_type == 'jpg' or self.logo_result.format_type == 'jpeg':
            file_filter = "JPEG Files (*.jpg)"
            default_ext = ".jpg"
        elif self.logo_result.format_type == 'webp':
            file_filter = "WebP Files (*.webp)"
            default_ext = ".webp"
        else:
            file_filter = "PNG Files (*.png)"
            default_ext = ".png"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Logo", 
            os.path.join(os.path.expanduser("~"), "Downloads", default_name + default_ext),
            file_filter
        )
        
        if file_path:
            # Save the logo
            try:
                with open(file_path, 'wb') as f:
                    f.write(self.logo_result.image_data)
                self.logo_result.file_path = file_path
                QMessageBox.information(self, "Success", f"Logo saved to {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error saving logo: {str(e)}")
    
    def copy_to_clipboard(self):
        """Copy the logo to the clipboard"""
        if not self.logo_result:
            return
        
        # Get the pixmap
        pixmap = self.logo_result.get_pixmap()
        if not pixmap or pixmap.isNull():
            QMessageBox.warning(self, "Error", "Could not copy logo to clipboard")
            return
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)
        
        QMessageBox.information(self, "Success", "Logo copied to clipboard")
    
    def add_to_favorites(self):
        """Add the current logo to favorites"""
        if hasattr(self, 'logo_result') and self.logo_result:
            # Find the main application window
            main_window = None
            parent = self.parent()
            
            # Traverse up the parent hierarchy until we find the LogoDownloaderApp
            while parent:
                if isinstance(parent, QMainWindow):
                    main_window = parent
                    break
                parent = parent.parent()
            
            # If we found the main window, add to favorites
            if main_window and hasattr(main_window, 'add_to_favorites'):
                main_window.add_to_favorites(self.logo_result)
            else:
                print("Could not find main application window to add to favorites")
        else:
            QMessageBox.information(self, "No Logo", "No logo is currently selected to add to favorites.")


class LogoDownloaderApp(QMainWindow):
    """Main application window"""
    def __init__(self):
        super().__init__()
        
        print("Initializing database...")
        # Initialize database
        self.db = Database()
        
        print("Loading settings...")
        # Load settings
        self.settings = self.load_settings()
        
        print("Initializing UI...")
        # Initialize UI
        self.initUI()
        
        print("Applying theme...")
        # Apply theme
        self.apply_theme()
        
        # Check for updates if enabled
        if self.settings['general']['check_updates']:
            print("Scheduling update check...")
            QTimer.singleShot(1000, self.check_for_updates)
        
        print("LogoDownloaderApp initialization complete")
    
    def initUI(self):
        """Initialize the user interface"""
        print("initUI: Setting window properties...")
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setGeometry(100, 100, 1000, 700)
        
        # Set application icon
        self.setWindowIcon(self.get_app_icon())
        
        print("initUI: Creating central widget...")
        # Create central widget and main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        print("initUI: Creating toolbar...")
        # Create toolbar
        self.create_toolbar()
        
        print("initUI: Creating menu...")
        # Create menu
        self.create_menu()
        
        print("initUI: Creating status bar...")
        # Create status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        
        print("initUI: Creating main splitter...")
        # Create main splitter
        main_splitter = QSplitter(Qt.Vertical)
        
        # Top section (search controls)
        top_widget = QWidget()
        top_layout = QVBoxLayout()
        top_widget.setLayout(top_layout)
        
        print("initUI: Creating header...")
        # Header with logo and title
        header_layout = QHBoxLayout()
        
        logo_label = QLabel()
        logo_pixmap = self.get_app_icon().pixmap(64, 64)
        logo_label.setPixmap(logo_pixmap)
        
        title_label = QLabel(APP_NAME)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        top_layout.addLayout(header_layout)
        
        print("initUI: Creating search form...")
        # Search form
        search_group = QGroupBox("Search for Company Logo")
        search_layout = QVBoxLayout()
        
        # Company name input with autocomplete
        name_layout = QHBoxLayout()
        name_label = QLabel("Company Name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter company name (e.g., Google, Microsoft, etc.)")
        
        print("initUI: Setting up autocomplete...")
        # Set up autocomplete from history
        self.setup_autocomplete()
        
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.search_logos)
        search_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input, 1)
        name_layout.addWidget(search_button)
        
        search_layout.addLayout(name_layout)
        
        # Quick options
        options_layout = QHBoxLayout()
        
        # Format options
        format_group = QGroupBox("Format")
        format_layout = QHBoxLayout()
        
        self.png_checkbox = QCheckBox("PNG")
        self.png_checkbox.setChecked(self.settings['general']['download_png'])
        self.svg_checkbox = QCheckBox("SVG")
        self.svg_checkbox.setChecked(self.settings['general']['download_svg'])
        
        format_layout.addWidget(self.png_checkbox)
        format_layout.addWidget(self.svg_checkbox)
        
        format_group.setLayout(format_layout)
        options_layout.addWidget(format_group)
        
        # Processing options
        processing_group = QGroupBox("Processing")
        processing_layout = QHBoxLayout()
        
        self.remove_bg_checkbox = QCheckBox("Remove Background")
        self.remove_bg_checkbox.setChecked(self.settings['general']['remove_background'])
        self.enhance_checkbox = QCheckBox("Enhance")
        self.enhance_checkbox.setChecked(self.settings['general']['enhance_logo'])
        
        processing_layout.addWidget(self.remove_bg_checkbox)
        processing_layout.addWidget(self.enhance_checkbox)
        
        processing_group.setLayout(processing_layout)
        options_layout.addWidget(processing_group)
        
        # Search options
        search_options_group = QGroupBox("Search Options")
        search_options_layout = QHBoxLayout()
        
        self.search_all_checkbox = QCheckBox("Search All Sources")
        self.search_all_checkbox.setChecked(self.settings['general']['search_all_sources'])
        
        max_results_label = QLabel("Max Results:")
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 50)
        self.max_results_spin.setValue(self.settings['general']['max_results'])
        
        search_options_layout.addWidget(self.search_all_checkbox)
        search_options_layout.addWidget(max_results_label)
        search_options_layout.addWidget(self.max_results_spin)
        
        search_options_group.setLayout(search_options_layout)
        options_layout.addWidget(search_options_group)
        
        search_layout.addLayout(options_layout)
        
        search_group.setLayout(search_layout)
        top_layout.addWidget(search_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.hide()
        top_layout.addWidget(self.progress_bar)
        
        main_splitter.addWidget(top_widget)
        
        # Bottom section (results and preview)
        bottom_splitter = QSplitter(Qt.Horizontal)
        
        # Results panel
        results_widget = QWidget()
        results_layout = QVBoxLayout()
        results_widget.setLayout(results_layout)
        
        # Results tabs
        self.results_tabs = QTabWidget()
        
        # Search results tab
        self.search_results_widget = QWidget()
        search_results_layout = QVBoxLayout()
        
        # Add scroll area for results list to ensure it's always accessible
        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll_content = QWidget()
        results_scroll_layout = QVBoxLayout(results_scroll_content)
        
        self.results_list = QListWidget()
        self.results_list.setIconSize(QSize(64, 64))
        self.results_list.itemClicked.connect(self.show_logo_preview)
        
        results_scroll_layout.addWidget(self.results_list)
        results_scroll.setWidget(results_scroll_content)
        
        search_results_layout.addWidget(results_scroll)
        
        self.search_results_widget.setLayout(search_results_layout)
        self.results_tabs.addTab(self.search_results_widget, "Search Results")
        
        # Favorites tab
        self.favorites_widget = QWidget()
        favorites_layout = QVBoxLayout()
        
        # Add scroll area for favorites list to ensure it's always accessible
        favorites_scroll = QScrollArea()
        favorites_scroll.setWidgetResizable(True)
        favorites_scroll_content = QWidget()
        favorites_scroll_layout = QVBoxLayout(favorites_scroll_content)
        
        self.favorites_list = QListWidget()
        self.favorites_list.setIconSize(QSize(64, 64))
        self.favorites_list.itemClicked.connect(self.show_favorite_preview)
        
        favorites_scroll_layout.addWidget(self.favorites_list)
        favorites_scroll.setWidget(favorites_scroll_content)
        
        favorites_layout.addWidget(favorites_scroll)
        
        self.favorites_widget.setLayout(favorites_layout)
        self.results_tabs.addTab(self.favorites_widget, "Favorites")
        
        # History tab
        self.history_widget = QWidget()
        history_layout = QVBoxLayout()
        
        # Add scroll area for history table to ensure it's always accessible
        history_scroll = QScrollArea()
        history_scroll.setWidgetResizable(True)
        history_scroll_content = QWidget()
        history_scroll_layout = QVBoxLayout(history_scroll_content)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(3)
        self.history_table.setHorizontalHeaderLabels(["Company", "Date", "Results"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        history_scroll_layout.addWidget(self.history_table)
        history_scroll.setWidget(history_scroll_content)
        
        history_layout.addWidget(history_scroll)
        
        self.history_widget.setLayout(history_layout)
        self.results_tabs.addTab(self.history_widget, "History")
        
        # Log tab
        self.log_widget = QWidget()
        log_layout = QVBoxLayout()
        
        # Add scroll area for log output to ensure it's always accessible
        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll_content = QWidget()
        log_scroll_layout = QVBoxLayout(log_scroll_content)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        
        log_scroll_layout.addWidget(self.log_output)
        log_scroll.setWidget(log_scroll_content)
        
        log_layout.addWidget(log_scroll)
        
        self.log_widget.setLayout(log_layout)
        self.results_tabs.addTab(self.log_widget, "Log")
        
        results_layout.addWidget(self.results_tabs)
        
        bottom_splitter.addWidget(results_widget)
        
        # Preview panel
        preview_group = QGroupBox("Logo Preview")
        preview_layout = QVBoxLayout()
        
        # Add scroll area for preview widget to ensure it's always accessible
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll_content = QWidget()
        preview_scroll_layout = QVBoxLayout(preview_scroll_content)
        
        self.preview_widget = LogoPreviewWidget(self)
        preview_scroll_layout.addWidget(self.preview_widget)
        preview_scroll.setWidget(preview_scroll_content)
        
        preview_layout.addWidget(preview_scroll)
        preview_group.setLayout(preview_layout)
        
        bottom_splitter.addWidget(preview_group)
        
        # Set the initial sizes of the bottom splitter
        bottom_splitter.setSizes([300, 700])
        
        main_splitter.addWidget(bottom_splitter)
        
        # Set the initial sizes of the main splitter
        main_splitter.setSizes([200, 600])
        
        main_layout.addWidget(main_splitter)
        
        # Initialize the search manager
        self.search_manager = None
        self.search_results = []
        
        # Load favorites
        self.load_favorites()
        
        # Load history
        self.load_history()
        
        # Connect signals
        self.name_input.returnPressed.connect(self.search_logos)
    
    def create_toolbar(self):
        """Create the application toolbar"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # Search action
        search_action = QAction(self.style().standardIcon(QStyle.SP_FileDialogContentsView), "Search", self)
        search_action.setStatusTip("Search for company logos")
        search_action.triggered.connect(self.search_logos)
        toolbar.addAction(search_action)
        
        toolbar.addSeparator()
        
        # Save action
        save_action = QAction(self.style().standardIcon(QStyle.SP_DialogSaveButton), "Save", self)
        save_action.setStatusTip("Save the selected logo")
        save_action.triggered.connect(self.save_selected_logo)
        toolbar.addAction(save_action)
        
        # Copy action
        copy_action = QAction(self.style().standardIcon(QStyle.SP_DialogSaveButton), "Copy", self)
        copy_action.setStatusTip("Copy the selected logo to clipboard")
        copy_action.triggered.connect(self.copy_to_clipboard)
        toolbar.addAction(copy_action)
        
        toolbar.addSeparator()
        
        # Settings action
        settings_action = QAction(self.style().standardIcon(QStyle.SP_FileDialogDetailedView), "Settings", self)
        settings_action.setStatusTip("Open settings dialog")
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)
        
        # Help action
        help_action = QAction(self.style().standardIcon(QStyle.SP_DialogHelpButton), "Help", self)
        help_action.setStatusTip("Show help")
        help_action.triggered.connect(self.show_help)
        toolbar.addAction(help_action)
    
    def create_menu(self):
        """Create the application menu"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        search_action = QAction("&Search", self)
        search_action.setShortcut("Ctrl+F")
        search_action.setStatusTip("Search for company logos")
        search_action.triggered.connect(self.search_logos)
        file_menu.addAction(search_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("&Save Logo", self)
        save_action.setShortcut("Ctrl+S")
        save_action.setStatusTip("Save the selected logo")
        save_action.triggered.connect(self.save_selected_logo)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        
        copy_action = QAction("&Copy to Clipboard", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.setStatusTip("Copy the selected logo to clipboard")
        copy_action.triggered.connect(self.copy_to_clipboard)
        edit_menu.addAction(copy_action)
        
        edit_menu.addSeparator()
        
        remove_bg_action = QAction("Remove &Background", self)
        remove_bg_action.setStatusTip("Remove the background from the selected logo")
        remove_bg_action.triggered.connect(self.remove_background)
        edit_menu.addAction(remove_bg_action)
        
        enhance_action = QAction("&Enhance Logo", self)
        enhance_action.setStatusTip("Enhance the selected logo")
        enhance_action.triggered.connect(self.enhance_logo)
        edit_menu.addAction(enhance_action)
        
        resize_action = QAction("&Resize Logo", self)
        resize_action.setStatusTip("Resize the selected logo")
        resize_action.triggered.connect(self.resize_logo)
        edit_menu.addAction(resize_action)
        
        convert_action = QAction("&Convert Format", self)
        convert_action.setStatusTip("Convert the selected logo to a different format")
        convert_action.triggered.connect(self.convert_format)
        edit_menu.addAction(convert_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        settings_action = QAction("&Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.setStatusTip("Open settings dialog")
        settings_action.triggered.connect(self.open_settings)
        tools_menu.addAction(settings_action)
        
        tools_menu.addSeparator()
        
        clear_cache_action = QAction("Clear &Cache", self)
        clear_cache_action.setStatusTip("Clear the logo cache")
        clear_cache_action.triggered.connect(self.clear_cache)
        tools_menu.addAction(clear_cache_action)
        
        clear_history_action = QAction("Clear &History", self)
        clear_history_action.setStatusTip("Clear search history")
        clear_history_action.triggered.connect(self.clear_history)
        tools_menu.addAction(clear_history_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        help_action = QAction("&Help", self)
        help_action.setShortcut("F1")
        help_action.setStatusTip("Show help")
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)
        
        about_action = QAction("&About", self)
        about_action.setStatusTip("Show about dialog")
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        check_updates_action = QAction("Check for &Updates", self)
        check_updates_action.setStatusTip("Check for updates")
        check_updates_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(check_updates_action)
    
    def get_app_icon(self):
        """Get the application icon"""
        # Create a simple icon if none is available
        icon = QIcon()
        
        # Create a pixmap with a logo-like design
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw a rounded rectangle
        painter.setBrush(QBrush(QColor(41, 128, 185)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 10, 10)
        
        # Draw a stylized "L" for Logo
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRoundedRect(16, 16, 12, 32, 4, 4)
        painter.drawRoundedRect(16, 40, 32, 8, 4, 4)
        
        painter.end()
        
        icon.addPixmap(pixmap)
        return icon
    
    def setup_autocomplete(self):
        """Set up autocomplete for the company name input"""
        print("setup_autocomplete: Starting...")
        try:
            # Get company names from history
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT company_name FROM search_history ORDER BY timestamp DESC LIMIT 100")
            company_names = [row[0] for row in cursor.fetchall()]
            print(f"setup_autocomplete: Retrieved {len(company_names)} company names from history")
            
            # Create completer
            completer = QCompleter(company_names, self)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            self.name_input.setCompleter(completer)
            print("setup_autocomplete: Completer set up successfully")
        except Exception as e:
            print(f"setup_autocomplete: Error - {str(e)}")
    
    def load_settings(self):
        """Load application settings"""
        # Create a QSettings object
        qsettings = QSettings("LogoDownloader", "LogoDownloaderPro")
        
        # Start with default settings
        settings = DEFAULT_SETTINGS.copy()
        
        # Update with saved settings if available
        if qsettings.contains("settings"):
            saved_settings = qsettings.value("settings")
            
            # Update each section
            for section in saved_settings:
                if section in settings:
                    for key in saved_settings[section]:
                        if key in settings[section]:
                            settings[section][key] = saved_settings[section][key]
        
        return settings
    
    def save_settings(self):
        """Save application settings"""
        qsettings = QSettings("LogoDownloader", "LogoDownloaderPro")
        qsettings.setValue("settings", self.settings)
    
    def apply_theme(self):
        """Apply the selected theme"""
        theme = self.settings['general']['theme']
        
        if theme == "system":
            # Use system theme
            QApplication.setStyle("Fusion")
        elif theme == "dark":
            # Set dark theme
            dark_palette = QPalette()
            
            dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.WindowText, Qt.white)
            dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
            dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
            dark_palette.setColor(QPalette.ToolTipText, Qt.white)
            dark_palette.setColor(QPalette.Text, Qt.white)
            dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ButtonText, Qt.white)
            dark_palette.setColor(QPalette.BrightText, Qt.red)
            dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.HighlightedText, Qt.black)
            
            QApplication.setPalette(dark_palette)
            QApplication.setStyle("Fusion")
        elif theme == "light":
            # Set light theme
            QApplication.setPalette(QApplication.style().standardPalette())
            QApplication.setStyle("Fusion")
    
    def search_logos(self):
        """Start the logo search process"""
        company_name = self.name_input.text().strip()
        
        if not company_name:
            QMessageBox.warning(self, "Input Error", "Please enter a company name")
            return
        
        # Update settings from UI
        self.settings['general']['download_png'] = self.png_checkbox.isChecked()
        self.settings['general']['download_svg'] = self.svg_checkbox.isChecked()
        self.settings['general']['remove_background'] = self.remove_bg_checkbox.isChecked()
        self.settings['general']['enhance_logo'] = self.enhance_checkbox.isChecked()
        self.settings['general']['search_all_sources'] = self.search_all_checkbox.isChecked()
        self.settings['general']['max_results'] = self.max_results_spin.value()
        
        if not self.settings['general']['download_png'] and not self.settings['general']['download_svg']:
            QMessageBox.warning(self, "Format Error", "Please select at least one output format (PNG or SVG)")
            return
        
        # Clear previous results
        self.results_list.clear()
        self.search_results = []
        self.preview_widget.set_logo(None)
        
        # Show progress bar
        self.progress_bar.show()
        
        # Switch to the log tab
        self.results_tabs.setCurrentIndex(3)  # Log tab
        
        # Clear log
        self.log_output.clear()
        self.log_output.append(f"Searching for logos: {company_name}")
        
        # Create and start the search manager
        self.search_manager = LogoSearchManager(company_name, self.settings, self.db)
        self.search_manager.progress_update.connect(self.update_log)
        self.search_manager.search_result.connect(self.add_search_result)
        self.search_manager.search_complete.connect(self.search_finished)
        self.search_manager.start_search()
        
        # Update status
        self.statusBar.showMessage(f"Searching for {company_name} logos...")
    
    def update_log(self, message):
        """Update the log output with a new message"""
        self.log_output.append(message)
        # Scroll to the bottom
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())
    
    def add_search_result(self, result):
        """Add a search result to the results list"""
        self.search_results.append(result)
        
        # Create a list item
        item = QListWidgetItem()
        item.setText(f"{result.source} ({result.format_type.upper()})")
        item.setData(Qt.UserRole, result.id)  # Store the result ID
        
        # Set the icon if possible
        pixmap = result.get_pixmap()
        if pixmap and not pixmap.isNull():
            item.setIcon(QIcon(pixmap))
        
        # Add the item to the list
        self.results_list.addItem(item)
        
        # Switch to the results tab
        self.results_tabs.setCurrentIndex(0)  # Search Results tab
        
        # If this is the first result, show it in the preview
        if len(self.search_results) == 1:
            self.preview_widget.set_logo(result)
    
    def search_finished(self, success, results):
        """Handle the completion of the search process"""
        # Hide progress bar
        self.progress_bar.hide()
        
        if success:
            self.statusBar.showMessage(f'Found {len(results)} logos')
            self.update_log(f"✅ Search completed successfully. Found {len(results)} logos.")
            
            # Select the first result if available
            if self.results_list.count() > 0:
                self.results_list.setCurrentRow(0)
                self.show_logo_preview(self.results_list.item(0))
            
            # Auto-save if enabled
            if self.settings['general']['auto_save'] and results:
                self.auto_save_results(results)
        else:
            self.statusBar.showMessage('No logos found')
            self.update_log("❌ Search completed. No logos found.")
            self.preview_widget.set_logo(None)
        
        # Refresh the history
        self.load_history()
        
        # Update autocomplete
        self.setup_autocomplete()
    
    def show_logo_preview(self, item):
        """Show a preview of the selected logo"""
        if not item:
            return
        
        result_id = item.data(Qt.UserRole)
        
        # Find the result with this ID
        for result in self.search_results:
            if result.id == result_id:
                self.preview_widget.set_logo(result)
                break
    
    def show_favorite_preview(self, item):
        """Show a preview of the selected favorite logo"""
        if not item:
            return
        
        result_id = item.data(Qt.UserRole)
        
        # Find the result with this ID
        favorites = self.db.get_favorites()
        for favorite in favorites:
            if favorite.id == result_id:
                self.preview_widget.set_logo(favorite)
                break
    
    def save_selected_logo(self):
        """Save the selected logo to a file"""
        self.preview_widget.save_logo()
    
    def copy_to_clipboard(self):
        """Copy the selected logo to the clipboard"""
        self.preview_widget.copy_to_clipboard()
    
    def remove_background(self):
        """Remove the background from the selected logo"""
        self.preview_widget.remove_background()
    
    def enhance_logo(self):
        """Enhance the selected logo"""
        self.preview_widget.enhance_logo()
    
    def resize_logo(self):
        """Resize the selected logo"""
        self.preview_widget.resize_logo()
    
    def convert_format(self):
        """Convert the selected logo to a different format"""
        self.preview_widget.convert_format()
    
    def add_to_favorites(self, logo_result):
        """Add a logo to favorites"""
        if not logo_result:
            return
        
        # Add to database
        if self.db.add_to_favorites(logo_result):
            QMessageBox.information(self, "Success", f"Added {logo_result.company_name} logo to favorites")
            
            # Refresh favorites list
            self.load_favorites()
        else:
            QMessageBox.warning(self, "Error", "Failed to add logo to favorites")
    
    def load_favorites(self):
        """Load favorites from the database"""
        self.favorites_list.clear()
        
        favorites = self.db.get_favorites()
        
        for favorite in favorites:
            item = QListWidgetItem()
            item.setText(f"{favorite.company_name} ({favorite.format_type.upper()})")
            item.setData(Qt.UserRole, favorite.id)
            
            # Set the icon if possible
            pixmap = favorite.get_pixmap()
            if pixmap and not pixmap.isNull():
                item.setIcon(QIcon(pixmap))
            
            self.favorites_list.addItem(item)
    
    def load_history(self):
        """Load search history from the database"""
        self.history_table.setRowCount(0)
        
        history = self.db.get_history()
        
        for i, (company, timestamp, results_count) in enumerate(history):
            self.history_table.insertRow(i)
            self.history_table.setItem(i, 0, QTableWidgetItem(company))
            self.history_table.setItem(i, 1, QTableWidgetItem(timestamp))
            self.history_table.setItem(i, 2, QTableWidgetItem(str(results_count)))
    
    def auto_save_results(self, results):
        """Automatically save the best results"""
        if not results:
            return
        
        # Sort by score
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        
        # Save the best result
        best_result = sorted_results[0]
        
        output_dir = self.settings['general']['output_directory']
        
        # Create directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Save the file
        file_path = best_result.save_to_file(output_dir)
        
        if file_path:
            self.update_log(f"✅ Automatically saved best logo to {file_path}")
    
    def open_settings(self):
        """Open the settings dialog"""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() == QDialog.Accepted:
            # Update settings
            self.settings = dialog.get_settings()
            
            # Save settings
            self.save_settings()
            
            # Apply theme
            self.apply_theme()
            
            # Update UI elements
            self.png_checkbox.setChecked(self.settings['general']['download_png'])
            self.svg_checkbox.setChecked(self.settings['general']['download_svg'])
            self.remove_bg_checkbox.setChecked(self.settings['general']['remove_background'])
            self.enhance_checkbox.setChecked(self.settings['general']['enhance_logo'])
            self.search_all_checkbox.setChecked(self.settings['general']['search_all_sources'])
            self.max_results_spin.setValue(self.settings['general']['max_results'])
    
    def clear_cache(self):
        """Clear the logo cache"""
        if QMessageBox.question(self, "Clear Cache", 
                               "Are you sure you want to clear the logo cache?",
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            if self.db.clear_cache():
                QMessageBox.information(self, "Success", "Cache cleared successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to clear cache")
    
    def clear_history(self):
        """Clear search history"""
        if QMessageBox.question(self, "Clear History", 
                               "Are you sure you want to clear the search history?",
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                cursor = self.db.conn.cursor()
                cursor.execute('DELETE FROM search_history')
                self.db.conn.commit()
                
                # Refresh history
                self.load_history()
                
                # Update autocomplete
                self.setup_autocomplete()
                
                QMessageBox.information(self, "Success", "History cleared successfully")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to clear history: {str(e)}")
    
    def check_for_updates(self):
        """Check for updates"""
        # This is a placeholder for update checking functionality
        # In a real implementation, you would check a server for updates
        QMessageBox.information(self, "Updates", f"You are running the latest version: {APP_VERSION}")
    
    def show_help(self):
        """Show help information"""
        help_text = f"""
        <h2>{APP_NAME} Help</h2>
        
        <h3>Basic Usage</h3>
        <p>1. Enter a company name in the search box</p>
        <p>2. Click "Search" or press Enter</p>
        <p>3. Select a logo from the results list to preview it</p>
        <p>4. Use the tools to edit the logo if needed</p>
        <p>5. Save or copy the logo</p>
        
        <h3>Features</h3>
        <ul>
            <li>Search for logos from multiple sources</li>
            <li>Remove backgrounds from logos</li>
            <li>Enhance and resize logos</li>
            <li>Convert between different formats</li>
            <li>Save favorites for quick access</li>
            <li>View search history</li>
        </ul>
        
        <h3>Keyboard Shortcuts</h3>
        <ul>
            <li>Ctrl+F: Search</li>
            <li>Ctrl+S: Save logo</li>
            <li>Ctrl+C: Copy to clipboard</li>
            <li>Ctrl+,: Open settings</li>
            <li>F1: Show help</li>
            <li>Ctrl+Q: Exit</li>
        </ul>
        
        <h3>Support</h3>
        <p>For support, please contact support@logodownloader.com</p>
        """
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Help")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(help_text)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.exec_()
    
    def show_about(self):
        """Show about information"""
        about_text = f"""
        <h2>{APP_NAME} v{APP_VERSION}</h2>
        
        <p>A professional tool for finding and downloading company logos.</p>
        
        <p> 2023 Logo Downloader Inc. All rights reserved.</p>
        
        <p>This software is provided "as is" without warranty of any kind.</p>
        """
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(about_text)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.exec_()
    
    def closeEvent(self, event):
        """Handle the window close event"""
        # Save settings
        self.save_settings()
        
        # Close database connection
        self.db.close()
        
        # Accept the event
        event.accept()


if __name__ == '__main__':
    print("Starting Logo Downloader application...")
    
    try:
        print("Initializing main window...")
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        app.setOrganizationName("Logo Downloader Inc.")
        app.setOrganizationDomain("logodownloader.com")
        window = LogoDownloaderApp()
        print("Main window initialized, showing UI...")
        window.show()
        print("UI shown, entering application event loop...")
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error starting application: {str(e)}")
        import traceback
        traceback.print_exc()