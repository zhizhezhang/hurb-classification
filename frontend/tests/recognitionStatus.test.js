import test from 'node:test'
import assert from 'node:assert/strict'
import { isRecognitionSuccessful, RECOGNITION_CONFIDENCE_THRESHOLD } from '../src/utils/recognitionStatus.js'

test('raw Top-1 probability uses an inclusive 60% threshold', () => {
  assert.equal(RECOGNITION_CONFIDENCE_THRESHOLD, 0.6)
  for (const [probability, expected] of [
    [0.5999, false],
    [0.6, true],
    [0.6001, true],
    [0.1403, false],
    [0.59999, false],
  ]) {
    assert.equal(isRecognitionSuccessful(probability), expected, `${probability}`)
  }
})

test('existing history records use their persisted confidence without changing the record', () => {
  const low = { predicted_class: '苍耳子', confidence: 0.1403, top3: [{ class_name: '苍耳子', probability: 0.1403 }] }
  const high = { predicted_class: '人参', confidence: 0.8001, top3: [{ class_name: '人参', probability: 0.8001 }] }
  assert.equal(isRecognitionSuccessful(low.confidence), false)
  assert.equal(isRecognitionSuccessful(high.confidence), true)
  assert.equal(low.predicted_class, '苍耳子')
  assert.equal(low.top3[0].probability, 0.1403)
})
