#!/bin/sh
# One-time install on macOS/Linux:  sh ~/.skills-bank/install.sh
set -e
BANK="${SKILLS_BANK_HOME:-$HOME/.skills-bank}"
python3 -m pip install -q --user -e "$BANK" 2>/dev/null || python3 -m pip install -q --break-system-packages -e "$BANK"
for RC in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile"; do
  [ -f "$RC" ] || continue
  sed -i.bak '/AI_BANK_HOME/d; /SKILLS_BANK_HOME/d' "$RC" && rm -f "$RC.bak"
  printf '\nexport SKILLS_BANK_HOME="%s"\nexport PATH="$HOME/.local/bin:$PATH"\n' "$BANK" >> "$RC"
done
if [ "$(uname)" = Darwin ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  launchctl unload "$HOME/Library/LaunchAgents/com.aibank.ingest.plist" 2>/dev/null || true; rm -f "$HOME/Library/LaunchAgents/com.aibank.ingest.plist"
  cp "$BANK/scripts/com.skillsbank.ingest.plist" "$HOME/Library/LaunchAgents/"
  launchctl unload "$HOME/Library/LaunchAgents/com.skillsbank.ingest.plist" 2>/dev/null || true
  launchctl load "$HOME/Library/LaunchAgents/com.skillsbank.ingest.plist"
  echo "launchd agent loaded: ingests every 10 min"
fi
echo "done — open a new terminal and run: bank stats"
