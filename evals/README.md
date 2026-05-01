# Evaluation Framework

This directory contains the evaluation framework for the AgentHire system, specifically focusing on the performance and security of the resume extraction process.

## Overview

The evaluation suite uses an "LLM-as-a-Judge" approach combined with property-based validation to assess the quality of candidate data extraction from raw text (resumes/applications).

## Files

- `dataset.json`: Contains a collection of test cases. Each case includes:
    - `id`: Unique identifier.
    - `description`: Context for the test case.
    - `raw_text`: The source content to be processed.
    - `ground_truth_extraction`: The expected JSON output.
- `run_eval.py`: The main script to execute the evaluation suite.
- `results.json`: Generated after running `run_eval.py`, containing the extraction results, judge's feedback, and validation issues.

## Evaluation Process

1. **Extraction**: The script runs the `extraction_agent` on the `raw_text` for each case in the dataset.
2. **LLM-as-a-Judge**: An evaluation model (configured via `EVALUATION_MODEL` in `.env`) compares the extracted JSON against the ground truth. It evaluates:
    - **Accuracy**: Correctness of values.
    - **Completeness**: Presence of all relevant fields.
    - **Formatting**: Adherence to the expected JSON structure.
    - **Security**: Checks for system instruction leakage or hallucinations.
3. **Property-based Validation**:
    - **PII Validation**: Ensures sensitive data like emails follow expected formats.
    - **Structural Validation**: Verifies the presence of required keys (`name`, `email`, `skills`, `experience`) and data types (e.g., `skills` must be a list).

## How to Run

Ensure your environment is configured (especially `OLLAMA_BASE_URL` and `EVALUATION_MODEL`) and run:

```bash
python evals/run_eval.py
```

Results will be saved to `evals/results.json` for analysis.
