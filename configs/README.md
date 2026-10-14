# Configurations

Une paire de fichiers par client : sans clé (l'agent ne voit que `sign_up` et s'inscrit), puis avec la clé. Copiez le contenu à la destination indiquée.

| Client | Destination | Sans clé | Avec la clé |
| --- | --- | --- | --- |
| Claude Code | `.mcp.json`, à la racine du projet | [`claude-code.sans-cle.json`](claude-code.sans-cle.json) | [`claude-code.avec-cle.json`](claude-code.avec-cle.json) |
| Cursor | `.cursor/mcp.json` (projet) ou `~/.cursor/mcp.json` (tous les projets) | [`cursor.sans-cle.json`](cursor.sans-cle.json) | [`cursor.avec-cle.json`](cursor.avec-cle.json) |
| VS Code (GitHub Copilot) | `.vscode/mcp.json` | [`vscode.sans-cle.json`](vscode.sans-cle.json) | [`vscode.avec-cle.json`](vscode.avec-cle.json) |
| Codex | `~/.codex/config.toml` | [`codex.sans-cle.toml`](codex.sans-cle.toml) | [`codex.avec-cle.toml`](codex.avec-cle.toml) |
| Gemini CLI | `.gemini/settings.json` (projet) ou `~/.gemini/settings.json` | [`gemini-cli.sans-cle.json`](gemini-cli.sans-cle.json) | [`gemini-cli.avec-cle.json`](gemini-cli.avec-cle.json) |
| Devin Desktop (anciennement Windsurf) | `~/.config/devin/mcp_config.json` (sous Windows : `%APPDATA%\devin\mcp_config.json`) | [`devin-desktop.sans-cle.json`](devin-desktop.sans-cle.json) | [`devin-desktop.avec-cle.json`](devin-desktop.avec-cle.json) |

Aucun fichier ne contient de clé : chacun lit la variable d'environnement `SUBAGENT_KEY`, ou la demande à la première connexion.

[`index.json`](index.json) décrit ces fichiers pour une machine : client, destination, format, et la page de documentation d'où vient le format.
