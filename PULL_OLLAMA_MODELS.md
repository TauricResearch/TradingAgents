# Quick Guide: Pull Ollama Models for TradingAgents

## ⚠️ IMPORTANT: Pull Models Before Running

When you see a **404 error** like:
```
ResponseError: 404 page not found (status code: 404)
```

It means **the model isn't downloaded yet**. You must pull it first!

## 📥 How to Pull Models

Open a terminal and run:

```bash
# RECOMMENDED - Start with this
ollama pull llama3.2

# OR choose from these tool-compatible models:
ollama pull llama3.2:1b       # Fastest (1B)
ollama pull llama3.1          # Better quality (8B)
ollama pull mistral-nemo      # Mistral (12B)
ollama pull qwen2.5:7b        # Qwen (7B)
ollama pull qwen2.5-coder:7b  # Coding-focused (7B)
```

## ✅ Verify Models Are Installed

```bash
ollama list
```

You should see your models listed:
```
NAME            ID              SIZE    MODIFIED
llama3.2:latest abc123...       2.0 GB  2 minutes ago
mistral-nemo    def456...       7.1 GB  1 hour ago
```

## 🎯 Recommended Setup for TradingAgents

### For Quick Testing (Fastest)
```bash
ollama pull llama3.2:1b
```
- **Size**: ~1GB
- **Speed**: Very fast
- **Quality**: Good enough for testing

### For Production Use (Balanced)
```bash
ollama pull llama3.2
```
- **Size**: ~2GB
- **Speed**: Fast
- **Quality**: Good

### For Best Quality (Slower)
```bash
ollama pull llama3.1
```
- **Size**: ~5GB
- **Speed**: Medium
- **Quality**: Excellent

### For Mistral Fans
```bash
ollama pull mistral-nemo
```
- **Size**: ~7GB
- **Speed**: Medium
- **Quality**: Excellent

### For Qwen Models
```bash
# Standard Qwen
ollama pull qwen2.5:7b

# OR Coding-focused variant
ollama pull qwen2.5-coder:7b
```
- **Size**: ~4-5GB each
- **Speed**: Fast
- **Quality**: Very good

## 🚀 Complete Workflow

### 1. Pull a Model
```bash
ollama pull llama3.2
```

### 2. Verify It's Downloaded
```bash
ollama list
```

### 3. Run TradingAgents
```bash
python -m cli.main
```

### 4. Select Settings
- **Provider**: Ollama
- **Quick-Thinking**: llama3.2 (or your choice)
- **Deep-Thinking**: llama3.2 (or your choice)

## 📊 Model Comparison

| Model | Size | Download Time* | RAM Usage | Speed | Quality | Tools Support |
|-------|------|---------------|-----------|-------|---------|---------------|
| **llama3.2:1b** | 1GB | ~1 min | 2GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ |
| **llama3.2** | 2GB | ~2 min | 4GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ |
| **llama3.1** | 5GB | ~5 min | 8GB | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ |
| **mistral-nemo** | 7GB | ~7 min | 12GB | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ |
| **qwen2.5:7b** | 4.7GB | ~5 min | 7GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ |
| **qwen2.5-coder** | 4.7GB | ~5 min | 7GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ |

*Approximate download time on typical broadband connection

## ⚡ Pro Tips

### 1. Pull Multiple Models
You can have multiple models installed and switch between them:
```bash
ollama pull llama3.2     # Fast for testing
ollama pull llama3.1     # High quality for production
```

### 2. Check Model Info
```bash
ollama show llama3.2
```

### 3. Remove Unwanted Models
```bash
ollama rm llama3  # Remove old llama3 (doesn't support tools)
```

### 4. Keep Models Updated
```bash
ollama pull llama3.2  # Updates to latest version
```

## 🐛 Troubleshooting

### Error: "404 page not found"
**Solution**: Model not downloaded. Pull it first:
```bash
ollama pull llama3.2
```

### Error: "model 'qwen2.5' not found"
**Solution**: Use full tag:
```bash
ollama pull qwen2.5:7b  # Not just "qwen2.5"
```

### Slow Performance
**Solution**: Use smaller model:
```bash
ollama pull llama3.2:1b
```

### Out of Memory
**Solution**: Use smaller model or close other applications:
```bash
ollama pull llama3.2:1b  # Only needs ~2GB RAM
```

### Model Takes Forever to Download
**Solution**: Start with smallest model:
```bash
ollama pull llama3.2:1b  # Only 1GB download
```

## 🎓 Learning Path

### Beginner
1. Start with: `ollama pull llama3.2:1b`
2. Test with simple analysis
3. Upgrade if needed

### Intermediate
1. Use: `ollama pull llama3.2`
2. Good balance of speed and quality
3. Most popular choice

### Advanced
1. Try: `ollama pull llama3.1` or `mistral-nemo`
2. Best quality for complex analysis
3. Requires more resources

## 📝 Summary

**TL;DR - Quick Start:**

```bash
# 1. Pull the recommended model
ollama pull llama3.2

# 2. Verify it's there
ollama list

# 3. Run the app
python -m cli.main
```

**That's it!** 🚀

---

## Need Help?

Check if Ollama is running:
```bash
ollama list
```

If you see an error, start Ollama:
```bash
ollama serve
```

Then pull your model and try again!
