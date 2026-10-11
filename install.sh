#!/bin/sh
# One-time install on macOS/Linux:  sh ~/.skills-bank/install.sh
set -e
BANK="${SKILLS_BANK_HOME:-$HOME/.skills-bank}"
python3 -m pip install -q --user -e "$BANK" 2>/dev/null || python3 -m pip install -q --break-system-packages -e "$BANK"
RC="$HOME/.zshrc"; [ -n "$BASH_VERSION" ] && RC="$HOME/.bashrc"
grep -q SKILLS_BANK_HOME "$RC" 2>/dev/null || printf '\nexport SKILLS_BANK_HOME="%s"\nexport PATH="$HOME/.local/bin:$PATH"\n' "$BANK" >> "$RC"
if [ "$(uname)" = Darwin ]; then
  launchctl unload "$HOME/Library/LaunchAgents/com.skillsbank.ingest.plist" 2>/dev/null || true   # retire old job name
  rm -f "$HOME/Library/LaunchAgents/com.skillsbank.ingest.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cp "$BANK/scripts/com.skillsbank.ingest.plist" "$HOME/Library/LaunchAgents/"
  launchctl unload "$HOME/Library/LaunchAgents/com.skillsbank.ingest.plist" 2>/dev/null || true
  launchctl load "$HOME/Library/LaunchAgents/com.skillsbank.ingest.plist"
  echo "launchd agent loaded: ingests every 10 min"
fi
echo "done — open a new terminal and run: bank stats"
