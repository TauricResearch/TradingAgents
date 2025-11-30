---
description: How to install Miniconda in WSL2
---

1. Download the Miniconda installer script:
```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
```

2. Run the installer script:
```bash
bash Miniconda3-latest-Linux-x86_64.sh
```
   - Press **Enter** to review the license.
   - Type **yes** to accept the license terms.
   - Press **Enter** to confirm the installation location.
   - Type **yes** when asked to initialize Miniconda3.

3. Activate the changes (or restart your terminal):
```bash
source ~/.bashrc
```

4. Verify installation:
```bash
conda --version
```

5. (Optional) Create your environment:
```bash
conda create -n tradingagents python=3.10
conda activate tradingagents
pip install -r requirements.txt
```
