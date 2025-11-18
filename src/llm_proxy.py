import asyncio
from typing import Any, Awaitable, Callable, Dict, List

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
import tiktoken

import config


enc = tiktoken.encoding_for_model("gpt-4")

def truncate_tokens(text: str) -> str:
    """
    Count the number of tokens in a text.
    """
    tokens = enc.encode(text)

    # count tokens
    length = len(tokens)

    if length > config.MAX_TOKENS_PER_TOOL_RESPONSE:
        # truncate the text
        text = enc.decode(tokens[:config.MAX_TOKENS_PER_TOOL_RESPONSE])
        text += "\n... [truncated because it exceeds the max tokens limit, try deeper paths]"

    return text

def _create_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=config.BASE_URL,
        api_key=config.API_KEY,
    )


def is_gpt_oss_model(model: str | None) -> bool:
    """Return True when the requested model points at a local GPT-OSS build."""
    if not model:
        return False
    return "gpt-oss" in model.lower()


def get_llm(model: str = None) -> OpenAIChatModel:
    """Initialize and return the specified LLM"""

    model = model or config.MODEL

    model = OpenAIChatModel(
        model_name=model,
        provider=OpenAIProvider(
            base_url=config.BASE_URL,
            api_key=config.API_KEY
        ),
        settings=OpenAIChatModelSettings(
            temperature=0.0,
            max_tokens=36000,
            timeout=300
        )
    )

    return model
    
async def run_llm_natively(model: str = None, prompt: str = None, messages: list[dict] = None) -> str:
    client = _create_async_client()

    if messages is None:
        messages = [{"role": "user", "content": prompt}]

    response = await client.chat.completions.create(
        model=model or config.MODEL,
        messages=messages,
    )

    return response.choices[0].message.content


async def run_chat_with_tools(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    handle_tool_call: Callable[[Dict[str, Any]], Awaitable[str]],
) -> str:
    """
    Execute a Chat Completions conversation that supports tool calls (e.g., GPT-OSS on Ollama).

    Parameters
    ----------
    model:
        Target model identifier (e.g., gpt-oss:20b).
    messages:
        Initial conversation history (system prompt + user prompt, etc.).
    tools:
        The tool/function schema definitions to expose to the model.
    handle_tool_call:
        Coroutine invoked for each tool_call payload. It receives the raw tool_call dict and
        must return a string result that will be passed back to the model as a tool message.

    Returns
    -------
    str:
        Final assistant message content.
    """

    client = _create_async_client()
    conversation: List[Dict[str, Any]] = list(messages)
    tool_invocations = 0

    while True:
        response = await client.chat.completions.create(
            model=model,
            messages=conversation,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=False,
        )
        message = response.choices[0].message

        if message.tool_calls:
            tool_calls_payload = []
            for tc in message.tool_calls:
                payload = {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                tool_calls_payload.append(payload)

            conversation.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": tool_calls_payload,
                }
            )

            for tool_call in tool_calls_payload:
                tool_invocations += 1
                tool_response = await handle_tool_call(tool_call)
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_response,
                    }
                )
            continue

        if tool_invocations == 0:
            print("Warning: GPT-OSS returned an answer without making any docs_navigator tool calls.")

        return message.content or ""

if __name__ == "__main__":
    result = asyncio.run(run_llm_natively(model="gpt-oss-120b", messages=[{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "Hello, world!"}]))
    print(result)

# ------------------------------------------------------------
# Embeddings
# ------------------------------------------------------------

async def get_embeddings(texts: list[str]) -> list[list[float]]:
    client = AsyncOpenAI(
        base_url=config.BASE_URL,
        api_key=config.API_KEY,
    )
    response = await client.embeddings.create(
        input=texts,
        model=config.EMBEDDING_MODEL,
    )

    return [embedding.embedding for embedding in response.data]
