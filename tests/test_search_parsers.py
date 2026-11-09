from __future__ import annotations

import base64
import unittest

from app.search import bing, yahoo


def _bing_href(url: str) -> str:
    token = "a1" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return (
        "https://www.bing.com/ck/a?!&&p=abc&ptn=3&ver=2&hsh=4"
        f"&u={token}&ntb=1"
    )


class BingParserTests(unittest.TestCase):
    def test_parse_and_decode(self) -> None:
        html = f"""
        <html><body>
          <li class="b_algo"><h2><a href="{_bing_href('https://example.com/event')}">
            Мероприятие
          </a></h2></li>
          <li class="b_algo"><h2><a href="{_bing_href('https://vk.com/event')}">
            Соцсеть
          </a></h2></li>
        </body></html>
        """
        self.assertEqual(bing.parse_results(html), ["https://example.com/event"])

    def test_no_results(self) -> None:
        self.assertEqual(bing.parse_results("<html><body></body></html>"), [])


class YahooParserTests(unittest.TestCase):
    def test_parse_and_decode(self) -> None:
        html = """
        <html><body>
          <div class="algo">
            <a href="https://r.search.yahoo.com/x/RV=2/RE=1/RO=10/RU=https%3a%2f%2fexample.com%2fevent/RK=2/RS=abc-">
              Мероприятие
            </a>
          </div>
          <div class="algo">
            <a href="https://r.search.yahoo.com/x/RU=https%3a%2f%2fvk.com%2fevent/RK=2/RS=def-">
              Соцсеть
            </a>
          </div>
        </body></html>
        """
        self.assertEqual(yahoo.parse_results(html), ["https://example.com/event"])

    def test_no_results(self) -> None:
        self.assertEqual(yahoo.parse_results("<html><body></body></html>"), [])


if __name__ == "__main__":
    unittest.main()
