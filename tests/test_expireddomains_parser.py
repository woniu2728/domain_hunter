from __future__ import annotations

import unittest

from crawler.expireddomains import build_deleted_url
from crawler.expireddomains_parser import parse_deleted_domains


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
            "https://member.expireddomains.net/domains/expiredcom/?o=changes&r=d#listing",
        )

    def test_build_deleted_url_with_crawl_filters(self) -> None:
        self.assertEqual(
            build_deleted_url("com", max_length=5, allow_digits=False),
            "https://member.expireddomains.net/domains/expiredcom/?o=changes&r=d&fmaxhost=5&fnumhost=1#listing",
        )

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


if __name__ == "__main__":
    unittest.main()
