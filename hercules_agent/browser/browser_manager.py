# Browser Automation module for Hercules Agent
# CDP (Chrome DevTools Protocol) browser control

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import asyncio
import logging
import json
import base64
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class BrowserType(Enum):
    """Browser types"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class Viewport:
    """Browser viewport"""
    width: int = 1280
    height: int = 720
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    is_touch: bool = False


@dataclass
class BrowserConfig:
    """Browser configuration"""
    browser_type: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    viewport: Viewport = None
    user_agent: str = ""
    proxy: str = ""  # proxy URL
    slow_mo: int = 0  # ms
    timeout: int = 30000  # ms
    ignore_https_errors: bool = False
    downloads_path: str = ""
    
    # Advanced
    enable_cdp: bool = True  # Chrome DevTools Protocol
    cdp_url: str = ""  # Connect to existing browser
    browser_args: List[str] = field(default_factory=list)


@dataclass
class Element:
    """Page element"""
    selector: str
    xpath: str = ""
    text: str = ""
    tag_name: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    is_visible: bool = True
    is_enabled: bool = True
    bounding_box: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenshotResult:
    """Screenshot result"""
    data: bytes  # base64 encoded
    path: Optional[str]
    format: str  # png, jpeg


@dataclass
class BrowserState:
    """Current browser state"""
    url: str = ""
    title: str = ""
    cookies: List[Dict] = field(default_factory=list)
    local_storage: Dict[str, str] = field(default_factory=dict)
    scroll_position: Dict[str, int] = field(default_factory=dict)


# ==================== Browser Client ====================

class CDPClient:
    """Chrome DevTools Protocol client"""
    
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._connection = None
        self._send_id = 0
        self._callbacks: Dict[int, asyncio.Future] = {}
    
    async def connect(self):
        """Connect to browser via CDP"""
        import websockets
        
        self._connection = await websockets.connect(self.ws_url)
        logger.info(f"Connected to CDP: {self.ws_url}")
    
    async def send(self, method: str, params: Dict = None) -> Dict:
        """Send CDP command"""
        if not self._connection:
            raise RuntimeError("Not connected")
        
        self._send_id += 1
        message = {
            "id": self._send_id,
            "method": method,
            "params": params or {}
        }
        
        future = asyncio.Future()
        self._callbacks[self._send_id] = future
        
        await self._connection.send(json.dumps(message))
        
        # Wait for response
        result = await future
        return result
    
    async def _receive_loop(self):
        """Receive CDP messages"""
        async for message in self._connection:
            data = json.loads(message)
            
            if "id" in data:
                callback_id = data["id"]
                if callback_id in self._callbacks:
                    future = self._callbacks.pop(callback_id)
                    future.set_result(data.get("result", {}))
    
    async def close(self):
        """Close connection"""
        if self._connection:
            await self._connection.close()


# ==================== Browser Page ====================

class BrowserPage:
    """Browser page/tab"""
    
    def __init__(self, browser: 'Browser', page_id: str):
        self.browser = browser
        self.page_id = page_id
        self._cdp: Optional[CDPClient] = None
    
    @property
    def cdp(self) -> CDPClient:
        """Get CDP client"""
        if self._cdp is None:
            raise RuntimeError("CDP not connected")
        return self._cdp
    
    async def goto(self, url: str, wait_until: str = "networkidle") -> Dict:
        """Navigate to URL"""
        result = await self.cdp.send("Page.navigate", {"url": url})
        await self.cdp.send("Page.waitUntil", {"waitUntil": wait_until})
        return result
    
    async def reload(self):
        """Reload page"""
        await self.cdp.send("Page.reload")
    
    async def go_back(self):
        """Go back"""
        await self.cdp.send("Page.goBack")
    
    async def go_forward(self):
        """Go forward"""
        await self.cdp.send("Page.goForward")
    
    async def url(self) -> str:
        """Get current URL"""
        result = await self.cdp.send("Page.getLayoutMetrics")
        return result.get("url", "")
    
    async def title(self) -> str:
        """Get page title"""
        result = await self.cdp.send("Page.getNavigationHistory")
        return result.get("entries", [{}])[-1].get("title", "")
    
    async def screenshot(
        self,
        full_page: bool = False,
        format: str = "png",
        quality: int = 80
    ) -> ScreenshotResult:
        """Take screenshot"""
        params = {
            "format": format,
            "quality": quality,
            "captureBeyondViewport": full_page,
        }
        
        result = await self.cdp.send("Page.captureScreenshot", params)
        
        return ScreenshotResult(
            data=base64.b64decode(result["data"]),
            path=None,
            format=format
        )
    
    async def click(self, selector: str):
        """Click element"""
        # First find element
        await self.cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const el = document.querySelector('{selector}');
                    if (!el) throw new Error('Element not found');
                    el.click();
                }})()
            """
        })
    
    async def type(self, selector: str, text: str, clear: bool = True):
        """Type into element"""
        expr = f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el) throw new Error('Element not found');
                if ({clear}) el.value = '';
                el.value += '{text}';
            }})()
        """
        await self.cdp.send("Runtime.evaluate", {"expression": expr})
    
    async def evaluate(self, expression: str) -> Any:
        """Execute JavaScript"""
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        return result.get("result", {}).get("value")
    
    async def wait_for_selector(
        self,
        selector: str,
        timeout: int = 30000
    ) -> Optional[Element]:
        """Wait for element"""
        expr = f"""
            (() => {{
                return document.querySelector('{selector}');
            }})()
        """
        result = await self.cdp.send("Runtime.evaluate", {"expression": expr})
        # Note: Real implementation would poll
        return None
    
    async def get_elements(self, selector: str) -> List[Element]:
        """Get all elements matching selector"""
        expr = f"""
            (() => {{
                const els = document.querySelectorAll('{selector}');
                return Array.from(els).map(el => ({{
                    tagName: el.tagName,
                    text: el.textContent,
                    attributes: Object.fromEntries(
                        Array.from(el.attributes).map(a => [a.name, a.value])
                    )
                }}));
            }})()
        """
        result = await self.cdp.send("Runtime.evaluate", {"expression": expr})
        data = result.get("result", {}).get("value", [])
        
        return [Element(selector=selector, **item) for item in data]
    
    async def scroll_to(self, x: int, y: int):
        """Scroll to position"""
        await self.evaluate(f"window.scrollTo({x}, {y})")
    
    async def scroll_by(self, delta_x: int, delta_y: int):
        """Scroll by delta"""
        await self.evaluate(f"window.scrollBy({delta_x}, {delta_y})")
    
    async def cookies(self) -> List[Dict]:
        """Get cookies"""
        result = await self.cdp.send("Network.getCookies")
        return result.get("cookies", [])
    
    async def set_cookies(self, cookies: List[Dict]):
        """Set cookies"""
        await self.cdp.send("Network.setCookies", {"cookies": cookies})
    
    async def local_storage(self) -> Dict[str, str]:
        """Get local storage"""
        result = await self.evaluate("Object.fromEntries(Object.entries(localStorage))")
        return result or {}
    
    async def set_local_storage(self, data: Dict[str, str]):
        """Set local storage"""
        for key, value in data.items():
            await self.evaluate(f"localStorage.setItem('{key}', '{value}')")
    
    async def close(self):
        """Close this page"""
        await self.browser._cdp.send("Target.closeTarget", {
            "targetId": self.page_id
        })


# ==================== Browser ====================

class Browser:
    """Main browser controller"""
    
    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self._browser = None
        self._cdp: Optional[CDPClient] = None
        self._pages: Dict[str, BrowserPage] = {}
        self._current_page: Optional[BrowserPage] = None
    
    async def launch(self) -> bool:
        """Launch browser"""
        try:
            from playwright.async_api import async_playwright
            
            pw = await async_playwright().start()
            
            if self.config.browser_type == BrowserType.CHROMIUM:
                self._browser = await pw.chromium.launch(
                    headless=self.config.headless,
                    args=self.config.browser_args,
                    proxy={
                        "server": self.config.proxy
                    } if self.config.proxy else None,
                )
            elif self.config.browser_type == BrowserType.FIREFOX:
                self._browser = await pw.firefox.launch(
                    headless=self.config.headless,
                )
            else:
                self._browser = await pw.webkit.launch(
                    headless=self.config.headless,
                )
            
            # Create context
            context = await self._browser.new_context(
                user_agent=self.config.user_agent or None,
                viewport=(
                    self.config.viewport.__dict__
                    if self.config.viewport
                    else None
                ),
                ignore_https_errors=self.config.ignore_https_errors,
            )
            
            # Get CDP session
            if self.config.enable_cdp:
                cdp = await context.new_cdp_session(context.browser)
                self._cdp = cdp
            
            # Create initial page
            page = await context.new_page()
            self._current_page = BrowserPage(self, page._impl_obj._browser_context._channel._connection)
            
            logger.info("Browser launched")
            return True
            
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return False
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            return False
    
    async def connect(self, cdp_url: str) -> bool:
        """Connect to existing browser"""
        self._cdp = CDPClient(cdp_url)
        await self._cdp.connect()
        
        # Get targets
        result = await self._cdp.send("Target.getTargets")
        
        logger.info(f"Connected to browser at {cdp_url}")
        return True
    
    async def new_page(self, url: str = "about:blank") -> BrowserPage:
        """Open new page/tab"""
        if self._browser:
            context = (await self._browser.contexts()[0]) if self._browser.contexts else await self._browser.new_context()
            page = await context.new_page()
            
            if url != "about:blank":
                await page.goto(url)
            
            return BrowserPage(self, page)
        
        raise RuntimeError("Browser not launched")
    
    async def close(self):
        """Close browser"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._cdp:
            await self._cdp.close()
            self._cdp = None
        
        logger.info("Browser closed")
    
    @property
    def page(self) -> Optional[BrowserPage]:
        """Get current page"""
        return self._current_page
    
    async def get_state(self) -> BrowserState:
        """Get browser state"""
        if not self._current_page:
            return BrowserState()
        
        return BrowserState(
            url=await self._current_page.url(),
            title=await self._current_page.title(),
            cookies=await self._current_page.cookies(),
            local_storage=await self._current_page.local_storage(),
        )


# ==================== Browser Manager ====================

class BrowserManager:
    """Manages multiple browser instances"""
    
    def __init__(self):
        self._browsers: Dict[str, Browser] = {}
        self._default: Optional[Browser] = None
    
    async def create_browser(
        self,
        name: str = "default",
        config: BrowserConfig = None
    ) -> Browser:
        """Create browser instance"""
        browser = Browser(config or BrowserConfig())
        success = await browser.launch()
        
        if success:
            self._browsers[name] = browser
            self._default = browser
            return browser
        
        raise RuntimeError("Failed to create browser")
    
    def get_browser(self, name: str = "default") -> Optional[Browser]:
        """Get browser by name"""
        return self._browsers.get(name)
    
    def get_default(self) -> Optional[Browser]:
        """Get default browser"""
        return self._default
    
    async def close_browser(self, name: str = "default"):
        """Close browser"""
        browser = self._browsers.get(name)
        if browser:
            await browser.close()
            del self._browsers[name]
    
    async def close_all(self):
        """Close all browsers"""
        for browser in self._browsers.values():
            await browser.close()
        self._browsers.clear()
        self._default = None