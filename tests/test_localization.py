# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path
import tkinter as tk
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import i18n


class LocalizationTests(unittest.TestCase):
    def test_road_information_date_remains_visible_in_all_six_languages(self):
        from road_provider import road_information
        from types import SimpleNamespace
        import re
        road=SimpleNamespace(ways=[object()],_index_stamp=1_798_761_600_000_000_000)
        text=road_information(road)
        date=re.search(r'\b\d{2}-\d{2}-\d{4}\b',text).group()
        for code in i18n.LANGUAGES:
            i18n.configure(code,ROOT/'src')
            self.assertIn(date,i18n.tr(text))
            if code!='nl':
                self.assertIn(i18n.catalog['~ Gegevens van '],i18n.tr(text))
                self.assertNotIn(' Gegevens van ',i18n.tr(text))

    def tearDown(self):
        i18n.configure("nl", ROOT / "src")

    def test_cache_is_cleared_when_language_changes(self):
        for language, expected in [
            ("en", "File"),
            ("de", "Datei"),
            ("fr", "Fichier"),
            ("es", "Archivo"),
            ("pt", "Ficheiro"),
            ("nl", "Bestand"),
        ]:
            i18n.configure(language, ROOT / "src")
            self.assertEqual(i18n.tr("Bestand"), expected)
            self.assertEqual(i18n.tr("Bestand"), expected)

    def test_display_variable_keeps_source_for_application_logic(self):
        i18n.configure("de", ROOT / "src")
        root = tk.Tcl()
        value = i18n.DisplayVar(root, value="Bestand")
        self.assertEqual(value.get(), "Bestand")
        self.assertEqual(root.globalgetvar(value._name), "Datei")
        value.set("Kaart")
        self.assertEqual(value.get(), "Kaart")
        self.assertEqual(root.globalgetvar(value._name), "Karte")

    def test_untranslated_user_text_and_nonstrings_pass_through(self):
        i18n.configure("fr", ROOT / "src")
        self.assertEqual(i18n.tr("My personal route 123.gpx"), "My personal route 123.gpx")
        value = {"key": "Bestand"}
        self.assertIs(i18n.tr(value), value)

    def test_spanish_and_portuguese_cover_the_entire_catalogue(self):
        english=json.loads((ROOT/'src/locales/en.json').read_text(encoding='utf-8'))
        for code in ('es','pt'):
            translated=json.loads((ROOT/f'src/locales/{code}.json').read_text(encoding='utf-8'))
            self.assertEqual(set(translated),set(english))
            self.assertTrue(all(v.strip() for v in translated.values()))
            for key,value in translated.items():
                self.assertNotIn('\ufffd',value)
                self.assertEqual(value.count('\n'),english[key].count('\n'),key)

    def test_transport_keys_survive_spanish_and_portuguese_display(self):
        for code,label in (('es','Caminar'),('pt','Caminhada')):
            i18n.configure(code,ROOT/'src')
            root=tk.Tcl();value=i18n.DisplayVar(root,value='Lopen')
            self.assertEqual(value.get(),'Lopen')
            self.assertEqual(root.globalgetvar(value._name),label)


if __name__ == "__main__":
    unittest.main()
