"""
Computing — derived exemplar records (NaCCA CCP, Basic 7).

Derived from the official *Computing Common Core Programme (CCP)* curriculum,
NaCCA / Ministry of Education, 2021 — Strand 1 (Introduction to Computing),
Sub-strand 1 (Components of Computers and Computer Systems).

Only DERIVED information is stored: the action verbs each official exemplar list
implies, a short learning focus, and author-written teacher-ready activity
structures. No sentence of the official document is reproduced here.
"""

from __future__ import annotations

from typing import List

from . import ExemplarRecord

_SOURCE = dict(
    source_title=(
        "Computing Curriculum for Basic 7–10, Common Core Programme (CCP), "
        "NaCCA / Ministry of Education, Ghana"
    ),
    source_url="https://nacca.gov.gh/wp-content/uploads/2023/06/COMPUTING.pdf",
    source_version="NaCCA/Ministry of Education 2021 (CCP, Basic 7–10)",
)

_STRAND = "Introduction to Computing"
_SUB_STRAND = "Components of Computers and Computer Systems"

_CS_B7111 = "B7.1.1.1"   # Examine the parts of a computer
_CS_B7112 = "B7.1.1.2"   # Demonstrate the use of the features of the Windows Desktop


RECORDS: List[ExemplarRecord] = [
    ExemplarRecord(
        subject="Computing",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code=_CS_B7111,
        indicator_code="B7.1.1.1.1",
        learning_focus="Fourth-generation computers and the microchip",
        curriculum_action_verbs=["discuss", "identify", "explore"],
        exemplar_activity_patterns=[
            "Hold up a microchip (or a clear picture of one) next to a picture of "
            "an early room-sized computer. Ask learners which is newer and why, "
            "write their reasons on the board, then tell them both are computers.",
            "Name the features of fourth-generation computers one at a time — "
            "microprocessor, much smaller size, lower cost, faster speed — "
            "pointing to the microchip each time so learners connect the part to "
            "the feature. Ask learners to repeat each feature in their own words.",
            "Give pairs a labelled diagram of a processor. Learners trace the "
            "path from the microchip to the parts it controls and write one "
            "sentence on why the microchip changed computers.",
        ],
        assessment_patterns=[
            "Ask each pair to name two features of fourth-generation computers "
            "and point to the microchip on the diagram.",
            "Listen for 'microprocessor' and 'smaller' rather than a memorised list.",
        ],
        assignment_patterns=[
            "Find one device at home that uses a microchip and write what it does.",
            "Draw and label the microchip you saw in class.",
        ],
        class_assignment_pattern=(
            "In pairs, learners label a simple processor diagram and write one "
            "sentence on why the microchip changed computers. The teacher checks "
            "each pair names both the part and the feature it made possible."
        ),
        home_assignment_pattern=(
            "Find one device at home that contains a microchip and write two "
            "sentences on what the device does and which feature of modern "
            "computers it shows."
        ),
        suitable_resource_patterns=[
            "a real microchip or a clear picture of one",
            "diagram of a processor",
            "chart comparing computer generations",
        ],
        focus_terms=[
            "fourth-generation computers", "microchip", "microprocessor",
            "processor", "computer generations",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
            "Digital Literacy",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Computing CCP "
            "exemplars for B7.1.1.1.1 (features of fourth-generation computers; "
            "identify a microchip; explore processor architecture). Exemplar "
            "wording was read and transformed into activity structures; no "
            "official text is stored."
        ),
        **_SOURCE,
    ),
    ExemplarRecord(
        subject="Computing",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code=_CS_B7111,
        indicator_code="B7.1.1.1.2",
        learning_focus="Input devices: manual and automatic",
        curriculum_action_verbs=["demonstrate", "distinguish", "explore"],
        exemplar_activity_patterns=[
            "Show pictures of a keyboard, mouse, touchscreen, barcode reader and "
            "scanner. Ask learners which of these they have used and record their "
            "answers on the board.",
            "Demonstrate one device from each group in front of the class: type on "
            "the keyboard (manual) and scan a barcode (automatic). Learners watch "
            "and then say which needed a person and which worked on its own.",
            "Give each pair the device pictures. Learners sort them into manual and "
            "automatic groups, then list one advantage and one disadvantage of "
            "each group and say where each device is used.",
        ],
        assessment_patterns=[
            "Give each pair four device cards and ask them to sort the cards as "
            "manual or automatic, giving one reason per card.",
            "Ask two pairs to explain a borderline device and listen for the words "
            "'manual' and 'automatic' used correctly.",
        ],
        assignment_patterns=[
            "Identify three input devices used where you live and write one use "
            "for each.",
            "Draw and label one manual and one automatic input device.",
        ],
        class_assignment_pattern=(
            "Pairs sort the device pictures into manual and automatic groups, "
            "write one reason for each group, and state where each device is "
            "used. The teacher checks a sample and asks two pairs to justify a "
            "borderline device."
        ),
        home_assignment_pattern=(
            "Find and list three input devices used in your home or community. "
            "For each one, say whether it is manual or automatic and what it is "
            "used for."
        ),
        suitable_resource_patterns=[
            "picture cards showing keyboard, mouse, touchscreen, barcode reader, scanner",
            "a real keyboard and a real barcode reader or scanner",
            "sorting chart labelled MANUAL / AUTOMATIC",
        ],
        focus_terms=[
            "input devices", "keyboard", "mouse", "touchscreen", "barcode reader",
            "scanner", "manual input", "automatic input",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
            "Digital Literacy",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Computing CCP "
            "exemplars for B7.1.1.1.2 (observe/show input devices; demonstrate "
            "their use; distinguish manual and automatic devices; explore "
            "advantages and disadvantages; explore areas of use)."
        ),
        **_SOURCE,
    ),
    ExemplarRecord(
        subject="Computing",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code=_CS_B7111,
        indicator_code="B7.1.1.1.4",
        learning_focus="Hard drives and optical storage media",
        curriculum_action_verbs=["identify", "discuss", "explore", "compare"],
        exemplar_activity_patterns=[
            "Display a portable hard drive and two optical discs (one CD, one DVD). "
            "Ask learners where they save school work and why, and note their "
            "answers on the board.",
            "Name and point to each storage item: magnetic hard drive, portable "
            "hard drive, CD-ROM, DVD-ROM. Learners repeat each name and say which "
            "one holds the most data and why.",
            "In groups, learners read the printed capacities and write speeds from "
            "the disc labels into a table, then compare the items and state one "
            "strength and one weakness of each.",
        ],
        assessment_patterns=[
            "Ask each group to name the storage item with the largest capacity on "
            "the table and give the evidence from the label.",
            "Check that learners can say why an optical disc is read-only while a "
            "hard drive can be written many times.",
        ],
        assignment_patterns=[
            "List the storage devices in your school or home and arrange them from "
            "smallest to largest capacity.",
            "Find the capacity written on any storage device you can reach and "
            "explain what the number means.",
        ],
        class_assignment_pattern=(
            "Groups build a comparison table of the hard drive, portable hard "
            "drive, CD-ROM and DVD-ROM using the printed capacities and write "
            "speeds, then state one strength and one weakness of each. The teacher "
            "checks each table has the correct units."
        ),
        home_assignment_pattern=(
            "Find one storage device at home or school. Write the capacity printed "
            "on it, whether it is magnetic or optical, and one advantage of that "
            "type of storage."
        ),
        suitable_resource_patterns=[
            "a portable hard drive or picture of one",
            "CD-ROM and DVD-ROM discs (or pictures)",
            "chart of storage capacities and read/write speeds",
        ],
        focus_terms=[
            "hard drive", "portable hard drive", "optical disc", "CD-ROM",
            "DVD-ROM", "storage capacity", "write speed", "disk caching",
        ],
        core_competencies=[
            "Critical Thinking and Problem Solving",
            "Communication and Collaboration",
            "Digital Literacy",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Computing CCP "
            "exemplars for B7.1.1.1.4 (identify magnetic storage and optical "
            "media; discuss their features; explore capacities and write speeds; "
            "explore differences between hard disk drives)."
        ),
        **_SOURCE,
    ),
    ExemplarRecord(
        subject="Computing",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code=_CS_B7112,
        indicator_code="B7.1.1.2.1",
        learning_focus="Windows desktop: Start screen, tiles and taskbar",
        curriculum_action_verbs=["discover", "show", "demonstrate", "explore"],
        exemplar_activity_patterns=[
            "Ask learners what they see when a Windows computer finishes starting. "
            "Record the parts they name on the board and add any missing ones.",
            "At the computer (or using a screenshot on the board) point out the "
            "Start screen, the tiles, the taskbar buttons and a preview thumbnail. "
            "Learners name each part as the teacher points to it.",
            "In pairs at a computer or with the screenshot, learners open two "
            "windows and use the taskbar to preview one another, then write down "
            "the four features they used and what each one does.",
        ],
        assessment_patterns=[
            "Point to a screen part and ask a learner to name it and say what it "
            "does; require all four feature names across the class.",
            "Ask a pair to demonstrate previewing a window from the taskbar.",
        ],
        assignment_patterns=[
            "On any computer you can reach, write down the names of the taskbar "
            "buttons you can see and what each one does.",
            "Draw the Windows screen and label the Start screen, tiles and taskbar.",
        ],
        class_assignment_pattern=(
            "Pairs use the computer (or the labelled screenshot) to open two "
            "windows, preview one from the taskbar, and record the four desktop "
            "features with what each one does. The teacher observes and asks each "
            "pair to demonstrate one feature."
        ),
        home_assignment_pattern=(
            "Draw the Windows desktop from memory and label the Start screen, "
            "tiles and the taskbar. Write one sentence on what a preview thumbnail "
            "shows."
        ),
        suitable_resource_patterns=[
            "a computer with Windows, or a labelled screenshot of the desktop",
            "chart naming the Start screen, tiles, taskbar and preview thumbnails",
        ],
        focus_terms=[
            "Windows desktop", "Start screen", "tiles", "taskbar",
            "preview thumbnail", "window",
        ],
        core_competencies=[
            "Digital Literacy",
            "Communication and Collaboration",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Computing CCP "
            "exemplars for B7.1.1.2.1 (show the desktop, tiles and taskbar; "
            "demonstrate previewing thumbnails; explore taskbar features; "
            "demonstrate previewing windows on the taskbar)."
        ),
        **_SOURCE,
    ),
    ExemplarRecord(
        subject="Computing",
        level="B7",
        strand=_STRAND,
        sub_strand=_SUB_STRAND,
        content_standard_code=_CS_B7112,
        indicator_code="B7.1.1.2.2",
        learning_focus="File, folder and user-account management",
        curriculum_action_verbs=["practise", "demonstrate", "explore"],
        exemplar_activity_patterns=[
            "Show a messy folder on the screen and a tidy one beside it. Ask "
            "learners which would be easier to use at examination time and why.",
            "Demonstrate the naming convention: create a folder, create two "
            "subfolders inside it, name them clearly and move a file into one. "
            "Learners watch the steps and write them down in order.",
            "In pairs, learners create a folder with two subfolders, name them by "
            "the convention and save a file into the correct subfolder. Then they "
            "open the file properties and note the file extension.",
        ],
        assessment_patterns=[
            "Observe each pair performing the folder, subfolder and file steps and "
            "check the names follow the convention taught.",
            "Ask learners to explain what a file extension tells you.",
        ],
        assignment_patterns=[
            "Draw a folder tree with one folder and two subfolders and write what "
            "belongs in each.",
            "Write down three file extensions you have seen and what each one tells "
            "you about the file.",
        ],
        class_assignment_pattern=(
            "Pairs create a folder with two subfolders following the naming "
            "convention, save a file into the correct subfolder, and record the "
            "file's extension. The teacher checks the naming and the file "
            "placement, then asks what a user account controls."
        ),
        home_assignment_pattern=(
            "Write the steps you would follow to organise your exercise files "
            "into folders and subfolders, and explain why permission levels matter "
            "on a shared computer."
        ),
        suitable_resource_patterns=[
            "a computer with a file manager, or labelled screenshots of the steps",
            "chart showing a folder tree and common file extensions",
        ],
        focus_terms=[
            "file management", "folder", "subfolder", "file extension",
            "user account", "permission level", "naming convention",
        ],
        core_competencies=[
            "Digital Literacy",
            "Critical Thinking and Problem Solving",
            "Personal Development and Leadership",
        ],
        provenance=(
            "Derived by SchemeKnit from the official NaCCA Computing CCP "
            "exemplars for B7.1.1.2.2 (demonstrate file management following "
            "naming conventions; explore types and importance of file extensions; "
            "explore account levels and permission levels)."
        ),
        **_SOURCE,
    ),
]
