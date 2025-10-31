# Ollama Models for TradingAgents

## ✅ Verified Tool-Compatible Models

These models support **tool calling / function calling** which is required for TradingAgents to work:

### Recommended Models

| Model | Size | Speed | Quality | Command |
|-------|------|-------|---------|---------|
| **llama3.2** ⭐ | 3B | Fast | Good | `ollama pull llama3.2` |
| llama3.2:1b | 1B | Fastest | Moderate | `ollama pull llama3.2:1b` |
| llama3.1 | 8B | Medium | Better | `ollama pull llama3.1` |
| mistral-nemo | 12B | Medium | Better | `ollama pull mistral-nemo` |
| qwen2.5 | 7B | Fast | Good | `ollama pull qwen2.5` |

### ⭐ Best Choice for Most Users

```bash
ollama pull llama3.2
```

**Why llama3.2?**
- ✅ Supports tool calling
- ✅ Fast inference
- ✅ Good quality
- ✅ Reasonable memory usage (~4GB)

## Model Details

### llama3.2 (RECOMMENDED)
- **Variants**: 1B, 3B (default)
- **Best For**: General trading analysis
- **Memory**: ~2-4GB
- **Speed**: 2-3 minutes per analysis
- **Tools**: ✅ Full support

```bash
# Default (3B)
ollama pull llama3.2

# Smallest (1B) - fastest
ollama pull llama3.2:1b
```

### llama3.1
- **Variants**: 8B, 70B, 405B
- **Best For**: Higher quality analysis
- **Memory**: ~8GB+ (for 8B)
- **Speed**: 3-5 minutes per analysis
- **Tools**: ✅ Full support

```bash
# Most common (8B)
ollama pull llama3.1

# High quality (70B) - requires powerful GPU
ollama pull llama3.1:70b
```

### mistral-nemo
- **Size**: 12B
- **Best For**: Balanced quality/speed
- **Memory**: ~12GB
- **Speed**: 3-4 minutes per analysis
- **Tools**: ✅ Full support

```bash
ollama pull mistral-nemo
```

### qwen2.5
- **Variants**: 0.5B, 1.5B, 3B, 7B, 14B, 32B, 72B
- **Best For**: Good multilingual support
- **Memory**: Varies (7B ~7GB)
- **Speed**: Fast
- **Tools**: ✅ Full support

```bash
# Default (7B)
ollama pull qwen2.5

# Smaller variants
ollama pull qwen2.5:3b
ollama pull qwen2.5:1.5b
```

## ❌ Models That DON'T Support Tools

These models will **NOT work** with TradingAgents:

- ❌ `llama3` (original)
- ❌ `llama2` 
- ❌ `mistral` (v0.1-0.2)
- ❌ `codellama` (designed for code, not tools)
- ❌ Most older models

## Quick Start

### 1. Install Ollama
Download from: https://ollama.ai

### 2. Pull a Model
```bash
# RECOMMENDED
ollama pull llama3.2

# OR for better quality (slower)
ollama pull llama3.1

# OR for Mistral
ollama pull mistral-nemo
```

### 3. Verify Model Works
```bash
ollama list
```

You should see your model listed.

### 4. Use in TradingAgents

When running the CLI, select:
- **Provider**: Ollama
- **Quick-Thinking LLM**: llama3.2 (or your choice)
- **Deep-Thinking LLM**: llama3.2 (or your choice)

## Performance Comparison

### Speed Test (Single AAPL Analysis)

| Model | Time | Memory | Quality |
|-------|------|--------|---------|
| llama3.2:1b | ~1-2 min | 2GB | ⭐⭐⭐ |
| llama3.2 (3B) | ~2-3 min | 4GB | ⭐⭐⭐⭐ |
| llama3.1 (8B) | ~3-5 min | 8GB | ⭐⭐⭐⭐⭐ |
| mistral-nemo | ~3-4 min | 12GB | ⭐⭐⭐⭐⭐ |
| qwen2.5 | ~2-3 min | 7GB | ⭐⭐⭐⭐ |

*Times approximate on modern consumer hardware (RTX 3060+)*

## Advanced Options

### Different Model Sizes

Many models have variants. List all available versions:

```bash
ollama list | grep llama3.2
```

Pull specific variants:

```bash
# Smallest llama3.2
ollama pull llama3.2:1b

# Default llama3.2
ollama pull llama3.2

# Latest llama3.2
ollama pull llama3.2:latest
```

### Check Model Info

```bash
ollama show llama3.2
```

### Remove Models

```bash
ollama rm llama3
ollama rm mistral
```

## Troubleshooting

### Error: "does not support tools"

**Problem**: You're using a model that doesn't support function calling.

**Solution**: Switch to a supported model:
```bash
ollama pull llama3.2
```

### Slow Performance

**Solution 1**: Use a smaller model
```bash
ollama pull llama3.2:1b
```

**Solution 2**: Check GPU usage
```bash
# Make sure Ollama is using GPU
ollama show llama3.2 | grep gpu
```

### Out of Memory

**Solution**: Use smaller model or reduce context
```bash
# Smallest option
ollama pull llama3.2:1b
```

## Recommendations by Use Case

### Development & Testing
**Fastest**: `llama3.2:1b`
```bash
ollama pull llama3.2:1b
```

### Production (Free/Local)
**Balanced**: `llama3.2` (3B default)
```bash
ollama pull llama3.2
```

### High Quality (Local)
**Best**: `llama3.1` (8B)
```bash
ollama pull llama3.1
```

### Budget GPU
**Efficient**: `qwen2.5:3b`
```bash
ollama pull qwen2.5:3b
```

## Future Models

New models are constantly being released. Check for tool support:

1. Visit: https://ollama.ai/library
2. Look for "Tools" or "Function Calling" in model description
3. Test with: `python quick_test_ollama.py`

## Summary

✅ **Best for most users**: `llama3.2`  
✅ **Best quality (local)**: `llama3.1`  
✅ **Fastest**: `llama3.2:1b`  
✅ **Balanced**: `mistral-nemo` or `qwen2.5`

**Command to get started:**
```bash
ollama pull llama3.2
```

Then run:
```bash
python -m cli.main
```

And select **Ollama** as your provider! 🚀
