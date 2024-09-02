# detect.py
from typing import List
from ultralytics import YOLO
import cv2
import numpy as np
from threading import Semaphore
from loguru import logger

from models import LabelBox

# YOLO model and semaphore configuration
class DetectConfig:
    model_path: str = "yolov10b-doclaynet.pt"
    max_connections: int = 10

conf = DetectConfig()
model = YOLO(conf.model_path)
semaphore = Semaphore(conf.max_connections)

def detect_layout(image_data: bytes) -> List[LabelBox]:
    """
    Perform object detection using the YOLO model.

    Args:
        image_data: The image data in bytes format.

    Returns:
        A list of detected LabelBox objects.
    """
    logger.info("Starting object detection...")

    with semaphore:
        image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            logger.error("Invalid image")
            return []

        result = model.predict(image, verbose=False)[0]
    
    height = result.orig_shape[0]
    width = result.orig_shape[1]
    label_boxes = []

    for label, box in zip(result.boxes.cls.tolist(), result.boxes.xyxyn.tolist()):
        label_boxes.append(
            LabelBox(
                label=result.names[int(label)],
                box=[box[0] * width, box[1] * height, box[2] * width, box[3] * height],
            )
        )

    logger.info(f"Detected {len(label_boxes)} objects, Image size: {width}x{height}")
    
    return label_boxes

