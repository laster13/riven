import contextlib
import signal
import sys
import threading
import time
import traceback

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from program.tasks import start_background_tasks
from controllers.script_router import router as scripts_router
from controllers.default import router as default_router
from controllers.items import router as items_router
from controllers.scrape import router as scrape_router
from controllers.settings import router as settings_router
from controllers.tmdb import router as tmdb_router
from controllers.webhooks import router as webhooks_router
from controllers.ws import router as ws_router
from scalar_fastapi import get_scalar_api_reference
from program import Program
from program.settings.models import get_version
from utils.cli import handle_args
from utils.logger import logger
from contextlib import asynccontextmanager
import subprocess
import os
import fcntl

USER = os.getenv("USER") or os.getlogin()

def decrypt_vault_file(vault_file_path, vault_password_file):
    try:
        print(f"Déchiffrement du fichier {vault_file_path} en cours...")

        command = f"ansible-vault view {vault_file_path} --vault-password-file {vault_password_file}"
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

        # Ignorer complètement l'erreur "input is not vault encrypted data"
        if result.returncode != 0:
            if "input is not vault encrypted data" in result.stderr:
                return None
            else:
                return None

        decrypted_content = result.stdout
        return decrypted_content

    except Exception as e:
        return None


class LoguruMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            logger.exception(f"Exception during request processing: {e}")
            raise
        finally:
            process_time = time.time() - start_time
            logger.log(
                "API",
                f"{request.method} {request.url.path} - {response.status_code if 'response' in locals() else '500'} - {process_time:.2f}s",
            )
        return response

args = handle_args()

app = FastAPI(
    title="Riven",
    summary="A media management system.",
    version=get_version(),
    redoc_url=None,
    license_info={
        "name": "GPL-3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
    },
)

# Lancer les tâches en arrière-plan au démarrage de l'application
@asynccontextmanager
async def lifespan(app: FastAPI):    
    # Ajout de la partie déchiffrement
    try:
        decrypted_content = decrypt_vault_file(f'/home/{USER}/.ansible/inventories/group_vars/all.yml', 'f/home/{USER}/.vault_pass')
    except Exception as e:
        sys.exit(1)  # Arrête l'application si le déchiffrement échoue

    start_background_tasks()
    yield
    # Ce qui remplace @app.on_event("shutdown")

app = FastAPI(lifespan=lifespan)

@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )

app.program = Program()

app.add_middleware(LoguruMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(default_router)
app.include_router(settings_router)
app.include_router(items_router)
app.include_router(scrape_router)
app.include_router(webhooks_router)
app.include_router(tmdb_router)
app.include_router(ws_router)
app.include_router(scripts_router)



class Server(uvicorn.Server):
    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        thread = threading.Thread(target=self.run, name="Riven")
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        except Exception as e:
            logger.error(f"Error in server thread: {e}")
            logger.exception(traceback.format_exc())
            raise e
        finally:
            self.should_exit = True
            sys.exit(0)

def signal_handler(signum, frame):
    logger.log("PROGRAM","Exiting Gracefully.")
    app.program.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_config=None)
server = Server(config=config)

with server.run_in_thread():
    try:
        app.program.start()
        app.program.run()
    except Exception as e:
        logger.error(f"Error in main thread: {e}")
        logger.exception(traceback.format_exc())
    finally:
        logger.critical("Server has been stopped")
        sys.exit(0)