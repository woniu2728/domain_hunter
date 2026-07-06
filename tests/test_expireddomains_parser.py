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
        self.assertEqual(build_deleted_url("com"), "https://www.expireddomains.net/deleted-com-domains/")


if __name__ == "__main__":
    unittest.main()
