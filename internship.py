import os

from dotenv import load_dotenv

from plugins import Plugin
from retrieval import search

load_dotenv(override=True)

MAX_DISTANCE = 0.5


def match_profile(requirement: str) -> str:
    """Find the user's relevant experience for a specific job requirement."""
    hits = search(requirement, k=3)
    hits = [h for h in hits if h["distance"] <= MAX_DISTANCE]

    if not hits:
        return (
            f"No experience found matching '{requirement}'. "
            "Do not invent experience — report this gap honestly."
        )

    return "\n\n".join(
        f"[chunk {h['id']}, distance {h['distance']:.3f}]\n{h['content']}"
        for h in hits
    )


INTERNSHIP_PLUGIN = Plugin(
    name="internship",
    description="Tools for tailoring applications to job descriptions.",
    schemas=[
        {
            "name": "match_profile",
            "description": (
                "Search the user's background for experience matching a specific "
                "job requirement or skill. Call this once per requirement, using "
                "the requirement itself as the search term."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "requirement": {
                        "type": "string",
                        "description": "A single skill or requirement from the job description.",
                    }
                },
                "required": ["requirement"],
            },
        }
    ],
    implementations={"match_profile": match_profile},
    prompt_fragment=(
        "When the user shares a job description:\n"
        "1. Identify the key requirements yourself from the text.\n"
        "2. Call match_profile once per requirement to find their real experience.\n"
        "3. Draft resume bullets grounded ONLY in what match_profile returns.\n"
        "4. State plainly which requirements they have no evidence for.\n"
        "Never invent experience the user does not have."
    ),
)
