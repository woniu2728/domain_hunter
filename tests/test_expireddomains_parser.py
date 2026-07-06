from __future__ import annotations

import unittest
from unittest.mock import patch

from crawler.expireddomains import ExpiredDomainsCrawler, build_deleted_url
from crawler.types import CrawlerAccount
from crawler.expireddomains_parser import ParseError, parse_deleted_domains


class ExpiredDomainsParserTests(unittest.TestCase):
    def test_parse_available_domains_from_table(self) -> None:
        html = """
        <html><body>
          <table>
            <thead><tr><th>Domain</th><th>Status</th><th>Dropped</th><th>BL</th></tr></thead>
            <tbody>
              <tr><td><a>flowmint.com</a></td><td>available</td><td>2026-07-06</td><td>1</td></tr>
              <tr><td><a>taken.com</a></td><td>registered</td><td>2026-07-06</td><td>2</td></tr>
            </tbody>
          </table>
          <a rel="next" href="/deleted-com-domains/2/">Next</a>
        </body></html>
        """

        domains, seen, next_url = parse_deleted_domains(html, "com")

        self.assertEqual(seen, 2)
        self.assertEqual(next_url, "/deleted-com-domains/2/")
        self.assertEqual(len(domains), 1)
        self.assertEqual(domains[0].domain, "flowmint.com")
        self.assertEqual(domains[0].metrics["BL"], "1")

    def test_build_deleted_url(self) -> None:
        self.assertEqual(
            build_deleted_url("com"),
            "https://member.expireddomains.net/domains/combinedexpired/?o=changes&r=d&ftlds[]=2#listing",
        )

    def test_build_deleted_url_with_crawl_filters(self) -> None:
        self.assertEqual(
            build_deleted_url("com", max_length=5, allow_digits=False),
            "https://member.expireddomains.net/domains/combinedexpired/?o=changes&r=d&ftlds[]=2&fmaxhost=5&fnumhost=1#listing",
        )

    def test_build_deleted_url_rejects_unsupported_tld(self) -> None:
        with self.assertRaises(ValueError):
            build_deleted_url("net")

    def test_parse_member_listing_without_status_column(self) -> None:
        html = """
        <html><body>
          <div id="listing">
            <table>
              <thead><tr><th>Domain</th><th>Changes</th><th>BL</th></tr></thead>
              <tbody>
                <tr><td><a>flowmint.com</a></td><td>1</td><td>2</td></tr>
              </tbody>
            </table>
          </div>
        </body></html>
        """

        domains, seen, next_url = parse_deleted_domains(html, "com")

        self.assertIsNone(next_url)
        self.assertEqual(seen, 1)
        self.assertEqual(len(domains), 1)
        self.assertEqual(domains[0].domain, "flowmint.com")

    def test_parse_email_auth_page_reports_verification_required(self) -> None:
        html = """
        <html>
          <head>
            <title>Multi Factor Authentication</title>
            <link rel="canonical" href="https://www.expireddomains.net/emailauth/token/">
          </head>
          <body>
            <form action="/emailauth/token/">
              <p>Please enter the code we just sent to your email.</p>
              <input type="text" name="secret_code">
              <button>Verify Code</button>
            </form>
          </body>
        </html>
        """

        with self.assertRaisesRegex(ParseError, "邮箱验证码"):
            parse_deleted_domains(html, "com")

    def test_parse_combined_expired_next_page_link(self) -> None:
        html = """
        <html><body>
          <div id="listing">
            <table>
              <thead><tr><th>Domain</th><th>Changes</th></tr></thead>
              <tbody><tr><td><a>flowmint.com</a></td><td>1</td></tr></tbody>
            </table>
          </div>
          <a href="/domains/combinedexpired/?start=25&ftlds[]=2&o=changes&r=d#listing">2</a>
        </body></html>
        """

        _, _, next_url = parse_deleted_domains(html, "com")

        self.assertEqual(next_url, "/domains/combinedexpired/?start=25&ftlds[]=2&o=changes&r=d#listing")

    def test_crawler_follows_member_next_page(self) -> None:
        import asyncio

        first_page = """
        <html><body>
          <div id="listing">
            <table>
              <thead><tr><th>Domain</th><th>Changes</th></tr></thead>
              <tbody><tr><td><a>first.com</a></td><td>1</td></tr></tbody>
            </table>
          </div>
          <a href="/domains/combinedexpired/?start=25&ftlds[]=2&o=changes&r=d#listing">2</a>
        </body></html>
        """
        second_page = """
        <html><body>
          <div id="listing">
            <table>
              <thead><tr><th>Domain</th><th>Changes</th></tr></thead>
              <tbody><tr><td><a>second.com</a></td><td>1</td></tr></tbody>
            </table>
          </div>
        </body></html>
        """
        fetched_urls = []

        def fake_fetch(self, url):
            fetched_urls.append(url)
            return first_page if len(fetched_urls) == 1 else second_page

        crawler = ExpiredDomainsCrawler(CrawlerAccount("acc", "user", "pass"), request_delay_seconds=0)
        with patch.object(ExpiredDomainsCrawler, "_fetch_html", fake_fetch):
            result = asyncio.run(crawler.crawl_tld("com", max_pages=2))

        self.assertEqual(result.pages_fetched, 2)
        self.assertEqual([item.domain for item in result.available_domains], ["first.com", "second.com"])
        self.assertTrue(fetched_urls[1].startswith("https://member.expireddomains.net/domains/combinedexpired/"))


if __name__ == "__main__":
    unittest.main()
