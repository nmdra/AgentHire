from langchain_ollama import OllamaLLM
llm = OllamaLLM(model="test", temperature=0, top_k=10, top_p=0.9, repeat_penalty=1.1, seed=42, num_ctx=2048, num_predict=600, stop=["<|end-output|>", "<|endoftext|>"])
print("OK")
