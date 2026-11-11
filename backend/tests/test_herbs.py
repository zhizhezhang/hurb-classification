"""Real atlas data, startup validation, and read-only HTTP behavior."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.core.config import PROJECT_ROOT
from backend.main import app
from backend.services.herb_service import ATLAS_PATH, load_herbs


MAPPING_PATH = PROJECT_ROOT / "reports" / "data_split" / "class_to_idx.json"
MODEL_PATH = PROJECT_ROOT / "models" / "convnext_tiny_best.pt"

# Per-herb snapshots of the three paragraphs supplied for task 06.3.2.
# Copy-only source labels (for example, website names followed by "+1") are excluded.
EXPECTED_DETAILS_SHA256 = {
    "jiucengta": "baea4529128fc5b7da226b7820ac26bbc0166e76665f33dbc8c5a46df7ebd3d7",
    "renshen": "6018c4c8408282f4ab3df0ec5a1d1e00c19ed46d561e742ddc4fd93e64093fda",
    "dongchongxiacao": "ba7138e5cbbf558f6c457050c13623e5b48842adc4cde925c7ae82e44f69354c",
    "gangouqi": "14ac1ae07fd7d60e4541848c811039b2a6c8d3cb08943194a3d4d08df437b42b",
    "danggui": "9eef6f9fa46dbdd7ab725caa9553752c0a486105304691ac8b71df4ada1bf6ca",
    "wuhuaguo": "23273b664155aa8ae1664f2388d9ae809e108d8348ab1a7a84aca8a44b8392ca",
    "shidi": "a0646fa536bb984f163b8c353a99f4aefe07894f2e1ff060cc1213b8dddcc354",
    "huaihua": "ccd5b11e42a5f76113f6f02b5e891303d3fe8a7ec4aa95e77bb1f40565b0f2af",
    "lingzhi": "ceeeecc0709a6c93facece3114177685e7cdbc2e9a8188088b9966b6196f7350",
    "luohanguo": "3fddc1b343db9c2ef1c6001b68e25f6676ef71e958ddc2e594efee810d4e235b",
    "aiye": "5528160f6eed97946464df712409176556ae9d33706b79fd1e79c2811d38a025",
    "luhui": "acf15727e631d051b3001bc5d9ae56a3e8a14d4140c3360e287a9f2c6241ab92",
    "cangerzi": "32fe22ae5ac52de7463900bd74c03e6300b80d10c8a26d6cf1e437e9b6cc56b9",
    "cheqiancao": "78652352222ef72c19e8f81a08e87a5e7c870ec788593c9f868109eaf541e55b",
    "jinqiancao": "ff86aaf1e9fd435a39d0ce38c34671ba7795f635921ea72134d373b6101763d4",
    "jinyinhua": "b53b519d2b096aa54fe7dc014bfa2ac5d03fe2630ebaa41986def6ce5782770c",
    "chenpi": "9e73f07a55002834f64c71ca026253c94ba656100fda9872afd9e27250dd50e3",
    "huangqi": "9130c6d6d6ee47a81404a8d6660117cd013308420447c819d8ec0f2128bb1b05",
}


class HerbDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))

    def test_real_records_match_model_and_illustrations(self) -> None:
        catalog = load_herbs(self.mapping)
        self.assertEqual(len(catalog.ordered), 18)
        self.assertEqual({herb.name for herb in catalog.ordered}, set(self.mapping))
        self.assertEqual(len(catalog.by_id), 18)
        self.assertEqual([herb.name for herb in catalog.ordered],
                         [name for name, _ in sorted(self.mapping.items(), key=lambda item: item[1])])
        for herb in catalog.ordered:
            image = PROJECT_ROOT / "frontend/public" / herb.image_url.lstrip("/")
            self.assertTrue(image.is_file(), herb.id)
            self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertTrue(herb.references)

    def test_json_order_is_not_required(self) -> None:
        records = json.loads(ATLAS_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reversed.json"
            path.write_text(json.dumps(list(reversed(records)), ensure_ascii=False), encoding="utf-8")
            catalog = load_herbs(self.mapping, path)
        self.assertEqual(catalog.ordered[0].name, "九层塔")

    def test_recognition_intros_are_complete(self) -> None:
        catalog = load_herbs(self.mapping)
        for herb in catalog.ordered:
            with self.subTest(herb_id=herb.id):
                self.assertTrue(herb.recognition_intro)
                self.assertNotIn("模型类别", herb.recognition_intro)
                self.assertNotIn("尚未核实", herb.recognition_intro)

    def test_detail_paragraphs_match_supplied_source(self) -> None:
        records = json.loads(ATLAS_PATH.read_text(encoding="utf-8"))
        self.assertEqual([record["id"] for record in records], list(EXPECTED_DETAILS_SHA256))
        self.assertEqual([record["name"] for record in records],
                         [name for name, _ in sorted(self.mapping.items(), key=lambda item: item[1])])
        for record in records:
            with self.subTest(herb_id=record["id"]):
                values = [record[key] for key in ("appearance", "traditional_effects", "allusion")]
                self.assertTrue(all(isinstance(value, str) and value.strip() for value in values))
                digest = hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":"))
                                        .encode("utf-8")).hexdigest()
                self.assertEqual(digest, EXPECTED_DETAILS_SHA256[record["id"]])
                self.assertTrue(record["summary"])
                self.assertTrue(record["recognition_intro"])
                self.assertEqual(record["image_url"], f"/assets/herbs/herb_{record['id']}.png")

    def test_bad_data_prevents_startup(self) -> None:
        records = json.loads(ATLAS_PATH.read_text(encoding="utf-8"))
        cases = [
            (records[:-1], "exactly 18"),
            ([{**records[0], "id": records[1]["id"]}, *records[1:]], "IDs must be unique"),
            ([{**records[0], "name": records[1]["name"]}, *records[1:]], "names must be unique"),
            ([{**records[0], "name": "不存在的类别"}, *records[1:]], "categories differ"),
            ([{**records[0], "image_url": "/assets/herbs/herb_notfound.png"}, *records[1:]], "Invalid illustration URL"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "atlas.json"
            for candidate, message in cases:
                with self.subTest(message=message):
                    path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, message):
                        load_herbs(self.mapping, path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unable to read herbal atlas JSON"):
                load_herbs(self.mapping, path)

    def test_missing_artwork_is_explicit(self) -> None:
        records = json.loads(ATLAS_PATH.read_text(encoding="utf-8"))
        records[0]["id"] = "missing_artwork"
        records[0]["image_url"] = "/assets/herbs/herb_missing_artwork.png"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "atlas.json"
            path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Missing illustration for 九层塔"):
                load_herbs(self.mapping, path)


class HerbApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime_temp = tempfile.TemporaryDirectory()
        cls.env_patch = patch.dict(os.environ, {
            "HERB_MODEL_PATH": str(MODEL_PATH), "HERB_DEVICE": "auto",
            "HERB_HISTORY_DB_PATH": str(Path(cls.runtime_temp.name) / "history.db"),
            "HERB_UPLOADS_DIR": str(Path(cls.runtime_temp.name) / "uploads"),
        })
        cls.env_patch.start()
        cls.client = TestClient(app)
        try:
            cls.client.__enter__()
        except Exception:
            cls.env_patch.stop()
            cls.runtime_temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        cls.env_patch.stop()
        cls.runtime_temp.cleanup()

    def test_list_order_search_and_no_match(self) -> None:
        response = self.client.get("/api/herbs")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total"], 18)
        self.assertEqual(data["data"][0]["name"], "九层塔")
        for query, expected in (("人参", "人参"), ("REN SHEN", "人参"), ("renshen", "人参")):
            with self.subTest(query=query):
                result = self.client.get("/api/herbs", params={"q": query}).json()
                self.assertEqual(result["total"], 1)
                self.assertEqual(result["data"][0]["name"], expected)
        self.assertEqual(self.client.get("/api/herbs", params={"q": "nonexistent"}).json(),
                         {"success": True, "total": 0, "data": []})

    def test_details_and_not_found(self) -> None:
        response = self.client.get("/api/herbs/jinqiancao")
        self.assertEqual(response.status_code, 200, response.text)
        herb = response.json()["data"]
        self.assertEqual(herb["name"], "金钱草")
        self.assertEqual(herb["image_url"], "/assets/herbs/herb_jinqiancao.png")
        self.assertIn("文献记述", herb["traditional_uses"])
        self.assertEqual(self.client.get("/api/herbs/not_here").status_code, 404)

    def test_all_recognition_intros_are_returned_by_detail_api(self) -> None:
        records = json.loads(ATLAS_PATH.read_text(encoding="utf-8"))
        for record in records:
            with self.subTest(herb_id=record["id"]):
                response = self.client.get(f"/api/herbs/{record['id']}")
                self.assertEqual(response.status_code, 200)
                herb = response.json()["data"]
                self.assertEqual(herb["name"], record["name"])
                self.assertEqual(herb["recognition_intro"], record["recognition_intro"])
                self.assertEqual(herb["summary"], record["summary"])
                self.assertEqual(herb["image_url"], record["image_url"])
                for field in ("appearance", "traditional_effects", "allusion"):
                    self.assertEqual(herb[field], record[field])

    def test_requests_use_startup_cache(self) -> None:
        with patch("backend.services.herb_service.Path.read_text", side_effect=AssertionError("unexpected JSON read")):
            self.assertEqual(self.client.get("/api/herbs").status_code, 200)
            self.assertEqual(self.client.get("/api/herbs/renshen").status_code, 200)

    def test_existing_routes_and_docs(self) -> None:
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/docs").status_code, 200)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("post", paths["/api/predict"])
        self.assertIn("get", paths["/api/herbs"])
        self.assertIn("get", paths["/api/herbs/{herb_id}"])


if __name__ == "__main__":
    unittest.main()
