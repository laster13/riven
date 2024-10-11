from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from subprocess import Popen, PIPE
from fastapi.responses import StreamingResponse
import os
import subprocess
import yaml
import json
from program.json_manager import update_json_files, save_json_to_file, load_json_from_file

USER = os.getenv("USER") or os.getlogin()

SCRIPTS_DIR = f"/home/{USER}/projet-riven/riven-frontend/scripts"
YAML_PATH = f"/home/{USER}/.ansible/inventories/group_vars/all.yml"
VAULT_PASSWORD_FILE = f"/home/{USER}/.vault_pass"
BACKEND_JSON_PATH = f"/home/{USER}/projet-riven/riven/data/settings.json"
FRONTEND_JSON_PATH = f"/home/{USER}/projet-riven/riven-frontend/static/settings.json"


# Création du router pour les scripts et les configurations YAML
router = APIRouter(
    prefix="/scripts",
    tags=["scripts"],
    responses={404: {"description": "Not found"}},
)

class ScriptModel(BaseModel):
    name: str
    params: list[str] = []

# Route pour vérifier l'existence d'un fichier
@router.get("/check-file")
async def check_file():
    file_path = f'/home/{USER}/seedbox-compose/ssddb'
    
    try:
        if os.path.exists(file_path):
            return {"exists": True}
        else:
            return {"exists": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

# Route pour exécuter un script Bash
@router.get("/run/{script_name}")
async def run_script(script_name: str, label: str = Query(None, description="Label du conteneur")):
    if not script_name.isalnum():
        raise HTTPException(status_code=400, detail="Nom de script invalide.")

    script_path = os.path.join(SCRIPTS_DIR, f"{script_name}.sh")
    
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=404, detail=f"Script non trouvé: {script_name}.sh")

    def stream_logs():
        try:
            if label:
                process = Popen(['bash', script_path, label], stdout=PIPE, stderr=PIPE, text=True)
            else:
                process = Popen(['bash', script_path], stdout=PIPE, stderr=PIPE, text=True)

            for line in process.stdout:
                yield f"data: {line}\n\n"
            for err in process.stderr:
                yield f"data: Erreur: {err}\n\n"

            process.wait()
            yield "event: end\ndata: Fin du script\n\n"
        except Exception as e:
            yield f"data: Erreur lors de l'exécution: {str(e)}\n\n"

    return StreamingResponse(stream_logs(), media_type="text/event-stream")

@router.post("/update-config")
async def update_config():
    try:
        # Tenter de déchiffrer le fichier YAML avec Ansible Vault
        command = f"ansible-vault view {YAML_PATH} --vault-password-file {VAULT_PASSWORD_FILE}"
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

        # Log du résultat pour analyse
        print(f"Résultat de la commande ansible-vault: {result.stdout}, Erreurs: {result.stderr}")

        if result.returncode != 0:
            raise Exception(f"Erreur lors du déchiffrement : {result.stderr}")

        decrypted_yaml_content = result.stdout

        # Charger les données YAML dans un dictionnaire
        yaml_data = yaml.safe_load(decrypted_yaml_content)

        # Vérifie si yaml_data est vide ou incorrect
        if not yaml_data:
            raise Exception("Le fichier YAML déchiffré est vide ou mal formaté.")

        # Mettre à jour les fichiers JSON avec les données 'sub' déchiffrées du YAML
        update_json_files(decrypted_yaml_content)

        # Charger les fichiers JSON backend (pour user et cloudflare)
        backend_json_data = load_json_from_file(BACKEND_JSON_PATH)

        # Mise à jour des clés cloudflare et utilisateur uniquement dans le backend
        if 'cloudflare' in yaml_data:
            backend_json_data['cloudflare']['cloudflare_login'] = yaml_data['cloudflare']['login']
            backend_json_data['cloudflare']['cloudflare_api_key'] = yaml_data['cloudflare']['api']

        if 'user' in yaml_data:
            backend_json_data['utilisateur']['username'] = yaml_data['user']['name']
            backend_json_data['utilisateur']['email'] = yaml_data['user']['mail']
            backend_json_data['utilisateur']['domain'] = yaml_data['user']['domain']
            backend_json_data['utilisateur']['password'] = yaml_data['user']['pass']

        # Sauvegarder les fichiers JSON mis à jour
        save_json_to_file(backend_json_data, BACKEND_JSON_PATH)

        return {"message": "Configuration mise à jour avec succès."}

    except Exception as e:
        # Log de l'erreur pour analyse
        print(f"Erreur lors de la mise à jour : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour : {str(e)}")
