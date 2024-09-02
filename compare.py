# compare.py
from models import TextRect
from fastapi import HTTPException
from loguru import logger
from pathlib import Path
import json

def convert_pdf_to_image_coords(x0, y0, x1, y1, scale_x, scale_y):
    return (
        x0 * scale_x,
        y0 * scale_y,
        x1 * scale_x,
        y1 * scale_y
    )

def compare_layout(file_id: str, page_number: int, layout_data: dict, text_data: dict, scaling_factors: dict, output_dir: Path):
    if file_id not in layout_data or file_id not in text_data:
        logger.error(f"File ID {file_id} not found in layout_data or text_data.")
        raise HTTPException(status_code=400, detail="No layout or text data available for this file.")

    layout_rects = layout_data[file_id].get(page_number, [])
    text_rects = text_data[file_id].get(page_number, [])

    scale_x, scale_y = scaling_factors.get((file_id, page_number), (1, 1))

    inside = []
    outside = []

    def get_intersection_area(rect1, rect2):
        x_left = max(rect1[0], rect2[0])
        y_top = max(rect1[1], rect2[1])
        x_right = min(rect1[2], rect2[2])
        y_bottom = min(rect1[3], rect2[3])

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        return (x_right - x_left) * (y_bottom - y_top)

    def get_area(rect):
        return (rect[2] - rect[0]) * (rect[3] - rect[1])

    def is_significantly_inside(text_rect, layout_rects, threshold=0.5):
        text_area = get_area(text_rect)
        for layout_rect in layout_rects:
            intersection_area = get_intersection_area(text_rect, layout_rect)
            if intersection_area > 0 and (intersection_area / text_area) >= threshold:
                return True
        return False

    for text_rect in text_rects:
        converted_rect = convert_pdf_to_image_coords(
            text_rect.x0, text_rect.y0, text_rect.x1, text_rect.y1, scale_x, scale_y
        )

        scaled_text_rect = TextRect(
            x0=converted_rect[0],
            y0=converted_rect[1],
            x1=converted_rect[2],
            y1=converted_rect[3],
            text=text_rect.text,
            fontname=text_rect.fontname,
            size=text_rect.size
        )

        if is_significantly_inside(converted_rect, [layout.box for layout in layout_rects], 0.3):
            inside.append(scaled_text_rect)
        else:
            outside.append(scaled_text_rect)

    # Return the comparison result instead of directly updating comparison_results
    comparison_result = {"inside": inside, "outside": outside}

    inside_file = output_dir / f"{file_id}_page_{page_number}_inside.json"
    outside_file = output_dir / f"{file_id}_page_{page_number}_outside.json"

    with inside_file.open("w", encoding="utf-8") as f:
        json.dump([rect.dict() for rect in inside], f, ensure_ascii=False, indent=4)

    with outside_file.open("w", encoding="utf-8") as f:
        json.dump([rect.dict() for rect in outside], f, ensure_ascii=False, indent=4)

    return comparison_result
