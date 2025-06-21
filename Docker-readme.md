# Local run with Docker or docker-compose

## Environment Configuration with .env

This project uses a `.env` file to manage environment-specific configurations for local development, especially when using Docker Compose. This allows you to customize settings without modifying version-controlled files like `docker-compose.yml`.

### Setup
1.  **Create your local `.env` file:**
    Copy the example configuration to a new `.env` file:
    ```bash
    cp .env.example .env
    ```
2.  **Customize your `.env` file:**
    Open the `.env` file in a text editor and modify the variables as needed for your local setup. For example, you might want to change LLM models or API keys. 

### How it Works with Docker Compose
When you run `docker-compose up` or `docker-compose run`, Docker Compose automatically looks for a `.env` file in the project root directory (where `docker-compose.yml` is located) and loads the environment variables defined in it. These variables are then passed into the container environment for the `app` service.

The `.env` file itself is ignored by Git (as specified in `.gitignore`), so your local configurations will not be committed to the repository.

For streamlined experience, it is recommended to use docker compose as it simplifies experience eg handles mounting of directories for caching. Skip to [Docker Compose](#using-docker-compose) section for this.


## Running with Docker

This project supports running within a Docker container, which ensures a consistent environment for development and testing. 

### Prerequisites
- Docker installed and running on your system.

### Build the Docker Image
Navigate to the root directory of the project (where the `Dockerfile` is located) and run:
```bash
docker build -t tradingagents .
```

### Test local ollama setup
To test ollama connectivity and local model:
```bash
docker run -it --env-file .env tradingagents python test_ollama_connection.py
```
for picking environment settings from .env file. You can pass values directly using: 
```bash
docker run -it \
  -e LLM_PROVIDER="ollama" \
  -e LLM_BACKEND_URL="http://localhost:11434/v1" \
  -e LLM_DEEP_THINK_MODEL="qwen3:0.6b" \
  -e LLM_EMBEDDING_MODEL="nomic-embed-text"\ 
  tradingagents \
  python test_ollama_connection.py
```
For prevent re-downloading of Ollama models, mount folder from your host and run as
```bash
docker run -it \
  -e LLM_PROVIDER="ollama" \
  -e LLM_BACKEND_URL="http://localhost:11434/v1" \
  -e LLM_DEEP_THINK_MODEL="qwen3:0.6b" \
  -e LLM_EMBEDDING_MODEL="nomic-embed-text"\ 
  -v ./ollama_cache:/app/.ollma \
  tradingagents \
  python test_ollama_connection.py
```

**Notes on Ollama for Local Docker:**
When `LLM_PROVIDER` is set to `ollama` the ollama server is automatically started in the docker conatiner. The `LLM_BACKEND_URL` is set to `http://localhost:11434/v1`. This assumes you have Ollama running on your host machine and accessible at port 11434. '/v1' is added to url at the end for OpenAI api compatibility. 


### Run the Main Application
To run the `main.py` script:
```bash
docker run -it --env-file .env tradingagents python -m main
```
or 
```bash
  -e LLM_PROVIDER="ollama" \
  -e LLM_BACKEND_URL="http://localhost:11434/v1" \
  -e LLM_DEEP_THINK_MODEL="qwen3:0.6b" \
  -e LLM_QUICK_THINK_MODEL="qwen3:0.6b" \
  -e LLM_EMBEDDING_MODEL="nomic-embed-text"\ 
  -e MAX_DEBATE_ROUNDS="1" \
  -e ONLINE_TOOLS="False" \
  -v ./ollama_cache:/app/.ollama \
  tradingagents python -m main
```
Adjust environment variables as needed for your local setup.

### Run the TradingAgents CLI
To run the cli interface (default in the container)
```bash
docker run -it --env-file .env tradingagents 
```
or 
or 
```bash
  -e LLM_PROVIDER="ollama" \
  -e LLM_BACKEND_URL="http://localhost:11434/v1" \
  -v ./ollama_cache:/app/.ollma \
  tradingagents python -m cli.main
```
Adjust environment variables as needed for your local setup.

### Using Docker Compose

For a more streamlined local development experience, it is recommended to use Docker Compose. The `docker-compose.yml` file in the project root is configured to use the existing `Dockerfile`.

**Build and Run Tests:**

The default command in `docker-compose.yml` is set to run the test suite.
```bash
docker-compose up --build
```
This command will build the image (if it's not already built or if changes are detected) and then run the `pytest tests/test_main.py` command. The `--rm` flag is implicitly handled by `up` when the process finishes, or you can run:
```bash
docker-compose run --it app # This will use the default command from docker-compose.yml
```
If you want to explicitly run the tests:
```bash
docker-compose run --rm app python test_ollama_connection.py
```

**Run the Main Application:**

To run the `main.py` script, you can override the default command:
```bash
docker-compose run --rm app python -m main
```
Or, you can modify the `command` in `docker-compose.yml` if you primarily want `docker-compose up` to run the main application.

**Run the TradingAgents CLI Application:**

To run the `cli/main.py` script, you can override the default command:
```bash
docker-compose run --it app python -m cli.main
```

**Environment Variables:**
The necessary environment variables (like `LLM_PROVIDER`, `LLM_BACKEND_URL`, model names, etc.) are configured in the `docker-compose.yml` for the `app` service. Ollama is started by the entrypoint script within the same container when LLM_PROVIDER is set to `ollama`, and `LLM_BACKEND_URL` is set to `http://localhost:11434/v1`.

When using enviroment file for `docker` command, please do not put extra quotes around the values, or any extra comments at the end otherwise docker will not pick the values. 

**Live Code Reloading:**
The current directory is mounted as a volume into the container at `/app`. This means changes you make to your local code will be reflected inside the container, which is useful for development. You might need to rebuild the image with `docker-compose build` or `docker-compose up --build` if you change dependencies in `requirements.txt` or modify the `Dockerfile` itself.

**Ollama Model Caching:**
To prevent re-downloading Ollama models, `docker-compose.yml` now mounts `./.ollama` on your host to `/app/.ollama` in the container. Models pulled by Ollama will be stored in `./.ollama/models` locally and persist across runs. Ensure this directory is in your `.gitignore`. If Docker has permission issues creating this directory, you might need to create it manually (`mkdir .ollama`).


