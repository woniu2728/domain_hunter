from __future__ import annotations

from bs4 import BeautifulSoup

from domain_hunter.types import SourceDomain


class ParseError(ValueError):
    pass


def parse_deleted_domains(html: str, tld: str) -> tuple[list[SourceDomain], int, str | None]:
    soup = BeautifulSoup(html, "lxml")
    block_reason = _blocked_reason(soup)
    if block_reason:
        raise ParseError(block_reason)

    table = _find_domain_table(soup)
    if table is None:
        raise ParseError("未找到域名列表表格。")

    headers = [_clean_text(cell.get_text(" ")) for cell in table.select("thead th")]
    if not headers:
        first_row = table.find("tr")
        headers = [_clean_text(cell.get_text(" ")) for cell in first_row.find_all(["th", "td"])] if first_row else []
    header_map = {header.lower(): index for index, header in enumerate(headers)}
    domain_index = _find_header_index(header_map, ("domain", "domain name"))
    status_index = _find_header_index(header_map, ("status",))
    dropped_index = _find_header_index(header_map, ("dropped", "delete date", "date"))
    if domain_index is None:
        raise ParseError("表格缺少 Domain 列。")

    results: list[SourceDomain] = []
    seen = 0
    for row in table.select("tbody tr") or table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) <= domain_index:
            continue
        domain = _extract_domain(cells[domain_index])
        if not domain or "." not in domain:
            continue
        seen += 1
        status = _clean_text(cells[status_index].get_text(" ")) if status_index is not None and len(cells) > status_index else "available"
        if status and "available" not in status.lower():
            continue
        dropped = _clean_text(cells[dropped_index].get_text(" ")) if dropped_index is not None and len(cells) > dropped_index else None
        metrics = _row_metrics(headers, cells)
        results.append(
            SourceDomain(
                domain=domain.lower(),
                tld=domain.rsplit(".", 1)[1].lower(),
                source_status="available",
                dropped_date=dropped or None,
                metrics=metrics,
            )
        )

    next_url = _next_page_url(soup)
    return results, seen, next_url


def _find_domain_table(soup: BeautifulSoup):
    listing = soup.select_one("#listing")
    if listing:
        table = listing.find("table")
        if table:
            return table
    for table in soup.find_all("table"):
        text = table.get_text(" ").lower()
        if "domain" in text and ("status" in text or "available" in text or "changes" in text or "whois" in text):
            return table
    return None


def _find_header_index(header_map: dict[str, int], names: tuple[str, ...]) -> int | None:
    for name in names:
        if name in header_map:
            return header_map[name]
    for header, index in header_map.items():
        if any(name in header for name in names):
            return index
    return None


def _extract_domain(cell) -> str:
    link = cell.find("a")
    text = link.get_text(" ") if link else cell.get_text(" ")
    return _clean_text(text).lower()


def _row_metrics(headers: list[str], cells) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for index, header in enumerate(headers):
        if index >= len(cells):
            continue
        key = header.strip()
        if key and key.lower() not in {"domain", "status"}:
            metrics[key] = _clean_text(cells[index].get_text(" "))
    return metrics


def _next_page_url(soup: BeautifulSoup) -> str | None:
    for link in soup.find_all("a"):
        text = _clean_text(link.get_text(" ")).lower()
        rel = " ".join(link.get("rel", [])).lower() if isinstance(link.get("rel"), list) else str(link.get("rel", "")).lower()
        if text in {"next", "next page", ">"} or "next" in rel:
            href = link.get("href")
            return str(href) if href else None
    return None


def _blocked_reason(soup: BeautifulSoup) -> str:
    text = soup.get_text(" ").lower()
    title = _clean_text(soup.title.get_text(" ")) if soup.title else ""
    canonical = soup.select_one('link[rel="canonical"]')
    canonical_href = str(canonical.get("href", "")) if canonical else ""
    if "emailauth" in canonical_href.lower() or "multi factor authentication" in title.lower() or "verify code" in text:
        return "ExpiredDomains.net 要求邮箱验证码验证，请在账号配置中提交邮件验证码后重试。"
    patterns = ("captcha", "verify", "access denied", "too many requests", "login")
    if any(pattern in text for pattern in patterns) and "domain" not in text:
        return "页面疑似出现验证码、登录失效或访问限制。"
    return ""


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())
