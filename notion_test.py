import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv(override=True)
notion = Client(auth=os.environ["NOTION_TOKEN"])

results = notion.search(page_size=10).get("results", [])
print(f"{len(results)} objects visible to this integration\n")

for r in results:
    kind = r["object"]
    title = "Untitled"
    if kind == "page":
        for prop in r.get("properties", {}).values():
            if prop.get("type") == "title" and prop["title"]:
                title = prop["title"][0]["plain_text"]
                break
    elif kind == "database":
        t = r.get("title", [])
        title = t[0]["plain_text"] if t else "Untitled"
    print(f"- [{kind}] {title}")
    print(f"  id: {r['id']}")