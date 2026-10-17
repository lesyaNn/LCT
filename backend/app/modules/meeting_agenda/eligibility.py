"""Meeting-stage recognition shared by transitions and agenda generation."""

import re


_MEETING_WORD = re.compile(r"(?<!\w)встреч(?:а|и|у|е|ей)(?!\w)", re.IGNORECASE)


def is_meeting_stage(name: str, template_stage_id: object | None) -> bool:
    return template_stage_id is not None and bool(_MEETING_WORD.search(name))
