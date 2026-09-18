import cv2
import numpy as np
import os
from database.database import get_all_face_embeddings
from utils.cv_engine import _get_models

# Configurable recognition threshold for cosine similarity
FACE_RECOGNITION_THRESHOLD = 0.363 

class FaceRecognitionEngine:
    def __init__(self, db_path):
        self.db_path = db_path
        self.enrolled_students = []
        self._load_enrollments()
        
    def _load_enrollments(self):
        """Loads and deserializes enrolled embeddings from the database."""
        raw_enrollments = get_all_face_embeddings(self.db_path, model_name='sface_2021dec')
        for record in raw_enrollments:
            try:
                emb_array = np.frombuffer(record['embedding'], dtype=np.float32).reshape(1, 128)
                self.enrolled_students.append({
                    'user_id': record['user_id'],
                    'student_id': record['student_id'],
                    'student_name': record['student_name'],
                    'feature': emb_array
                })
            except Exception:
                # Silently skip malformed embeddings
                pass

    def process_classroom_image(self, image_bytes):
        """
        Processes a raw image byte array, detects faces, extracts embeddings, 
        and compares them against enrolled students.
        """
        # Edge case: invalid image bytes
        if not image_bytes:
            return self._error_response("Invalid or empty image data")
            
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return self._error_response("Failed to decode image")
            
        try:
            detector, recognizer = _get_models()
        except Exception as e:
            return self._error_response(f"Model loading failure: {str(e)}")
            
        height, width, _ = img.shape
        detector.setInputSize((width, height))
        
        try:
            faces = detector.detect(img)
            faces_data = faces[1] if faces[1] is not None else []
        except Exception as e:
            return self._error_response(f"Detection failed: {str(e)}")
            
        results = []
        recognized_count = 0
        unknown_count = 0
        
        for idx, face in enumerate(faces_data):
            box = face[0:4].astype(np.int32)
            
            # Edge case: extremely small detected face bounding box
            if box[2] < 5 or box[3] < 5:
                continue 
                
            try:
                aligned_face = recognizer.alignCrop(img, face)
                feature = recognizer.feature(aligned_face)
                
                best_match = None
                highest_sim = -1.0
                
                # Compare against all enrolled students
                for student in self.enrolled_students:
                    sim = recognizer.match(feature, student['feature'], cv2.FaceRecognizerSF_FR_COSINE)
                    if sim > highest_sim:
                        highest_sim = sim
                        best_match = student
                
                is_recognized = False
                matched_student_id = None
                matched_student_name = None
                matched_user_id = None
                
                if best_match and highest_sim >= FACE_RECOGNITION_THRESHOLD:
                    is_recognized = True
                    matched_student_id = best_match['student_id']
                    matched_student_name = best_match['student_name']
                    matched_user_id = best_match['user_id']
                    recognized_count += 1
                else:
                    unknown_count += 1
                    
                results.append({
                    "face_index": idx,
                    "bbox": {
                        "x": int(box[0]),
                        "y": int(box[1]),
                        "width": int(box[2]),
                        "height": int(box[3])
                    },
                    "user_id": matched_user_id,
                    "student_id": matched_student_id,
                    "student_name": matched_student_name,
                    "similarity": float(highest_sim),
                    "recognized": is_recognized
                })
                
            except Exception as e:
                unknown_count += 1
                results.append({
                    "face_index": idx,
                    "bbox": {
                        "x": int(box[0]),
                        "y": int(box[1]),
                        "width": int(box[2]),
                        "height": int(box[3])
                    },
                    "user_id": None,
                    "student_id": None,
                    "student_name": None,
                    "similarity": 0.0,
                    "recognized": False,
                    "error": str(e)
                })

        return {
            "success": True,
            "total_detected_faces": len(results),
            "recognized_faces": recognized_count,
            "unknown_faces": unknown_count,
            "results": results
        }
        
    def _error_response(self, message):
        return {
            "success": False,
            "error": message,
            "total_detected_faces": 0,
            "recognized_faces": 0,
            "unknown_faces": 0,
            "results": []
        }
