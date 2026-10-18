"""Offline tests for the Gemini adapter: message translation both ways."""

from google.genai import types

from filament_agent.gemini_llm import from_response, to_contents, to_declarations
from filament_agent.graph import FINAL_ANSWER_TOOL


def response(*parts, finish="STOP"):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)),
                                    finish_reason=finish)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=10, thoughts_token_count=5),
        model_version="gemini-test-001",
    )


def test_function_call_becomes_tool_use_and_keeps_signature():
    r = from_response(response(
        types.Part(text="thinking...", thought=True),
        types.Part(function_call=types.FunctionCall(name="list_spools", args={}), thought_signature=b"sig"),
    ), "gemini-x")
    assert r.stop_reason == "tool_use"
    call = r.tool_calls[0]
    assert call["name"] == "list_spools" and call["id"].startswith("call_")
    assert r.text == ""  # thought text is never shown
    assert (r.input_tokens, r.output_tokens, r.model) == (100, 15, "gemini-test-001")
    raw = next(b for b in r.content if b["type"] == "gemini_parts")["parts"]
    assert raw[1]["function_call"]["id"] == call["id"]

    # Replaying: the stored parts go back verbatim, signature included; results map by id.
    messages = [
        {"role": "user", "content": "how much?"},
        {"role": "assistant", "content": r.content},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call["id"], "content": '{"spools":[]}'}]},
    ]
    contents = to_contents(messages)
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[1].thought_signature == b"sig"
    fr = contents[2].parts[0].function_response
    assert (fr.name, fr.id, fr.response) == ("list_spools", call["id"], {"result": {"spools": []}})


def test_error_results_and_plain_messages():
    messages = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "get_spool", "input": {"spool_id": 9}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "spool 9 not found",
                                      "is_error": True}]},
        {"role": "user", "content": "Please give your answer by calling the final_answer tool."},
    ]
    contents = to_contents(messages)
    assert contents[1].parts[0].function_call.args == {"spool_id": 9}
    assert contents[2].parts[0].function_response.response == {"error": "spool 9 not found"}
    assert contents[3].parts[0].text.startswith("Please")


def test_finish_reasons():
    assert from_response(response(types.Part(text="hi")), "m").stop_reason == "end_turn"
    assert from_response(response(types.Part(text="..."), finish="MAX_TOKENS"), "m").stop_reason == "max_tokens"
    assert from_response(response(types.Part(text=""), finish="SAFETY"), "m").stop_reason == "refusal"
    blocked = types.GenerateContentResponse(prompt_feedback=types.GenerateContentResponsePromptFeedback(
        block_reason="SAFETY"))
    assert from_response(blocked, "m").stop_reason == "refusal"


def test_declarations_accept_our_schemas():
    decl = to_declarations([FINAL_ANSWER_TOOL])[0].function_declarations[0]
    assert decl.name == "final_answer"
    assert decl.parameters_json_schema["properties"]["grams_needed"]["type"] == ["number", "null"]
