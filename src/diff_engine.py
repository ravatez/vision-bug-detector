from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from skimage.metrics import structural_similarity


DEFAULT_PIXEL_THRESHOLD = 25
DEFAULT_MIN_REGION_AREA = 120


@dataclass(frozen=True)
class DiffConfig:
    pixel_threshold: int = DEFAULT_PIXEL_THRESHOLD
    min_region_area: int = DEFAULT_MIN_REGION_AREA
    blur_kernel_size: Tuple[int, int] = (5, 5)
    morphology_kernel_size: Tuple[int, int] = (5, 5)
    dilation_iterations: int = 2


@dataclass(frozen=True)
class DiffRegion:
    x: int
    y: int
    width: int
    height: int
    area: float


@dataclass(frozen=True)
class DiffResult:
    score: float
    diff_map: np.ndarray
    mask: np.ndarray
    regions: List[DiffRegion]
    highlighted_image: np.ndarray


def load_image(image_path: Path) -> np.ndarray:
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Unable to load image: {image_path}")
    return image


def load_images(baseline_path: Path, current_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    baseline = load_image(baseline_path)
    current = load_image(current_path)
    validate_image_shapes(baseline, current, baseline_path, current_path)
    return baseline, current


def validate_image_shapes(
    baseline: np.ndarray,
    current: np.ndarray,
    baseline_path: Path,
    current_path: Path,
) -> None:
    if baseline.shape != current.shape:
        raise ValueError(
            "Baseline and current screenshots must have identical dimensions. "
            f"Got {baseline.shape} for {baseline_path.name} and {current.shape} for {current_path.name}."
        )


def preprocess_image(image: np.ndarray, blur_kernel_size: Tuple[int, int]) -> np.ndarray:
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray_image, blur_kernel_size, 0)


def create_pixel_diff_mask(
    baseline_gray: np.ndarray,
    current_gray: np.ndarray,
    pixel_threshold: int,
) -> Tuple[np.ndarray, np.ndarray]:
    pixel_diff = cv2.absdiff(baseline_gray, current_gray)
    _, pixel_mask = cv2.threshold(pixel_diff, pixel_threshold, 255, cv2.THRESH_BINARY)
    return pixel_diff, pixel_mask


def create_ssim_diff_map(
    baseline_gray: np.ndarray,
    current_gray: np.ndarray,
) -> Tuple[float, np.ndarray, np.ndarray]:
    score, ssim_map = structural_similarity(baseline_gray, current_gray, full=True)
    ssim_diff = ((1.0 - ssim_map) * 255).astype("uint8")
    _, ssim_mask = cv2.threshold(
        ssim_diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return score, ssim_diff, ssim_mask


def postprocess_mask(mask: np.ndarray, config: DiffConfig) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, config.morphology_kernel_size)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel)
    return cv2.dilate(closed, kernel, iterations=config.dilation_iterations)


def extract_regions(mask: np.ndarray, min_region_area: int) -> List[DiffRegion]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions: List[DiffRegion] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_region_area:
            continue

        x, y, width, height = cv2.boundingRect(contour)
        regions.append(DiffRegion(x=x, y=y, width=width, height=height, area=area))

    return sorted(regions, key=lambda region: region.area, reverse=True)


def highlight_regions(image: np.ndarray, regions: List[DiffRegion]) -> np.ndarray:
    output = image.copy()

    for region in regions:
        top_left = (region.x, region.y)
        bottom_right = (region.x + region.width, region.y + region.height)
        cv2.rectangle(output, top_left, bottom_right, (0, 0, 255), 2)

    return output


def analyze_images(
    baseline: np.ndarray,
    current: np.ndarray,
    config: DiffConfig | None = None,
) -> DiffResult:
    config = config or DiffConfig()

    baseline_gray = preprocess_image(baseline, config.blur_kernel_size)
    current_gray = preprocess_image(current, config.blur_kernel_size)

    pixel_diff, pixel_mask = create_pixel_diff_mask(
        baseline_gray,
        current_gray,
        config.pixel_threshold,
    )
    score, ssim_diff, ssim_mask = create_ssim_diff_map(baseline_gray, current_gray)

    combined_diff = cv2.max(pixel_diff, ssim_diff)
    combined_mask = cv2.bitwise_or(pixel_mask, ssim_mask)
    cleaned_mask = postprocess_mask(combined_mask, config)

    regions = extract_regions(cleaned_mask, config.min_region_area)
    highlighted_image = highlight_regions(current, regions)

    return DiffResult(
        score=score,
        diff_map=combined_diff,
        mask=cleaned_mask,
        regions=regions,
        highlighted_image=highlighted_image,
    )


def save_diff_outputs(test_dir: Path, result: DiffResult) -> None:
    diff_path = test_dir / "diff.png"
    highlight_path = test_dir / "highlighted.png"

    cv2.imwrite(str(diff_path), result.diff_map)
    cv2.imwrite(str(highlight_path), result.highlighted_image)


def run_diff(test_name: str = "login_test", config: DiffConfig | None = None) -> DiffResult:
    base_dir = Path(__file__).resolve().parent.parent
    test_dir = base_dir / "data" / "screenshots" / test_name

    baseline_path = test_dir / "baseline.png"
    current_path = test_dir / "current.png"

    baseline, current = load_images(baseline_path, current_path)
    result = analyze_images(baseline, current, config=config)
    save_diff_outputs(test_dir, result)

    print(
        f"[SUCCESS] Diff generated for {test_name} | "
        f"SSIM={result.score:.4f} | regions={len(result.regions)}"
    )
    return result


if __name__ == "__main__":
    run_diff("login_test")
