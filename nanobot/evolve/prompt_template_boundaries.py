from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

_EDITABLE_START = "<!-- evolve:prompt-editable:start -->"
_EDITABLE_END = "<!-- evolve:prompt-editable:end -->"
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


class PromptTemplateBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class EditableRegion:
    start_line: int
    end_line: int


def changed_baseline_line_numbers(
    baseline_body: str,
    proposed_body: str,
    editable_regions: list[EditableRegion] | None = None,
) -> list[int]:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=proposed_lines,
        autojunk=False,
    )
    changed_lines: set[int] = set()
    for tag, baseline_start, baseline_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if baseline_start != baseline_end:
            changed_lines.update(range(baseline_start, baseline_end))
            continue
        anchor_lines = insertion_anchor_lines(baseline_start, len(baseline_lines))
        if editable_regions is not None:
            editable_anchor_lines = [
                line_number
                for line_number in anchor_lines
                if line_in_regions(line_number, editable_regions)
            ]
            if editable_anchor_lines:
                changed_lines.update(editable_anchor_lines)
                continue
            if insertion_in_empty_region(baseline_start, editable_regions):
                changed_lines.add(baseline_start)
                continue
        if anchor_lines:
            changed_lines.add(anchor_lines[0])
        elif proposed_start != proposed_end:
            changed_lines.add(0)
    return sorted(changed_lines)


def insertion_anchor_lines(baseline_start: int, baseline_line_count: int) -> list[int]:
    anchor_lines: list[int] = []
    if baseline_start < baseline_line_count:
        anchor_lines.append(baseline_start)
    if baseline_start > 0:
        anchor_lines.append(baseline_start - 1)
    return anchor_lines


def line_in_regions(line_number: int, regions: list[EditableRegion]) -> bool:
    return any(region.start_line <= line_number <= region.end_line for region in regions)


def line_allowed_by_regions(line_number: int, regions: list[EditableRegion]) -> bool:
    return any(
        region.start_line <= line_number <= region.end_line
        or (region.start_line > region.end_line and line_number == region.start_line)
        for region in regions
    )


def insertion_in_empty_region(baseline_start: int, regions: list[EditableRegion]) -> bool:
    return any(
        region.start_line > region.end_line and baseline_start == region.start_line
        for region in regions
    )


def regions_touched_by_lines(
    changed_line_numbers: list[int], regions: list[EditableRegion]
) -> list[EditableRegion]:
    return [
        region
        for region in regions
        if any(line_allowed_by_regions(line_number, [region]) for line_number in changed_line_numbers)
    ]


def has_region_span_bypass(
    baseline_regions: list[EditableRegion],
    proposed_regions: list[EditableRegion],
    baseline_body: str,
    proposed_body: str,
) -> bool:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    for baseline_region, proposed_region in zip(baseline_regions, proposed_regions, strict=True):
        proposed_region_text = region_text(proposed_body, proposed_region).splitlines()
        for baseline_line in region_text(baseline_body, baseline_region).splitlines():
            if not baseline_line or baseline_line in proposed_region_text:
                continue
            baseline_outside_count = line_count_outside_region(
                baseline_lines,
                baseline_region,
                baseline_line,
            )
            proposed_outside_count = line_count_outside_region(
                proposed_lines,
                proposed_region,
                baseline_line,
            )
            if proposed_outside_count > baseline_outside_count:
                return True
    return False


def line_count_outside_region(lines: list[str], region: EditableRegion, target_line: str) -> int:
    region_lines = set(region_line_numbers(region, len(lines)))
    return sum(
        1
        for line_number, line in enumerate(lines)
        if line == target_line and line_number not in region_lines
    )


def region_line_numbers(region: EditableRegion, line_count: int) -> list[int]:
    if region.end_line < region.start_line:
        return []
    return list(range(region.start_line, min(region.end_line + 1, line_count)))


def region_text(body: str, region: EditableRegion) -> str:
    lines = body.splitlines()
    if region.end_line < region.start_line:
        return ""
    return "\n".join(lines[region.start_line : region.end_line + 1])


def proposed_region_texts(
    *,
    baseline_body: str,
    proposed_body: str,
    regions: list[EditableRegion],
) -> list[str]:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=proposed_lines,
        autojunk=False,
    )
    region_indices = range(len(regions))
    proposed_region_lines: dict[int, list[str]] = {index: [] for index in region_indices}
    for tag, baseline_start, baseline_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            line_pairs = zip(
                range(baseline_start, baseline_end),
                proposed_lines[proposed_start:proposed_end],
                strict=True,
            )
            for baseline_line_number, line in line_pairs:
                for index, region in enumerate(regions):
                    if region.start_line <= baseline_line_number <= region.end_line:
                        proposed_region_lines[index].append(line)
            continue
        anchored_regions = {
            index
            for index, region in enumerate(regions)
            if baseline_start <= region.end_line and baseline_end > region.start_line
        }
        if not anchored_regions and baseline_start == baseline_end:
            anchor_lines = insertion_anchor_lines(baseline_start, len(baseline_lines))
            anchored_regions = {
                index
                for index, region in enumerate(regions)
                if any(line_allowed_by_regions(line_number, [region]) for line_number in anchor_lines)
                or insertion_in_empty_region(baseline_start, [region])
            }
        for index in anchored_regions:
            proposed_region_lines[index].extend(proposed_lines[proposed_start:proposed_end])
    return [
        "\n".join(proposed_region_lines[index])
        for index in region_indices
        if proposed_region_lines[index]
    ]


def proposed_changed_text(proposed_body: str, baseline_body: str) -> str:
    proposed_lines = proposed_body.splitlines()
    changed_lines = changed_proposed_line_numbers(baseline_body, proposed_body)
    return "\n".join(proposed_lines[line_number] for line_number in changed_lines)


def changed_text_contexts(proposed_body: str, changed_line_numbers: list[int]) -> list[str]:
    proposed_lines = proposed_body.splitlines()
    return [
        "\n".join(
            proposed_lines[context_line_number]
            for context_line_number in range(line_number - 2, line_number + 3)
            if 0 <= context_line_number < len(proposed_lines)
            and proposed_lines[context_line_number].strip() not in {_EDITABLE_START, _EDITABLE_END}
        )
        for line_number in changed_line_numbers
    ]


def changed_proposed_line_numbers(baseline_body: str, proposed_body: str) -> list[int]:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=proposed_lines,
        autojunk=False,
    )
    changed_lines: set[int] = set()
    for tag, _baseline_start, _baseline_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_lines.update(range(proposed_start, proposed_end))
    return sorted(changed_lines)


def parse_editable_regions(body: str) -> list[EditableRegion]:
    lines = body.splitlines()
    fence_marker: str | None = None
    fence_length = 0
    active_start: int | None = None
    regions: list[EditableRegion] = []
    for index, line in enumerate(lines):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence_marker is None:
                fence_marker = marker[0]
                fence_length = len(marker)
                continue
            if (
                marker[0] == fence_marker
                and len(marker) >= fence_length
                and line[fence_match.end() :].strip(" 	") == ""
            ):
                fence_marker = None
                fence_length = 0
                continue
        if fence_marker is not None:
            continue
        stripped = line.strip()
        if stripped == _EDITABLE_START:
            if active_start is not None:
                raise PromptTemplateBoundaryError("nested editable region marker")
            active_start = index + 1
            continue
        if stripped == _EDITABLE_END:
            if active_start is None:
                raise PromptTemplateBoundaryError("unbalanced editable region marker")
            regions.append(EditableRegion(start_line=active_start, end_line=index - 1))
            active_start = None
    if active_start is not None:
        raise PromptTemplateBoundaryError("unbalanced editable region marker")
    return regions
