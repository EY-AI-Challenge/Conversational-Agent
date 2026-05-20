from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from langchain_core.documents import Document


DGEG_PUBLICATIONS_URL = "https://www.dgeg.gov.pt/pt/estatistica/energia/publicacoes/"
DGEG_DOMAIN = "www.dgeg.gov.pt"
DGEG_SOURCE_PREFIX = "DGEG"
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "EY-Knowledge-Assistant/1.0"


@dataclass(frozen=True)
class Link:
    url: str
    text: str


class _ReadableHTMLParser(HTMLParser):
    """Extract readable text and links from DGEG HTML pages."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._current_href: str | None = None
        self._current_link_text: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[Link] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "br"}:
            self.text_parts.append("\n")

        if tag == "a":
            attrs_dict = dict(attrs)
            self._current_href = attrs_dict.get("href")
            self._current_link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag == "a" and self._current_href:
            text = _clean_text(" ".join(self._current_link_text))
            if text:
                self.links.append(Link(url=self._current_href, text=text))
            self._current_href = None
            self._current_link_text = []

        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return

        data = html.unescape(data)
        self.text_parts.append(data)
        if self._current_href is not None:
            self._current_link_text.append(data)


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _is_dgeg_html_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != DGEG_DOMAIN:
        return False
    path = parsed.path.lower()
    return not path.endswith((".pdf", ".xlsx", ".xls", ".csv", ".zip", ".jpg", ".png"))


def _publication_links(base_url: str, links: Iterable[Link], max_pages: int) -> list[Link]:
    selected: list[Link] = []
    seen = {base_url.rstrip("/")}

    for link in links:
        absolute_url = urljoin(base_url, link.url).split("#", 1)[0]
        if not _is_dgeg_html_url(absolute_url):
            continue

        parsed_path = urlparse(absolute_url).path
        if "/pt/estatistica/energia/" not in parsed_path:
            continue

        key = absolute_url.rstrip("/")
        if key in seen:
            continue

        seen.add(key)
        selected.append(Link(url=absolute_url, text=link.text))
        if len(selected) >= max_pages:
            break

    return selected


def _parse_page(url: str, source_name: str) -> tuple[Document, list[Link]]:
    parser = _ReadableHTMLParser()
    parser.feed(_fetch(url))
    text = _clean_text("\n".join(parser.text_parts))
    page_content = (
        f"Fonte: {source_name}\n"
        f"URL: {url}\n\n"
        f"{text}"
    )
    return (
        Document(
            page_content=page_content,
            metadata={
                "source": source_name,
                "type": "dgeg_publication",
                "url": url,
            },
        ),
        parser.links,
    )


def load_dgeg_publications(max_pages: int = 8) -> list[Document]:
    """
    Load DGEG energy publications pages as LangChain documents.

    The DGEG source is public HTML, so this loader keeps the implementation
    lightweight and resilient: it fetches the public publications landing page
    plus the first same-section publication/category pages linked from it.
    """

    docs: list[Document] = []
    try:
        main_doc, links = _parse_page(
            DGEG_PUBLICATIONS_URL,
            f"{DGEG_SOURCE_PREFIX} - Publicações de Energia",
        )
        docs.append(main_doc)
    except Exception as exc:
        print(f"  ❌ Erro DGEG {DGEG_PUBLICATIONS_URL}: {exc}")
        return docs

    for link in _publication_links(DGEG_PUBLICATIONS_URL, links, max_pages=max_pages):
        try:
            doc, _ = _parse_page(
                link.url,
                f"{DGEG_SOURCE_PREFIX} - {link.text}",
            )
            docs.append(doc)
        except Exception as exc:
            print(f"  ⚠️  DGEG ignorado {link.url}: {exc}")

    print(f"  ✅ DGEG: {len(docs)} páginas carregadas")
    return docs
