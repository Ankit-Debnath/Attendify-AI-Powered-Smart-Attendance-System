import cv2
import numpy as np
import os


_detector = None
_recognizer = None

def _get_models():
    global _detector, _recognizer
    if _detector is None or _recognizer is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_dir = os.environ.get('MODEL_DIRECTORY', os.path.join(base_dir, 'models'))
        det_path = os.path.join(model_dir, 'face_detection_yunet_2023mar.onnx')
        rec_path = os.path.join(model_dir, 'face_recognition_sface_2021dec.onnx')

        if not os.path.exists(det_path) or not os.path.exists(rec_path):
            raise FileNotFoundError(f"Model files not found in {model_dir}. Please ensure they are deployed correctly.")

        _detector = cv2.FaceDetectorYN.create(det_path, "", (320, 320), score_threshold=0.6, nms_threshold=0.3, top_k=5000)
        _recognizer = cv2.FaceRecognizerSF.create(rec_path, "")
    return _detector, _recognizer

def extract_single_face_embedding(image_bytes):
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            return {"success": False, "error": "Invalid image format or corrupted file."}

        detector, recognizer = _get_models()
        height, width, _ = img.shape
        detector.setInputSize((width, height))

        faces = detector.detect(img)
        faces_data = faces[1] if faces[1] is not None else []

        num_faces = len(faces_data)

        if num_faces == 0:
            return {"success": False, "error": "No face detected. Please upload a clear photo of your face."}
        elif num_faces > 1:
            return {"success": False, "error": "Multiple faces detected. Please ensure only you are in the photo."}

        face = faces_data[0]

        aligned_face = recognizer.alignCrop(img, face)
        feature = recognizer.feature(aligned_face)

        if feature.shape != (1, 128):
            return {"success": False, "error": "Invalid embedding shape."}

        feature = feature.astype(np.float32)
        if not np.isfinite(feature).all():
            return {"success": False, "error": "Embedding contains invalid values."}

        return {
            "success": True,
            "embedding": feature.tobytes(),
            "model_name": "sface_2021dec"
        }
    except Exception as e:
        return {"success": False, "error": f"Face extraction failed: {str(e)}"}

def validate_and_extract_reference_face(image_bytes):
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            return {"success": False, "error": "Invalid image format or corrupted file."}

        height, width, _ = img.shape

        # 1. Resolution Check
        min_res = int(os.environ.get('MIN_FACE_IMAGE_RESOLUTION', 200))
        if width < min_res or height < min_res:
            return {"success": False, "error": f"Image resolution is too low. Minimum {min_res}x{min_res} required."}

        # 2. Blur Check
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur_val = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_threshold = float(os.environ.get('FACE_BLUR_THRESHOLD', 50.0))
        if blur_val < blur_threshold:
            return {"success": False, "error": "Image is too blurry."}

        # 3. Lighting Check
        mean_brightness = np.mean(gray)
        if mean_brightness < 30:
            return {"success": False, "error": "Image is too dark."}
        if mean_brightness > 230:
            return {"success": False, "error": "Image is overexposed/too bright."}

        detector, recognizer = _get_models()
        detector.setInputSize((width, height))

        faces = detector.detect(img)
        faces_data = faces[1] if faces[1] is not None else []

        num_faces = len(faces_data)

        if num_faces == 0:
            return {"success": False, "error": "No face detected. Please upload an image containing only your face."}
        elif num_faces > 1:
            return {"success": False, "error": "Multiple faces detected. Please upload an image containing only your face."}

        face = faces_data[0]
        box = face[0:4].astype(np.int32)

        # 4. Face Size Check (Face should be at least a certain percentage of the image)
        face_width, face_height = box[2], box[3]
        face_area = face_width * face_height
        img_area = width * height
        min_face_ratio = float(os.environ.get('MIN_FACE_AREA_RATIO', 0.05))

        if (face_area / img_area) < min_face_ratio:
            return {"success": False, "error": "Detected face is too small. Please ensure your face is clearly visible."}

        aligned_face = recognizer.alignCrop(img, face)
        feature = recognizer.feature(aligned_face)

        if feature.shape != (1, 128):
            return {"success": False, "error": "Invalid embedding shape."}

        feature = feature.astype(np.float32)
        if not np.isfinite(feature).all():
            return {"success": False, "error": "Embedding contains invalid values."}

        return {
            "success": True,
            "embedding": feature.tobytes(),
            "model_name": "sface_2021dec",
            "quality": "Good"
        }
    except Exception as e:
        return {"success": False, "error": f"Face processing failed: {str(e)}"}


def process_student_attendance(image_bytes, required_pose, enrolled_references, threshold=0.363):
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "error": "Invalid image format."}

        detector, recognizer = _get_models()
        height, width, _ = img.shape
        detector.setInputSize((width, height))

        faces = detector.detect(img)
        faces_data = faces[1] if faces[1] is not None else []

        if len(faces_data) == 0:
            return {"success": False, "error": "No face detected."}
        elif len(faces_data) > 1:
            return {"success": False, "error": "Multiple faces detected. Please ensure only you are in the frame."}

        face = faces_data[0]

        # Liveness check
        rx, ry = face[4], face[5]
        lx, ly = face[6], face[7]
        nx, ny = face[8], face[9]

        eye_dist = lx - rx # lx is usually > rx in YuNet
        if eye_dist <= 0:
            eye_dist = 1

        nose_pos = (nx - rx) / eye_dist

        liveness_passed = False
        if required_pose == 'straight':
            liveness_passed = (0.35 <= nose_pos <= 0.65)
        elif required_pose == 'left':
            liveness_passed = (nose_pos > 0.55)
        elif required_pose == 'right':
            liveness_passed = (nose_pos < 0.45)

        # Extract embedding
        aligned_face = recognizer.alignCrop(img, face)
        feature = recognizer.feature(aligned_face)
        feature = feature.astype(np.float32)

        # Match with references
        highest_sim = -1.0
        for ref_emb_bytes in enrolled_references:
            ref_emb = np.frombuffer(ref_emb_bytes, dtype=np.float32).reshape(1, 128)
            sim = recognizer.match(feature, ref_emb, cv2.FaceRecognizerSF_FR_COSINE)
            if sim > highest_sim:
                highest_sim = sim

        face_match_passed = (highest_sim >= threshold)

        if not face_match_passed:
            status = 'NEEDS_CONFIRMATION'
            reason = 'Face identity confidence was insufficient.'
        elif not liveness_passed:
            status = 'NEEDS_CONFIRMATION'
            reason = 'Liveness verification was unsuccessful.'
        else:
            status = 'PRESENT'
            reason = 'Successfully verified.'

        return {
            "success": True,
            "status": status,
            "reason": reason,
            "similarity": float(highest_sim),
            "liveness_passed": liveness_passed,
            "face_passed": face_match_passed
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
