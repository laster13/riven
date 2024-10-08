from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from subprocess import Popen, PIPE
from fastapi.responses import StreamingResponse
import os
from typing import List

USER = os.getenv("USER") or os.getlogin()
SCRIPTS_DIR = f"/home/{USER}/projet-riven/riven-frontend/scripts"

# Création du router pour les scripts Bash avec le préfixe `/scripts`
router = APIRouter(
    prefix="/scripts",  # Toutes les routes seront préfixées par `/scripts`
    tags=["scripts"],
    responses={404: {"description": "Not found"}},
)

class ScriptModel(BaseModel):
    name: str
    params: List[str] = []


@router.get("/check-file")
async def check_file():
    file_path = '/home/laster13/seedbox-compose/ssddb'  # Chemin du fichier à vérifier
    
    try:
        # Vérification de l'existence du fichier
        if os.path.exists(file_path):
            return {"exists": True}  # Le fichier existe
        else:
            return {"exists": False}  # Le fichier n'existe pas
    except Exception as e:
        # Gestion des erreurs (par exemple, problème de permissions)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@router.get("/run/{script_name}")
async def run_script(script_name: str, label: str = Query(None, description="Label du conteneur")):
    # Validation du nom du script
    if not script_name.isalnum():
        raise HTTPException(status_code=400, detail="Nom de script invalide.")

    # Chemin vers le script bash
    script_path = os.path.join(SCRIPTS_DIR, f"{script_name}.sh")
    
    # Vérification de l'existence du script
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=404, detail=f"Script non trouvé: {script_name}.sh")

    # Fonction pour streamer les logs
    def stream_logs():
        try:
            # Si un label est fourni, on l'utilise comme argument du script
            if label:
                process = Popen(['bash', script_path, label], stdout=PIPE, stderr=PIPE, text=True)
            else:
                # Si pas de label, on exécute le script sans paramètres
                process = Popen(['bash', script_path], stdout=PIPE, stderr=PIPE, text=True)

            # Stream des logs du script
            for line in process.stdout:
                yield f"data: {line}\n\n"
            for err in process.stderr:
                yield f"data: Erreur: {err}\n\n"

            process.wait()
            yield "event: end\ndata: Fin du script\n\n"
        except Exception as e:
            yield f"data: Erreur lors de l'exécution: {str(e)}\n\n"

    # Retourne les logs en streaming
    return StreamingResponse(stream_logs(), media_type="text/event-stream")


@router.post("/run")
async def run_script_with_params(script: ScriptModel):
    if not script.name.isalnum():
        raise HTTPException(status_code=400, detail="Nom de script invalide.")
    script_path = os.path.join(SCRIPTS_DIR, f"{script.name}.sh")
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=404, detail="Script non trouvé.")

    def stream_logs():
        process = Popen(['bash', script_path] + script.params, stdout=PIPE, stderr=PIPE, text=True)
        for line in process.stdout:
            yield f"data: {line}\n\n"
        for err in process.stderr:
            yield f"data: Erreur: {err}\n\n"
        process.wait()
        print("Script terminé, envoi de l'événement 'end'")
        yield "event: end\ndata: Fin du script\n\n"

    return StreamingResponse(stream_logs(), media_type="text/event-stream")
