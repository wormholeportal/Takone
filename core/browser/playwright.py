"""Browser automation for video research.

Manually spawns Chrome (no --enable-automation flag) with a dedicated
user-data-dir, then connects Playwright via CDP.

- No automation banner ("Chrome is being controlled by automated software")
- No conflict with user's running Chrome (separate profile)
- Login state persists across sessions (first-time login only)
"""

import asyncio
import json
import os
import random
import subprocess
import sys
import time as _time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class BrowserConnectionError(Exception):
    """Raised when unable to connect to Chrome."""
    pass


@dataclass
class VideoRef:
    """A reference video found during search."""
    title: str = ""
    url: str = ""
    likes: str = ""
    platform: str = ""
    thumbnail_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "likes": self.likes,
            "platform": self.platform,
        }


# Platform search URL templates
PLATFORM_SEARCH_URLS = {
    "douyin": "https://www.douyin.com/search/{query}",
    "bilibili": "https://search.bilibili.com/all?keyword={query}",
    "xiaohongshu": "https://www.xiaohongshu.com/search_result?keyword={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
}

# Web search engine templates
WEB_SEARCH_URLS = {
    "baidu": "https://www.baidu.com/s?wd={query}",
    "google": "https://www.google.com/search?q={query}",
    "baidu_image": "https://image.baidu.com/search/index?tn=baiduimage&word={query}",
    "google_image": "https://www.google.com/search?tbm=isch&q={query}",
    "zhihu": "https://www.zhihu.com/search?type=content&q={query}",
    "baike": "https://baike.baidu.com/search?word={query}",
}

# ── User-Agent pool ─────────────────────────────────────────────────────

_UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]


def random_ua() -> str:
    """Return a random User-Agent string from the pool."""
    return random.choice(_UA_POOL)


# ── Domain rate limiter ─────────────────────────────────────────────────


class DomainRateLimiter:
    """Per-domain rate limiter with exponential backoff on errors."""

    def __init__(self, min_interval: float = 3.0, max_interval: float = 6.0):
        self._last_request: dict[str, float] = {}
        self._min = min_interval
        self._max = max_interval
        self._backoff: dict[str, int] = defaultdict(int)

    async def wait(self, url: str):
        """Wait if needed before making a request to this domain."""
        domain = urlparse(url).netloc
        now = _time.monotonic()
        interval = random.uniform(self._min, self._max)
        backoff = self._backoff.get(domain, 0)
        if backoff > 0:
            interval *= min(2 ** backoff, 30)
        elapsed = now - self._last_request.get(domain, 0)
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        self._last_request[domain] = _time.monotonic()

    def success(self, url: str):
        """Record a successful request — reset backoff."""
        self._backoff[urlparse(url).netloc] = 0

    def error(self, url: str):
        """Record a failed request — increase backoff."""
        domain = urlparse(url).netloc
        self._backoff[domain] = self._backoff.get(domain, 0) + 1


# Module-level singleton shared across all browser instances
_rate_limiter = DomainRateLimiter()


# ── Paths & constants ────────────────────────────────────────────────────

DIRECTOR_BROWSER_DIR = Path.home() / ".director" / "browser-profile"

# macOS Chrome paths
CHROME_EXECUTABLES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    # Fallbacks
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
]

CDP_PORT = 19222  # Use non-standard port to avoid conflict with user's debug port


# ── Chrome process management ────────────────────────────────────────────

def find_chrome_executable() -> str | None:
    """Find a Chrome/Chromium executable on the system."""
    for path in CHROME_EXECUTABLES:
        if os.path.exists(path):
            return path
    return None


def _get_cdp_ws_url() -> str | None:
    """Get the CDP WebSocket URL from Chrome's /json/version endpoint.

    Returns the ws:// URL if Chrome is running, None otherwise.
    """
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{CDP_PORT}/json/version",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            return data.get("webSocketDebuggerUrl") or None
    except Exception:
        return None


def is_director_chrome_running() -> bool:
    """Check if Director's Chrome instance is already running on our CDP port."""
    return _get_cdp_ws_url() is not None


def launch_director_chrome() -> subprocess.Popen:
    """Spawn a dedicated Chrome instance for Director (no automation flags).

    Key: We do NOT pass --enable-automation, so Chrome won't show
    "Chrome is being controlled by automated test software" banner.
    This avoids triggering bot detection on most platforms.
    """
    chrome_path = find_chrome_executable()
    if not chrome_path:
        raise BrowserConnectionError(
            "Chrome browser not found. Please install Google Chrome:\n"
            "  https://www.google.com/chrome/"
        )

    user_data_dir = str(DIRECTOR_BROWSER_DIR)
    os.makedirs(user_data_dir, exist_ok=True)

    args = [
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={user_data_dir}",
        # No --enable-automation! (critical difference from Playwright launcher)
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-features=Translate,MediaRouter",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--password-store=basic",
        # Open blank tab so CDP has a target
        "about:blank",
    ]

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


# ── Platform-specific extraction JavaScript ──────────────────────────────

# Douyin uses div-based cards (no <a> links). We find cards by locating
# thumbnail images (class contains "videoImage") and walk up to the card
# container, then parse visible text for title/likes/author/duration.
EXTRACT_JS = {
    "douyin": """
(function() {
    var results = [];
    var seen = {};
    // Strategy 1: find video thumbnail containers
    var images = document.querySelectorAll('[class*="videoImage"], [class*="VideoImage"]');
    if (images.length === 0) {
        // Fallback: find Douyin-specific thumbnail images
        images = document.querySelectorAll('img[src*="douyinpic"], img[src*="tplv-dy"]');
    }
    images.forEach(function(img) {
        var card = img;
        // Walk up to find the card wrapper (contains both image and title text)
        for (var i = 0; i < 8; i++) {
            if (!card.parentElement) break;
            card = card.parentElement;
            var text = (card.innerText || '').trim();
            if (text.length > 30 && text.includes('@')) break;
        }
        var text = (card.innerText || '').trim();
        if (text.length < 20) return;
        // Deduplicate by text content
        var textKey = text.substring(0, 50);
        if (seen[textKey]) return;
        seen[textKey] = true;
        // Parse card text into structured fields
        var lines = text.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
        var title = '', likes = '', duration = '', author = '';
        for (var j = 0; j < lines.length; j++) {
            var line = lines[j];
            if (/^\\d{2}:\\d{2}(:\\d{2})?$/.test(line)) {
                duration = line;
            } else if (/^[\\d.]+[万亿]?$/.test(line) && !likes) {
                likes = line;
            } else if (line.startsWith('@')) {
                author = line.substring(1);
            } else if (line.length > 8 && !title && !/^·|^\\d{1,2}月|^\\d{4}年|^\\d+天前|^\\d+小时前|^综合$|^视频$|^用户$|^直播$|^多列$|^单列$|^筛选$|^全部/.test(line)) {
                title = line;
            }
        }
        if (title) {
            results.push({
                title: title.substring(0, 150),
                url: 'https://www.douyin.com/search/' + encodeURIComponent(title.substring(0, 30)),
                likes: likes,
                duration: duration,
                author: author,
                platform: 'douyin'
            });
        }
    });
    // Strategy 2 fallback: if no videoImage found, try link-based extraction
    if (results.length === 0) {
        document.querySelectorAll('a[href*="/video/"]').forEach(function(a) {
            var href = a.getAttribute('href') || '';
            if (!href || seen[href]) return;
            seen[href] = true;
            var title = a.getAttribute('aria-label') || a.innerText.trim();
            if (title.length > 3 && !/ICP|备案|许可证|版权|京B2/.test(title)) {
                if (!href.startsWith('http')) href = 'https://www.douyin.com' + href;
                results.push({title: title.substring(0, 100), url: href, likes: '', platform: 'douyin'});
            }
        });
    }
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "bilibili": """
(function() {
    var results = [];
    document.querySelectorAll('.video-list-item, .bili-video-card').forEach(function(card) {
        var titleEl = card.querySelector('.title, .bili-video-card__info--tit a');
        var title = titleEl ? titleEl.innerText.trim() : '';
        var linkEl = card.querySelector('a[href*="/video/"]');
        var href = linkEl ? linkEl.getAttribute('href') : '';
        if (href && !href.startsWith('http')) href = 'https://www.bilibili.com' + href;
        var statEl = card.querySelector('[class*="stat"], [class*="count"]');
        var likes = statEl ? statEl.innerText.trim() : '';
        if (title) results.push({title: title.substring(0, 100), url: href, likes: likes, platform: 'bilibili'});
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "xiaohongshu": """
(function() {
    var results = [];
    var seen = {};
    document.querySelectorAll('section.note-item a, a[href*="/explore/"], a[href*="/discovery/"]').forEach(function(a) {
        var href = a.getAttribute('href') || '';
        if (!href || seen[href]) return;
        seen[href] = true;
        if (!href.startsWith('http')) href = 'https://www.xiaohongshu.com' + href;
        var titleEl = a.querySelector('[class*="title"], [class*="desc"], span.title, p');
        var title = titleEl ? titleEl.innerText.trim() : a.innerText.trim();
        if (title && title.length > 3)
            results.push({title: title.substring(0, 100), url: href, likes: '', platform: 'xiaohongshu'});
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "youtube": """
(function() {
    var results = [];
    document.querySelectorAll('ytd-video-renderer').forEach(function(item) {
        var titleEl = item.querySelector('#video-title');
        var title = titleEl ? titleEl.innerText.trim() : '';
        var href = titleEl ? titleEl.getAttribute('href') : '';
        if (href && !href.startsWith('http')) href = 'https://www.youtube.com' + href;
        var viewEl = item.querySelector('[class*="metadata"] span');
        var views = viewEl ? viewEl.innerText.trim() : '';
        if (title) results.push({title: title.substring(0, 100), url: href, likes: views, platform: 'youtube'});
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "_generic": """
(function() {
    var results = [];
    var seen = {};
    var noise = /ICP|备案|许可证|版权|cookie|京公网|京B2/;
    document.querySelectorAll('a[href]').forEach(function(a) {
        var href = a.getAttribute('href') || '';
        var text = a.innerText.trim();
        if (!text || text.length < 8 || seen[href] || noise.test(text)) return;
        seen[href] = true;
        results.push({title: text.substring(0, 100), url: href, likes: '', platform: '__PLATFORM__'});
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
}

# Web search extraction JS (for search_web / search_images)
WEB_EXTRACT_JS = {
    "baidu": """
(function() {
    var results = [];
    document.querySelectorAll('.result, .c-container').forEach(function(item) {
        var titleEl = item.querySelector('h3 a, .t a');
        if (!titleEl) return;
        var title = titleEl.innerText.trim();
        var href = titleEl.getAttribute('href') || '';
        var snippetEl = item.querySelector('.c-abstract, .content-right_2s-H4, [class*="content"]');
        var snippet = snippetEl ? snippetEl.innerText.trim().substring(0, 200) : '';
        if (title && title.length > 2)
            results.push({title: title.substring(0, 150), url: href, snippet: snippet});
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "google": """
(function() {
    var results = [];
    document.querySelectorAll('div.g, div[data-hveid]').forEach(function(item) {
        var titleEl = item.querySelector('h3');
        if (!titleEl) return;
        var title = titleEl.innerText.trim();
        var linkEl = item.querySelector('a[href^="http"]');
        var href = linkEl ? linkEl.getAttribute('href') : '';
        var snippetEl = item.querySelector('[data-sncf], .VwiC3b, [class*="IsZvec"]');
        var snippet = snippetEl ? snippetEl.innerText.trim().substring(0, 200) : '';
        if (title)
            results.push({title: title.substring(0, 150), url: href, snippet: snippet});
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "zhihu": """
(function() {
    var results = [];
    document.querySelectorAll('.SearchResult-Card, .Card').forEach(function(item) {
        var titleEl = item.querySelector('h2, [class*="ContentItem-title"] a');
        if (!titleEl) return;
        var title = titleEl.innerText.trim();
        var linkEl = item.querySelector('a[href*="/question/"], a[href*="/p/"], a[href*="/answer/"]');
        var href = linkEl ? linkEl.getAttribute('href') : '';
        if (href && !href.startsWith('http')) href = 'https://www.zhihu.com' + href;
        var snippetEl = item.querySelector('[class*="RichText"], .CopyrightRichText-richText');
        var snippet = snippetEl ? snippetEl.innerText.trim().substring(0, 200) : '';
        if (title && title.length > 3)
            results.push({title: title.substring(0, 150), url: href, snippet: snippet});
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "baike": """
(function() {
    var results = [];
    document.querySelectorAll('.searchResult .resultList dd, .search-list dd, .result-list li').forEach(function(item) {
        var titleEl = item.querySelector('a[href*="/item/"], a[href*="baike.baidu.com"]');
        if (!titleEl) return;
        var title = titleEl.innerText.trim();
        var href = titleEl.getAttribute('href') || '';
        if (href && !href.startsWith('http')) href = 'https://baike.baidu.com' + href;
        var snippetEl = item.querySelector('p, .abstract, [class*="desc"]');
        var snippet = snippetEl ? snippetEl.innerText.trim().substring(0, 200) : '';
        if (title && title.length > 1)
            results.push({title: title.substring(0, 150), url: href, snippet: snippet});
    });
    // Fallback: if on a direct baike page, extract summary
    if (results.length === 0) {
        var mainTitle = document.querySelector('h1');
        var summary = document.querySelector('.lemma-summary, [class*="lemmaSummary"], .para[label-module="para"]');
        if (mainTitle && summary) {
            results.push({
                title: mainTitle.innerText.trim(),
                url: window.location.href,
                snippet: summary.innerText.trim().substring(0, 500)
            });
        }
    }
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "baidu_image": """
(function() {
    var results = [];
    var seen = {};
    // Try imgdata global variable first (Baidu image internal data)
    if (window.imgData && window.imgData.data) {
        window.imgData.data.forEach(function(item) {
            if (item.thumbURL || item.objURL || item.middleURL) {
                results.push({
                    title: (item.fromPageTitleEnc || item.fromPageTitle || '').substring(0, 100),
                    url: item.fromURL || '',
                    image_url: item.objURL || item.middleURL || item.thumbURL,
                    thumbnail_url: item.thumbURL || item.middleURL || ''
                });
            }
        });
    }
    // Fallback: find all img tags with baidu CDN URLs (modern Baidu Image layout)
    if (results.length === 0) {
        document.querySelectorAll('img[src*="baidu.com/it/"], img[src*="baiduimage"], img[data-imgurl]').forEach(function(img) {
            var src = img.getAttribute('data-imgurl') || img.getAttribute('src') || '';
            if (!src || !src.startsWith('http') || seen[src]) return;
            // Skip tiny icons and logos
            var w = img.naturalWidth || img.width || 0;
            var h = img.naturalHeight || img.height || 0;
            if (w > 0 && w < 50) return;
            if (h > 0 && h < 50) return;
            // Skip result@2 logo
            if (src.includes('/img/flexible/logo/')) return;
            seen[src] = true;
            results.push({
                title: img.getAttribute('alt') || img.getAttribute('title') || '',
                url: '',
                image_url: src,
                thumbnail_url: src
            });
        });
    }
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
    "google_image": """
(function() {
    var results = [];
    document.querySelectorAll('[data-ri], [jsname] img[src^="http"]').forEach(function(el) {
        var img = el.tagName === 'IMG' ? el : el.querySelector('img');
        if (!img) return;
        var src = img.getAttribute('src') || '';
        if (!src.startsWith('http') || src.includes('gstatic.com/images')) return;
        var title = img.getAttribute('alt') || '';
        results.push({
            title: title.substring(0, 100),
            url: '',
            image_url: src,
            thumbnail_url: src
        });
    });
    return JSON.stringify(results.slice(0, __MAX__));
})()
""",
}

# JS to extract main text content from a page (strips nav/ads/footer)
EXTRACT_TEXT_JS = """
(function() {
    // Remove noise elements
    var selectors = ['nav', 'header', 'footer', 'aside', '.ad', '.ads', '.sidebar',
                     '.comment', '.comments', '#comment', '[class*="recommend"]',
                     '[class*="related"]', 'script', 'style', 'noscript'];
    selectors.forEach(function(sel) {
        document.querySelectorAll(sel).forEach(function(el) { el.remove(); });
    });
    // Try article/main content first
    var main = document.querySelector('article, main, .article, .content, .post, .entry, [class*="article-content"], [class*="post-content"], [role="main"], .lemma-summary, .para[label-module="para"]');
    if (!main) main = document.body;
    var text = (main.innerText || '').trim();
    // Clean up excessive whitespace
    text = text.replace(/\\n{3,}/g, '\\n\\n').replace(/[ \\t]{2,}/g, ' ');
    return text.substring(0, 10000);
})()
"""


# ── Main browser class ───────────────────────────────────────────────────

class PlaywrightBrowser:
    """Browser automation via CDP:
    manually spawn Chrome + connect Playwright via CDP.

    - No automation banner
    - Dedicated profile (~/.director/browser-profile/)
    - Login state persists across sessions
    - Does not conflict with user's running Chrome
    """

    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._chrome_proc = None

    async def _ensure_browser(self):
        """Ensure Director's Chrome is running and Playwright is connected."""
        if self._context is not None:
            return

        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()

        # Step 1: Check if Director's Chrome is already running
        if not is_director_chrome_running():
            is_first_run = not DIRECTOR_BROWSER_DIR.exists() or not any(DIRECTOR_BROWSER_DIR.iterdir())

            print("  Starting Director browser...", file=sys.stderr)
            self._chrome_proc = launch_director_chrome()

            # Wait for CDP to be ready (poll /json/version)
            ready = False
            for _ in range(20):  # Up to 10 seconds
                await asyncio.sleep(0.5)
                if is_director_chrome_running():
                    ready = True
                    break

            if not ready:
                raise BrowserConnectionError(
                    "Failed to start Chrome. Please ensure Google Chrome is installed."
                )

            if is_first_run:
                print("  ✓ Director browser started (first run)", file=sys.stderr)
                print("  ℹ To log in to platforms (e.g. Douyin), use the launched browser", file=sys.stderr)
                print("    Login state is saved automatically; no need to log in again next time\n", file=sys.stderr)
            else:
                print("  ✓ Director browser started", file=sys.stderr)
        else:
            print("  ✓ Connected to Director browser", file=sys.stderr)

        # Step 2: Connect Playwright via CDP websocket URL directly
        # (avoids Playwright's HTTP resolution which can fail with 400)
        ws_url = _get_cdp_ws_url()
        if not ws_url:
            raise BrowserConnectionError("Failed to get Chrome CDP WebSocket URL")

        try:
            self._browser = await self._pw.chromium.connect_over_cdp(
                ws_url,
                timeout=10000,
            )
        except Exception as e:
            raise BrowserConnectionError(f"Playwright CDP connection failed: {e}")

        # Reuse existing context (preserves cookies/login state)
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context(
                viewport={
                    "width": 1280 + random.randint(-20, 20),
                    "height": 800 + random.randint(-10, 10),
                },
                locale="zh-CN",
                user_agent=random_ua(),
            )

    # ── Human-like behavior helpers ─────────────────────────────────────

    async def _human_scroll(self, page, rounds: int = 8):
        """Scroll with human-like randomness in distance, speed, and pauses."""
        for _ in range(rounds):
            dist = random.randint(500, 1000)
            await page.evaluate(f"window.scrollBy(0, {dist})")
            await page.wait_for_timeout(random.randint(800, 2500))
            # 15% chance of a longer pause (simulating reading)
            if random.random() < 0.15:
                await page.wait_for_timeout(random.randint(2000, 4000))

    async def _human_wait(self, page, min_ms: int = 1500, max_ms: int = 3500):
        """Random wait simulating human reaction time."""
        await page.wait_for_timeout(random.randint(min_ms, max_ms))

    async def _human_mouse(self, page):
        """Random mouse movement to simulate human activity."""
        try:
            await page.mouse.move(
                random.randint(100, 1100), random.randint(100, 600)
            )
            await page.wait_for_timeout(random.randint(50, 200))
        except Exception:
            pass

    async def ensure_logged_in(self, platform: str = "douyin"):
        """Open platform page and wait for user to log in.

        Call this before search_videos if the user hasn't logged in yet.
        Login state persists in the browser profile.
        """
        await self._ensure_browser()

        platform_urls = {
            "douyin": "https://www.douyin.com",
            "xiaohongshu": "https://www.xiaohongshu.com",
            "bilibili": "https://www.bilibili.com",
        }
        url = platform_urls.get(platform)
        if not url:
            print(f"  Unsupported platform: {platform}", file=sys.stderr)
            return False

        page = await self._context.new_page()
        try:
            print(f"  Opening {platform}...", file=sys.stderr)
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)

            # Check if already logged in
            is_logged_in = await self._check_logged_in(page, platform)
            if is_logged_in:
                print(f"  ✓ {platform} already logged in", file=sys.stderr)
                return True

            # Not logged in — bring Chrome to foreground and wait
            try:
                subprocess.run(
                    ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                    timeout=3, capture_output=True,
                )
            except Exception:
                pass

            print(f"\n  Please log in to {platform} in the browser", file=sys.stderr)
            print(f"  QR code login or phone verification supported", file=sys.stderr)
            print(f"  Login state is saved automatically; no need to log in again next time", file=sys.stderr)
            print(f"  ⏳ Waiting for login... (up to 10 minutes)\n", file=sys.stderr)

            login_wait = 600
            interval = 3
            for i in range(login_wait // interval):
                await page.wait_for_timeout(interval * 1000)

                elapsed = (i + 1) * interval
                if elapsed % 30 == 0:
                    remaining = login_wait - elapsed
                    print(f"    ⏳ Still waiting for login... ({remaining // 60}m {remaining % 60}s remaining)", file=sys.stderr)

                if await self._check_logged_in(page, platform):
                    print(f"  ✓ {platform} login successful!", file=sys.stderr)
                    return True

            print(f"  ⚠ Login wait timed out", file=sys.stderr)
            return False
        finally:
            await page.close()

    async def _check_logged_in(self, page, platform: str) -> bool:
        """Check if the user is logged in to the platform."""
        return await page.evaluate("""
        (function() {
            var text = document.body ? (document.body.innerText || '') : '';
            // If login prompts are visible, not logged in
            if (text.includes('登录后即可搜索') || text.includes('扫码登录'))
                return false;
            // Check for login button in header (present = not logged in)
            var loginBtns = document.querySelectorAll(
                'button:not([disabled]),[class*="login-btn"],[class*="LoginBtn"]'
            );
            for (var i = 0; i < loginBtns.length; i++) {
                var btnText = (loginBtns[i].innerText || '').trim();
                if (btnText === '登录' || btnText === '登录/注册')
                    return false;
            }
            // Check for avatar (present = logged in)
            var avatars = document.querySelectorAll(
                '[class*="avatar"], [class*="Avatar"], img[src*="avatar"]'
            );
            if (avatars.length > 0) return true;
            // If no clear signal, assume logged in if no login prompt
            return true;
        })()
        """)

    async def search_videos(
        self,
        query: str,
        platform: str = "douyin",
        max_results: int = 20,
        screenshot_dir: Path | None = None,
    ) -> list[dict]:
        """Search for videos using Director's Chrome browser.

        Args:
            query: Search keyword.
            platform: Platform name (douyin, bilibili, xiaohongshu, youtube).
            max_results: Maximum number of results to extract.
            screenshot_dir: If provided, save search result page screenshots here.

        Returns:
            List of video dicts. Each dict has: title, url, likes, platform, etc.
        """
        await self._ensure_browser()

        url_template = PLATFORM_SEARCH_URLS.get(platform)
        if not url_template:
            return [{"error": f"Unsupported platform: {platform}"}]

        url = url_template.format(query=query)
        await _rate_limiter.wait(url)
        page = await self._context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            _rate_limiter.success(url)

            # Handle CAPTCHA / verification / login walls
            await self._handle_verification(page, platform)

            # Wait for content
            await self._wait_for_content(page, platform)

            # Scroll extensively to trigger lazy-loading
            await self._human_scroll(page, rounds=8)

            # Take search results page screenshots if requested
            if screenshot_dir:
                screenshot_dir = Path(screenshot_dir)
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                # Scroll back to top and capture visible area
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(random.randint(400, 800))
                await page.screenshot(
                    path=str(screenshot_dir / "search_top.jpg"),
                    full_page=False, type="jpeg", quality=80,
                )
                # Capture middle section
                await page.evaluate("window.scrollBy(0, 1200)")
                await page.wait_for_timeout(random.randint(400, 800))
                await page.screenshot(
                    path=str(screenshot_dir / "search_mid.jpg"),
                    full_page=False, type="jpeg", quality=80,
                )
                # Capture bottom section
                await page.evaluate("window.scrollBy(0, 1200)")
                await page.wait_for_timeout(random.randint(400, 800))
                await page.screenshot(
                    path=str(screenshot_dir / "search_bot.jpg"),
                    full_page=False, type="jpeg", quality=80,
                )

            await page.evaluate("window.scrollTo(0, 0)")
            await self._human_wait(page, 400, 800)

            # Extract results via platform-specific JavaScript
            results = await self._extract_results(page, platform, max_results)
            return results

        except BrowserConnectionError:
            raise
        except Exception as e:
            return [{"error": f"Search failed: {str(e)}"}]
        finally:
            await page.close()

    async def _handle_verification(self, page, platform: str):
        """Handle CAPTCHA or login walls — wait for user to act in browser."""
        await self._human_wait(page, 1500, 3500)  # Let page settle

        # Step 1: Check for CAPTCHA by page title
        title = await page.title()
        if "验证" in title or "verify" in title.lower():
            print("  ⚠ Please complete the CAPTCHA in the browser...", file=sys.stderr)
            # Bring Chrome to foreground
            try:
                subprocess.run(
                    ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                    timeout=3, capture_output=True,
                )
            except Exception:
                pass
            for _ in range(150):  # Up to 5 minutes
                await page.wait_for_timeout(2000)
                new_title = await page.title()
                if "验证" not in new_title and "verify" not in new_title.lower():
                    print("  ✓ Verification passed", file=sys.stderr)
                    await page.wait_for_timeout(2000)
                    break
            else:
                print("  ⚠ Verification timed out", file=sys.stderr)

        # Step 2: Check for login walls by detecting visible text
        has_login_wall = await page.evaluate("""
        (function() {
            var text = document.body ? (document.body.innerText || '') : '';
            // Douyin shows "登录后即可搜索更多精彩视频" with QR code
            if (text.includes('登录后即可搜索') || text.includes('扫码登录'))
                return 'douyin_login';
            // Generic login modal detection
            var modals = document.querySelectorAll(
                '[class*="login-guide"], [class*="login-modal"], ' +
                '[class*="LoginModal"], #login-panel'
            );
            for (var i = 0; i < modals.length; i++) {
                if (modals[i].offsetWidth > 0 && modals[i].offsetHeight > 0)
                    return 'modal';
            }
            return '';
        })()
        """)

        if has_login_wall:
            # Bring Chrome to foreground so user can interact
            try:
                subprocess.run(
                    ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                    timeout=3, capture_output=True,
                )
            except Exception:
                pass

            print(f"\n  ⚠ Login required for {platform}. Please log in via the browser window", file=sys.stderr)
            print(f"    QR code login or phone verification supported", file=sys.stderr)
            print(f"    Login state is saved automatically; no need to log in again next time", file=sys.stderr)
            print(f"    ⏳ Waiting for login... (up to 10 minutes)\n", file=sys.stderr)

            # Wait for login to complete (up to 10 minutes)
            login_wait_seconds = 600
            check_interval = 3  # Check every 3 seconds
            checks = login_wait_seconds // check_interval
            for i in range(checks):
                await page.wait_for_timeout(check_interval * 1000)

                # Print periodic reminder every 30 seconds
                elapsed = (i + 1) * check_interval
                if elapsed % 30 == 0:
                    remaining = login_wait_seconds - elapsed
                    print(f"    ⏳ Still waiting for login... ({remaining // 60}m {remaining % 60}s remaining)", file=sys.stderr)

                still_login = await page.evaluate("""
                (function() {
                    var text = document.body ? (document.body.innerText || '') : '';
                    if (text.includes('登录后即可搜索') || text.includes('扫码登录'))
                        return true;
                    var modals = document.querySelectorAll(
                        '[class*="login-guide"], [class*="login-modal"], ' +
                        '[class*="LoginModal"], #login-panel'
                    );
                    for (var i = 0; i < modals.length; i++) {
                        if (modals[i].offsetWidth > 0 && modals[i].offsetHeight > 0)
                            return true;
                    }
                    return false;
                })()
                """)
                if not still_login:
                    print("  ✓ Login successful", file=sys.stderr)
                    # Reload search page after login
                    await page.reload(wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(3000)
                    return

            print("  ⚠ Login wait timed out (10 minutes). Continuing search attempt...", file=sys.stderr)

    async def _wait_for_content(self, page, platform: str):
        """Wait for platform-specific content to load."""
        selectors = {
            # Douyin: video thumbnail containers or waterfall container
            "douyin": '[class*="videoImage"], #waterFallScrollContainer, img[src*="douyinpic"]',
            "bilibili": ".video-list-item, .bili-video-card",
            "xiaohongshu": 'section.note-item, a[href*="/explore/"]',
            "youtube": "ytd-video-renderer, a#video-title",
        }
        sel = selectors.get(platform)
        if sel:
            try:
                await page.wait_for_selector(sel, timeout=15000)
                # Extra wait for dynamic content to fully render
                await self._human_wait(page, 1500, 3000)
            except Exception:
                await self._human_wait(page, 3000, 6000)
        else:
            await self._human_wait(page, 2000, 4000)

    async def _extract_results(self, page, platform: str, max_results: int) -> list[dict]:
        """Run platform-specific extraction JavaScript."""
        js_template = EXTRACT_JS.get(platform, EXTRACT_JS["_generic"])
        js_code = (
            js_template
            .replace("__MAX__", str(max_results))
            .replace("__PLATFORM__", platform)
        )

        try:
            result_str = await page.evaluate(js_code)
            if result_str:
                return json.loads(result_str)
        except Exception:
            pass
        return []

    async def screenshot(self, url: str, save_path: Path) -> Path:
        """Take a screenshot of a URL."""
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(save_path), full_page=False)
            return save_path
        finally:
            await page.close()

    # ── Web research methods ──────────────────────────────────────────

    async def search_web(
        self,
        query: str,
        engine: str = "baidu",
        max_results: int = 10,
    ) -> list[dict]:
        """Search the web using a search engine.

        Args:
            query: Search keywords.
            engine: Search engine (baidu, google, zhihu, baike).
            max_results: Maximum results to return.

        Returns:
            List of dicts: [{title, url, snippet}]
        """
        await self._ensure_browser()

        url_template = WEB_SEARCH_URLS.get(engine)
        if not url_template:
            return [{"error": f"Unsupported search engine: {engine}"}]

        url = url_template.format(query=query)
        await _rate_limiter.wait(url)
        page = await self._context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            _rate_limiter.success(url)
            await self._handle_verification(page, engine)

            # Wait for content to load
            wait_selectors = {
                "baidu": ".result, .c-container",
                "google": "div.g, #search",
                "zhihu": ".SearchResult-Card, .Card",
                "baike": ".searchResult, .search-list, .lemma-summary",
            }
            sel = wait_selectors.get(engine)
            if sel:
                try:
                    await page.wait_for_selector(sel, timeout=10000)
                except Exception:
                    pass
            await self._human_wait(page, 1500, 3000)

            # Scroll to load more results
            await self._human_scroll(page, rounds=random.randint(2, 4))
            await page.evaluate("window.scrollTo(0, 0)")
            await self._human_wait(page, 400, 800)

            # Extract results
            js_template = WEB_EXTRACT_JS.get(engine, WEB_EXTRACT_JS.get("baidu", ""))
            if not js_template:
                return [{"error": f"No extraction JS for engine: {engine}"}]

            js_code = js_template.replace("__MAX__", str(max_results))
            result_str = await page.evaluate(js_code)
            if result_str:
                return json.loads(result_str)
            return []
        except Exception as e:
            return [{"error": f"Web search failed: {str(e)}"}]
        finally:
            await page.close()

    async def search_images(
        self,
        query: str,
        engine: str = "baidu_image",
        max_results: int = 20,
    ) -> list[dict]:
        """Search for images.

        Args:
            query: Search keywords.
            engine: Image search engine (baidu_image, google_image).
            max_results: Maximum results to return.

        Returns:
            List of dicts: [{title, url, image_url, thumbnail_url}]
        """
        await self._ensure_browser()

        url_template = WEB_SEARCH_URLS.get(engine)
        if not url_template:
            return [{"error": f"Unsupported image search engine: {engine}"}]

        url = url_template.format(query=query)
        await _rate_limiter.wait(url)
        page = await self._context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            _rate_limiter.success(url)
            await self._human_wait(page, 2000, 4000)

            # Scroll extensively to trigger lazy-loading
            await self._human_scroll(page, rounds=5)
            await page.evaluate("window.scrollTo(0, 0)")
            await self._human_wait(page, 400, 800)

            js_template = WEB_EXTRACT_JS.get(engine, "")
            if not js_template:
                return [{"error": f"No extraction JS for engine: {engine}"}]

            js_code = js_template.replace("__MAX__", str(max_results))
            result_str = await page.evaluate(js_code)
            if result_str:
                return json.loads(result_str)
            return []
        except Exception as e:
            return [{"error": f"Image search failed: {str(e)}"}]
        finally:
            await page.close()

    async def browse_url(self, url: str) -> dict:
        """Browse a URL and extract its main text content.

        Args:
            url: URL to visit.

        Returns:
            Dict with: {title, url, text_content}
        """
        await self._ensure_browser()
        await _rate_limiter.wait(url)
        page = await self._context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            _rate_limiter.success(url)
            await self._handle_verification(page, "")
            await self._human_wait(page, 2000, 4000)
            await self._human_mouse(page)

            title = await page.title()

            # Extract main text content
            text_content = await page.evaluate(EXTRACT_TEXT_JS)

            return {
                "title": title,
                "url": url,
                "text_content": text_content or "(No text content extracted)",
            }
        except Exception as e:
            return {
                "title": "",
                "url": url,
                "text_content": f"(Failed to load page: {str(e)})",
            }
        finally:
            await page.close()

    async def download_image(self, url: str, save_path: Path) -> Path:
        """Download an image from a URL.

        Args:
            url: Image URL.
            save_path: Full path to save the image.

        Returns:
            Path to saved image.
        """
        import httpx

        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            verify=False,
            headers={
                "User-Agent": random_ua(),
                "Referer": url,
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            save_path.write_bytes(resp.content)
            return save_path

    async def close(self):
        """Disconnect Playwright (Chrome stays running for next time)."""
        self._context = None
        self._browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        # Note: we do NOT kill Chrome — it stays running for fast reconnection
