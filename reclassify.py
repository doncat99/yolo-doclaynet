from collections import defaultdict
from typing import List, Dict, Tuple

from loguru import logger

from models import LabelBox, TextRect

# Define the first echelon layout types
FIRST_ECHELON_TYPES = {"Picture", "Table", "Page-header", "Page-footer", "Footnote"}

LABEL_PRIORITY = {
    "Title": 4,
    "Section-header": 3,
    "Text": 2,
    "Footnote": 1
}

# Define the overlap threshold and within a line threshold
INSIDE_THRESHOLD = 0.98
OVERLAP_THRESHOLD = 0.05
LINE_OVERLAP_THRESHOLD = 0.98

def validate_rectangle(rect: LabelBox) -> bool:
    """Ensure the rectangle has valid dimensions."""
    width = rect.box[2] - rect.box[0]
    height = rect.box[3] - rect.box[1]
    return width > 0 and height > 0

def is_inside(inner_box: List[float], outer_box: List[float], threshold=INSIDE_THRESHOLD) -> bool:
    """Check if inner_box is inside outer_box based on the area."""
    x_overlap = max(0, min(inner_box[2], outer_box[2]) - max(inner_box[0], outer_box[0]))
    y_overlap = max(0, min(inner_box[3], outer_box[3]) - max(inner_box[1], outer_box[1]))
    overlap_area = x_overlap * y_overlap
    inner_area = (inner_box[2] - inner_box[0]) * (inner_box[3] - inner_box[1])
    return overlap_area / inner_area >= threshold

def within_same_line(box1: List[float], box2: List[float], threshold=LINE_OVERLAP_THRESHOLD) -> bool:
    """Check if two rectangles are within the same horizontal line based on vertical overlap."""
    
    # Calculate the vertical overlap
    y_overlap = max(0, min(box1[3], box2[3]) - max(box1[1], box2[1]))
    
    # Calculate the height of the two rectangles
    min_height = min(box1[3] - box1[1], box2[3] - box2[1])
    
    # Calculate the vertical overlap ratio
    vertical_overlap_ratio = y_overlap / min_height if min_height > 0 else 0
    
    # Return True if the vertical overlap ratio meets or exceeds the threshold
    return vertical_overlap_ratio >= threshold


def adjust_rect(rect: LabelBox, first_echelon_rect: LabelBox) -> List[LabelBox]:
    """Adjust a rect to not overlap with a first echelon rect."""
    if is_inside(rect.box, first_echelon_rect.box):
        logger.info(f"Reclassified other_rects inside first_echelon_rect.")
        return []  # Delete the rect
    elif is_inside(first_echelon_rect.box, rect.box):
        logger.info(f"Reclassified first_echelon_rect inside other_rects.")
        # Split the rect into parts that are outside the first echelon rect
        split_rects = []
        if rect.box[1] < first_echelon_rect.box[1]:
            split_rects.append(LabelBox(label=rect.label, box=[rect.box[0], rect.box[1], rect.box[2], first_echelon_rect.box[1] - 1]))
        if rect.box[3] > first_echelon_rect.box[3]:
            split_rects.append(LabelBox(label=rect.label, box=[rect.box[0], first_echelon_rect.box[3] + 1, rect.box[2], rect.box[3]]))
        return split_rects
    else:
        # if within_same_line(rect.box, first_echelon_rect.box):
        #     logger.info(f"Reclassified first_echelon_rect and other_rects in the same line.")
        #     logger.info(f"Reclassified first_echelon_rect {first_echelon_rect.label}, {first_echelon_rect.box}.")
        #     logger.info(f"Reclassified other_rect {rect.label}, {rect.box}.")
        #     if rect.box[0] < first_echelon_rect.box[0]:
        #         rect.box[2] = first_echelon_rect.box[0] - 1
        #     else:
        #         rect.box[0] = first_echelon_rect.box[2] + 1
        return [rect]


def reclassify_layout(file_id: str, page_number: int, comparison_results: Dict, layout_data: Dict) -> List[LabelBox]:
    inside_rects = comparison_results[(file_id, page_number)]["inside"]
    outside_rects = comparison_results[(file_id, page_number)]["outside"]
    layout_rects = layout_data[file_id][page_number]

    logger.info(f"Reclassifying layout for file_id {file_id}, page_number {page_number}")

    # Step 1: Handle first echelon layout types
    processed_rects, first_echelon_rects = handle_first_echelon_rects(layout_rects)

    # Step 2: Handle rects inside other rects
    processed_rects = handle_rects_inside_other_rects(processed_rects)
    
    # Step 3: Handle rects inside other rects
    processed_rects = handle_rects_overlap_other_rects(processed_rects)

    # Step 4: Combine overlapping rects within a line
    processed_rects = combine_rects_within_line(processed_rects)
    
    # Step 5: Split layout rects based on font analysis
    font_stats = calculate_font_statistics(inside_rects, processed_rects)
    processed_rects = split_rects_based_on_fonts(processed_rects, inside_rects, font_stats)

    # Step 6: Validate and return the list of rectangles
    processed_rects = [rect for rect in processed_rects if validate_rectangle(rect)]
    processed_rects.extend(first_echelon_rects)
    
    # Step 7: Regroup text rects outside from processed rects
    processed_rects = regroup_outside_text(outside_rects, processed_rects, font_stats)
    
    logger.info(f"Reclassified layout contains {len(processed_rects)} rects.")
    return processed_rects

def handle_first_echelon_rects(layout_rects: List[LabelBox]) -> List[LabelBox]:
    first_echelon_rects = [rect for rect in layout_rects if rect.label in FIRST_ECHELON_TYPES]
    other_rects = [rect for rect in layout_rects if rect.label not in FIRST_ECHELON_TYPES]

    logger.info(f"Reclassified first_echelon_rects contains {len(first_echelon_rects)} rects.")
    logger.info(f"Reclassified other_rects contains {len(other_rects)} rects.")

    processed_rects = []
    for rect in other_rects:
        for first_echelon_rect in first_echelon_rects:
            adjusted_rects = adjust_rect(rect, first_echelon_rect)
            if not adjusted_rects:
                break  # The rect was deleted
            rect = adjusted_rects[0]  # Continue processing the adjusted rect
        else:
            processed_rects.append(rect)
    
    return processed_rects, first_echelon_rects

def handle_rects_inside_other_rects(layout_rects: List[LabelBox]) -> List[LabelBox]:
    """
    Handle rectangles that are inside other rectangles.
    This function deletes any rectangles that are fully inside another rectangle.
    """
    adjusted_rects = []
    
    while layout_rects:
        rect = layout_rects.pop(0)  # Take the first rect
        contained_in_other_rect = False

        for other_rect in layout_rects:
            if is_inside(rect.box, other_rect.box):
                logger.debug(f"Rect {rect.box} is inside {other_rect.box}, deleting it.")
                contained_in_other_rect = True
                break  # Break after finding the rect is inside another to avoid redundant checks

        if not contained_in_other_rect:
            adjusted_rects.append(rect)
    
    return adjusted_rects

def handle_rects_overlap_other_rects(layout_rects: List[LabelBox]) -> List[LabelBox]:
    """
    Handle rectangles that overlap with other rectangles.
    This function adjusts rectangles that overlap with each other to eliminate overlap.
    """
    adjusted_rects = []

    while layout_rects:
        rect = layout_rects.pop(0)  # Take the first rect
        i = 0
        while i < len(layout_rects):
            other_rect = layout_rects[i]
            if rects_overlap(rect.box, other_rect.box):
                logger.debug(f"Rect {rect.box} overlaps with {other_rect.box}, adjusting them.")

                # Determine if the overlap is primarily vertical or horizontal
                vertical_overlap = min(rect.box[3], other_rect.box[3]) - max(rect.box[1], other_rect.box[1])
                horizontal_overlap = min(rect.box[2], other_rect.box[2]) - max(rect.box[0], other_rect.box[0])

                if vertical_overlap > horizontal_overlap:
                    logger.debug(f"Primarily vertical overlap")
                    # Primarily vertical overlap
                    if rect.box[0] < other_rect.box[0]:
                        rect.box[2] = other_rect.box[0]  # Adjust right of rect to left of other_rect
                    else:
                        other_rect.box[2] = rect.box[0]  # Adjust right of other_rect to left of rect
                else:
                    logger.debug(f"Primarily horizontal overlap")
                    # Primarily horizontal overlap
                    if rect.box[1] < other_rect.box[1]:
                        rect.box[3] = other_rect.box[1]  # Adjust bottom of rect to top of other_rect
                    else:
                        other_rect.box[3] = rect.box[1]  # Adjust bottom of other_rect to top of rect

                # Update the modified other_rect in the list
                layout_rects[i] = other_rect
                break  # Stop after resolving the overlap with one rectangle
            else:
                i += 1

        # After adjustment, both rects need to be added to the final list
        adjusted_rects.append(rect)
    
    # Add any remaining rectangles that didn't require adjustment
    adjusted_rects.extend(layout_rects)
    return adjusted_rects


# def rects_overlap(rect1: List[float], rect2: List[float]) -> bool:
#     """
#     Check if two rectangles overlap.
#     """
#     return not (rect1[2] <= rect2[0] or rect1[0] >= rect2[2] or rect1[3] <= rect2[1] or rect1[1] >= rect2[3])

def rects_overlap(rect1: List[float], rect2: List[float], threshold: float = OVERLAP_THRESHOLD) -> bool:
    """
    Check if two rectangles overlap with a given threshold.
    
    Args:
        rect1: The first rectangle [x0, y0, x1, y1].
        rect2: The second rectangle [x0, y0, x1, y1].
        threshold: The overlap threshold (default is 0.98).

    Returns:
        True if the rectangles overlap by at least the threshold percentage of the smaller rectangle's area.
    """
    # Calculate overlap dimensions
    x_overlap = max(0, min(rect1[2], rect2[2]) - max(rect1[0], rect2[0]))
    y_overlap = max(0, min(rect1[3], rect2[3]) - max(rect1[1], rect2[1]))
    overlap_area = x_overlap * y_overlap

    # Calculate areas of the rectangles
    rect1_area = (rect1[2] - rect1[0]) * (rect1[3] - rect1[1])
    rect2_area = (rect2[2] - rect2[0]) * (rect2[3] - rect2[1])

    # Calculate the smaller rectangle area
    smaller_rect_area = min(rect1_area, rect2_area)

    # Determine if the overlap meets the threshold
    return overlap_area / smaller_rect_area >= threshold


def calculate_font_statistics(inside_rects: List[TextRect], layout_rects: List[LabelBox]) -> Dict[Tuple[str, float], str]:
    """
    Calculate font statistics for the text rects and map each font to the most common label.

    Args:
        inside_rects: List of TextRect objects containing the text with font information.
        layout_rects: List of LabelBox objects containing the labels.

    Returns:
        A dictionary mapping (font name, font size) to the most common label within that font group.
    """
    font_label_counts = defaultdict(lambda: defaultdict(int))

    for rect in inside_rects:
        font_key = (rect.fontname, rect.size)
        
        # Find the corresponding LabelBox for the current TextRect
        for label_box in layout_rects:
            if (label_box.box[0] <= rect.x0 <= label_box.box[2]) and \
               (label_box.box[1] <= rect.y0 <= label_box.box[3]):
                font_label_counts[font_key][label_box.label] += 1
                break

    # Create a map from font characteristics to the most common label
    font_to_label_map = {}
    for font_key, label_counts in font_label_counts.items():
        most_common_label = max(label_counts, key=label_counts.get)
        font_to_label_map[font_key] = most_common_label

    return font_to_label_map

def split_rects_based_on_fonts(layout_rects: List[LabelBox], inside_rects: List[TextRect], font_to_label_map: Dict[Tuple[str, float], str]) -> List[LabelBox]:
    adjusted_rects = []
    seen_rects = set()  # Track already split rectangles to avoid infinite loops

    while layout_rects:
        rect = layout_rects.pop(0)  # Remove the first element
        rect_key = tuple(rect.box)
        
        if rect_key in seen_rects:
            adjusted_rects.append(rect)
            continue
        
        if needs_split_based_on_fonts(rect, inside_rects, font_to_label_map):
            logger.info(f"Reclassified needs_split_based_on_fonts {rect.box}")
            split_rects = split_rect_based_on_fonts(rect, inside_rects, font_to_label_map)
            logger.debug(f"Splitting rect {rect.box} based on font analysis.")
            for split_rect in split_rects:
                logger.debug(f"Splited rect {split_rect.box}")
            layout_rects.extend(split_rects)
            seen_rects.add(rect_key)
        else:
            adjusted_rects.append(rect)
            seen_rects.add(rect_key)
    
    return adjusted_rects

def needs_split_based_on_fonts(rect: LabelBox, inside_rects: List[TextRect], font_to_label_map: Dict[Tuple[str, float], str]) -> bool:
    """
    Determine if a rect needs to be split based on font analysis.

    Args:
        rect: The LabelBox to be evaluated.
        inside_rects: List of TextRect objects within the current LabelBox.
        font_to_label_map: A dictionary mapping (font name, font size) to the corresponding label.

    Returns:
        True if the rect needs to be split based on font analysis, False otherwise.
    """
    fonts_in_rect = [(r.fontname, r.size) for r in inside_rects if r.x0 >= rect.box[0] and r.x1 <= rect.box[2] and r.y0 >= rect.box[1] and r.y1 <= rect.box[3]]
    logger.debug(f"Fonts in Rect {fonts_in_rect}")
    distinct_labels = set(font_to_label_map.get((font, size), rect.label) for font, size in fonts_in_rect)
    
    if len(distinct_labels) > 1:
        logger.debug(f"Rect {rect} has multiple distinct labels ({distinct_labels}) based on font distribution and may need to be split.")
        return True
    
    logger.debug(f"Rect {rect} does not need to be split based on font analysis.")
    return False

def split_rect_based_on_fonts(rect: LabelBox, inside_rects: List[TextRect], font_to_label_map: Dict[Tuple[str, float], str]) -> List[LabelBox]:
    split_rects = []
    fonts_in_rect = [(r.fontname, r.size) for r in inside_rects if r.x0 >= rect.box[0] and r.x1 <= rect.box[2] and r.y0 >= rect.box[1] and r.y1 <= rect.box[3]]
    for font in set(fonts_in_rect):
        matching_rects = [r for r in inside_rects if r.fontname == font[0] and r.size == font[1]]
        if matching_rects:
            x0 = min(r.x0 for r in matching_rects)
            y0 = min(r.y0 for r in matching_rects)
            x1 = max(r.x1 for r in matching_rects)
            y1 = max(r.y1 for r in matching_rects)
            
            new_label = font_to_label_map.get((font[0], font[1]), rect.label)  # Default to the original label if not found
            new_rect = LabelBox(label=new_label, box=[x0, y0, x1, y1])
            
            # Ensure the new rect is meaningfully different from the original to avoid re-triggering the split
            if rect.box != new_rect.box:
                split_rects.append(new_rect)

    return split_rects

def combine_rects_within_line(layout_rects: List[LabelBox]) -> List[LabelBox]:
    """Combine overlapping rects that are within the same line."""
    adjusted_rects = []
    while layout_rects:
        rect = layout_rects.pop(0)
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
    """
    Combine two rectangles by updating one and removing the other, considering label priority.
    
    Args:
        rect1: The first rectangle (this one will be updated).
        rect2: The second rectangle (this one will be removed).
    
    Returns:
        The updated rectangle.
    """
    logger.debug(f"Combining rect {rect1.box} (label: {rect1.label}) and {rect2.box} (label: {rect2.label}) by updating.")

    # Determine the label based on priority
    label = rect1.label if LABEL_PRIORITY[rect1.label] >= LABEL_PRIORITY[rect2.label] else rect2.label

    # Update rect1 to encompass rect2
    rect1.box = [
        min(rect1.box[0], rect2.box[0]),
        min(rect1.box[1], rect2.box[1]),
        max(rect1.box[2], rect2.box[2]),
        max(rect1.box[3], rect2.box[3])
    ]
    rect1.label = label
    
    return rect1


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

# def regroup_outside_text(outside_rects: List[TextRect], layout_rects: List[LabelBox], font_stats: Dict[Tuple[str, float], str]) -> List[LabelBox]:
#     """
#     Analyzes the existing layout rect types and groups the outside text rects into new layout rects,
#     ensuring that the new layout rects do not overlap with any existing layout rects.

#     Args:
#         outside_rects: List of text rectangles outside the existing layout rectangles.
#         layout_rects: List of existing layout rectangles.
#         font_stats: A dictionary mapping (font name, font size) to the most common label within that font group.

#     Returns:
#         A list of new layout rectangles created based on the outside text grouping.
#     """
#     # Step 1: Group outside rects to form new layout rectangles.
#     new_layout_rects = []
#     grouped_rects = []  # Track already grouped rectangles to avoid duplicates

#     for outside_rect in outside_rects:
#         if outside_rect in grouped_rects:
#             continue

#         # Determine the most likely layout type based on font similarity using font_stats
#         font_key = (outside_rect.fontname, outside_rect.size)
#         matching_type = font_stats.get(font_key, "Text")  # Default to "Text" if no match is found

#         # Group rects (for simplicity, consider nearby rects as part of the same group)
#         grouped_rect = outside_rect

#         for other_rect in outside_rects:
#             if other_rect != outside_rect and other_rect not in grouped_rects:
#                 # Basic proximity check for grouping
#                 if (abs(grouped_rect.x1 - other_rect.x0) < 20 or abs(grouped_rect.y1 - other_rect.y0) < 20):
#                     # Expand the grouped rectangle to include the other rectangle
#                     grouped_rect = TextRect(
#                         x0=min(grouped_rect.x0, other_rect.x0),
#                         y0=min(grouped_rect.y0, other_rect.y0),
#                         x1=max(grouped_rect.x1, other_rect.x1),
#                         y1=max(grouped_rect.y1, other_rect.y1),
#                         text=grouped_rect.text + " " + other_rect.text,
#                         fontname=grouped_rect.fontname,
#                         size=grouped_rect.size
#                     )
#                     grouped_rects.append(other_rect)

#         # Create a new layout rect based on the grouped rect
#         new_rect = LabelBox(
#             label=matching_type,
#             box=[grouped_rect.x0, grouped_rect.y0, grouped_rect.x1, grouped_rect.y1]
#         )

#         # Check if the new rect overlaps with any existing rects in layout_rects
#         if any(rects_overlap(new_rect.box, existing_rect.box) for existing_rect in layout_rects):
#             logger.debug(f"Skipping new rect {new_rect.box} due to overlap with existing layout rects.")
#             continue  # Skip adding this new rect if it overlaps with any existing layout rects

#         new_layout_rects.append(new_rect)
    
#     layout_rects.extend(new_layout_rects)

#     return layout_rects


# def regroup_outside_text(outside_rects: List[TextRect], layout_rects: List[LabelBox], font_stats: Dict[Tuple[str, float], str]) -> List[LabelBox]:
#     """
#     Group the outside text rectangles into larger blocks, combining them line by line while ensuring that
#     the new blocks do not overlap with any existing layout rectangles.

#     Args:
#         outside_rects: List of text rectangles outside the existing layout rectangles.
#         layout_rects: List of existing layout rectangles.
#         font_stats: A dictionary mapping (font name, font size) to the most common label within that font group.

#     Returns:
#         A list of new layout rectangles created by combining the outside text rectangles.
#     """
#     new_layout_rects = []
#     grouped_rects = set()  # Track already grouped rectangles to avoid duplicates

#     for outside_rect in outside_rects:
#         rect_key = (outside_rect.x0, outside_rect.y0, outside_rect.x1, outside_rect.y1)
#         if rect_key in grouped_rects:
#             continue

#         # Start with the first rect in the line
#         current_group = outside_rect

#         for other_rect in outside_rects:
#             other_key = (other_rect.x0, other_rect.y0, other_rect.x1, other_rect.y1)
#             if other_key != rect_key and other_key not in grouped_rects:
#                 # Check if other_rect is aligned horizontally (within the same line) and is close enough
#                 if abs(current_group.y1 - other_rect.y0) < 10 and within_same_line(
#                         [current_group.x0, current_group.y0, current_group.x1, current_group.y1],
#                         [other_rect.x0, other_rect.y0, other_rect.x1, other_rect.y1]):

#                     # Tentatively expand the current group to include the other rectangle
#                     tentative_group = TextRect(
#                         x0=min(current_group.x0, other_rect.x0),
#                         y0=min(current_group.y0, other_rect.y0),
#                         x1=max(current_group.x1, other_rect.x1),
#                         y1=max(current_group.y1, other_rect.y1),
#                         text=current_group.text + " " + other_rect.text,
#                         fontname=current_group.fontname,
#                         size=current_group.size
#                     )

#                     # Check if the new group overlaps with any existing layout rects
#                     new_rect_box = [tentative_group.x0, tentative_group.y0, tentative_group.x1, tentative_group.y1]
#                     if not any(rects_overlap(new_rect_box, existing_rect.box) for existing_rect in layout_rects):
#                         # No overlap, so finalize the group
#                         current_group = tentative_group
#                         grouped_rects.add(other_key)
#                     else:
#                         # Overlap detected, so skip adding this rect to the current group
#                         logger.debug(f"Skipping adding rect {other_rect.box} to current group due to overlap.")

#         # Determine the label based on the font information
#         font_key = (current_group.fontname, current_group.size)
#         matching_type = font_stats.get(font_key, "Text")  # Default to "Text" if no match is found

#         # Create a new layout rect based on the grouped rect
#         new_rect = LabelBox(
#             label=matching_type,
#             box=[current_group.x0, current_group.y0, current_group.x1, current_group.y1]
#         )

#         # Add the new rect to the final layout
#         new_layout_rects.append(new_rect)
#         grouped_rects.add(rect_key)  # Add the current_group's rect key to the grouped_rects set

#     layout_rects.extend(new_layout_rects)

#     return layout_rects


def regroup_outside_text(outside_rects: List[TextRect], layout_rects: List[LabelBox], font_stats: Dict[Tuple[str, float], str]) -> List[LabelBox]:
    """
    Group the outside text rectangles into larger blocks, combining them line by line while ensuring that
    the new blocks do not overlap with any existing layout rectangles.

    Args:
        outside_rects: List of text rectangles outside the existing layout rectangles.
        layout_rects: List of existing layout rectangles.
        font_stats: A dictionary mapping (font name, font size) to the most common label within that font group.

    Returns:
        A list of new layout rectangles created by combining the outside text rectangles.
    """
    new_layout_rects = []
    grouped_rects = set()  # Track already combined rectangles

    # Sort outside_rects by y0 (top-to-bottom)
    outside_rects.sort(key=lambda r: r.y0)

    i = 0
    while i < len(outside_rects):
        if (outside_rects[i].x0, outside_rects[i].y0, outside_rects[i].x1, outside_rects[i].y1) in grouped_rects:
            i += 1
            continue
        
        # Start a new group with the current rectangle
        current_group = outside_rects[i]
        grouped_rects.add((current_group.x0, current_group.y0, current_group.x1, current_group.y1))
        i += 1
        
        # Try to combine with subsequent rectangles
        j = i
        while j < len(outside_rects):
            if (outside_rects[j].x0, outside_rects[j].y0, outside_rects[j].x1, outside_rects[j].y1) in grouped_rects:
                j += 1
                continue

            # # Check if the current rect is aligned and close enough to be in the same group
            # if abs(current_group.y1 - outside_rects[j].y0) < 10 and within_same_line(
            #         [current_group.x0, current_group.y0, current_group.x1, current_group.y1],
            #         [outside_rects[j].x0, outside_rects[j].y0, outside_rects[j].x1, outside_rects[j].y1]):

            # Tentatively expand the group to include the next rectangle
            tentative_group = TextRect(
                x0=min(current_group.x0, outside_rects[j].x0),
                y0=min(current_group.y0, outside_rects[j].y0),
                x1=max(current_group.x1, outside_rects[j].x1),
                y1=max(current_group.y1, outside_rects[j].y1),
                text=current_group.text + " " + outside_rects[j].text,
                fontname=current_group.fontname,
                size=current_group.size
            )

            # Check for overlap with existing layout rects
            new_rect_box = [tentative_group.x0, tentative_group.y0, tentative_group.x1, tentative_group.y1]
            if not any(rects_overlap(new_rect_box, existing_rect.box) for existing_rect in layout_rects):
                # No overlap, finalize this addition to the group
                current_group = tentative_group
                grouped_rects.add((outside_rects[j].x0, outside_rects[j].y0, outside_rects[j].x1, outside_rects[j].y1))
            else:
                # Overlap detected, stop trying to add more to this group
                break
            
            j += 1

        # Determine the label based on the font information
        font_key = (current_group.fontname, current_group.size)
        matching_type = font_stats.get(font_key, "Text")  # Default to "Text" if no match is found

        # Create a new layout rect based on the grouped rect
        new_rect = LabelBox(
            label=matching_type,
            box=[current_group.x0, current_group.y0, current_group.x1, current_group.y1]
        )

        # Add the new rect to the final layout
        new_layout_rects.append(new_rect)

    layout_rects.extend(new_layout_rects)

    return layout_rects
