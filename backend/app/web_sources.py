from dataclasses import dataclass
from html import unescape
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.documents import Document


@dataclass(frozen=True)
class WebSource:
    name: str
    url: str
    document_type: str = "external"


DEFAULT_WEB_SOURCES = [
    WebSource("Diario da Republica", "https://diariodarepublica.pt/dr/home"),
    WebSource(
        "Infarmed RCM",
        "https://www.infarmed.pt/web/infarmed/entidades/medicamentos-uso-humano/autorizacao-de-introducao-no-mercado/modelos_rcm_fi_procedimentos",
    ),
    WebSource("DGEG Energia Publicacoes", "https://www.dgeg.gov.pt/pt/estatistica/energia/publicacoes/"),
    WebSource(
        "Banco de Portugal Boletins Economicos",
        "https://www.bportugal.pt/page/listagem-de-publicacoes-do-banco-de-portugal?f%5B0%5D=pub_type_bdp%3A890",
    ),
]


def clean_text(text: str) -> str:
    lines = [line.strip() for line in unescape(text).splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def fetch_html(url: str, timeout: int = 20) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 EY-Knowledge-Navigator/1.0 "
                "(compatible; challenge prototype)"
            )
        },
    )
    response.raise_for_status()
    return response.text


def extract_page_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    candidates = [
        soup.select_one("#main-content"),
        soup.find("main"),
        soup.find("article"),
        soup.body,
        soup,
    ]
    best_text = ""
    for candidate in candidates:
        if not candidate:
            continue
        candidate_text = clean_text(candidate.get_text("\n", strip=True))
        if len(candidate_text) > len(best_text):
            best_text = candidate_text
    return best_text, title


def collect_relevant_links(base_url: str, html: str, limit: int = 4) -> list[str]:
    parsed_base = urlparse(base_url)
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = urldefrag(urljoin(base_url, anchor["href"]))[0]
        parsed_href = urlparse(href)
        if parsed_href.netloc and parsed_href.netloc != parsed_base.netloc:
            continue
        if href == urldefrag(base_url)[0]:
            continue
        if href in links:
            continue
        text = anchor.get_text(" ", strip=True).lower()
        href_lower = href.lower()
        if any(keyword in f"{text} {href_lower}" for keyword in ["pdf", "boletim", "publica", "relatorio", "modelo", "energia"]):
            links.append(href)
        if len(links) >= limit:
            break

    return links


def document_from_url(source: WebSource, url: str, title_suffix: str | None = None) -> Document | None:
    try:
        html = fetch_html(url)
        text, title = extract_page_text(html)
    except Exception as exc:
        print(f"Web scraping skipped for {url}: {exc}")
        return None

    if len(text) < 200:
        return None

    title_value = title_suffix or title or source.name
    return Document(
        page_content=text[:20000],
        metadata={
            "source": source.name,
            "document_type": source.document_type,
            "title": title_value,
            "url": url,
        },
    )


def scrape_web_sources(max_links_per_source: int = 4) -> list[Document]:
    documents: list[Document] = []

    for source in DEFAULT_WEB_SOURCES:
        html = None
        try:
            html = fetch_html(source.url)
            text, title = extract_page_text(html)
        except Exception as exc:
            print(f"Web scraping skipped for {source.url}: {exc}")
            continue

        if len(text) >= 200:
            documents.append(
                Document(
                    page_content=text[:20000],
                    metadata={
                        "source": source.name,
                        "document_type": source.document_type,
                        "title": title or source.name,
                        "url": source.url,
                    },
                )
            )

        for link in collect_relevant_links(source.url, html, limit=max_links_per_source):
            linked_document = document_from_url(source, link)
            if linked_document:
                documents.append(linked_document)

    return documents


def check_web_sources(max_links_per_source: int = 4) -> list[dict]:
    results: list[dict] = []

    for source in DEFAULT_WEB_SOURCES:
        result = {
            "source": source.name,
            "url": source.url,
            "status": "ok",
            "documents": 0,
            "chars": 0,
            "message": "",
        }
        try:
            html = fetch_html(source.url)
            text, title = extract_page_text(html)
            result["title"] = title or source.name
            result["chars"] = len(text)
            result["links"] = collect_relevant_links(source.url, html, limit=max_links_per_source)
            result["documents"] = 1 if len(text) >= 200 else 0
            if len(text) < 200:
                result["status"] = "empty"
                result["message"] = "Static HTML did not contain enough extractable text."
        except Exception as exc:
            result["status"] = "error"
            result["message"] = str(exc)
            result["links"] = []
        results.append(result)

    return results
