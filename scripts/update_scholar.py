"""Read citation counts from a public Google Scholar profile and save them to scholar.json.

If Google blocks the request or the page layout changes, this script exits with an
error and leaves scholar.json untouched, so the website keeps showing the last good numbers.
"""
import datetime
import json
import sys
import urllib.request
from html.parser import HTMLParser

PROFILE_ID = "jcwBpgIAAAAJ"
URL = f"https://scholar.google.com/citations?user={PROFILE_ID}&hl=en"
OUT = "scholar.json"


class StatsParser(HTMLParser):
    """Collects the 'All' column of the Citations / h-index / i10-index table."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_cell = False
        self.cells = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and a.get("id") == "gsc_rsb_st":
            self.in_table = True
        elif self.in_table and tag == "td" and "gsc_rsb_std" in (a.get("class") or ""):
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.in_table = False
        if tag == "td":
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell and data.strip().isdigit():
            self.cells.append(int(data.strip()))


def main():
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; homepage-metrics-updater)",
            "Accept-Language": "en",
        },
    )
    try:
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        sys.exit(f"Could not fetch Google Scholar: {e}")

    parser = StatsParser()
    parser.feed(html)
    # Cells come in order: citations (all, since), h-index (all, since), i10-index (all, since)
    if len(parser.cells) < 6:
        sys.exit("Scholar stats table not found (probably blocked or a CAPTCHA). Keeping old numbers.")

    citations, h_index, i10_index = parser.cells[0], parser.cells[2], parser.cells[4]
    if citations <= 0 or h_index <= 0:
        sys.exit(f"Unexpected values {parser.cells}. Keeping old numbers.")

    data = {
        "citations": citations,
        "h_index": h_index,
        "i10_index": i10_index,
        "updated": datetime.date.today().isoformat(),
        "profile": URL,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print("Saved:", data)


if __name__ == "__main__":
    main()
