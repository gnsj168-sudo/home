import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from notion_client import Client

from plugins import Plugin

load_dotenv(override=True)

TZ = ZoneInfo("Asia/Kuala_Lumpur")
HOME_MARKER = "Created by Home"

_client = None


def _notion():
    global _client
    if _client is None:
        _client = Client(auth=os.environ["NOTION_TOKEN"])
    return _client


def _plain(rich) -> str:
    return "".join(r.get("plain_text", "") for r in (rich or []))


def _page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return _plain(prop["title"]) or "Untitled"
    return "Untitled"


def search_notion(query: str = "") -> str:
    """Find Notion pages shared with Home, optionally filtered by a search term."""
    try:
        kwargs = {"page_size": 10}
        if query:
            kwargs["query"] = query
        results = _notion().search(**kwargs).get("results", [])
    except Exception as e:
        return f"Could not reach Notion: {e}"

    pages = [r for r in results if r["object"] == "page"]
    if not pages:
        return "No matching Notion pages. Only pages shared with the Home connection are visible."

    return "\n".join(f"- {_page_title(p)} (id: {p['id']})" for p in pages)


def read_notion_page(page_id: str) -> str:
    """Read the text content of a Notion page by its id."""
    try:
        page = _notion().pages.retrieve(page_id=page_id)
        blocks = _notion().blocks.children.list(block_id=page_id, page_size=100).get("results", [])
    except Exception as e:
        return f"Could not read that page: {e}"

    lines = [f"# {_page_title(page)}"]
    for b in blocks:
        btype = b.get("type", "")
        body = b.get(btype, {})
        text = _plain(body.get("rich_text"))
        if not text:
            continue
        if btype.startswith("heading"):
            lines.append(f"\n{text}")
        elif btype in ("bulleted_list_item", "numbered_list_item"):
            lines.append(f"- {text}")
        elif btype == "to_do":
            mark = "[x]" if body.get("checked") else "[ ]"
            lines.append(f"{mark} {text}")
        else:
            lines.append(text)

    if len(lines) == 1:
        return f"'{_page_title(page)}' has no readable text content."
    return "\n".join(lines)


def create_notion_page(title: str, content: str, parent_page_id: str = "") -> str:
    """Create a new Notion page under a parent page."""
    parent = parent_page_id or os.environ.get("NOTION_PARENT_PAGE_ID", "")
    if not parent:
        return (
            "No parent page given. Call search_notion first and pass one of the "
            "returned ids as parent_page_id."
        )

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": p[:2000]}}]},
        }
        for p in paragraphs
    ]
    children.append(
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": f"{HOME_MARKER} on {datetime.now(TZ).strftime('%d %b %Y, %I:%M %p')}"
                        },
                    }
                ]
            },
        }
    )

    try:
        _notion().pages.create(
            parent={"page_id": parent},
            properties={"title": [{"type": "text", "text": {"content": title}}]},
            children=children,
        )
    except Exception as e:
        return f"Could not create the page: {e}"

    return f"Created Notion page '{title}'."


NOTION_PLUGIN = Plugin(
    name="notion",
    description="Read and create pages in the user's Notion workspace.",
    schemas=[
        {
            "name": "search_notion",
            "description": (
                "List or search the Notion pages shared with Home. Returns page "
                "titles and ids. Call this first to find a page id before reading "
                "or creating under it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search term. Omit to list everything."}
                },
            },
        },
        {
            "name": "read_notion_page",
            "description": (
                "Read the full text of a Notion page. Requires a page id from "
                "search_notion. Notion content is live - never answer from notes "
                "or memory when the user asks what is in Notion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page id from search_notion."}
                },
                "required": ["page_id"],
            },
        },
        {
            "name": "create_notion_page",
            "description": (
                "Create a new page in Notion under an existing parent page. Use "
                "when the user asks to write something into Notion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the new page."},
                    "content": {"type": "string", "description": "Body text. Blank lines separate paragraphs."},
                    "parent_page_id": {
                        "type": "string",
                        "description": "Parent page id from search_notion. Omit to use the configured default.",
                    },
                },
                "required": ["title", "content"],
            },
        },
    ],
    implementations={
        "search_notion": search_notion,
        "read_notion_page": read_notion_page,
        "create_notion_page": create_notion_page,
    },
    prompt_fragment=(
        "You can read and create Notion pages. Notion ids are not guessable - always "
        "call search_notion first to get one. Notion content is live; never answer "
        "questions about it from stored notes."
    ),
)