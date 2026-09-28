import copy
import json
import unittest
from pathlib import Path

from backend.app.analysis_contract.client import (
    ProviderConfig,
    build_request_payload,
    extract_normalized_response,
)
from backend.app.analysis_contract.contract import (
    ContractError,
    build_analysis_context,
    load_json,
    validate_analysis,
)


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "config/analysis/inputs/w0-construction-set.v1.json"
SCHEMA = ROOT / "config/analysis/analysis-response.schema.v1.json"
PROMPT = ROOT / "config/analysis/prompts/construction-analysis.v1.md"
VALID = ROOT / "config/analysis/fixtures/synthetic-valid.response.json"
LIVE = ROOT / "config/analysis/fixtures/live/gatellm-luna-w0-v1.response.json"
THRESHOLDS = ROOT / "config/analysis/thresholds.v1.json"


class AnalysisContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build_analysis_context(load_json(INPUT), ROOT)
        cls.valid = load_json(VALID)

    def test_fixture_hashes_and_catalog_resolve(self):
        self.assertEqual(len(self.context["images"]), 3)
        self.assertEqual(len(self.context["plan_items"]), 3)
        self.assertEqual(self.context["catalog_version"], "w0-catalog-v1")

    def test_synthetic_contract_fixture_is_valid(self):
        result = validate_analysis(copy.deepcopy(self.valid), self.context)
        self.assertEqual(len(result["camera_observations"]), 3)

    def test_live_gate_llm_fixture_is_valid_and_clears_positive_threshold(self):
        result = validate_analysis(load_json(LIVE), self.context)
        thresholds = load_json(THRESHOLDS)
        positive_threshold = thresholds["model_evidence"]["positive_confidence"]
        positive_items = [
            item for item in result["evidence_items"] if item["polarity"] == "positive"
        ]
        uncertain_facts = [
            fact
            for observation in result["camera_observations"]
            for fact in observation["scene_facts"]
            if fact["state"] == "uncertain"
        ]
        self.assertTrue(positive_items)
        self.assertTrue(all(item["confidence"] >= positive_threshold for item in positive_items))
        self.assertTrue(all(item["confidence"] < positive_threshold for item in uncertain_facts))

    def test_unknown_image_reference_is_rejected(self):
        value = copy.deepcopy(self.valid)
        value["evidence_items"][0]["image_id"] = "IMG-UNKNOWN"
        with self.assertRaisesRegex(ContractError, "does not belong"):
            validate_analysis(value, self.context)

    def test_model_cannot_mark_visible_stage_not_observable(self):
        value = copy.deepcopy(self.valid)
        value["stage_evidence"][0]["status"] = "not_observable"
        value["stage_evidence"][0]["evidence_item_ids"] = []
        with self.assertRaisesRegex(ContractError, "cannot mark"):
            validate_analysis(value, self.context)

    def test_duplicate_evidence_id_is_rejected(self):
        value = copy.deepcopy(self.valid)
        value["evidence_items"][1]["evidence_id"] = value["evidence_items"][0]["evidence_id"]
        with self.assertRaisesRegex(ContractError, "duplicate"):
            validate_analysis(value, self.context)

    def test_responses_payload_uses_structured_output_and_images(self):
        config = ProviderConfig(
            provider="test",
            base_url="https://example.test/v1",
            api_key="secret",
            model="openai/gpt-6-luna",
            api_style="responses",
            reasoning_effort="low",
            timeout_seconds=90,
            image_max_edge=1024,
            image_jpeg_quality=75,
            input_price_per_million=0.2,
            output_price_per_million=1.2,
        )
        payload = build_request_payload(
            config,
            self.context,
            load_json(SCHEMA),
            PROMPT.read_text(encoding="utf-8"),
        )
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        images = [block for block in payload["input"][0]["content"] if block["type"] == "input_image"]
        self.assertEqual(len(images), 3)
        self.assertTrue(all(block["image_url"].startswith("data:image/jpeg;base64,") for block in images))
        self.assertNotIn("secret", json.dumps(payload))

    def test_responses_output_is_extracted(self):
        raw = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(self.valid)}],
                }
            ]
        }
        self.assertEqual(extract_normalized_response(raw, "responses"), self.valid)


if __name__ == "__main__":
    unittest.main()
