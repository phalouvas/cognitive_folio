import re
from typing import List, Tuple

import frappe

# Defaults tuned for financial statements
DEFAULT_MAX_URLS = 3
DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_HTML_MAX_BYTES = 600_000  # ~600 KB
DEFAULT_PDF_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_HTML_CHARS = 12000


def detect_urls(prompt: str) -> List[str]:
    """Detect http/https URLs in the prompt and clean trailing punctuation.

    Returns a list of unique URLs in original order, cleaned of common trailing
    punctuation characters.
    """
    if not prompt:
        return []

    # Regex: match http/https then any run of non-whitespace/non angle bracket/closing punctuation chars
    # Avoid premature termination by escaping quotes inside the character class.
    pattern = re.compile(r"(https?://[^\s<>\)\]\}\"']+)")
    raw_urls = pattern.findall(prompt)

    cleaned = []
    seen = set()
    for url in raw_urls:
        u = _clean_detected_url(url)
        if u and u not in seen:
            cleaned.append(u)
            seen.add(u)
    return cleaned


def _clean_detected_url(url: str) -> str:
    """Clean a detected URL by stripping common trailing punctuation and quotes."""
    u = url.rstrip('.,);:!?]')
    u = u.rstrip("\"'")
    return u


def _get_settings_limits():
    try:
        settings = frappe.get_single("CF Settings")
        max_urls = getattr(settings, "max_url_fetch", None) or DEFAULT_MAX_URLS
        timeout = getattr(settings, "url_fetch_timeout", None) or DEFAULT_TIMEOUT
        html_max_bytes = getattr(settings, "url_html_max_bytes", None) or DEFAULT_HTML_MAX_BYTES
        pdf_max_bytes = getattr(settings, "url_pdf_max_bytes", None) or DEFAULT_PDF_MAX_BYTES
        max_html_chars = getattr(settings, "max_chars_per_url", None) or DEFAULT_MAX_HTML_CHARS
        url_fetch_enabled = getattr(settings, "url_fetch_enabled", None)
        return int(max_urls), int(timeout), int(html_max_bytes), int(pdf_max_bytes), int(max_html_chars), bool(url_fetch_enabled) if url_fetch_enabled is not None else None
    except Exception:
        return DEFAULT_MAX_URLS, DEFAULT_TIMEOUT, DEFAULT_HTML_MAX_BYTES, DEFAULT_PDF_MAX_BYTES, DEFAULT_MAX_HTML_CHARS, None


def _safe_filename_from_url(url: str, fallback_ext: str = "") -> str:
    from urllib.parse import urlparse
    import os
    parsed = urlparse(url)
    name = os.path.basename(parsed.path) or "downloaded"
    name = name.split("?")[0].split("#")[0]
    if fallback_ext and not name.lower().endswith(fallback_ext.lower()):
        name = f"{name}{fallback_ext}"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name


def _truncate_text(text: str, limit: int) -> str:
    if text and len(text) > limit:
        return text[:limit] + "..."
    return text


def _process_html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _download_with_limit(resp, max_bytes: int) -> Tuple[bytes, bool]:
    content = bytearray()
    truncated = False
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > max_bytes:
            truncated = True
            break
    return bytes(content), truncated


def _replace_url_inline(text: str, cleaned_url: str, block: str) -> Tuple[str, bool]:
    """Replace the first occurrence of a URL (consider trailing punctuation variants) with block.

    Tries direct string replacement first; if not found, scans URL tokens and compares
    their cleaned form with cleaned_url, replacing the matched span.
    Returns (updated_text, replaced_flag).
    """
    # Direct replacement first
    if cleaned_url in text:
        return text.replace(cleaned_url, block, 1), True

    token_pat = re.compile(r"(https?://[^\s<>\)\]\}\"']+)")
    for m in token_pat.finditer(text):
        token = m.group(1)
        if _clean_detected_url(token) == cleaned_url:
            start, end = m.span(1)
            return text[:start] + block + text[end:], True
    return text, False


def fetch_and_embed_url_content(prompt: str, doc) -> str:
    if not prompt:
        return prompt
    try:
        import requests  # type: ignore
    except Exception:
        frappe.log_error("requests package not installed", "URL Fetch Error")
        return prompt

    urls = detect_urls(prompt)
    if not urls:
        return prompt

    max_urls, timeout, html_max_bytes, pdf_max_bytes, max_html_chars, settings_flag = _get_settings_limits()
    if settings_flag is False:
        return prompt

    processed = 0
    # Keep fallback sections only if we cannot inline-replace
    fallback_sections: List[str] = []
    updated_prompt = prompt

    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CF-URL-Fetcher/1.0)"}

    for url in urls:
        if processed >= max_urls:
            break
        processed += 1
        try:
            is_pdf_link = url.lower().endswith(".pdf")
            resp = session.get(url, stream=True, timeout=timeout, headers=headers)
            ct = (resp.headers.get("Content-Type") or "").lower()
            if resp.status_code >= 400:
                err_block = f"[Error fetching {url}: HTTP {resp.status_code}]"
                updated_prompt, replaced = _replace_url_inline(updated_prompt, url, err_block)
                if not replaced:
                    fallback_sections.append(err_block)
                resp.close()
                continue
            if is_pdf_link or "application/pdf" in ct:
                cl_header = resp.headers.get("Content-Length")
                if cl_header:
                    try:
                        cl = int(cl_header)
                        if cl > pdf_max_bytes:
                            err_block = f"[PDF too large to fetch: {url} (~{cl} bytes)]"
                            updated_prompt, replaced = _replace_url_inline(updated_prompt, url, err_block)
                            if not replaced:
                                fallback_sections.append(err_block)
                            resp.close()
                            continue
                    except Exception:
                        pass
                content, truncated = _download_with_limit(resp, pdf_max_bytes)
                resp.close()
                if truncated:
                    err_block = f"[PDF too large to fetch: {url} (truncated)]"
                    updated_prompt, replaced = _replace_url_inline(updated_prompt, url, err_block)
                    if not replaced:
                        fallback_sections.append(err_block)
                    continue
                try:
                    from frappe.utils.file_manager import save_file  # type: ignore
                except Exception:
                    frappe.log_error("Could not import save_file to attach PDF", "URL Fetch Error")
                    continue
                filename = _safe_filename_from_url(url, ".pdf")
                try:
                    file_doc = save_file(filename, content, doc.doctype, doc.name, is_private=1)
                    marker = f"<<{file_doc.file_name}>>"
                    updated_prompt, replaced = _replace_url_inline(updated_prompt, url, marker)
                    if not replaced:
                        # Last resort: keep a small note in fallback
                        fallback_sections.append(f"[Attached PDF from {url} as {file_doc.file_name}]")
                except Exception as e:
                    frappe.log_error(f"Failed to save PDF from {url}: {str(e)}", "URL Fetch Error")
                    err_block = f"[Error attaching PDF from {url}]"
                    updated_prompt, replaced = _replace_url_inline(updated_prompt, url, err_block)
                    if not replaced:
                        fallback_sections.append(err_block)
                continue
            content, _ = _download_with_limit(resp, html_max_bytes)
            resp.close()
            encoding = resp.encoding or "utf-8"
            try:
                text = content.decode(encoding, errors="replace")
            except Exception:
                text = content.decode("utf-8", errors="replace")
            extracted = _process_html_to_text(text)
            extracted = _truncate_text(extracted, max_html_chars)
            if extracted.strip():
                block = f"--- Fetched URL Content: {url} ---\n{extracted}\n--- End URL Content ---"
                updated_prompt, replaced = _replace_url_inline(updated_prompt, url, block)
                if not replaced:
                    fallback_sections.append(block)
            else:
                err_block = f"[No readable text found at {url}]"
                updated_prompt, replaced = _replace_url_inline(updated_prompt, url, err_block)
                if not replaced:
                    fallback_sections.append(err_block)
        except Exception as e:
            try:
                resp.close()  # type: ignore
            except Exception:
                pass
            frappe.log_error(f"Error fetching URL {url}: {str(e)}", "URL Fetch Error")
            err_block = f"[Error fetching {url}: {str(e)}]"
            updated_prompt, replaced = _replace_url_inline(updated_prompt, url, err_block)
            if not replaced:
                fallback_sections.append(err_block)

    if fallback_sections:
        prepend = "\n".join(fallback_sections)
        updated_prompt = f"{prepend}\n\n--- User Original Prompt ---\n" + updated_prompt
    return updated_prompt
