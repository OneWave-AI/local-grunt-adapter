"""Register the adapter with installed local MCP clients; preserve existing config."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--roots", default=str(Path.home() / "Documents" / "Codex"), help="Allowed text-file roots, separated by colons")
    p.add_argument("--fast", default="granite4.2:3b")
    p.add_argument("--quality", default="qwen3.5:9b")
    p.add_argument("--desktop", action="store_true", help="Also register with Claude Desktop")
    args = p.parse_args()
    env = {"LOCAL_GRUNT_ROOTS": args.roots, "LOCAL_GRUNT_FAST": args.fast, "LOCAL_GRUNT_QUALITY": args.quality,
           "LOCAL_GRUNT_STATE": str(HERE / ".state")}
    python = str(Path(sys.executable).absolute())
    command = [python, str(HERE / "adapter.py")]
    state = HERE / ".state"
    state.mkdir(mode=0o700, exist_ok=True)
    backups = state / "backups"
    backups.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    def backup(path):
        if path.exists():
            dest = backups / (path.name + "." + stamp)
            shutil.copy2(path, dest)
            dest.chmod(0o600)

    # Append only our own TOML table. Do not reserialize unrelated config.
    codex_dir = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    codex_config = codex_dir / "config.toml"
    if codex_dir.exists() or shutil.which("codex"):
        contents = codex_config.read_text() if codex_config.exists() else ""
        config = tomllib.loads(contents)
        entry = {"command": command[0], "args": command[1:], "env": env, "tool_timeout_sec": 240}
        existing = config.get("mcp_servers", {}).get("local-grunt")
        if existing is not None and existing != entry:
            raise RuntimeError("Codex already has a different local-grunt entry; refusing to overwrite it")
        if existing is None:
            backup(codex_config)
            codex_dir.mkdir(parents=True, exist_ok=True)
            block = '\n[mcp_servers.local-grunt]\ncommand = ' + json.dumps(command[0]) + '\nargs = ' + json.dumps(command[1:]) + '\ntool_timeout_sec = 240\n'
            block += '[mcp_servers.local-grunt.env]\n' + ''.join(k + ' = ' + json.dumps(v) + '\n' for k, v in env.items())
            tomllib.loads(contents + "\n" + block)
            codex_config.write_text(contents + "\n" + block)
            codex_config.chmod(0o600)
        print("Codex: registered local-grunt")

    claude_config = Path.home() / ".claude.json"
    if shutil.which("claude"):
        data = json.loads(claude_config.read_text()) if claude_config.exists() else {}
        existing = data.get("mcpServers", {}).get("local-grunt")
        if existing is None:
            backup(claude_config)
            cmd = ["claude", "mcp", "add", "local-grunt", "--scope", "user", "--transport", "stdio"]
            for key, value in env.items(): cmd.extend(["--env", key + "=" + value])
            cmd.extend(["--", *command])
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError("Claude MCP registration failed: " + result.stderr[:2000])
        elif existing != {"type": "stdio", "command": command[0], "args": command[1:], "env": env}:
            raise RuntimeError("Claude Code already has a different local-grunt entry; refusing to overwrite it")
        print("Claude Code: registered local-grunt")

    if args.desktop:
        path = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
        if path.parent.exists():
            data = json.loads(path.read_text()) if path.exists() else {}
            entry = {"command": command[0], "args": command[1:], "env": env}
            servers = data.setdefault("mcpServers", {})
            if "local-grunt" in servers and servers["local-grunt"] != entry:
                raise RuntimeError("Claude Desktop already has a different local-grunt entry")
            backup(path)
            servers["local-grunt"] = entry
            path.write_text(json.dumps(data, indent=2) + "\n")
            path.chmod(0o600)
            print("Claude Desktop: registered local-grunt")
    (HERE / "client-config.example.json").write_text(json.dumps({"mcpServers": {"local-grunt": {"command": command[0], "args": command[1:], "env": env}}}, indent=2) + "\n")
    print("Restart your clients to load the new tools. Existing Crest entries were preserved.")


if __name__ == "__main__": main()
