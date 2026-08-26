import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from memory import save_message, load_history
from plugins import PluginRegistry
from tools import CORE_PLUGIN
from internship import INTERNSHIP_PLUGIN
from calendar_plugin import CALENDAR_PLUGIN
from notion_plugin import NOTION_PLUGIN

load_dotenv(override=True)
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = os.environ.get("MODEL", "gemini-3.6-flash")
MAX_ITERATIONS = 8

registry = PluginRegistry()
registry.register(CORE_PLUGIN)
registry.register(INTERNSHIP_PLUGIN)
registry.register(CALENDAR_PLUGIN)
registry.register(NOTION_PLUGIN)

BASE_PROMPT = """You are Home, a personal assistant for the user.

Reply in plain text. Do not use markdown — no asterisks for bold, no hash headings,
no bullet syntax. For lists, put each item on its own line starting with a dash.
Keep answers short.

When you use retrieved notes, cite the chunk numbers you relied on.
If the notes contain nothing relevant, say so plainly."""


def system_prompt() -> str:
    return BASE_PROMPT + "\n\n" + registry.prompt_fragments()


def run_agent(question: str, conversation_id: str | None = None, verbose: bool = True) -> dict:
    contents = []

    if conversation_id:
        for msg in load_history(conversation_id):
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=msg["content"])])
            )

    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    tool_calls_made = []

    for i in range(MAX_ITERATIONS):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt(),
                    tools=[types.Tool(function_declarations=registry.schemas())],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )
        except Exception as e:
            return {
                "answer": f"The model is unavailable right now ({type(e).__name__}). Please try again shortly.",
                "tool_calls": tool_calls_made,
                "iterations": i + 1,
                "error": str(e),
            }

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if p.function_call]

        if not function_calls:
            answer = response.text or "I wasn't able to produce an answer for that."
            if conversation_id:
                save_message(conversation_id, "user", question)
                save_message(conversation_id, "assistant", answer, tool_calls_made)
            return {
                "answer": answer,
                "tool_calls": tool_calls_made,
                "iterations": i + 1,
            }

        contents.append(candidate.content)

        result_parts = []
        for call in function_calls:
            name = call.name
            args = dict(call.args or {})
            if verbose:
                print(f"  [iteration {i+1}] calling {name}({args})")
            tool_calls_made.append({"name": name, "args": args})

            fn = registry.implementations().get(name)
            if fn is None:
                output = f"Error: no tool named {name}."
            else:
                try:
                    output = fn(**args)
                except Exception as e:
                    output = f"Error running {name}: {e}"

            result_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=name, response={"result": output}
                    )
                )
            )

        contents.append(types.Content(role="user", parts=result_parts))

    return {
        "answer": "I couldn't complete that within the iteration limit.",
        "tool_calls": tool_calls_made,
        "iterations": MAX_ITERATIONS,
    }

if __name__ == "__main__":
    print(f"using model: {MODEL}")
    print(f"plugins loaded: {registry.loaded()}")

    jd = """AI Engineer Intern — Kuala Lumpur

Requirements:
- Experience building applications with large language models
- Familiarity with retrieval-augmented generation and vector databases
- Python and REST API development
- Kubernetes and distributed systems experience
- Strong background in computer vision or deep learning research"""

    result = run_agent(
        f"Here's a job description. Draft resume bullets for it:\n\n{jd}",
        conversation_id="internship-test",
    )
    print("\n" + result["answer"])
    print(f"\n({result['iterations']} iterations, {len(result['tool_calls'])} tool calls)")

if __name__ == "__main__":
    r = run_agent(
        "create a notion page called Home test with a short note saying this was written by my agent",
        conversation_id="notion-write",
    )
    print(r["answer"])
    print(f"tools: {[t['name'] for t in r['tool_calls']]}")

    