import os
import urllib.request
import sys

MODELS = {
    'face_detection_yunet_2023mar.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
    'face_recognition_sface_2021dec.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'
}

def download_models():
    models_dir = 'models'
    if not os.path.exists(models_dir):
        os.makedirs(models_dir)
        
    for filename, url in MODELS.items():
        model_path = os.path.join(models_dir, filename)
        
        if os.path.exists(model_path):
            if os.path.getsize(model_path) > 0:
                print(f"Model {filename} already exists and is non-empty. Skipping.")
                continue
            else:
                print(f"Model {filename} exists but is empty. Re-downloading...")
                os.remove(model_path)
                
        print(f"Downloading {url} to {model_path}...")
        try:
            urllib.request.urlretrieve(url, model_path)
            if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
                print(f"Download complete: {filename}")
            else:
                print(f"Error: Downloaded file {filename} is empty or missing.")
                if os.path.exists(model_path):
                    os.remove(model_path)
                sys.exit(1)
        except Exception as e:
            print(f"Failed to download model {filename}: {e}")
            if os.path.exists(model_path):
                os.remove(model_path)
            sys.exit(1)

if __name__ == '__main__':
    download_models()
