"""Look for papers under your ORCID iD that are not yet listed in publications.json (or index.html).

Sources: ORCID public API and OpenAlex (both free, no key). Nothing on the website is
changed. If new papers are found, they are written to new-papers.md so the workflow can
open a GitHub issue for you to review.

Ignore list: put a DOI (or a distinctive part of a title) on its own line in
scripts/ignored-papers.txt to stop it from being reported again.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ORCID = "0000-0002-7943-8923"
EMAIL = "v_vipin@cb.amrita.edu"          # used only to identify this script to OpenAlex
PAGES = ["index.html", "publications.json"]      # where your papers are listed
IGNORE_FILE = "scripts/ignored-papers.txt"
OUT = "new-papers.md"
SKIP_TYPES = {"peer-review", "dataset", "erratum", "paratext", "retraction", "editorial", "letter",
              "peer_review", "data_set", "supervised_student_publication", "other"}
UA = f"homepage-paper-checker (mailto:{EMAIL})"
ADD_PAGE = "https://drvipinvenugopal.github.io/add-paper.html"


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def norm_doi(d):
    if not d:
        return ""
    d = d.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d.rstrip("/.")


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def dig(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def parse_orcid(data):
    works = []
    for g in (data or {}).get("group", []) or []:
        summaries = g.get("work-summary") or []
        if not summaries:
            continue
        w = summaries[0]
        title = dig(w, "title", "title", "value") or ""
        doi = ""
        for e in (dig(w, "external-ids", "external-id") or []):
            if (e.get("external-id-type") or "").lower() == "doi":
                doi = norm_doi(e.get("external-id-value"))
                break
        year = dig(w, "publication-date", "year", "value") or ""
        wtype = (w.get("type") or "").lower()
        if wtype in SKIP_TYPES:
            continue
        works.append({"title": title, "doi": doi, "year": str(year),
                      "venue": dig(w, "journal-title", "value") or "", "source": "ORCID"})
    return works


def parse_openalex(data):
    works = []
    for r in (data or {}).get("results", []) or []:
        wtype = (r.get("type") or "").lower()
        if wtype in SKIP_TYPES:
            continue
        works.append({"title": r.get("title") or "", "doi": norm_doi(r.get("doi")),
                      "year": str(r.get("publication_year") or ""),
                      "venue": dig(r, "primary_location", "source", "display_name") or "",
                      "source": "OpenAlex"})
    return works


def fetch_orcid():
    return parse_orcid(get_json(f"https://pub.orcid.org/v3.0/{ORCID}/works"))


def fetch_openalex():
    works, cursor = [], "*"
    for _ in range(5):                                    # up to 500 works
        q = urllib.parse.urlencode({
            "filter": f"author.orcid:https://orcid.org/{ORCID}",
            "per-page": 100, "cursor": cursor, "mailto": EMAIL})
        data = get_json("https://api.openalex.org/works?" + q)
        works += parse_openalex(data)
        cursor = dig(data, "meta", "next_cursor")
        if not cursor:
            break
    return works


def page_index(html):
    dois = {norm_doi(m) for m in re.findall(r"doi\.org/([^\"'\s<>]+)", html, flags=re.I)}
    dois |= {norm_doi(m) for m in re.findall(r'"doi"\s*:\s*"([^"]+)"', html, flags=re.I)}
    text = norm_title(re.sub(r"<[^>]+>", " ", html))
    return dois, text


def load_ignored():
    if not os.path.exists(IGNORE_FILE):
        return set(), []
    dois, frags = set(), []
    for line in open(IGNORE_FILE, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("10.") or "doi.org" in line.lower():
            dois.add(norm_doi(line))
        else:
            frags.append(norm_title(line))
    return dois, frags


def find_new(works, page_dois, page_text, ign_dois, ign_frags):
    merged = {}
    for w in works:
        key = w["doi"] or norm_title(w["title"])
        if not key or not w["title"]:
            continue
        if key in merged:
            merged[key]["source"] += " + " + w["source"] if w["source"] not in merged[key]["source"] else ""
        else:
            merged[key] = dict(w)
    new = []
    for w in merged.values():
        nt = norm_title(w["title"])
        if w["doi"] and (w["doi"] in page_dois or w["doi"] in ign_dois):
            continue
        if nt and nt in page_text:
            continue
        if any(f and f in nt for f in ign_frags):
            continue
        new.append(w)
    new.sort(key=lambda w: w["year"], reverse=True)
    return new


def add_link(w):
    """Link that opens the Add a paper page with this paper already filled in."""
    if w["doi"]:
        q = {"doi": w["doi"]}
    else:
        q = {k: w[k] for k in ("title", "venue", "year") if w.get(k)}
    return ADD_PAGE + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def write_report(new):
    lines = ["These papers appear under your ORCID iD but are not on your homepage yet.", "",
             "Please check each one is really yours. For each paper that is, open its **Add this paper** link, "
             "check the details, add the quartile, impact factor and code link, and copy the entry into "
             "`publications.json`.", "",
             f"You can also open the [Add a paper page]({ADD_PAGE}) and start from a blank form.", ""]
    for w in new:
        link = f"https://doi.org/{w['doi']}" if w["doi"] else ""
        bits = [f"**{w['title']}**"]
        if w["year"]:
            bits.append(f"({w['year']})")
        if w["venue"]:
            bits.append(f"in {w['venue']}")
        line = "- " + " ".join(bits)
        if link:
            line += f" - {link}"
        line += f" _(found in {w['source']})_"
        line += f"\n  - [Add this paper]({add_link(w)})"
        lines.append(line)
    lines += ["", "To stop a paper being reported again (for example, it is not yours), add its DOI or part of "
              "its title on a new line in `scripts/ignored-papers.txt`."]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def set_output(found, count):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"found={'true' if found else 'false'}\ncount={count}\n")


def main():
    works, errors = [], []
    for name, fn in (("ORCID", fetch_orcid), ("OpenAlex", fetch_openalex)):
        try:
            got = fn()
            print(f"{name}: {len(got)} works")
            works += got
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"{name} failed: {e}")
    if len(errors) == 2:
        sys.exit("Both sources failed: " + "; ".join(errors))

    html = "\n".join(open(f, encoding="utf-8").read() for f in PAGES if os.path.exists(f))
    page_dois, page_text = page_index(html)
    ign_dois, ign_frags = load_ignored()
    new = find_new(works, page_dois, page_text, ign_dois, ign_frags)
    print(f"New papers not on the page: {len(new)}")
    if os.path.exists(OUT):
        os.remove(OUT)
    if new:
        write_report(new)
    set_output(bool(new), len(new))


if __name__ == "__main__":
    main()
