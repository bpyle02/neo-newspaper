import datetime
import requests
import sys
import re
import os
import random
import feedparser
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import datetime
from dateutil import parser as dateutil_parser  # pip install python-dateutil

# -------------------------------------------------------------
# RSS Feeds for each section (adjust URLs as needed)
# -------------------------------------------------------------
RSS_FEEDS = {
    "US": [
        "https://moxie.foxnews.com/google-publisher/politics.xml",
        "https://www.nationalreview.com/feed",
        "https://www.washingtontimes.com/rss/headlines/news/politics/",
        "https://www.theblaze.com/feeds/feed.rss",
        "https://townhall.com/feed",
        "https://thefederalist.com/feed/",
        "https://feeds.washingtonpost.com/rss/politics",
        "https://rsshub.netlify.app/apnews/rss",
        "https://www.dailywire.com/feeds/rss.xml",
        "https://nypost.com/feed/",
    ],
    "World": [
        "https://moxie.foxnews.com/google-publisher/world.xml",
        "https://feeds.washingtonpost.com/rss/world",
        "https://rsshub.netlify.app/apnews/rss",
    ],
    "Sports": [
        "https://moxie.foxnews.com/google-publisher/sports.xml",
        "https://nypost.com/sports/feed/",
    ],
    "Entertainment": [
        "https://moxie.foxnews.com/google-publisher/entertainment.xml",
        "https://nypost.com/entertainment/feed/",
    ],
    "Science & Tech": [
        "https://moxie.foxnews.com/google-publisher/tech.xml",
        "https://feeds.washingtonpost.com/rss/business/technology",
    ],
}

FULL_WIDTH_SECTIONS = {"US", "Science & Tech"}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

def get_source_name(url):
    if "foxnews" in url:
        return "Fox News"
    elif "washingtonpost" in url:
        return "Washington Post"
    elif "apnews" in url:
        return "AP News"
    elif "dailywire" in url:
        return "Daily Wire"
    elif "nypost" in url:
        return "New York Post"
    elif "nationalreview" in url:
        return "National Review"
    elif "washingtontimes" in url:
        return "Washington Times"
    elif "theblaze" in url:
        return "The Blaze"
    elif "townhall" in url:
        return "Townhall"
    elif "thefederalist" in url:
        return "The Federalist"
    else:
        return url.split('.')[0].capitalize() if url else "Unknown Source"

def trim_to_sentence(text):
    match = re.search(r'[.!?]["\')]?\s*$', text)
    if match:
        return text[:match.end()].strip()
    last = max(text.rfind('.'), text.rfind('!'), text.rfind('?'))
    if last != -1:
        return text[:last + 1].strip()
    return text.strip()


def scrape_article_text(url, description, max_chars=1800):
    if url:
        try:
            headers = {'User-Agent': USER_AGENT}
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                paragraphs = soup.find_all('p')
                long_text = ""
                for p in paragraphs:
                    text = p.get_text().strip()
                    if len(text.split()) > 15:
                        long_text += text + " "
                    if len(long_text) >= max_chars:
                        break

                if get_source_name(url) == "Fox News":
                    print("Fox News article detected, applying special cleaning.")
                if "data provided by LSEG." in long_text:
                    long_text = long_text.split("data provided by LSEG.")[1]
                    print("Success")
                else:
                    print("Data could not be cleaned")

                if len(long_text) > 200:
                    return trim_to_sentence(long_text)
        except Exception:
            pass
    clean = BeautifulSoup(description, "html.parser").get_text() if description else ""

    return trim_to_sentence(clean) if clean else "Wire report details currently unavailable."


def extract_image(entry):
    if "media_content" in entry:
        for media in entry.media_content:
            if media.get("type", "").startswith("image/"):
                return media.get("url")
    if "enclosures" in entry:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("href")
    summary = entry.get("summary", "") or entry.get("description", "")
    if summary:
        soup = BeautifulSoup(summary, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    return None


def get_domain(url):
    """Extract domain from a URL, e.g., 'https://www.foxnews.com/...' -> 'foxnews.com'"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except:
        return url

def parse_to_utc_aware(date_str):
    """Try hard to return a timezone‑aware datetime, or None on failure."""
    if not date_str:
        return None
    # 1) Standard RFC 2822 with explicit offset
    try:
        return datetime.datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        pass
    # 2) With timezone abbreviation (naive!) – use dateutil for proper tz handling
    try:
        # dateutil.parser is very flexible and will produce an aware datetime
        # if the string contains a timezone abbreviation or offset.
        dt = dateutil_parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)  # assume UTC if none given
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    # 3) Last resort: strip timezone info and assume UTC
    try:
        dt = datetime.datetime.strptime(date_str[:25], "%a, %d %b %Y %H:%M:%S")
        return dt.replace(tzinfo=datetime.datetime.timezone.utc)
    except Exception:
        return None

def fetch_section_news(feed_urls, seen_urls):
    articles = []
    for url in feed_urls:
        try:
            feed = feedparser.parse(url, agent=USER_AGENT)
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                if not title or not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                raw_desc = entry.get("summary", "") or entry.get("description", "")
                clean_desc = BeautifulSoup(raw_desc, "html.parser").get_text().strip()

                image_url = extract_image(entry)
                source_name = get_source_name(link)
                domain = get_domain(link)

                date_str = entry.get("published", "")
                dt_obj = parse_to_utc_aware(date_str)
                if dt_obj is None:
                    print(f"  Skipping article due to unparseable date: {title} ({date_str})")
                    continue

                now_utc = datetime.datetime.now(datetime.timezone.utc)

                if now_utc - dt_obj > datetime.timedelta(hours=24):
                    continue

                articles.append({
                    "title": title,
                    "url": link,
                    "published": date_str,
                    "summary": clean_desc,
                    "image_url": image_url,
                    "source": source_name,
                    "domain": domain,
                })
        except Exception as e:
            print(f"  Error parsing RSS feed {url}: {e}")
    return articles


def select_diverse_articles(articles, count=4):
    """
    Groups articles by domain, then picks one from each domain (round‑robin)
    until we have 'count' articles, ensuring source diversity.
    Returns a list of selected articles (max length = min(count, total_articles)).
    """
    if not articles:
        return []

    # Group by domain
    domain_map = {}
    for art in articles:
        domain = art.get("domain", "unknown")
        domain_map.setdefault(domain, []).append(art)

    # Shuffle the domain order to avoid always starting with the same source
    domains = list(domain_map.keys())
    random.shuffle(domains)

    selected = []
    indices = {d: 0 for d in domains}

    # Round‑robin selection
    while len(selected) < count:
        added = False
        for d in domains:
            lst = domain_map[d]
            if indices[d] < len(lst):
                selected.append(lst[indices[d]])
                indices[d] += 1
                added = True
                if len(selected) >= count:
                    break
        if not added:  # no more articles left in any domain
            break

    return selected


def generate_newspaper_html():
    print("Fetching news from RSS feeds…")
    today_str = datetime.date.today().strftime("%A, %B %d, %Y").upper()
    sections_html = ""
    seen_urls = set()

    for section_name, feed_urls in RSS_FEEDS.items():
        print(f" - Processing {section_name} desk…")
        all_articles = fetch_section_news(feed_urls, seen_urls)

        if len(all_articles) < 2:
            print(f"   (Not enough articles for {section_name}, skipping)")
            continue

        # Get a diverse set of up to 4 articles (1 lead + up to 3 secondaries)
        diverse = select_diverse_articles(all_articles, count=4)
        if len(diverse) < 2:
            print(f"   (Not enough diverse sources for {section_name}, skipping)")
            continue

        # Pick the lead article, preferring one with an image
        lead_article = None
        for i, art in enumerate(diverse):
            if art.get("image_url"):
                lead_article = diverse.pop(i)
                break
        if not lead_article:
            lead_article = diverse.pop(0)

        secondary_articles = diverse[:3]  # up to 3

        max_chars = 2400 if section_name in FULL_WIDTH_SECTIONS else 1400
        lead_article["long_summary"] = scrape_article_text(
            lead_article["url"], lead_article["summary"], max_chars=max_chars
        )

        for art in secondary_articles:
            art["long_summary"] = scrape_article_text(
                art["url"], art["summary"], max_chars=600
            )

        # Build HTML (identical to previous version)
        secondary_html = ""
        for art in secondary_articles:
            secondary_html += f"""
            <div class="story-minor">
                <h4>{art['title']}</h4>
                <p>{art['long_summary']}</p>
                <p class="source-credit">— {art['source']}</p>
            </div>"""

        image_html = ""
        if lead_article.get("image_url"):
            image_html = (
                f'<img src="{lead_article["image_url"]}" '
                f'alt="Lead Story Image" class="news-photo">'
            )

        lead_text = lead_article["long_summary"].strip()
        first_letter = lead_text[0] if lead_text else ""
        rest_of_text = lead_text[1:] if lead_text else ""

        safe_class = section_name.replace(" ", "").replace("&", "").replace("/", "")
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

    # ── Full HTML (unchanged styling) ──
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

        @page {{
            margin: 0;
        }}

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

        .front-page-columns {{
            column-count: 3;
            column-gap: 0;
            column-rule: 1px solid var(--ink);
        }}
        
        @media (max-width: 600px)  {{ .front-page-columns {{ column-count: 1; }} }}
        @media (max-width: 900px)  {{ .front-page-columns {{ column-count: 2; }} }}

        .news-section {{
            break-inside: avoid-column;
            border-top: 2px solid var(--ink);
            padding: 10px 14px 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

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