# Document Processing module for Hercules Agent
# PDF, Markdown processing

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import asyncio
import logging
import os
import re
import json
from pathlib import Path
from datetime import datetime
from io import BytesIO
from abc import ABC, abstractmethod
import base64
import hashlib

logger = logging.getLogger(__name__)


class DocumentType(Enum):
    """Supported document types"""
    MARKDOWN = "markdown"
    PDF = "pdf"
    TEXT = "text"
    HTML = "html"
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"
    UNKNOWN = "unknown"


@dataclass
class DocumentMetadata:
    """Document metadata"""
    filename: str = ""
    doc_type: DocumentType = DocumentType.UNKNOWN
    size: int = 0
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    
    # Content info
    char_count: int = 0
    word_count: int = 0
    line_count: int = 0
    
    # Extraction info
    pages: int = 0
    images: int = 0
    tables: int = 0
    
    # Custom metadata
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentContent:
    """Processed document content"""
    raw: str = ""
    text: str = ""
    html: str = ""
    markdown: str = ""
    
    # Extracted elements
    headings: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    code_blocks: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[List[Any]] = field(default_factory=list)
    
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)


# ==================== Base Processor ====================

class BaseProcessor(ABC):
    """Base class for document processors"""
    
    @abstractmethod
    async def process(self, content: Union[str, bytes], metadata: DocumentMetadata = None) -> DocumentContent:
        """Process document"""
        pass
    
    @abstractmethod
    async def extract_text(self, content: Union[str, bytes]) -> str:
        """Extract plain text"""
        pass


# ==================== Markdown Processor ====================

class MarkdownProcessor(BaseProcessor):
    """Markdown document processor"""
    
    def __init__(self):
        self._heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self._link_pattern = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')
        self._image_pattern = re.compile(r'!\[([^\]]*)\]\(([^\)]+)\)')
        self._code_block_pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
        self._table_pattern = re.compile(r'\|(.+)\|\n\|[-:\s]+\|', re.DOTALL)
    
    async def process(self, content: Union[str, bytes], metadata: DocumentMetadata = None) -> DocumentContent:
        """Process markdown document"""
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        doc = DocumentContent(raw=content, markdown=content)
        
        # Extract text (basic stripping)
        doc.text = self._strip_markdown(content)
        
        # Extract headings
        doc.headings = self._extract_headings(content)
        
        # Extract links
        doc.links = self._extract_links(content)
        
        # Extract images
        doc.images = self._extract_images(content)
        
        # Extract code blocks
        doc.code_blocks = self._extract_code_blocks(content)
        
        # Extract tables
        doc.tables = self._extract_tables(content)
        
        # Build metadata
        if metadata:
            doc.metadata = metadata
        
        doc.metadata.doc_type = DocumentType.MARKDOWN
        doc.metadata.char_count = len(doc.text)
        doc.metadata.word_count = len(doc.text.split())
        doc.metadata.line_count = len(content.split('\n'))
        
        return doc
    
    async def extract_text(self, content: Union[str, bytes]) -> str:
        """Extract plain text from markdown"""
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        return self._strip_markdown(content)
    
    def _strip_markdown(self, text: str) -> str:
        """Strip markdown formatting"""
        # Remove images
        text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
        
        # Remove links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove headers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # Remove bold/italic
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        
        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        
        # Remove inline code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Remove horizontal rules
        text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def _extract_headings(self, text: str) -> List[Dict[str, Any]]:
        """Extract headings"""
        headings = []
        for match in self._heading_pattern.finditer(text):
            level = len(match.group(1))
            text = match.group(2).strip()
            headings.append({"level": level, "text": text})
        return headings
    
    def _extract_links(self, text: str) -> List[Dict[str, str]]:
        """Extract links"""
        return [
            {"text": m.group(1), "url": m.group(2)}
            for m in self._link_pattern.finditer(text)
        ]
    
    def _extract_images(self, text: str) -> List[Dict[str, str]]:
        """Extract images"""
        return [
            {"alt": m.group(1), "url": m.group(2)}
            for m in self._image_pattern.finditer(text)
        ]
    
    def _extract_code_blocks(self, text: str) -> List[Dict[str, Any]]:
        """Extract code blocks"""
        blocks = []
        for match in self._code_block_pattern.finditer(text):
            blocks.append({
                "language": match.group(1) or "text",
                "code": match.group(2).strip()
            })
        return blocks
    
    def _extract_tables(self, text: str) -> List[List[Any]]:
        """Extract tables"""
        tables = []
        
        # Find table-like structures
        lines = text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('|') and line.endswith('|'):
                # Found potential table
                table = []
                
                # Check if next line is separator
                if i + 1 < len(lines) and re.match(r'\|[-:\s]+\|', lines[i + 1]):
                    # Parse header
                    header = [cell.strip() for cell in line.split('|')[1:-1]]
                    table.append(header)
                    
                    # Skip separator
                    i += 2
                    
                    # Parse rows
                    while i < len(lines) and lines[i].strip().startswith('|'):
                        row = [cell.strip() for cell in lines[i].split('|')[1:-1]]
                        table.append(row)
                        i += 1
                    
                    if table:
                        tables.append(table)
                else:
                    i += 1
            else:
                i += 1
        
        return tables


# ==================== PDF Processor ====================

class PDFProcessor(BaseProcessor):
    """PDF document processor using PyMuPDF"""
    
    def __init__(self):
        self._fitz = None
        self._try_import()
    
    def _try_import(self):
        """Try to import PyMuPDF"""
        try:
            import fitz
            self._fitz = fitz
        except ImportError:
            logger.warning("PyMuPDF not installed. PDF processing will be limited.")
    
    async def process(self, content: Union[str, bytes], metadata: DocumentMetadata = None) -> DocumentContent:
        """Process PDF document"""
        doc = DocumentContent()
        
        if metadata:
            doc.metadata = metadata
        
        if self._fitz:
            return await self._process_fitz(content, doc)
        else:
            return await self._process_simple(content, doc)
    
    async def _process_fitz(self, content: Union[str, bytes], doc: DocumentContent) -> DocumentContent:
        """Process with PyMuPDF"""
        # Open from bytes or path
        if isinstance(content, bytes):
            doc_file = self._fitz.open-stream(BytesIO(content))
        else:
            doc_file = self._fitz.open(content)
        
        doc.metadata.pages = len(doc_file)
        
        # Extract text from each page
        full_text = []
        for page_num, page in enumerate(doc_file):
            text = page.get_text()
            full_text.append(text)
            
            # Extract images
            images = page.get_images()
            doc.metadata.images += len(images)
            
            # Extract tables (basic)
            tables = page.find_tables()
            doc.metadata.tables += len(tables)
        
        doc.raw = b"\n\n".join([p.bytes for p in doc_file]) if hasattr(doc_file, 'bytes') else str(full_text)
        doc.text = "\n\n".join(full_text)
        
        doc_file.close()
        
        # Extract metadata from document
        if isinstance(content, str) and os.path.exists(content):
            stat = os.stat(content)
            doc.metadata.size = stat.st_size
            doc.metadata.created_at = datetime.fromtimestamp(stat.st_ctime)
            doc.metadata.modified_at = datetime.fromtimestamp(stat.st_mtime)
        
        doc.metadata.doc_type = DocumentType.PDF
        doc.metadata.char_count = len(doc.text)
        doc.metadata.word_count = len(doc.text.split())
        doc.metadata.line_count = len(doc.text.split('\n'))
        
        return doc
    
    async def _process_simple(self, content: Union[str, bytes], doc: DocumentContent) -> DocumentContent:
        """Simple fallback processing"""
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')
        
        doc.text = content
        doc.raw = content
        
        doc.metadata.doc_type = DocumentType.PDF
        doc.metadata.char_count = len(content)
        
        return doc
    
    async def extract_text(self, content: Union[str, bytes]) -> str:
        """Extract plain text from PDF"""
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')
        return content
    
    async def extract_images(self, content: Union[str, bytes]) -> List[Dict[str, Any]]:
        """Extract images from PDF"""
        if not self._fitz:
            return []
        
        images = []
        
        if isinstance(content, bytes):
            doc_file = self._fitz.open_stream(BytesIO(content))
        else:
            doc_file = self._fitz.open(content)
        
        for page_num, page in enumerate(doc_file):
            for img_index, img in enumerate(page.get_images()):
                xref = img[0]
                base_image = doc_file.extract_image(xref)
                
                images.append({
                    "page": page_num + 1,
                    "index": img_index,
                    "width": base_image.get("width"),
                    "height": base_image.get("height"),
                    "colorspace": base_image.get("colorspace"),
                    "bpc": base_image.get("bpc"),
                    "image": base_image.get("image")
                })
        
        doc_file.close()
        
        return images


# ==================== Text Processor ====================

class TextProcessor(BaseProcessor):
    """Plain text processor"""
    
    async def process(self, content: Union[str, bytes], metadata: DocumentMetadata = None) -> DocumentContent:
        """Process plain text"""
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')
        
        doc = DocumentContent(
            raw=content,
            text=content,
            markdown=content  # Plain text is also valid markdown
        )
        
        if metadata:
            doc.metadata = metadata
        
        doc.metadata.doc_type = DocumentType.TEXT
        doc.metadata.char_count = len(content)
        doc.metadata.word_count = len(content.split())
        doc.metadata.line_count = len(content.split('\n'))
        
        return doc
    
    async def extract_text(self, content: Union[str, bytes]) -> str:
        """Extract plain text"""
        if isinstance(content, bytes):
            return content.decode('utf-8', errors='ignore')
        return content


# ==================== JSON Processor ====================

class JSONProcessor(BaseProcessor):
    """JSON document processor"""
    
    async def process(self, content: Union[str, bytes], metadata: DocumentMetadata = None) -> DocumentContent:
        """Process JSON document"""
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        doc = DocumentContent()
        
        try:
            data = json.loads(content)
            doc.raw = content
            doc.text = json.dumps(data, indent=2)
            doc.metadata.custom["parsed"] = True
        except json.JSONDecodeError as e:
            doc.raw = content
            doc.text = content
            doc.metadata.custom["parsed"] = False
            doc.metadata.custom["error"] = str(e)
        
        if metadata:
            doc.metadata = metadata
        
        doc.metadata.doc_type = DocumentType.JSON
        doc.metadata.char_count = len(doc.text)
        
        return doc
    
    async def extract_text(self, content: Union[str, bytes]) -> str:
        """Extract text from JSON"""
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        try:
            data = json.loads(content)
            return json.dumps(data, indent=2)
        except:
            return content


# ==================== HTML Processor ====================

class HTMLProcessor(BaseProcessor):
    """HTML document processor"""
    
    def __init__(self):
        self._bs4 = None
        self._try_import()
    
    def _try_import(self):
        """Try to import BeautifulSoup"""
        try:
            from bs4 import BeautifulSoup
            self._bs4 = BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup4 not installed. HTML processing will be limited.")
    
    async def process(self, content: Union[str, bytes], metadata: DocumentMetadata = None) -> DocumentContent:
        """Process HTML document"""
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        doc = DocumentContent(raw=content, html=content)
        
        if self._bs4:
            soup = self._bs4(content, 'html.parser')
            
            # Extract text
            doc.text = soup.get_text()
            
            # Convert to markdown (basic)
            doc.markdown = self._html_to_md(soup)
            
            # Extract links
            for link in soup.find_all('a'):
                doc.links.append({
                    "text": link.get_text(strip=True),
                    "url": link.get('href', '')
                })
            
            # Extract images
            for img in soup.find_all('img'):
                doc.images.append({
                    "alt": img.get('alt', ''),
                    "url": img.get('src', '')
                })
            
            # Extract headings
            for i in range(1, 7):
                for heading in soup.find_all(f'h{i}'):
                    doc.headings.append({
                        "level": i,
                        "text": heading.get_text(strip=True)
                    })
        else:
            doc.text = content
            doc.markdown = content
        
        if metadata:
            doc.metadata = metadata
        
        doc.metadata.doc_type = DocumentType.HTML
        doc.metadata.char_count = len(doc.text)
        doc.metadata.word_count = len(doc.text.split())
        
        return doc
    
    async def extract_text(self, content: Union[str, bytes]) -> str:
        """Extract plain text from HTML"""
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        if self._bs4:
            soup = self._bs4(content, 'html.parser')
            return soup.get_text()
        
        return content
    
    def _html_to_md(self, soup) -> str:
        """Convert HTML to markdown"""
        md = []
        
        for element in soup.body.children if soup.body else []:
            if element.name == 'h1':
                md.append(f"# {element.get_text()}\n")
            elif element.name == 'h2':
                md.append(f"## {element.get_text()}\n")
            elif element.name == 'h3':
                md.append(f"### {element.get_text()}\n")
            elif element.name == 'p':
                md.append(f"{element.get_text()}\n")
            elif element.name == 'a':
                md.append(f"[{element.get_text()}]({element.get('href', '')})\n")
            elif element.name == 'img':
                md.append(f"![{element.get('alt', '')}]({element.get('src', '')})\n")
            elif element.name == 'ul':
                for li in element.find_all('li'):
                    md.append(f"- {li.get_text()}\n")
            elif element.name == 'ol':
                for i, li in enumerate(element.find_all('li'), 1):
                    md.append(f"{i}. {li.get_text()}\n")
            elif element.name == 'code':
                md.append(f"`{element.get_text()}`\n")
            elif element.name == 'pre':
                md.append(f"```\n{element.get_text()}\n```\n")
            elif element.name and element.name.startswith('h'):
                md.append(f"{element.get_text()}\n")
        
        return '\n'.join(md)


# ==================== Document Processor ====================

class DocumentProcessor:
    """Main document processor with auto-detection"""
    
    def __init__(self):
        self._processors: Dict[DocumentType, BaseProcessor] = {
            DocumentType.MARKDOWN: MarkdownProcessor(),
            DocumentType.PDF: PDFProcessor(),
            DocumentType.TEXT: TextProcessor(),
            DocumentType.JSON: JSONProcessor(),
            DocumentType.HTML: HTMLProcessor(),
        }
    
    def detect_type(self, content: Union[str, bytes], filename: str = "") -> DocumentType:
        """Detect document type"""
        # From filename
        if filename:
            ext = Path(filename).suffix.lower()
            type_map = {
                '.md': DocumentType.MARKDOWN,
                '.markdown': DocumentType.MARKDOWN,
                '.pdf': DocumentType.PDF,
                '.txt': DocumentType.TEXT,
                '.html': DocumentType.HTML,
                '.htm': DocumentType.HTML,
                '.json': DocumentType.JSON,
                '.yaml': DocumentType.YAML,
                '.yml': DocumentType.YAML,
                '.csv': DocumentType.CSV,
            }
            if ext in type_map:
                return type_map[ext]
        
        # From content
        if isinstance(content, bytes):
            content = content[:1000].decode('utf-8', errors='ignore')
        
        content = content.strip()
        
        # Check for specific patterns
        if content.startswith('{') or content.startswith('['):
            try:
                json.loads(content)
                return DocumentType.JSON
            except:
                pass
        
        if content.startswith('#') or content.startswith('##'):
            return DocumentType.MARKDOWN
        
        if '<!DOCTYPE' in content or '<html' in content:
            return DocumentType.HTML
        
        if content.startswith('%PDF'):
            return DocumentType.PDF
        
        return DocumentType.TEXT
    
    async def process(
        self,
        content: Union[str, bytes],
        filename: str = "",
        metadata: DocumentMetadata = None
    ) -> DocumentContent:
        """Process document with auto-detection"""
        doc_type = self.detect_type(content, filename)
        
        metadata = metadata or DocumentMetadata(filename=filename)
        metadata.doc_type = doc_type
        
        processor = self._processors.get(doc_type)
        
        if not processor:
            # Default to text
            processor = self._processors[DocumentType.TEXT]
        
        return await processor.process(content, metadata)
    
    async def extract_text(self, content: Union[str, bytes], filename: str = "") -> str:
        """Extract plain text from document"""
        doc_type = self.detect_type(content, filename)
        processor = self._processors.get(doc_type, self._processors[DocumentType.TEXT])
        
        return await processor.extract_text(content)
    
    def get_processor(self, doc_type: DocumentType) -> Optional[BaseProcessor]:
        """Get processor for specific type"""
        return self._processors.get(doc_type)
    
    def register_processor(self, doc_type: DocumentType, processor: BaseProcessor):
        """Register custom processor"""
        self._processors[doc_type] = processor


# ==================== Document Loader ====================

class DocumentLoader:
    """Load documents from various sources"""
    
    def __init__(self, processor: DocumentProcessor = None):
        self.processor = processor or DocumentProcessor()
    
    async def from_file(self, path: str) -> DocumentContent:
        """Load document from file"""
        path = os.path.expanduser(path)
        
        with open(path, 'rb') as f:
            content = f.read()
        
        filename = os.path.basename(path)
        
        return await self.processor.process(
            content,
            filename=filename,
            metadata=DocumentMetadata(
                filename=filename,
                size=len(content),
                created_at=datetime.fromtimestamp(os.path.getctime(path)),
                modified_at=datetime.fromtimestamp(os.path.getmtime(path))
            )
        )
    
    async def from_url(self, url: str) -> DocumentContent:
        """Load document from URL"""
        import aiohttp
        
        filename = url.split('/')[-1]
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                content = await response.read()
        
        return await self.processor.process(
            content,
            filename=filename,
            metadata=DocumentMetadata(
                filename=filename,
                size=len(content)
            )
        )
    
    async def from_bytes(self, content: bytes, filename: str = "unknown") -> DocumentContent:
        """Load document from bytes"""
        return await self.processor.process(
            content,
            filename=filename,
            metadata=DocumentMetadata(
                filename=filename,
                size=len(content)
            )
        )
    
    async def from_text(self, text: str, filename: str = "unknown") -> DocumentContent:
        """Load document from text"""
        return await self.processor.process(
            text,
            filename=filename,
            metadata=DocumentMetadata(
                filename=filename,
                size=len(text.encode('utf-8'))
            )
        )