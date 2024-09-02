from typing import List, Dict, Tuple
from loguru import logger
from models import LabelBox, TextRect

# Define the first echelon layout types
FIRST_ECHELON_TYPES = {"Picture", "Table", "Page-header", "Page-footer", "Footnote"}

# Define the overlap threshold and within a line threshold
OVERLAP_THRESHOLD = 0.98
LINE_OVERLAP_THRESHOLD = 0.98

def reclassify_layout(file_id: str, page_number: int, comparison_results: Dict, layout_data: Dict) -> List[LabelBox]:
    inside_rects = comparison_results[(file_id, page_number)]["inside"]
    outside_rects = comparison_results[(file_id, page_number)]["outside"]
    layout_rects = layout_data[file_id][page_number]

    logger.info(f"Reclassifying layout for file_id {file_id}, page_number {page_number}")

    # Step 1: Handle first echelon layout types
    layout_rects = handle_first_echelon(layout_rects, inside_rects)

    # Step 2: Split layout rects based on font analysis
    font_stats = calculate_font_statistics(inside_rects)
    layout_rects = split_rects_based_on_fonts(layout_rects, inside_rects, font_stats)

    # Step 3: Combine overlapping rects within a line
    layout_rects = combine_rects_within_line(layout_rects)
    
    # Step 4: Handle rects inside other rects
    # layout_rects = handle_rects_inside_other_rects(layout_rects)

    layout_rects = [rect for rect in layout_rects if validate_rectangle(rect)]
    logger.info(f"Reclassified layout contains {len(layout_rects)} rects.")
    return layout_rects

def handle_first_echelon(layout_rects: List[LabelBox], inside_rects: List[TextRect]) -> List[LabelBox]:
    adjusted_rects = []

    while layout_rects:
        rect = layout_rects.pop(0)  # Remove the first element
        if rect.label in FIRST_ECHELON_TYPES:
            # Check for any rects inside this first echelon rect
            rect, new_rects = handle_inside_rects(rect, layout_rects)
            # Add new rects generated from splitting, if any
            layout_rects.extend(new_rects)
            # Adjust any overlapping rects
            if rect is not None:
                rect = adjust_overlapping_rects(rect, layout_rects)
                adjusted_rects.append(rect)

    return adjusted_rects

def handle_inside_rects(rect: LabelBox, layout_rects: List[LabelBox]) -> Tuple[LabelBox, List[LabelBox]]:
    rects_to_remove = []
    new_rects = []

    for other_rect in layout_rects:
        if is_inside(rect.box, other_rect.box):
            logger.debug(f"Rect {other_rect.box} is inside {rect.box}, removing it.")
            rects_to_remove.append(other_rect)
        elif is_inside(other_rect.box, rect.box):
            logger.debug(f"Rect {rect.box} contains {other_rect.box}, splitting it.")
            split_results = split_rect(rect, other_rect)
            new_rects.extend(split_results)

    for rect_to_remove in rects_to_remove:
        layout_rects.remove(rect_to_remove)

    return rect, new_rects

def handle_rects_inside_other_rects(layout_rects: List[LabelBox]) -> List[LabelBox]:
    """
    Handle rectangles that are inside other rectangles.
    This function ensures that any rectangles fully or partially inside another rectangle are processed accordingly.
    """
    adjusted_rects = []
    while layout_rects:
        rect = layout_rects.pop(0)  # Take the first rect
        contained_in_other_rect = False

        for other_rect in layout_rects:
            if is_inside(rect.box, other_rect.box):
                logger.debug(f"Rect {rect.box} is inside {other_rect.box}, adjusting it.")
                # The rect is inside another rect, so we process it
                adjusted_rects.extend(split_rect(other_rect, rect))
                contained_in_other_rect = True
                break  # Break after handling to avoid redundant checks

        if not contained_in_other_rect:
            adjusted_rects.append(rect)
    
    return adjusted_rects

def adjust_overlapping_rects(rect: LabelBox, layout_rects: List[LabelBox]) -> LabelBox:
    for i in range(len(layout_rects)):
        other_rect = layout_rects[i]
        if rects_overlap(rect.box, other_rect.box):
            if rect.label in FIRST_ECHELON_TYPES:
                logger.debug(f"Adjusting rect {other_rect.box} to fit around {rect.box}.")
                layout_rects[i].box = adjust_rect(other_rect.box, rect.box)
            else:
                logger.debug(f"Adjusting rect {rect.box} to fit around {other_rect.box}.")
                rect.box = adjust_rect(rect.box, other_rect.box)

    return rect

def is_inside(inner_box: List[float], outer_box: List[float]) -> bool:
    inner_area = (inner_box[2] - inner_box[0]) * (inner_box[3] - inner_box[1])
    intersection_area = get_intersection_area(inner_box, outer_box)
    return intersection_area / inner_area >= OVERLAP_THRESHOLD

def adjust_rect(smaller_box: List[float], larger_box: List[float]) -> List[float]:
    logger.debug(f"Adjusting rect {smaller_box} to avoid overlap with {larger_box}.")
    if larger_box[1] <= smaller_box[1] <= larger_box[3]:  # Vertical overlap
        smaller_box[1] = larger_box[3] + 1
    if larger_box[0] <= smaller_box[0] <= larger_box[2]:  # Horizontal overlap
        smaller_box[0] = larger_box[2] + 1
    return smaller_box

def split_rect(larger_rect: LabelBox, smaller_rect: LabelBox) -> List[LabelBox]:
    new_rects = []
    if smaller_rect.box[0] > larger_rect.box[0]:
        new_rects.append(LabelBox(label=larger_rect.label, box=[larger_rect.box[0], larger_rect.box[1], smaller_rect.box[0] - 1, larger_rect.box[3]]))
    if smaller_rect.box[2] < larger_rect.box[2]:
        new_rects.append(LabelBox(label=larger_rect.label, box=[smaller_rect.box[2] + 1, larger_rect.box[1], larger_rect.box[2], larger_rect.box[3]]))
    if smaller_rect.box[1] > larger_rect.box[1]:
        new_rects.append(LabelBox(label=larger_rect.label, box=[max(larger_rect.box[0], smaller_rect.box[0]), larger_rect.box[1], min(larger_rect.box[2], smaller_rect.box[2]), smaller_rect.box[1] - 1]))
    if smaller_rect.box[3] < larger_rect.box[3]:
        new_rects.append(LabelBox(label=larger_rect.label, box=[max(larger_rect.box[0], smaller_rect.box[0]), smaller_rect.box[3] + 1, min(larger_rect.box[2], smaller_rect.box[2]), larger_rect.box[3]]))

    return new_rects

def calculate_font_statistics(rects: List[TextRect]) -> Dict[Tuple[str, float], int]:
    font_stats = {}
    for rect in rects:
        font_key = (rect.fontname, rect.size)
        if font_key not in font_stats:
            font_stats[font_key] = 0
        font_stats[font_key] += 1
    logger.debug(f"Font statistics calculated: {font_stats}")
    return font_stats

def split_rects_based_on_fonts(layout_rects: List[LabelBox], inside_rects: List[TextRect], font_stats: Dict[Tuple[str, float], int]) -> List[LabelBox]:
    adjusted_rects = []
    seen_rects = set()  # Track already split rectangles to avoid infinite loops

    while layout_rects:
        rect = layout_rects.pop(0)  # Remove the first element
        rect_key = tuple(rect.box)
        
        if rect_key in seen_rects:
            adjusted_rects.append(rect)
            continue
        
        if needs_split_based_on_fonts(rect, inside_rects, font_stats):
            split_rects = split_rect_based_on_fonts(rect, inside_rects)
            logger.debug(f"Splitting rect {rect.box} based on font analysis.")
            for split_rect in split_rects:
                logger.debug(f"Splited rect {split_rect.box}")
            layout_rects.extend(split_rects)
            seen_rects.add(rect_key)
        else:
            adjusted_rects.append(rect)
            seen_rects.add(rect_key)
    
    return adjusted_rects

def needs_split_based_on_fonts(rect: LabelBox, inside_rects: List[TextRect], font_stats: Dict[Tuple[str, float], int]) -> bool:
    fonts_in_rect = [(r.fontname, r.size) for r in inside_rects if r.x0 >= rect.box[0] and r.x1 <= rect.box[2] and r.y0 >= rect.box[1] and r.y1 <= rect.box[3]]
    for font, size in fonts_in_rect:
        if font_stats.get((font, size), 0) < len(fonts_in_rect) * 0.5:
            logger.debug(f"Rect {rect} has a diverse font distribution and may need to be split.")
            return True
    
    logger.debug(f"Rect {rect} does not need to be split based on font analysis.")
    return False

def split_rect_based_on_fonts(rect: LabelBox, inside_rects: List[TextRect]) -> List[LabelBox]:
    split_rects = []
    fonts_in_rect = [(r.fontname, r.size) for r in inside_rects if r.x0 >= rect.box[0] and r.x1 <= rect.box[2] and r.y0 >= rect.box[1] and r.y1 <= rect.box[3]]
    for font in set(fonts_in_rect):
        matching_rects = [r for r in inside_rects if r.fontname == font[0] and r.size == font[1]]
        if matching_rects:
            x0 = min(r.x0 for r in matching_rects)
            y0 = min(r.y0 for r in matching_rects)
            x1 = max(r.x1 for r in matching_rects)
            y1 = max(r.y1 for r in matching_rects)
            new_rect = LabelBox(label=rect.label, box=[x0, y0, x1, y1])
            
            # Ensure the new rect is meaningfully different from the original to avoid re-triggering the split
            if rect.box != new_rect.box:
                split_rects.append(new_rect)

    return split_rects

def combine_rects_within_line(layout_rects: List[LabelBox]) -> List[LabelBox]:
    adjusted_rects = []
    while layout_rects:
        rect = layout_rects.pop(0)  # Remove the first element
        combined = False
        for i, existing_rect in enumerate(adjusted_rects):
            if within_same_line(rect.box, existing_rect.box):
                logger.debug(f"Combining rect {rect.box} with {existing_rect.box} within the same line.")
                adjusted_rects[i] = combine_rects_update_one(existing_rect, rect)
                combined = True
                break
        if not combined:
            adjusted_rects.append(rect)
    return adjusted_rects

def combine_rects_update_one(rect1: LabelBox, rect2: LabelBox) -> LabelBox:
    logger.debug(f"Combining rect {rect1.box} and {rect2.box} by updating {rect1.label}.")
    
    # Update rect1 to encompass rect2
    rect1.box = [
        min(rect1.box[0], rect2.box[0]),
        min(rect1.box[1], rect2.box[1]),
        max(rect1.box[2], rect2.box[2]),
        max(rect1.box[3], rect2.box[3])
    ]
    
    return rect1

def within_same_line(box1: List[float], box2: List[float]) -> bool:
    horizontal_overlap = get_intersection_area([box1[0], 0, box1[2], 0], [box2[0], 0, box2[2], 0]) / min(box1[2] - box1[0], box2[2] - box2[0])
    return horizontal_overlap >= LINE_OVERLAP_THRESHOLD

def get_intersection_area(rect1: List[float], rect2: List[float]) -> float:
    x_left = max(rect1[0], rect2[0])
    y_top = max(rect1[1], rect2[1])
    x_right = min(rect1[2], rect2[2])
    y_bottom = min(rect1[3], rect2[3])
    if x_right < x_left or y_bottom < y_top:
        return 0.0
    return (x_right - x_left) * (y_bottom - y_top)

def rects_overlap(rect1: List[float], rect2: List[float]) -> bool:
    return not (rect1[2] <= rect2[0] or rect1[0] >= rect2[2] or rect1[3] <= rect2[1] or rect1[1] >= rect2[3])

def validate_rectangle(rect: LabelBox) -> bool:
    width = rect.box[2] - rect.box[0]
    height = rect.box[3] - rect.box[1]
    return width > 0 and height > 0
