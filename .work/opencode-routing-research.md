# OpenCode provider routing notes

- Official OpenCode provider docs: https://opencode.ai/docs/providers/
  - OpenCode supports 75+ LLM providers; provider API credentials are added with `/connect` and stored locally in `~/.local/share/opencode/auth.json`.
  - NVIDIA is a documented provider; the page says NVIDIA offers access to Nemotron and other open models through build.nvidia.com and documents custom NIM endpoints.
  - OpenCode also supports custom OpenAI-compatible providers via `baseURL`.
- Official OpenCode CLI docs: https://opencode.ai/docs/cli/
  - `opencode run` supports a non-interactive prompt and `--model provider/model`.
- OpenRouter's official OpenCode integration: https://openrouter.ai/docs/cookbook/coding-agents/opencode-integration
  - OpenRouter is an OpenCode built-in provider. Its key and model are configured in OpenCode; `openrouter/<model-slug>` is the model ID form.
  - OpenCode is a client, not a quota bypass; requests still depend on the configured provider credential and its limits.
- Local check at 2026-10-21: OpenCode CLI v1.19.3; auth list showed NVIDIA and Google credentials, no OpenRouter credential; catalog listed `openrouter/minimax/minimax-m3.1-flash:free` and NVIDIA Step 5 Preview, Muse Glimmer 30B, and Nemotron 3.5 Super VL.
