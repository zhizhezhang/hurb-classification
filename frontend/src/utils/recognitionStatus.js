export const RECOGNITION_CONFIDENCE_THRESHOLD = 0.6

export const LOW_CONFIDENCE_MESSAGE = '当前图片未达到识别置信度要求，请尝试上传更清晰的中药材图片。'

export function isRecognitionSuccessful(confidence) {
  return typeof confidence === 'number'
    && Number.isFinite(confidence)
    && confidence >= RECOGNITION_CONFIDENCE_THRESHOLD
}
