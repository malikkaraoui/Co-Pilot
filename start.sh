#!/usr/bin/env bash
# ============================================================
#  Co-Pilot -- Script de lancement complet
#  Usage :  ./start.sh          (lance tout)
#           ./start.sh --seed   (force le re-seed des données)
#           ./start.sh --reset  (supprime la DB et repart à zéro)
# ============================================================
set -e

# -- Couleurs (sobre) ----------------------------------------
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }
step() { echo -e "\n${CYAN}[$1]${NC} $2"; }

cd "$(dirname "$0")"
PORT=5001
VENV=".venv"
DB="data/copilot.db"

# -- Flags ----------------------------------------------------
FORCE_SEED=false
RESET=false
for arg in "$@"; do
  case "$arg" in
    --seed)  FORCE_SEED=true ;;
    --reset) RESET=true ;;
  esac
done

echo -e "${CYAN}╔═══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        Co-Pilot  ·  Démarrage         ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════╝${NC}"

# -- 1. Python ------------------------------------------------
step "1/6" "Vérification de Python"
if command -v python3 &>/dev/null; then
  PY=$(python3 --version 2>&1)
  ok "Python trouvé : $PY"
else
  fail "Python 3 introuvable. Installe-le d'abord."
fi

# -- 2. Venv --------------------------------------------------
step "2/6" "Environnement virtuel"
if [ ! -d "$VENV" ]; then
  warn "Venv absent -- création en cours..."
  python3 -m venv "$VENV"
  ok "Venv créé dans $VENV/"
else
  ok "Venv existant : $VENV/"
fi
source "$VENV/bin/activate"

# -- 3. Dépendances -------------------------------------------
step "3/6" "Dépendances"
# Vérifie si Flask est installé comme proxy pour "tout est installé"
if python -c "import flask" 2>/dev/null; then
  ok "Dépendances déjà installées"
else
  warn "Installation des dépendances..."
  pip install -q -r requirements.txt
  ok "requirements.txt installé"
fi
# Dev dependencies (pytest, ruff) -- optionnel, silencieux
if [ -f requirements-dev.txt ]; then
  if ! python -c "import pytest" 2>/dev/null; then
    pip install -q -r requirements-dev.txt
    ok "requirements-dev.txt installé"
  fi
fi

# -- 4. Reset (si demandé) ------------------------------------
if [ "$RESET" = true ]; then
  step "4/6" "Reset de la base de données"
  if [ -f "$DB" ]; then
    rm "$DB"
    warn "Base supprimée : $DB"
  fi
  FORCE_SEED=true
fi

# -- 5. Base de données + seeds --------------------------------
step "4/6" "Base de données"
mkdir -p data
NEED_SEED=false
if [ ! -f "$DB" ]; then
  warn "Base absente -- initialisation..."
  python scripts/init_db.py
  NEED_SEED=true
  ok "Tables créées"
else
  ok "Base existante : $DB"
  # Synchronise le schéma (ajoute les colonnes manquantes + migration contraintes)
  python -c "
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)

    # Migration market_prices : ancienne contrainte 4 colonnes → 5 colonnes (avec fuel)
    # SQLite ne supporte pas ALTER CONSTRAINT, on doit recréer la table
    if 'market_prices' in inspector.get_table_names():
        uqs = inspector.get_unique_constraints('market_prices')
        old_constraint = any(
            set(u['column_names']) == {'make', 'model', 'year', 'region'}
            for u in uqs
        )
        if old_constraint:
            db.session.execute(text('DROP TABLE market_prices'))
            db.session.commit()
            db.metadata.tables['market_prices'].create(db.engine)
            print('  ↻ market_prices recréée (migration fuel)')

    for table in db.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        existing = {c['name'] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(db.engine.dialect)
                db.session.execute(text(
                    f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'
                ))
                print(f'  + colonne ajoutée: {table.name}.{col.name}')
    db.session.commit()
" 2>/dev/null && ok "Schéma synchronisé" || ok "Schéma OK"
fi

if [ "$NEED_SEED" = true ] || [ "$FORCE_SEED" = true ]; then
  step "5/6" "Chargement des données (seeds)"
  python data/seeds/seed_vehicles.py
  ok "Référentiel véhicules (70 modèles)"
  python data/seeds/seed_argus.py
  ok "Cotations Argus (seeds)"
  # YouTube seeds are long-running (~17 min) -- run manually with:
  #   python data/seeds/seed_youtube.py
else
  step "5/6" "Seeds"
  ok "Données déjà en base (utilise --seed pour forcer)"
fi

# -- 6. Vérification port libre --------------------------------
step "6/6" "Lancement du serveur"
if lsof -i :$PORT -sTCP:LISTEN &>/dev/null; then
  PID=$(lsof -ti :$PORT -sTCP:LISTEN)
  warn "Port $PORT déjà utilisé (PID $PID)"
  echo -e "     Arrêter avec : ${YELLOW}kill $PID${NC}"
  echo -e "     Ou relancer  : ${YELLOW}./start.sh${NC}"
  fail "Port $PORT occupé -- arrête le processus existant d'abord."
fi

ok "Serveur Flask sur http://localhost:$PORT"
echo ""
echo -e "  ${GREEN}Dashboard admin${NC}  →  http://localhost:$PORT/admin/"
echo -e "  ${GREEN}API Health${NC}       →  http://localhost:$PORT/api/health"
echo -e "  ${GREEN}Extension Chrome${NC} →  chrome://extensions (charger extension/)"
echo ""
echo -e "  ${YELLOW}Ctrl+C${NC} pour arrêter le serveur"
echo ""

# Lance Flask (bloquant)
flask run --port $PORT
