import unittest

from olx_parser import listing_links, normalize_url, offer_id, parse_core, parse_offer


class ParserTests(unittest.TestCase):
    def test_core_fields(self):
        price, area, rooms, ppm = parse_core("299 000 zł 48,5 m² 2 pokoje")
        self.assertEqual(price, 299000)
        self.assertEqual(area, 48.5)
        self.assertEqual(rooms, 2)
        self.assertAlmostEqual(ppm, 299000 / 48.5)

    def test_listing_link(self):
        html = '<div data-cy="l-card"><a href="/d/oferta/mieszkanie-IDABC123.html">Mieszkanie</a></div>'
        links = listing_links(html)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0], "https://www.olx.pl/d/oferta/mieszkanie-IDABC123.html")

    def test_offer_id(self):
        self.assertEqual(offer_id("https://www.olx.pl/d/oferta/x-IDAbC123.html"), "AbC123")

    def test_offer_page(self):
        html = '''
        <html><head><meta name="description" content="Mieszkanie do remontu"></head>
        <body><h1>2 pokoje Gliwice</h1><p>299 000 zł</p><p>48,5 m²</p><p>Piętro: 2</p></body></html>
        '''
        result = parse_offer(html, "https://www.olx.pl/d/oferta/x-IDXYZ.html")
        self.assertEqual(result["price"], 299000)
        self.assertEqual(result["area"], 48.5)
        self.assertEqual(result["rooms"], 2)
        self.assertEqual(result["source_offer_id"], "XYZ")
        self.assertIn("Piętro", result["floor_text"])

    def test_normalize_url_removes_query(self):
        self.assertEqual(
            normalize_url("/d/oferta/x-ID1.html?reason=observed_ad"),
            "https://www.olx.pl/d/oferta/x-ID1.html",
        )


if __name__ == "__main__":
    unittest.main()
