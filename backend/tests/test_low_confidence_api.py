"""Keep raw prediction data available at every confidence boundary."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend.api.history import router as history_router
from backend.api.predict import router as predict_router
from backend.core.config import PROJECT_ROOT
from backend.services.history_service import HistoryStore


MAPPING = json.loads((PROJECT_ROOT / 'reports/data_split/class_to_idx.json').read_text(encoding='utf-8'))


class LowConfidenceApiTests(unittest.TestCase):
    def test_predict_and_history_preserve_raw_probabilities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = HistoryStore(root / 'history.db', root / 'uploads', MAPPING)
            store.initialize()
            app = FastAPI()
            app.include_router(predict_router)
            app.include_router(history_router)
            app.state.model = object()
            app.state.history_store = store
            client = TestClient(app)
            image = io.BytesIO()
            Image.new('RGB', (12, 8)).save(image, format='PNG')

            for confidence in (0.5999, 0.6, 0.6001, 0.1403):
                with self.subTest(confidence=confidence):
                    top3 = [
                        {'class_name': '苍耳子', 'probability': confidence},
                        {'class_name': '人参', 'probability': 0.13},
                        {'class_name': '黄芪', 'probability': 0.12},
                    ]
                    simulated = {
                        'predicted_class': '苍耳子', 'confidence': confidence,
                        'top3': top3, 'inference_time_ms': 1.0,
                        'model_version': 'simulated_run02',
                    }
                    with patch('backend.api.predict.infer_image', return_value=simulated):
                        response = client.post('/api/predict', files={
                            'file': ('sample.png', image.getvalue(), 'image/png'),
                        })
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()['data']
                    self.assertEqual(result['confidence'], confidence)
                    self.assertEqual(result['top3'], top3)
                    saved = client.get(f"/api/history/{result['record_id']}")
                    self.assertEqual(saved.status_code, 200)
                    self.assertEqual(saved.json()['data']['confidence'], confidence)
                    self.assertEqual(saved.json()['data']['predicted_class'], '苍耳子')
                    self.assertEqual(saved.json()['data']['top3'], top3)

            page = client.get('/api/history').json()['data']
            self.assertEqual(page['total'], 4)
            self.assertEqual({item['confidence'] for item in page['items']},
                             {0.5999, 0.6, 0.6001, 0.1403})


if __name__ == '__main__':
    unittest.main()
