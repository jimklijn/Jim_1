#!/bin/bash
# Start regie.py. De eerste keer installeert dit zelf wat er nodig is.
cd "$(dirname "$0")/.." || exit 1

wacht() { echo; read -n 1 -s -r -p "Druk op een toets om dit venster te sluiten."; echo; }

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
  echo "Python 3.9 of nieuwer is nodig, en dat staat nog niet op deze Mac."
  echo "Er verschijnt zo een venster om de 'Command Line Tools' van Apple te installeren."
  echo "Kies 'Installeer', wacht tot het klaar is en dubbelklik daarna opnieuw op dit bestand."
  xcode-select --install 2>/dev/null
  wacht
  exit 1
fi

if [ ! -x .venv/bin/python ] || [ requirements.txt -nt .venv/klaar ]; then
  echo "Eerste keer: onderdelen installeren (duurt een minuutje)..."
  if python3 -m venv .venv \
    && .venv/bin/python -m pip install --quiet --upgrade pip \
    && .venv/bin/python -m pip install --quiet -r requirements.txt; then
    touch .venv/klaar
    echo "Klaar."
    echo
  else
    echo
    echo "Installeren is mislukt. Staat de internetverbinding aan? Probeer het nog een keer."
    wacht
    exit 1
  fi
fi

.venv/bin/python regie.py "$@"
wacht
