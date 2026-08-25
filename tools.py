from retrieval import search

MAX_DISTANCE = 0.45


def search_notes(query: str) -> str:
    """Search the user's personal notes and return relevant passages."""
    hits = search(query, k=3)
    hits = [h for h in hits if h["distance"] <= MAX_DISTANCE]

    if not hits:
        return "No relevant notes found."

    return "\n\n".join(
        f"[chunk {h['id']}, distance {h['distance']:.3f}]\n{h['content']}"
        for h in hits
    )


TOOL_SCHEMAS = [
    {
        "name": "search_notes",
        "description": (
            "Search the user's personal notes and documents for information about "
            "their research, projects, coursework, or background. Use this whenever "
            "the question refers to the user's own work or life."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, phrased as a natural question or topic.",
                }
            },
            "required": ["query"],
        },
    }
]

TOOL_IMPLEMENTATIONS = {
    "search_notes": search_notes,
}