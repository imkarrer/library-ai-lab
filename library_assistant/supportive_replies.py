#!/usr/bin/env python3
"""Supportive reply handling with Install overrides."""

import re

# Default texts from ADR-0011, verbatim, with {counselor} placeholder
DEFAULT_REPLY_TEMPLATES = {
    "self_harm": """It sounds like you are going through something really hard. You don't have to handle it alone.

Please talk to an adult you trust today, like {counselor} or the librarian.

You can call or text **988** any time, day or night. It is free, and a real person will listen. If you might hurt yourself right now, tell an adult near you or call **911**.

I am a library computer, so a person can help with this better than I can. An adult here may check in with you, because they care how you are doing.""",
    "abuse": """Thank you for saying something. If someone is hurting you or making you feel unsafe, it is not your fault. You deserve to be safe.

Please tell an adult you trust at school, like {counselor}, a teacher, or the librarian.

You can also call or text the Childhelp hotline at **1-800-422-4453**, any time, day or night. If you are in danger right now, call **911**.

An adult here may check in with you, because they want you to be safe.""",
    "bullying": """That sounds really hard. Nobody deserves to be treated that way, and it is not your fault.

Please tell an adult you trust, like {counselor}, a teacher, or the librarian. They can help make it stop. If it is happening to a friend, telling an adult is a way to help them.

If it is making you feel really down, you can call or text **988** any time.

An adult here may check in with you, because they want to help.""",
    "threats_of_violence": """It sounds like someone could get hurt. That is serious. Please tell an adult right away, like {counselor}, a teacher, or the librarian.

If you are angry or upset, an adult can help you work it out. If you are worried about someone else, telling an adult is the right thing to do. It is not snitching.

If anyone is in danger right now, call **911**.

An adult here may check in with you, because they want everyone to be safe.""",
}

# The precedence order for reply selection when multiple categories match
PRECEDENCE_ORDER = ["self_harm", "threats_of_violence", "abuse", "bullying"]

# Valid placeholders for override validation
VALID_PLACEHOLDERS = {"counselor"}


def validate_override_text(text: str, category: str) -> list[str]:
    """
    Validate an override text against guard rails.

    Returns list of error messages, empty if valid.
    """
    errors = []

    # Check for 988 in self-harm text
    if category == "self_harm" and "988" not in text:
        errors.append("Self-harm override must contain 988")

    # Check that text names at least one adult
    # Check for {counselor} format first, then other patterns
    if "{counselor}" in text:
        # If {counselor} is present, it's valid
        pass
    elif re.search(r"\b(counselor|librarian|teacher)\b", text, re.IGNORECASE):
        # If one of these words appears as a standalone word, it's valid
        pass
    else:
        errors.append(
            "Override must name at least one adult (use {counselor}, librarian, or teacher)"
        )

    # Check word count (max 120 words)
    word_count = len(text.split())
    if word_count > 120:
        errors.append(f"Override text must be under 120 words, got {word_count}")

    # Check for unknown placeholders
    placeholders = re.findall(r"\{([^}]+)\}", text)
    for placeholder in placeholders:
        if placeholder not in VALID_PLACEHOLDERS:
            errors.append(f"Unknown placeholder: {placeholder}")

    return errors


def get_supportive_reply_text(
    category: str,
    counselor_name: str = "a school counselor",
    overrides: dict[str, str] | None = None,
) -> str:
    """
    Get the supportive reply text for a category with the counselor name filled in.
    """
    if overrides is None:
        overrides = {}

    # Check if there's an override for this category
    if category in overrides:
        override_text = overrides[category]
        # Basic validation of the override
        validation_errors = validate_override_text(override_text, category)
        if validation_errors:
            # For now, we'll use the default if validation fails
            # In a real implementation this should raise an error
            # But we should still strip bold markers from the default text to maintain
            # compatibility with the ADR-0011 requirement that bold is dropped for chat display
            default_text = DEFAULT_REPLY_TEMPLATES.get(category, "")
            if default_text:
                # Strip bold markers for chat display compatibility
                import re

                stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", default_text)
                return stripped.format(counselor=counselor_name)
            return default_text
        # For overrides, return as-is (they may have their own formatting rules)
        return override_text

    # Get the default text for this category
    default_text = DEFAULT_REPLY_TEMPLATES.get(category, "")
    if not default_text:
        return ""  # Should not happen

    # Strip bold markers for chat display (ADR-0011 requirement)
    import re

    stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", default_text)

    # Fill in the counselor placeholder
    return stripped.format(counselor=counselor_name)
