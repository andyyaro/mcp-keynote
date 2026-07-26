"""The rendered-check helpers themselves, on synthetic images.

These pin the detectors the live harness relies on. They matter because the
first version of the pie detector filtered candidate fills by saturation,
which silently reported a healthy 3-slice pie as 2 (Keynote's second chart
series color is neutral gray) - a check that is wrong in this direction
would have let the original one-100%-slice defect through a second time.
"""

import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "verify_tools_helpers", REPO / "scripts" / "verify_tools.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HARNESS = _load_harness()


def _chart_image(slice_colors, background=(240, 240, 240)):
    """A 400x300 'slide' with a 200x200 'chart' of N equal wedges at (100, 50)."""
    image = Image.new("RGB", (400, 300), background)
    draw = ImageDraw.Draw(image)
    step = 360 / len(slice_colors)
    for i, color in enumerate(slice_colors):
        draw.pieslice([100, 50, 300, 250], i * step, (i + 1) * step, fill=color)
    return image


class TestFillAreas:
    BOX = (100, 50, 200, 200)

    def test_one_fill_is_the_shipped_pie_defect(self):
        image = _chart_image([(70, 160, 250)])
        assert len(HARNESS.fill_areas(image, 1.0, self.BOX)) == 1

    def test_three_slices_are_seen_as_three(self):
        image = _chart_image([(70, 160, 250), (130, 215, 85), (240, 190, 65)])
        assert len(HARNESS.fill_areas(image, 1.0, self.BOX)) == 3

    def test_a_neutral_gray_series_still_counts(self):
        """Saturation must not be the filter - this is the case that broke."""
        image = _chart_image([(70, 160, 250), (172, 172, 172), (20, 60, 116)])
        assert len(HARNESS.fill_areas(image, 1.0, self.BOX)) == 3

    def test_background_is_not_counted_as_a_fill(self):
        image = _chart_image([(70, 160, 250)], background=(255, 255, 255))
        fills = HARNESS.fill_areas(image, 1.0, self.BOX)
        assert [c for c, _ in fills] == [(70, 160, 250)]

    def test_areas_are_ordered_largest_first(self):
        image = Image.new("RGB", (400, 300), (240, 240, 240))
        draw = ImageDraw.Draw(image)
        draw.rectangle([100, 50, 300, 180], fill=(200, 30, 30))  # big
        draw.rectangle([100, 190, 300, 240], fill=(30, 30, 200))  # smaller
        fills = HARNESS.fill_areas(image, 1.0, self.BOX)
        assert [c for c, _ in fills] == [(200, 30, 30), (30, 30, 200)]


class TestInkDetection:
    def test_a_gradient_background_carries_no_ink(self):
        """The reason ink is a high-pass and not 'differs from background'.

        Slate paints a gradient; a background-color comparison flagged the
        whole slide and reported a 96pt title as 1024pt wide.
        """
        image = Image.new("RGB", (400, 300))
        for y in range(300):
            for x in range(400):
                image.putpixel((x, y), (60 + x // 8, 60 + x // 8, 60 + x // 8))
        assert HARNESS.ink_fraction(image, 1.0) < 0.01
        assert HARNESS.ink_bbox(image, 1.0) is None

    def test_drawn_detail_on_a_gradient_is_found(self):
        image = Image.new("RGB", (400, 300))
        for y in range(300):
            for x in range(400):
                image.putpixel((x, y), (60 + x // 8, 60 + x // 8, 60 + x // 8))
        ImageDraw.Draw(image).rectangle([100, 100, 300, 140], outline=(255, 255, 255), width=4)
        bbox = HARNESS.ink_bbox(image, 1.0)
        assert bbox is not None
        assert 95 <= bbox[0] <= 105 and 295 <= bbox[2] <= 310
        assert HARNESS.ink_fraction(image, 1.0) > 0.01


class TestPdfPageCount:
    def test_counts_pages_from_the_file(self, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4\n/Type /Pages /Count 7\n/Type /Page\n")
        assert HARNESS.pdf_page_count(pdf) == 7

    def test_falls_back_to_counting_page_objects(self, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4\n/Type /Page x\n/Type /Page y\n")
        assert HARNESS.pdf_page_count(pdf) == 2
