def chunk_text(text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """Split text into chunks of at most max_chars, with overlap chars repeated."""
    chunks = []

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue

        if len(para) <= max_chars:
            chunks.append(para)
        else:
            start = 0
            step = max_chars - overlap
            while start < len(para):
                chunks.append(para[start:start + max_chars])
                start += step

    return chunks


if __name__ == "__main__":
    text = open("notes.txt", encoding="utf-8").read()
    chunks = chunk_text(text)
    print(f"{len(chunks)} chunks")
    for i, c in enumerate(chunks[:3]):
        print(f"\n--- {i} ({len(c)} chars) ---\n{c}")