"""Minimal public inference example for FinVector-Market-4B on Apple Silicon."""

from huggingface_hub import snapshot_download
from mlx_lm import generate, load


ADAPTER_ID = "alinakhay/FinVector-Market-4B"
BASE_MODEL = "Qwen/Qwen3.5-4B"
BASE_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"


def main() -> None:
    adapter_dir = snapshot_download(ADAPTER_ID)
    model, tokenizer = load(
        BASE_MODEL,
        revision=BASE_REVISION,
        adapter_path=adapter_dir,
    )

    # This small public schema is an inference example, not a training or benchmark prompt.
    messages = [
        {
            "role": "user",
            "content": (
                "Return exactly one valid JSON object with keys tone, confidence, and rationale. "
                "tone must be one of hawkish, neutral, or dovish; confidence must be a number "
                "from 0 to 1. Interpret this statement: The committee held rates steady while "
                "emphasizing that inflation risks remain persistent."
            ),
        }
    ]
    prompt = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=False,
        enable_thinking=False,
    )
    response = generate(model, tokenizer, prompt=prompt, max_tokens=700)
    print(response)


if __name__ == "__main__":
    main()
