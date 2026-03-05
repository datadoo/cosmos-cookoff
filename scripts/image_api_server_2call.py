#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "flask>=3.0.0",
#   "openai",
#   "pydantic>=2.0",
#   "pyyaml",
#   "pillow",
# ]
# ///

"""
Two-Call Image Traversability Analysis API Server.

This server receives images via REST API and returns terrain traversability
analysis using a two-step approach:
  1. Reasoning call: Cosmos-Reason2 with reasoning enabled (no JSON schema)
  2. Extraction call: Structured JSON extraction from the reasoning output

Usage:
    # Terminal 1: Start vLLM server
    vllm serve nvidia/Cosmos-Reason2-2B --port 8000 --host 0.0.0.0

    # Terminal 2: Start this API server
    python scripts/image_api_server_2call.py --port 5000 --vllm-port 8000

    # From client machine
    curl -X POST http://server:5000/analyze -F "image=@picture.jpg"

Endpoints:
    POST /analyze - Analyze an image for terrain traversability (two-call)
    GET /health   - Health check endpoint
"""

import argparse
import base64
import io
import json
import sys
from pathlib import Path
from typing import Literal

import pydantic
import yaml
from flask import Flask, request, jsonify
from PIL import Image

ROOT = Path(__file__).parents[1]


# =============================================================================
# Reasoning Prompt
# =============================================================================

REASONING_PROMPT = """Answer the question using the following format:

<think>
Your reasoning.
</think>
<answer>
Your answer.
</answer>
"""


# =============================================================================
# Pydantic Schema for Structured Output
# =============================================================================


class PathEvaluation(pydantic.BaseModel):
    """Simplified evaluation of a single path."""

    surface: str = pydantic.Field(
        description="Terrain type (e.g., asphalt, grass, mud, snow)"
    )
    grip: Literal["low", "medium", "high"] = pydantic.Field(
        description="estimated grip level"
    )
    confidence: float = pydantic.Field(
        ge=0.0, le=1.0, description="Traversability confidence 0.0-1.0 based on grip"
    )

class ImageTraversabilityAnalysis(pydantic.BaseModel):
    """Path decision using left/right naming."""

    left_path: PathEvaluation = pydantic.Field(
        description="Left slope evaluation"
    )
    right_path: PathEvaluation = pydantic.Field(
        description="Right slope evaluation"
    )
    chosen_path: Literal["left", "right"] = pydantic.Field(
        description="Recommended path: 'left' or 'right'"
    )
    reason: str = pydantic.Field(
        description="One sentence explanation of the decision"
    )



# =============================================================================
# Prompt Loading
# =============================================================================


def load_prompt_from_yaml(prompt_path: Path) -> str:
    """Load user prompt from YAML file."""
    with open(prompt_path, "r") as f:
        data = yaml.safe_load(f)
    if "user_prompt" not in data:
        raise ValueError(f"YAML file {prompt_path} must contain 'user_prompt' key")
    return data["user_prompt"]


def get_default_prompt() -> str:
    """Get the default image traversability analysis prompt."""
    default_path = ROOT / "prompts" / "image_traversability.yaml"
    if default_path.exists():
        return load_prompt_from_yaml(default_path)
    raise FileNotFoundError(
        f"Default prompt file not found: {default_path}. "
        "Please provide --prompt argument."
    )


# =============================================================================
# Image Processing
# =============================================================================


def image_to_base64(image_bytes: bytes) -> str:
    """Convert image bytes to base64 data URL."""
    img = Image.open(io.BytesIO(image_bytes))

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def parse_json_from_text(text: str) -> dict:
    """Extract JSON object from text output."""
    text = text.strip()
    start_idx = text.find("{")
    end_idx = text.rfind("}")

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        raise ValueError(f"Could not find valid JSON in output: {text[:200]}")

    json_str = text[start_idx : end_idx + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}. Text: {json_str[:200]}")


# =============================================================================
# Flask Application
# =============================================================================


def create_app(
    vllm_host: str,
    vllm_port: int,
    model_name: str | None,
    prompt_text: str,
    reasoning_max_tokens: int = 4096,
    extraction_max_tokens: int = 1024,
    temperature: float = 0.05,
) -> Flask:
    """Create and configure the Flask application.

    Args:
        vllm_host: vLLM server hostname
        vllm_port: vLLM server port
        model_name: Model name (None for auto-detect)
        prompt_text: The prompt text to use for analysis
        reasoning_max_tokens: Max tokens for reasoning call
        extraction_max_tokens: Max tokens for extraction call
        temperature: Sampling temperature

    Returns:
        Configured Flask application
    """
    import openai

    app = Flask(__name__)

    client = openai.OpenAI(
        api_key="EMPTY",
        base_url=f"http://{vllm_host}:{vllm_port}/v1",
    )

    detected_model = model_name
    if detected_model is None:
        try:
            models = client.models.list()
            detected_model = models.data[0].id
            print(f"Auto-detected model: {detected_model}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not auto-detect model: {e}", file=sys.stderr)
            detected_model = "nvidia/Cosmos-Reason2-2B"

    app.config["openai_client"] = client
    app.config["model_name"] = detected_model
    app.config["prompt_text"] = prompt_text
    app.config["reasoning_max_tokens"] = reasoning_max_tokens
    app.config["extraction_max_tokens"] = extraction_max_tokens
    app.config["temperature"] = temperature
    app.config["vllm_host"] = vllm_host
    app.config["vllm_port"] = vllm_port

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        vllm_ok = False
        try:
            app.config["openai_client"].models.list()
            vllm_ok = True
        except Exception:
            pass

        return jsonify({
            "status": "ok" if vllm_ok else "degraded",
            "vllm_connected": vllm_ok,
            "model": app.config["model_name"],
            "vllm_endpoint": f"http://{app.config['vllm_host']}:{app.config['vllm_port']}/v1",
            "mode": "two-call",
        })

    @app.route("/analyze", methods=["POST"])
    def analyze():
        """Analyze an image for terrain traversability using two LLM calls.

        Call 1: Reasoning with <think> tags (no JSON schema)
        Call 2: Structured JSON extraction from reasoning output

        Accepts:
            - multipart/form-data with 'image' file
            - application/json with 'image_base64' field

        Returns:
            JSON with:
              - reasoning: Full reasoning output including <think> tags
              - analysis: Structured JSON data
        """
        try:
            if request.content_type and "multipart/form-data" in request.content_type:
                if "image" not in request.files:
                    return jsonify({"error": "No 'image' file in request"}), 400
                image_file = request.files["image"]
                image_bytes = image_file.read()
            elif request.is_json:
                data = request.get_json()
                if "image_base64" not in data:
                    return jsonify({"error": "No 'image_base64' field in JSON"}), 400
                image_bytes = base64.b64decode(data["image_base64"])
            else:
                return jsonify({
                    "error": "Invalid content type. Use multipart/form-data or application/json"
                }), 400

            if len(image_bytes) == 0:
                return jsonify({"error": "Empty image data"}), 400

            image_b64_url = image_to_base64(image_bytes)

            # =================================================================
            # CALL 1: Reasoning (no JSON schema)
            # =================================================================
            reasoning_prompt = app.config["prompt_text"] + "\n\n" + REASONING_PROMPT

            messages_reasoning = [
                {
                    "role": "system",
                    "content": "You are a 1/10 scale RC car navigation assistant.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_b64_url}},
                        {"type": "text", "text": reasoning_prompt},
                    ],
                },
            ]

            response1 = app.config["openai_client"].chat.completions.create(
                model=app.config["model_name"],
                messages=messages_reasoning,
                max_tokens=app.config["reasoning_max_tokens"],
                temperature=app.config["temperature"],
            )
            reasoning_output = response1.choices[0].message.content

            # =================================================================
            # CALL 2: Structured JSON extraction
            # =================================================================
            extraction_prompt = f"""Based on the following terrain analysis, extract the structured path decision.

Analysis:
{reasoning_output}

Extract the path evaluations and decision into the required JSON format."""

            messages_extraction = [
                {
                    "role": "system",
                    "content": "You are a data extraction assistant. Extract structured information from terrain analysis.",
                },
                {
                    "role": "user",
                    "content": extraction_prompt,
                },
            ]

            response2 = app.config["openai_client"].chat.completions.create(
                model=app.config["model_name"],
                messages=messages_extraction,
                max_tokens=app.config["extraction_max_tokens"],
                temperature=0.1,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ImageTraversabilityAnalysis",
                        "schema": ImageTraversabilityAnalysis.model_json_schema(),
                    },
                },
            )
            extraction_content = response2.choices[0].message.content

            result_json = parse_json_from_text(extraction_content)
            validated = ImageTraversabilityAnalysis.model_validate(result_json)

            # Map left/right to numeric 0/1
            chosen_numeric = 0 if validated.chosen_path == "left" else 1

            return jsonify({
                "reasoning": reasoning_output,
                "chosen_path": chosen_numeric,
                "analysis": {
                    "left_path": validated.left_path.model_dump(),
                    "right_path": validated.right_path.model_dump(),
                    "reason": validated.reason,
                },
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/schema", methods=["GET"])
    def schema():
        """Return the JSON schema used for structured output."""
        return jsonify(ImageTraversabilityAnalysis.model_json_schema())

    return app


# =============================================================================
# Main Entry Point
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Two-Call Image Traversability Analysis API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start server with default settings
  %(prog)s --port 5000 --vllm-port 8000

  # Start with custom model
  %(prog)s --port 5000 --vllm-port 8000 --model nvidia/Cosmos-Reason2-8B

  # With custom prompt
  %(prog)s --port 5000 --vllm-port 8000 --prompt my_prompt.yaml

  # Adjust token limits
  %(prog)s --reasoning-max-tokens 4096 --extraction-max-tokens 1024

Client usage:
  # With curl (file upload)
  curl -X POST http://localhost:5000/analyze -F "image=@terrain.jpg"

  # Response includes:
  #   - reasoning: Full <think>...</think> output
  #   - analysis: Structured JSON data

  # Health check
  curl http://localhost:5000/health

  # Get schema
  curl http://localhost:5000/schema
        """,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="API server port (default: 5000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="API server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--vllm-host",
        type=str,
        default="localhost",
        help="vLLM server hostname (default: localhost)",
    )
    parser.add_argument(
        "--vllm-port",
        type=int,
        default=8000,
        help="vLLM server port (default: 8000)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: auto-detect from vLLM server)",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=None,
        help="Path to YAML file containing user_prompt",
    )
    parser.add_argument(
        "--reasoning-max-tokens",
        type=int,
        default=4096,
        help="Maximum tokens for reasoning call (default: 4096)",
    )
    parser.add_argument(
        "--extraction-max-tokens",
        type=int,
        default=1024,
        help="Maximum tokens for extraction call (default: 1024)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.05,
        help="Sampling temperature for reasoning (default: 0.05)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode",
    )

    args = parser.parse_args()

    if args.prompt:
        if not args.prompt.exists():
            raise FileNotFoundError(f"Prompt file not found: {args.prompt}")
        prompt_text = load_prompt_from_yaml(args.prompt)
    else:
        prompt_text = get_default_prompt()

    print(f"Starting Two-Call Image Traversability API Server", file=sys.stderr)
    print(f"  API endpoint: http://{args.host}:{args.port}", file=sys.stderr)
    print(f"  vLLM backend: http://{args.vllm_host}:{args.vllm_port}/v1", file=sys.stderr)
    print(f"  Reasoning max tokens: {args.reasoning_max_tokens}", file=sys.stderr)
    print(f"  Extraction max tokens: {args.extraction_max_tokens}", file=sys.stderr)

    app = create_app(
        vllm_host=args.vllm_host,
        vllm_port=args.vllm_port,
        model_name=args.model,
        prompt_text=prompt_text,
        reasoning_max_tokens=args.reasoning_max_tokens,
        extraction_max_tokens=args.extraction_max_tokens,
        temperature=args.temperature,
    )

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    # Uncomment and modify the args below to test without command line.
    #
    # args = argparse.Namespace(
    #     port=5000,                    # API server port
    #     host="0.0.0.0",               # API server bind address
    #     vllm_host="localhost",        # vLLM server hostname
    #     vllm_port=8000,               # vLLM server port
    #     model=None,                   # Model name (None = auto-detect)
    #     prompt=None,                  # Path to custom prompt YAML (None = default)
    #     reasoning_max_tokens=4096,    # Max tokens for reasoning call
    #     extraction_max_tokens=1024,   # Max tokens for extraction call
    #     temperature=0.05,             # Sampling temperature
    #     debug=True,                   # Enable Flask debug mode
    # )
    #
    # # Load prompt
    # if args.prompt:
    #     prompt_text = load_prompt_from_yaml(args.prompt)
    # else:
    #     prompt_text = get_default_prompt()
    #
    # print(f"Starting Two-Call Image Traversability API Server (DEBUG)", file=sys.stderr)
    # print(f"  API endpoint: http://{args.host}:{args.port}", file=sys.stderr)
    # print(f"  vLLM backend: http://{args.vllm_host}:{args.vllm_port}/v1", file=sys.stderr)
    #
    # app = create_app(
    #     vllm_host=args.vllm_host,
    #     vllm_port=args.vllm_port,
    #     model_name=args.model,
    #     prompt_text=prompt_text,
    #     reasoning_max_tokens=args.reasoning_max_tokens,
    #     extraction_max_tokens=args.extraction_max_tokens,
    #     temperature=args.temperature,
    # )
    # app.run(host=args.host, port=args.port, debug=args.debug)
    # =========================================================================

    main()
