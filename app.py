import datetime
import requests
import sys
import re
from bs4 import BeautifulSoup
import os

# -------------------------------------------------------------
# API Key (Consider rotating this key if it gets overused!)
# -------------------------------------------------------------
API_KEY = os.environ.get("API_KEY", "")

SECTIONS = {
    "US": {"country": "us"},
    "World": {"sources": "bbc-news,al-jazeera-english,reuters"},
    "Sports": {"country": "us", "category": "sports"},
    "Entertainment": {"country": "us", "category": "entertainment"},
    "Science & Tech": {"country": "us", "category": "technology"}
}

# Sections that span full width with a 2-column internal layout (lead + sidebar)
FULL_WIDTH_SECTIONS = {"US", "Science & Tech"}


def trim_to_sentence(text):
    """
    Trims text so it always ends on a sentence-closing punctuation mark
    (. ! ? or a closing quote/paren after one).
    If no such boundary is found, returns the text as-is.
    """
    # Walk backwards to find the last '.', '!', or '?' (optionally followed
    # by a closing quote or parenthesis, e.g. '."' or '!')
    match = re.search(r'[.!?]["\')]?\s*$', text)
    if match:
        return text[:match.end()].strip()

    # No terminal punctuation found — find the last occurrence anywhere
    last = max(text.rfind('.'), text.rfind('!'), text.rfind('?'))
    if last != -1:
        return text[:last + 1].strip()

    return text.strip()


def scrape_article_text(url, description, content, max_chars=1800):
    """
    Scrapes the article URL for body paragraphs.
    Returns progressively more text the higher max_chars is set,
    falling back gracefully to the NewsAPI description + content fields.
    Always ends on a complete sentence.
    """
    if url:
        try:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            }
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                paragraphs = soup.find_all('p')
                long_text = ""
                for p in paragraphs:
                    text = p.get_text().strip()
                    # Skip navigation snippets, bylines, etc.
                    if len(text.split()) > 15:
                        long_text += text + " "
                    if len(long_text) >= max_chars:
                        break
                if len(long_text) > 200:
                    return trim_to_sentence(long_text)
        except Exception:
            pass

    # Fallback: stitch description + NewsAPI's truncated content
    clean_content = re.sub(r'\[\+\d+\s*chars\]', '', content if content else "").strip()
    fallback = f"{description} {clean_content}".strip()
    return trim_to_sentence(fallback) if fallback else "Wire report details currently unavailable."


def fetch_section_news(section_name, params):
    """Fetches articles from NewsAPI, filtering out 'Live Updates' titles."""
    url = "https://newsapi.org/v2/top-headlines"
    req_params = {**params, "apiKey": API_KEY}

    try:
        response = requests.get(url, params=req_params, timeout=10)
        data = response.json()
        if data.get("status") == "error":
            print(f"  NewsAPI error [{section_name}]: {data.get('message')}")
            return []
    except requests.RequestException as e:
        print(f"  Network error [{section_name}]: {e}")
        return []

    articles = []
    for item in data.get("articles", []):
        title       = (item.get("title") or "").strip()
        description = (item.get("description") or "").strip()
        content     = item.get("content")
        art_url     = item.get("url")
        image_url   = item.get("urlToImage")
        source_name = item.get("source", {}).get("name", "Wire Report")

        # ── FIX 1: Skip "Live Updates" articles ──
        if "live update" in title.lower():
            continue

        if "jazeera" in source_name.lower():
            continue

        if not (title and description):
            continue

        # Strip trailing " - Source Name" appended by NewsAPI
        if title.endswith(f" - {source_name}"):
            title = title[:-(len(source_name) + 3)]

        articles.append({
            "title":     title,
            "summary":   description,
            "content":   content,
            "url":       art_url,
            "image_url": image_url,
            "source":    source_name,
        })

    return articles


def generate_newspaper_html():
    if API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Insert your NewsAPI key into the script.")
        sys.exit(1)

    print("Fetching wire reports from NewsAPI…")
    today_str    = datetime.date.today().strftime("%A, %B %d, %Y").upper()
    sections_html = ""

    for section_name, params in SECTIONS.items():
        print(f" - Processing {section_name} desk…")
        articles = fetch_section_news(section_name, params)

        if not articles:
            print(f"   (No articles found for {section_name})")
            continue

        # ── Pick lead article (prefer one with a photo) ──
        lead_article = None
        for i, art in enumerate(articles):
            if art.get("image_url"):
                lead_article = articles.pop(i)
                break
        if not lead_article:
            lead_article = articles.pop(0)

        # ── FIX 2: Scrape more body text to fill whitespace ──
        # Full-width sections get even more text (they have room for it)
        max_chars = 2400 if section_name in FULL_WIDTH_SECTIONS else 1400
        lead_article["long_summary"] = scrape_article_text(
            lead_article.get("url"),
            lead_article.get("summary"),
            lead_article.get("content"),
            max_chars=max_chars,
        )

        # Secondary articles also get scraped body text (more than before)
        secondary_articles = articles[:3]
        for art in secondary_articles:
            art["long_summary"] = scrape_article_text(
                art.get("url"),
                art.get("summary"),
                art.get("content"),
                max_chars=600,   # enough to fill gaps without overwhelming
            )

        # ── Build secondary story HTML ──
        secondary_html = ""
        for art in secondary_articles:
            secondary_html += f"""
            <div class="story-minor">
                <h4>{art['title']}</h4>
                <p>{art['long_summary']}</p>
                <p class="source-credit">— {art['source']}</p>
            </div>"""

        # ── Build image HTML ──
        image_html = ""
        if lead_article.get("image_url"):
            image_html = (
                f'<img src="{lead_article["image_url"]}" '
                f'alt="Lead Story Image" class="news-photo">'
            )

        # Drop-cap setup
        lead_text    = lead_article["long_summary"].strip()
        first_letter = lead_text[0] if lead_text else ""
        rest_of_text = lead_text[1:] if lead_text else ""

        safe_class = section_name.replace(" ", "").replace("&", "").replace("/", "")

        # ── FIX 3: Science & Tech gets same full-width layout as US ──
        is_full_width = section_name in FULL_WIDTH_SECTIONS

        if is_full_width:
            sections_html += f"""
        <section class="news-section section-{safe_class} section-fullwidth">
            <div class="section-banner">{section_name}</div>
            <article class="story-lead">
                {image_html}
                <h3>{lead_article['title']}</h3>
                <p class="lead-summary"><strong class="drop-cap">{first_letter}</strong>{rest_of_text}</p>
                <p class="source-credit">— {lead_article['source']}</p>
            </article>
            <div class="minor-stories-container">{secondary_html}</div>
        </section>"""
        else:
            sections_html += f"""
        <section class="news-section section-{safe_class}">
            <div class="section-banner">{section_name}</div>
            <article class="story-lead">
                {image_html}
                <h3>{lead_article['title']}</h3>
                <p class="lead-summary"><strong class="drop-cap">{first_letter}</strong>{rest_of_text}</p>
                <p class="source-credit">— {lead_article['source']}</p>
            </article>
            {f'<div class="minor-stories-container">{secondary_html}</div>' if secondary_html else ''}
        </section>"""

    # ── Full HTML document ──
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Neo News</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,400&family=UnifrakturMaguntia&family=PT+Serif:ital,wght@0,400;0,700;1,400&display=swap');

        :root {{
            --ink: #1a1a1a;
            --paper: #f4ebd0;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            background-color: #c8c0a8;
            color: var(--ink);
            font-family: 'PT Serif', Georgia, serif;
            padding: 16px;
            display: flex;
            justify-content: center;
        }}

        .newspaper-container {{
            width: 100%;
            max-width: 1200px;
            background: var(--paper);
            padding: 20px 28px 28px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.35);
        }}

        /* ── HEADER ── */
        header {{
            text-align: center;
            border-bottom: 5px double var(--ink);
            margin-bottom: 14px;
            padding-bottom: 8px;
        }}
        .masthead {{
            font-family: 'UnifrakturMaguntia', cursive, serif;
            font-size: clamp(2.8rem, 7vw, 4.8rem);
            line-height: 1;
        }}
        .tagline {{
            font-family: 'PT Serif', serif;
            font-style: italic;
            font-size: 0.82rem;
            margin: 6px 0 4px;
        }}
        .meta-bar {{
            border-top: 2px solid var(--ink);
            border-bottom: 1px solid var(--ink);
            padding: 3px 8px;
            display: flex;
            justify-content: space-between;
            font-size: 0.72rem;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        /* ── CSS COLUMN FLOW ── */
        .front-page-columns {{
            column-count: 1;
            column-gap: 0;
            column-rule: 1px solid var(--ink);
        }}
        @media (min-width: 600px)  {{ .front-page-columns {{ column-count: 2; }} }}
        @media (min-width: 900px)  {{ .front-page-columns {{ column-count: 3; }} }}

        /* ── STANDARD SECTION ── */
        .news-section {{
            break-inside: avoid-column;
            border-top: 2px solid var(--ink);
            padding: 10px 14px 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        /* ── FULL-WIDTH SECTIONS (US + Science & Tech) ── */
        .section-fullwidth {{
            column-span: all;
            border-top: 3px solid var(--ink);
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
            padding: 10px 0 16px;
        }}
        @media (min-width: 700px) {{
            .section-fullwidth {{
                grid-template-columns: 1.6fr 1fr;
                align-items: start;
            }}
            .section-fullwidth .section-banner {{
                grid-column: 1 / -1;
            }}
            .section-fullwidth .minor-stories-container {{
                border-top: none;
                border-left: 1px solid var(--ink);
                padding: 0 0 0 14px;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
        }}

        /* ── SECTION BANNER ── */
        .section-banner {{
            text-align: center;
            font-family: 'Playfair Display', serif;
            font-weight: 900;
            font-size: clamp(1.15rem, 2.4vw, 1.85rem);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            border-bottom: 1px solid var(--ink);
            padding-bottom: 4px;
            margin-bottom: 4px;
        }}

        /* ── LEAD STORY ── */
        .story-lead h3 {{
            font-family: 'Playfair Display', serif;
            font-size: clamp(1.15rem, 2.4vw, 1.85rem);
            font-weight: 900;
            line-height: 1.1;
            margin: 6px 0 5px;
        }}
        .lead-summary {{
            font-size: 0.88rem;
            line-height: 1.55;
            text-align: justify;
            hyphens: auto;
        }}
        .drop-cap {{
            font-size: 2.5rem;
            font-family: 'Playfair Display', serif;
            font-weight: 900;
            float: left;
            line-height: 1;
            padding-right: 5px;
            padding-top: 3px;
        }}

        /* ── MINOR STORIES ── */
        .minor-stories-container {{
            border-top: 1px dashed var(--ink);
            padding-top: 8px;
            display: flex;
            flex-direction: column;
            gap: 0;
        }}
        .story-minor {{
            padding: 6px 0;
            border-bottom: 1px dotted #999;
        }}
        .story-minor:last-child {{ border-bottom: none; padding-bottom: 0; }}
        .story-minor h4 {{
            font-family: 'Playfair Display', serif;
            font-size: 1.2rem;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 3px;
        }}
        .story-minor p {{
            font-size: 0.78rem;
            line-height: 1.45;
            text-align: justify;
            hyphens: auto;
        }}

        /* ── CREDITS & PHOTO ── */
        .source-credit {{
            font-size: 0.67rem !important;
            font-style: italic;
            text-align: right !important;
            color: #444;
            margin-top: 4px;
        }}
        .news-photo {{
            width: 100%;
            height: auto;
            max-height: 400px;
            object-fit: cover;
            filter: grayscale(100%) contrast(1.35) brightness(0.9) sepia(25%);
            mix-blend-mode: multiply;
            border: 2px double var(--ink);
            display: block;
        }}

        @media print {{
            body {{ background: var(--paper); padding: 0;
                    -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .newspaper-container {{ box-shadow: none; max-width: 100%; }}
        }}
    </style>
</head>
<body>
<div class="newspaper-container">
    <header>
        <h1 class="masthead">The Neo News</h1>
        <div class="tagline">"Keeping You Informed the Old-Fashioned Way"</div>
        <div class="meta-bar">
            <span>VOL. CXXIV · No. 42,110</span>
            <span>{today_str}</span>
            <span>PRICE 25 CENTS</span>
        </div>
    </header>
    <main class="front-page-columns">
        {sections_html}
    </main>
</div>
</body>
</html>
"""

    out_path = "index.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\nSuccess! '{out_path}' has been generated.")


if __name__ == "__main__":
    generate_newspaper_html()