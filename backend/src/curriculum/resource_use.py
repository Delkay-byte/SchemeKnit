"""Deterministic sentences that describe how an approved TLR is USED.

A resource is not a teaching resource merely because it appears in the
summary row. These sentences are generated only for resources the uploaded
scheme (or the teacher) supplied, and each names a concrete teacher/learner
action for that resource.
"""

from __future__ import annotations

import re

_DEVICE = re.compile(
    r"computer|printer|mouse|keyboard|monitor|system unit|flash drive|laptop|"
    r"tablet|projector|speaker|headphone|phone|device|machine|apparatus|"
    r"microscope|balance|thermometer|calculator", re.I)
_VISUAL = re.compile(
    r"chart|picture|diagram|poster|model|photo|card|map|globe|specimen|"
    r"real object|sample|flashcard|illustration|display|chalkboard|"
    r"whiteboard|blackboard|board", re.I)
_BOOK = re.compile(
    r"book|exercise|notebook|paper|pencil|pen|marker|ruler|worksheet|"
    r"sheet|journal|portfolio", re.I)
_CONSUMABLE = re.compile(
    r"chalk|string|stick|stone|leaf|seed|bottle|container|glue|scissors|"
    r"tape|clay|paint|brush|needle|thread|material", re.I)


def resource_use_sentence(resource: str, focus: str, index: int = 0) -> str:
    """One concrete use of ``resource`` in the lesson."""
    name = (resource or "").strip().rstrip(" .;:,")
    topic = (focus or "the lesson focus").strip().rstrip(" .;:,")
    if not name:
        return ""
    plural = name.split()[-1].lower().endswith("s") or "&" in name
    them = "them" if plural else "it"

    if _DEVICE.search(name):
        options = (
            f"The teacher demonstrates the {topic} task on the {name}, and "
            f"each learner practises the same step.",
            f"Learners use the {name} to carry out the {topic} task while the "
            f"teacher checks each learner's technique.",
        )
    elif _VISUAL.search(name):
        options = (
            f"The teacher displays the {name} and learners use {them} to name "
            f"and compare examples of {topic}.",
            f"Learners study the {name}, point out the key features of {topic} "
            f"and explain what each one shows.",
        )
    elif _BOOK.search(name):
        options = (
            f"Each learner records the {topic} task in the {name} and the "
            f"teacher checks the entries.",
            f"Learners write their answers about {topic} in the {name}, then "
            f"swap and peer-check them.",
        )
    elif _CONSUMABLE.search(name):
        options = (
            f"Learners use the {name} to build or demonstrate {topic}, and the "
            f"teacher checks that each group uses {them} correctly.",
            f"The teacher models the {topic} task with the {name}; learners "
            f"then repeat the task in their groups.",
        )
    else:
        options = (
            f"The teacher uses the {name} to model the {topic} task, and "
            f"learners then apply {them} to their own work.",
            f"Learners use the {name} while working on {topic}; the teacher "
            f"checks how each group applies {them}.",
        )
    return options[index % len(options)]
