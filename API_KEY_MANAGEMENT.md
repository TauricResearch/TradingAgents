# API Key Management

This document provides instructions for managing the API keys required to run the TradingAgents framework.

## Google API Key

The TradingAgents framework uses Google's Generative AI models. You will need a Google API key to use the service.

### Obtaining a Google API Key

1.  Go to the [Google AI Studio](https://aistudio.google.com/).
2.  Log in with your Google account.
3.  Click on "Get API key" to create a new API key.

### Setting the Google API Key

To use the Google API key, you need to set it as an environment variable named `GOOGLE_API_KEY`.

#### For Linux and macOS:

You can set the environment variable in your shell's configuration file (e.g., `.bashrc`, `.zshrc`).

```bash
export GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
```

Replace `"YOUR_GOOGLE_API_KEY"` with the API key you obtained from the Google AI Studio.

After adding the line to your configuration file, restart your shell or run the following command to apply the changes:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

#### For Windows:

You can set the environment variable through the system settings.

1.  Search for "Environment Variables" in the Start menu and select "Edit the system environment variables".
2.  In the System Properties window, click on the "Environment Variables..." button.
3.  In the Environment Variables window, click on "New..." under the "System variables" section.
4.  Set the "Variable name" to `GOOGLE_API_KEY` and the "Variable value" to your Google API key.
5.  Click "OK" to close all windows.

You may need to restart your command prompt or IDE for the changes to take effect.
