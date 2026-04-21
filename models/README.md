# AgentHire Local Model Management

AgentHire uses local LLMs via Ollama to ensure complete data privacy during the application review process. This repository includes dedicated `Modelfile` definitions to build and run the specific models required for each agent in the LangGraph pipeline.

## Prerequisites

1.  **Install Ollama:**
    Download and install Ollama from [ollama.com](https://ollama.com).
2.  **Ensure Ollama is Running:**
    Start the Ollama app or run `ollama serve` in your terminal.

## Model Overview

AgentHire uses different models optimized for specific tasks. Phase 1 currently implements the **Extraction Agent**.

| Agent      | Base Model      | Custom Model Name     | Modelfile Path         | Purpose                                      |
| ---------- | --------------- | --------------------- | ---------------------- | -------------------------------------------- |
| Extraction | `smollm:360m`   | `agenthire-extractor` | `models/extractor.Modelfile` | Strict JSON parsing of unstructured text.    |
| Evaluation | `gemma3:1b`     | *Pending (Phase 2)* | *Pending* | Scoring applications against a rubric.       |
| Decision   | `phi4-mini`     | *Pending (Phase 3)* | *Pending* | Threshold logic and reasoning generation.    |

## Building the Models

You must build the custom models before running the FastAPI server or tests. The build process pulls the base model and bakes in the system prompts and temperature settings defined in the Modelfiles.

### 1. Build the Extraction Agent Model (Phase 1)

1. Open your terminal in the `agenthire` project root.
2. Run the following command:

```bash
ollama create agenthire-extractor -f models/extractor.Modelfile
```

Ollama will pull the `smollm:360m` base model (if you don't already have it) and create the custom `agenthire-extractor` model.

### 2. Verify the Build

Check that the model is available locally:

```bash
ollama list
```
You should see `agenthire-extractor:latest` in the output list.

## Usage in Code

The models are pre-configured in the agent nodes. You do not need to change the code unless you are customizing the model names.

**Example (`app/agents/extraction_agent.py`):**
```python
from langchain_ollama import OllamaLLM

_LLM = OllamaLLM(
    model="agenthire-extractor",  # Calls the custom model built above
    temperature=0.0,              # Overrides local default to ensure JSON compliance
    format="json",
)
```

## Updating Models

If you modify the `Modelfile` (for example, to refine the system prompt or change the schema), you must rebuild the model to apply the changes:

```bash
# Rebuilds the model, overwriting the previous version
ollama create agenthire-extractor -f models/extractor.Modelfile
```
