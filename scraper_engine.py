import io
import os
import re
import time
import socket
import ipaddress
import hashlib
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, unquote
from urllib import robotparser

import requests
import pandas as pd
from bs4 import BeautifulSoup
import tldextract

SAFE_DEFAULTS = {
    "MAX_PAGES_CAP": 20,
    "MAX_DEPTH_CAP": 2,
    "MAX_DOCUMENTS_CAP": 100,
    "MAX_FILE_MB": 25,
    "REQUEST_TIMEOUT": 20,
    "USER_AGENT": "Web-Scraping-Lab/1.0 (+educational-demo)",
}

ALLOWED_DEMO_DOMAINS = [
    "cbic-gst.gov.in",
    "taxinformation.cbic.gov.in",
    "sebi.gov.in",
    "cercind.gov.in",
    "dea.gov.in",
    "financialservices.gov.in",
]

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv",
    ".ppt", ".pptx", ".zip", ".txt", ".rtf", ".xml"
}

CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "text/plain": ".txt",
    "application/rtf": ".rtf",
    "application/xml": ".xml",
    "text/xml": ".xml",
}

CATEGORY_KEYWORDS = {
    "Circulars": ["circular"],
    "Notifications": ["notification", "gazette"],
    "Forms": ["form"],
    "Orders": ["order"],
    "Rules": ["rule"],
    "Acts": ["act"],
    "Instructions": ["instruction"],
    "Guidelines": ["guideline", "manual", "handbook"],
    "FAQs": ["faq", "frequently asked"],
    "Reports": ["report", "annual report"],
}

def _normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url, _ = urldefrag(url)
    return url

def _registered_domain(url):
    ext = tldextract.extract(url)
    return ".".join(x for x in [ext.domain, ext.suffix] if x).lower()

def _is_public_ip(ip_text):
    try:
        ip = ipaddress.ip_address(ip_text)
        return not (
            ip.is_private or ip.is_loopback or ip.is_link_local or
            ip.is_multicast or ip.is_reserved or ip.is_unspecified
        )
    except ValueError:
        return False

def validate_target_url(url, restrict_to_demo_domains=False):
    url = _normalize_url(url)
    if not url:
        return False, "Please enter a URL."

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "Only http:// and https:// URLs are allowed."

    host = parsed.hostname
    if not host:
        return False, "Invalid hostname."

    if host.lower() in {"localhost", "localhost.localdomain"}:
        return False, "Local/private hosts are not allowed."

    try:
        ips = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return False, "The hostname could not be resolved."

    if not ips or any(not _is_public_ip(ip) for ip in ips):
        return False, "Private, local, link-local or reserved network targets are blocked."

    if restrict_to_demo_domains:
        allowed = any(host == d or host.endswith("." + d) for d in ALLOWED_DEMO_DOMAINS)
        if not allowed:
            return False, "This URL is not in the classroom demo-domain list."

    return True, "OK"

def _same_registered_domain(a, b):
    return _registered_domain(a) == _registered_domain(b)

def _robots_allowed(session, url):
    try:
        p = urlparse(url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        r = session.get(robots_url, timeout=10)
        if r.status_code >= 400:
            return True
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(r.text.splitlines())
        return rp.can_fetch(SAFE_DEFAULTS["USER_AGENT"], url)
    except Exception:
        return True

def _sanitize_filename(name, max_len=150):
    name = unquote(str(name or "")).strip()
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "downloaded_file")[:max_len]

def _classify(text):
    hay = (text or "").lower()
    for category, keys in CATEGORY_KEYWORDS.items():
        if any(k in hay for k in keys):
            return category
    return "Other"

def _looks_like_document(url):
    path = unquote(urlparse(url).path).lower()
    return any(ext in path for ext in DOCUMENT_EXTENSIONS)

def _filename_from_response(response, url, anchor_text=""):
    cd = response.headers.get("Content-Disposition", "")
    m = re.search(r'filename="?([^";]+)"?', cd, flags=re.I)
    if m:
        filename = m.group(1)
    else:
        filename = os.path.basename(unquote(urlparse(response.url or url).path).rstrip("/"))
        filename = filename or anchor_text or "document"
    filename = _sanitize_filename(filename)
    if Path(filename).suffix.lower() not in DOCUMENT_EXTENSIONS:
        ct = (response.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
        ext = CONTENT_TYPE_EXTENSIONS.get(ct, "")
        if ext:
            filename += ext
    return filename

def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def scrape_site(
    start_url,
    max_pages=5,
    max_depth=1,
    max_documents=50,
    delay_seconds=1.0,
    save_html=False,
    save_text=True,
    progress_callback=None,
):
    start_url = _normalize_url(start_url)
    max_pages = min(max(int(max_pages), 1), SAFE_DEFAULTS["MAX_PAGES_CAP"])
    max_depth = min(max(int(max_depth), 0), SAFE_DEFAULTS["MAX_DEPTH_CAP"])
    max_documents = min(max(int(max_documents), 1), SAFE_DEFAULTS["MAX_DOCUMENTS_CAP"])
    delay_seconds = min(max(float(delay_seconds), 1.0), 3.0)

    session = requests.Session()
    session.headers.update({
        "User-Agent": SAFE_DEFAULTS["USER_AGENT"],
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    })

    queue = [(start_url, 0)]
    queued = {start_url}
    visited, doc_urls_seen, file_hashes_seen = set(), set(), set()
    pages, documents, archive_files = [], [], {}

    while queue and len(visited) < max_pages:
        page_url, depth = queue.pop(0)
        if page_url in visited or depth > max_depth:
            continue

        ok, message = validate_target_url(page_url)
        if not ok:
            pages.append({
                "Page_URL": page_url, "Depth": depth, "HTTP_Status": "",
                "Title": "", "Links_Found": 0, "Documents_Found": 0,
                "Status": "Blocked by safety validation", "Error": message
            })
            visited.add(page_url)
            continue

        if not _same_registered_domain(page_url, start_url):
            continue

        if not _robots_allowed(session, page_url):
            pages.append({
                "Page_URL": page_url, "Depth": depth, "HTTP_Status": "",
                "Title": "", "Links_Found": 0, "Documents_Found": 0,
                "Status": "Skipped by robots.txt", "Error": ""
            })
            visited.add(page_url)
            continue

        visited.add(page_url)

        if progress_callback:
            progress_callback(len(visited), max_pages, f"Processing page {len(visited)} of up to {max_pages}")

        try:
            r = session.get(page_url, timeout=SAFE_DEFAULTS["REQUEST_TIMEOUT"], allow_redirects=True)
            status = r.status_code
            ct = (r.headers.get("Content-Type", "") or "").lower()

            if status != 200:
                pages.append({
                    "Page_URL": page_url, "Depth": depth, "HTTP_Status": status,
                    "Title": "", "Links_Found": 0, "Documents_Found": 0,
                    "Status": "HTTP error", "Error": f"HTTP {status}"
                })
                time.sleep(delay_seconds)
                continue

            if "html" not in ct:
                pages.append({
                    "Page_URL": page_url, "Depth": depth, "HTTP_Status": status,
                    "Title": "", "Links_Found": 0, "Documents_Found": 0,
                    "Status": "Not HTML", "Error": ""
                })
                time.sleep(delay_seconds)
                continue

            html = r.text
            soup = BeautifulSoup(html, "lxml")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""

            if save_html:
                archive_files[f"Webpages/HTML/page_{len(visited):03d}.html"] = html.encode("utf-8", "ignore")

            if save_text:
                text = "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())
                archive_files[f"Webpages/Text/page_{len(visited):03d}.txt"] = text.encode("utf-8", "ignore")

            links = []
            for a in soup.find_all("a", href=True):
                absolute = urljoin(r.url, a.get("href"))
                absolute, _ = urldefrag(absolute)
                if absolute.startswith(("http://", "https://")):
                    links.append((absolute, " ".join(a.get_text(" ", strip=True).split())))

            docs_here = 0

            for absolute, link_text in links:
                if len(documents) >= max_documents:
                    break

                if not _same_registered_domain(absolute, start_url):
                    continue

                if _looks_like_document(absolute):
                    if absolute in doc_urls_seen:
                        continue
                    doc_urls_seen.add(absolute)
                    docs_here += 1

                    try:
                        dr = session.get(absolute, timeout=SAFE_DEFAULTS["REQUEST_TIMEOUT"], allow_redirects=True)
                        if dr.status_code != 200:
                            documents.append({
                                "Source_Page": page_url, "Link_Text": link_text,
                                "Document_URL": absolute, "File_Name": "",
                                "Category": _classify(link_text + " " + absolute),
                                "Size": "", "Status": f"HTTP {dr.status_code}"
                            })
                            continue

                        if len(dr.content) > SAFE_DEFAULTS["MAX_FILE_MB"] * 1024 * 1024:
                            documents.append({
                                "Source_Page": page_url, "Link_Text": link_text,
                                "Document_URL": absolute, "File_Name": "",
                                "Category": _classify(link_text + " " + absolute),
                                "Size": len(dr.content), "Status": "Skipped - file too large"
                            })
                            continue

                        digest = _sha256_bytes(dr.content)
                        if digest in file_hashes_seen:
                            documents.append({
                                "Source_Page": page_url, "Link_Text": link_text,
                                "Document_URL": absolute, "File_Name": "",
                                "Category": _classify(link_text + " " + absolute),
                                "Size": len(dr.content), "Status": "Duplicate - not saved"
                            })
                            continue

                        file_hashes_seen.add(digest)
                        filename = _filename_from_response(dr, absolute, link_text)
                        category = _classify(link_text + " " + absolute + " " + filename)
                        arc = f"Documents/{category}/{filename}"

                        if arc in archive_files:
                            stem, suffix, n = Path(filename).stem, Path(filename).suffix, 2
                            while f"Documents/{category}/{stem}_{n}{suffix}" in archive_files:
                                n += 1
                            arc = f"Documents/{category}/{stem}_{n}{suffix}"

                        archive_files[arc] = dr.content
                        documents.append({
                            "Source_Page": page_url, "Link_Text": link_text,
                            "Document_URL": absolute, "File_Name": Path(arc).name,
                            "Category": category, "Size": len(dr.content),
                            "Status": "Downloaded"
                        })

                    except Exception as exc:
                        documents.append({
                            "Source_Page": page_url, "Link_Text": link_text,
                            "Document_URL": absolute, "File_Name": "",
                            "Category": _classify(link_text + " " + absolute),
                            "Size": "", "Status": f"Failed: {exc}"
                        })

                    time.sleep(delay_seconds)
                    continue

                if depth < max_depth and absolute not in queued and absolute not in visited:
                    path = urlparse(absolute).path.lower()
                    if not any(path.endswith(ext) for ext in [
                        ".jpg",".jpeg",".png",".gif",".svg",".webp",".css",".js",
                        ".woff",".woff2",".ico",".mp4",".mp3"
                    ]):
                        queue.append((absolute, depth + 1))
                        queued.add(absolute)

            pages.append({
                "Page_URL": page_url, "Depth": depth, "HTTP_Status": status,
                "Title": title, "Links_Found": len(links),
                "Documents_Found": docs_here, "Status": "Processed", "Error": ""
            })

        except Exception as exc:
            pages.append({
                "Page_URL": page_url, "Depth": depth, "HTTP_Status": "",
                "Title": "", "Links_Found": 0, "Documents_Found": 0,
                "Status": "Failed", "Error": str(exc)
            })

        time.sleep(delay_seconds)

    pages_df = pd.DataFrame(pages)
    documents_df = pd.DataFrame(documents)

    if pages_df.empty:
        pages_df = pd.DataFrame(columns=[
            "Page_URL","Depth","HTTP_Status","Title","Links_Found",
            "Documents_Found","Status","Error"
        ])
    if documents_df.empty:
        documents_df = pd.DataFrame(columns=[
            "Source_Page","Link_Text","Document_URL","File_Name",
            "Category","Size","Status"
        ])

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        pages_df.to_excel(writer, sheet_name="Pages", index=False)
        documents_df.to_excel(writer, sheet_name="Documents", index=False)
        if not documents_df.empty:
            documents_df.groupby(["Category","Status"]).size().reset_index(name="Count").to_excel(
                writer, sheet_name="Summary", index=False
            )

    excel_bytes = excel_buffer.getvalue()
    archive_files["Reports/Web_Scraping_Report.xlsx"] = excel_bytes

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in archive_files.items():
            zf.writestr(name, content)

    downloaded = int((documents_df["Status"] == "Downloaded").sum()) if len(documents_df) else 0

    return {
        "pages_df": pages_df,
        "documents_df": documents_df,
        "excel_bytes": excel_bytes,
        "zip_bytes": zip_buffer.getvalue(),
        "summary": {
            "pages_processed": len(pages_df),
            "documents_found": len(documents_df),
            "downloaded": downloaded,
            "failed_or_skipped": len(documents_df) - downloaded,
        }
    }
