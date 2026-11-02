# SPDX-License-Identifier: GPL-3.0-only
"""Keep translated instructions aligned with real controls and available images."""
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ManualContentTests(unittest.TestCase):
    def test_each_language_covers_the_complete_walkthrough(self):
        book = json.loads((ROOT/'docs/manuals/guidebook.json').read_text(encoding='utf-8'))
        self.assertEqual(set(book), {'nl','en','de','fr','es','pt'})
        for code, chapters in book.items():
            with self.subTest(language=code):
                self.assertEqual([c['id'] for c in chapters], list(range(1,34)))
                self.assertTrue(all(c['title'] and c['tip'] and 4<=len(c['steps'])<=6
                                    and all(c['steps']) for c in chapters))
                text = json.dumps(chapters,ensure_ascii=False)
                self.assertNotIn('\ufffd',text)
                self.assertNotIn('[[', re.sub(r'\[\[.*?\]\]', '', text))

    def test_referenced_controls_have_translations_and_real_capture_files(self):
        book = json.loads((ROOT/'docs/manuals/guidebook.json').read_text(encoding='utf-8'))
        names = {'files','editor','transport','route','progress','proposal','context',
                 'connection','time','stats','waypoint'}
        for code, chapters in book.items():
            catalogue=json.loads((ROOT/f'src/locales/{code if code!="nl" else "en"}.json').read_text(encoding='utf-8'))
            for key in re.findall(r'\[\[(.*?)\]\]',json.dumps(chapters,ensure_ascii=False)):
                self.assertIn(key,catalogue, (code,key))
            captures=ROOT/'docs/manuals/screens/0.5.5'/code
            self.assertEqual({p.stem for p in captures.glob('*.jpg')}, names)
            for name in names:
                self.assertEqual((captures/(name+'.jpg')).read_bytes()[:3],b'\xff\xd8\xff')


if __name__ == '__main__':
    unittest.main()
