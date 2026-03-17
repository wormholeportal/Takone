"""Video Researcher — Viral Video Research + VLM Analysis + Report Generation

Connects to Chrome browser to search trending videos, uses VLM to analyze
visual styles, then generates a structured research report with creative insights.

Flow:
  1. Scraping — Search platform for 20+ videos
  2. Screenshots — Take screenshots of search results page
  3. VLM Analysis — Analyze screenshots with vision model
  4. LLM Report — Generate structured research report
  5. Output — Print report + save to project directory
"""

import asyncio
import tempfile
import re
from pathlib import Path
from datetime import datetime

from .config import Colors, DirectorConfig, load_config


# ── Likes parsing helper ──────────────────────────────────────────────

def _parse_likes(likes_str: str) -> float:
    """Parse likes string like '226.2万' (10k unit) or '8003' into a numeric value for sorting."""
    if not likes_str:
        return 0
    s = likes_str.strip()
    try:
        if s.endswith("亿"):
            return float(s[:-1]) * 100_000_000
        elif s.endswith("万"):
            return float(s[:-1]) * 10_000
        else:
            return float(re.sub(r'[^\d.]', '', s) or 0)
    except (ValueError, TypeError):
        return 0


# ── VLM analysis prompt ──────────────────────────────────────────────

VLM_ANALYZE_PROMPT = """\
You are a short-video content planning expert. Carefully observe this platform search results page screenshot and analyze the following:

1. **Cover Visual Style**: Mainstream cover composition methods, color tone tendencies, use of text overlays, people vs. scene ratio
2. **Thumbnail Commonalities**: What common features do high-liked video covers share? (e.g., large title text, emotional expressions, contrasting colors, etc.)
3. **Content Type Distribution**: What types are present (drama, tutorial, vlog, special effects showcase, comedy, etc.), and which is most common?
4. **Attraction Elements**: Which visual elements are most likely to attract user clicks?

Please answer concisely, 2-3 sentences per point."""

# ── LLM report generation prompt ─────────────────────────────────────

REPORT_PROMPT_TEMPLATE = """\
You are a senior short-video content planning expert. Based on the following search result data and visual analysis, generate a detailed viral video research report.

## Search Keywords: {query}
## Platform: {platform}
## Scraping Time: {timestamp}

## Scraped Video Data (total {count} entries, sorted by popularity):
{video_data}

## VLM Visual Analysis:
{vlm_analysis}

---

Please generate a research report with the following structure (in Markdown format):

# Viral Video Overview
- List the Top 5 most popular videos (title, likes, author)
- Summarize the overall popularity distribution

# Content Trends
- Analyze topic distribution (which types are most popular)
- Trending hashtags and keywords
- Content duration trends

# Visual Style
- Based on VLM analysis, summarize cover design patterns
- Color tone and composition trends
- Visual commonalities of high-liked videos

# Copywriting Techniques
- Title patterns and conventions (emotional words, suspense, numbers, etc.)
- Differences between high-liked titles vs. low-liked titles
- Reusable title templates

# Creative Suggestions
- Provide 5 specific, actionable creative inspirations
- Each suggestion should include: topic direction + visual style + title approach
- Based on data analysis, predict what type of content might go viral

Please ensure the report is concise and practical, emphasizing actionable creative suggestions."""


class VideoResearcher:
    """Search and analyze trending videos with VLM + LLM."""

    def __init__(self, config: DirectorConfig | None = None):
        self.config = config or load_config()

    def run(
        self,
        query: str,
        platform: str = "douyin",
        project_dir: Path | None = None,
    ) -> str | None:
        """Run full research pipeline. Returns the report text (or None on failure).

        Phases:
          1. Scraping — scrape 20+ videos from platform
          2. Screenshots — screenshot search results page
          3. VLM — analyze screenshots with vision model
          4. LLM — generate structured report
          5. Output — print + save report
        """
        Y = Colors.YELLOW
        C = Colors.CYAN
        G = Colors.GREEN
        D = Colors.DIM
        R = Colors.RED
        B = Colors.BOLD
        E = Colors.ENDC

        print(f"\n{B}{Y}  Takone — Viral Video Research{E}\n")
        print(f"  {C}Search:{E} {query}")
        print(f"  {C}Platform:{E} {platform}\n")

        # ── Phase 1: Scraping ────────────────────────────────────────
        print(f"  {D}[1/4] Scraping video data...{E}", flush=True)

        try:
            from core.browser.playwright import PlaywrightBrowser, BrowserConnectionError
        except ImportError as e:
            print(f"  {R}Playwright not installed: {e}{E}")
            print(f"  {Y}Please run: pip install playwright && playwright install chromium{E}\n")
            return None

        # Use temp dir for screenshots (or project subdir if available)
        if project_dir:
            screenshot_dir = project_dir / "research" / _safe_filename(query)
        else:
            screenshot_dir = Path(tempfile.mkdtemp(prefix="takone_research_"))

        async def _search():
            browser = PlaywrightBrowser()
            try:
                return await browser.search_videos(
                    query, platform,
                    max_results=20,
                    screenshot_dir=screenshot_dir,
                )
            finally:
                await browser.close()

        try:
            results = asyncio.run(_search())
        except BrowserConnectionError as e:
            print(f"  {Y}⚠ Browser connection failed{E}\n")
            for line in str(e).split("\n"):
                print(f"  {D}{line}{E}")
            return None
        except Exception as e:
            print(f"  {R}Scraping failed: {e}{E}\n")
            return None

        # Filter valid results
        valid = [r for r in results if isinstance(r, dict) and "error" not in r]
        if not valid:
            errors = [r.get("error", "") for r in results if isinstance(r, dict) and "error" in r]
            for err in errors:
                print(f"  {R}{err}{E}")
            if not errors:
                print(f"  {Y}No related videos found{E}")
            return None

        # Sort by likes (descending)
        valid.sort(key=lambda r: _parse_likes(r.get("likes", "")), reverse=True)

        print(f"  {G}✓ Scraped {len(valid)} videos{E}")

        # Print top 5 preview
        for i, r in enumerate(valid[:5], 1):
            title = r.get("title", "")[:60]
            likes = r.get("likes", "")
            tag = f" ({likes} likes)" if likes else ""
            print(f"    {D}{i}. {title}{tag}{E}")

        if len(valid) > 5:
            print(f"    {D}... and {len(valid) - 5} more{E}")
        print()

        # ── Phase 2 + 3: VLM Screenshot Analysis ────────────────────
        vlm_analysis = ""
        screenshot_files = sorted(screenshot_dir.glob("search_*.jpg"))

        if screenshot_files:
            print(f"  {D}[2/4] Analyzing visual style with VLM...{E}", flush=True)
            vlm_analysis = self._analyze_screenshots(screenshot_files)
            if vlm_analysis:
                print(f"  {G}✓ VLM visual analysis complete{E}\n")
            else:
                print(f"  {Y}⚠ VLM analysis skipped (no available vision model or API key){E}\n")
        else:
            print(f"  {D}[2/4] Skipped (no screenshots){E}\n")

        # ── Phase 4: LLM Report Generation ──────────────────────────
        print(f"  {D}[3/4] Generating research report...{E}", flush=True)
        report = self._generate_report(query, platform, valid, vlm_analysis)

        if not report:
            print(f"  {Y}⚠ Report generation failed, outputting raw data{E}\n")
            report = self._fallback_report(query, platform, valid, vlm_analysis)

        # ── Phase 5: Output ───────────────────────────────────────────
        print(f"  {D}[4/4] Outputting research report{E}\n")
        _print_report(report)

        # Save report
        if project_dir:
            report_path = project_dir / "research" / f"{_safe_filename(query)}.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report, encoding="utf-8")
            print(f"\n  {G}✓ Report saved: {report_path}{E}\n")
        else:
            print(f"\n  {D}Tip: Create a project and use /learn to auto-save reports{E}\n")

        return report

    # ── VLM analysis ──────────────────────────────────────────────────

    def _analyze_screenshots(self, screenshot_files: list[Path]) -> str:
        """Use VLM to analyze search result page screenshots."""
        try:
            from core.vision.factory import create_vision
            vision = create_vision(self.config)
        except (ValueError, RuntimeError, ImportError) as e:
            return ""

        # Analyze the first screenshot (top of search results — most important)
        # If there are multiple, combine analyses
        analyses = []
        for i, ss_path in enumerate(screenshot_files[:3]):
            try:
                prompt = VLM_ANALYZE_PROMPT
                if i > 0:
                    prompt = f"This is a screenshot of page {i+1} of the search results. " + prompt
                result = asyncio.run(vision.analyze_image(ss_path, prompt))
                if result:
                    analyses.append(result)
            except Exception:
                continue

        return "\n\n---\n\n".join(analyses) if analyses else ""

    # ── LLM report generation ─────────────────────────────────────────

    def _generate_report(
        self,
        query: str,
        platform: str,
        videos: list[dict],
        vlm_analysis: str,
    ) -> str | None:
        """Use LLM to generate a structured research report."""
        # Build video data string
        lines = []
        for i, v in enumerate(videos, 1):
            parts = [f"{i}. \"{v.get('title', '')}\""]
            if v.get("likes"):
                parts.append(f"Likes:{v['likes']}")
            if v.get("author"):
                parts.append(f"Author:@{v['author']}")
            if v.get("duration"):
                parts.append(f"Duration:{v['duration']}")
            lines.append("  ".join(parts))

        video_data = "\n".join(lines)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        prompt = REPORT_PROMPT_TEMPLATE.format(
            query=query,
            platform=platform,
            timestamp=timestamp,
            count=len(videos),
            video_data=video_data,
            vlm_analysis=vlm_analysis or "(No visual analysis data available)",
        )

        # Try to use the configured LLM
        try:
            return self._call_llm(prompt)
        except Exception:
            return None

    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM to generate text."""
        cfg = self.config.llm

        # Determine which LLM to use (prefer the one that's configured)
        # Priority: ark (doubao) → minimax → openai → claude
        if cfg.ark_api_key:
            return self._call_openai_compat(
                api_key=cfg.ark_api_key,
                base_url=cfg.ark_base_url,
                model=cfg.ark_model,
                prompt=prompt,
            )
        elif cfg.minimax_api_key:
            return self._call_openai_compat(
                api_key=cfg.minimax_api_key,
                base_url="https://api.minimax.chat/v1",
                model=cfg.minimax_model,
                prompt=prompt,
            )
        elif cfg.openai_api_key:
            return self._call_openai_compat(
                api_key=cfg.openai_api_key,
                base_url="https://api.openai.com/v1",
                model=cfg.openai_model,
                prompt=prompt,
            )
        elif cfg.claude_api_key:
            return self._call_anthropic(
                api_key=cfg.claude_api_key,
                model=cfg.claude_model,
                prompt=prompt,
            )
        else:
            raise RuntimeError("No LLM API key configured")

    @staticmethod
    def _call_openai_compat(api_key: str, base_url: str, model: str, prompt: str) -> str:
        """Call an OpenAI-compatible API."""
        import httpx
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(proxy=None, trust_env=False),
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": "You are a senior short-video content planning expert skilled at analyzing viral video patterns and providing creative suggestions."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

    @staticmethod
    def _call_anthropic(api_key: str, model: str, prompt: str) -> str:
        """Call Anthropic Claude API."""
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system="You are a senior short-video content planning expert skilled at analyzing viral video patterns and providing creative suggestions.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    # ── Fallback report (no LLM) ──────────────────────────────────────

    @staticmethod
    def _fallback_report(
        query: str,
        platform: str,
        videos: list[dict],
        vlm_analysis: str,
    ) -> str:
        """Generate a basic report without LLM (just structured data)."""
        lines = [
            f"# Viral Video Research Report: {query}",
            f"Platform: {platform}  |  Scraping Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Total scraped: {len(videos)} videos\n",
            "## Sorted by Popularity\n",
        ]
        for i, v in enumerate(videos, 1):
            title = v.get("title", "")
            likes = v.get("likes", "N/A")
            author = v.get("author", "")
            line = f"{i}. **{title}**  (Likes: {likes})"
            if author:
                line += f"  @{author}"
            lines.append(line)

        if vlm_analysis:
            lines.append("\n## VLM Visual Analysis\n")
            lines.append(vlm_analysis)

        lines.append("\n---\n*Report generated by Takone (LLM analysis unavailable, showing raw data only)*")
        return "\n".join(lines)


# ── Display helpers ───────────────────────────────────────────────────

def _safe_filename(s: str) -> str:
    """Convert string to safe filename."""
    return re.sub(r'[/\\:*?"<>|\s]+', '_', s).strip('_')[:50]


def _print_report(report: str):
    """Pretty-print a markdown report to the terminal."""
    B = Colors.BOLD
    C = Colors.CYAN
    Y = Colors.YELLOW
    G = Colors.GREEN
    D = Colors.DIM
    E = Colors.ENDC

    for line in report.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            print(f"\n  {B}{Y}{stripped[2:]}{E}")
            print(f"  {D}{'─' * 50}{E}")
        elif stripped.startswith("## "):
            print(f"\n  {B}{C}{stripped[3:]}{E}")
        elif stripped.startswith("### "):
            print(f"  {B}{stripped[4:]}{E}")
        elif stripped.startswith("- "):
            print(f"    {G}•{E} {stripped[2:]}")
        elif re.match(r'^\d+\.', stripped):
            print(f"    {stripped}")
        elif stripped.startswith("**") and stripped.endswith("**"):
            print(f"  {B}{stripped[2:-2]}{E}")
        elif stripped == "---":
            print(f"  {D}{'─' * 50}{E}")
        elif stripped:
            print(f"  {stripped}")
        else:
            print()
