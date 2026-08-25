import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import TOOL_SCHEMAS, TOOL_IMPLEMENTATIONS

from memory import save_message, load_history

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-3.6-flash"
MAX_ITERATIONS = 8

SYSTEM_PROMPT = """You are Home, a personal assistant for the user.

You have tools available. Use search_notes whenever the question concerns the
user's own research, projects, or background — do not answer those from memory.
When you use retrieved notes, cite the chunk numbers you relied on.
If the notes contain nothing relevant, say so plainly."""

def run_agent(question: str, conversation_id: str | None = None, verbose: bool = True) -> dict:
    contents = []

    if conversation_id:
        for msg in load_history(conversation_id):
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=msg["content"])])
            )

    contents.append(
        types.Content(role="user", parts=[types.Part(text=question)])
    )
    tool_calls_made = []

    for i in range(MAX_ITERATIONS):
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(function_declarations=TOOL_SCHEMAS)],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if p.function_call]

        if not function_calls:
            answer = response.text
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

            fn = TOOL_IMPLEMENTATIONS.get(name)
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
    convo = "test-session-1"

    for q in [
        "what were my HTNet results?",
        "what was the UAR again?",
        "and what hardware did I run it on?",
    ]:
        print(f"\n=== {q} ===")
        result = run_agent(q, conversation_id=convo)
        print(result["answer"])
        print(f"({result['iterations']} iterations, {len(result['tool_calls'])} tool calls)")